#!/usr/bin/env python3
"""Full underwater pass: analytic colored scattering, source/view extinction and actual wet intervals."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest
from test_water_volume import WAVES, VOLUME, cells, WATER, AIR, SOLID, close
from test_dynamic_lighting import atlas, cell, sources, N

ROOT=Path(__file__).resolve().parents[1]/'client/shaders'
VOXEL=(ROOT/'common/voxel_lighting.glsl').read_text()
LIGHT=(ROOT/'common/water_lighting.glsl').read_text()
BODY=(ROOT/'water_volume/opengl_fragment.glsl').read_text().replace(
    'CENTROID_ VARYING_ mediump vec2 varTexCoord;','#define varTexCoord (gl_FragCoord.xy/64.0)')
SIGMA=(0.32,0.085,0.035)
ALBEDO=tuple(0.035/s for s in SIGMA)
BASE=(0.8,0.5,0.2)
FOG=(0.1,0.3,0.5)


def source(dynamic):
    flags='#define ENABLE_WATER_VOLUME\n#define ENABLE_VOXEL_LIGHTING\n#define ENABLE_VOXEL_WATER_LIGHTING\n'
    if dynamic: flags+='#define ENABLE_VOXEL_DYNAMIC_DIRECT\n#define MAX_VOXEL_DYNAMIC_LIGHTS 8\n'
    return flags+WAVES+VOLUME+VOXEL+LIGHT+BODY


def probes(columns,direct=(0,0,0),bounce=(0,0,0)):
    data=atlas(columns)
    for z in range(N):
        for y in range(N):
            for x in range(N):
                for group in range(12):cell(data,columns,group,x,y,z,(direct if group<6 else bounce)+(1,))
    return data


def optics(gpu,data,columns):
    gpu.texture(4,data,linear=True,width=N*columns,height=N*N)


def geometry(gpu,function=lambda x,y,z:WATER):
    gpu.texture(6,cells(N,function),width=2*N,height=N*N)


def camera(gpu,x=80,y=40,z=40):
    identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
    view=identity[:];view[12:15]=[x,y,z]
    projection=identity[:];projection[0]=projection[5]=0;projection[10]=40
    gpu.matrix('inverseView',view);gpu.matrix('inverseProjection',projection)


def setup(gpu,dynamic):
    for name,slot in (('texture0',0),('texture1',1),('texture4',4),('texture6',6)):gpu.sampler(name,slot)
    gpu.texture(0,BASE+(0.37,));gpu.texture(1,(0.75,0,0,1))
    gpu.uniform('waterVolumeOrigin',0,0,0);gpu.uniform('waterAbsoluteOrigin',0,0,0)
    gpu.uniform('waterVolumeParams',1,N,200,0.7);gpu.uniform('waterWaves',0,20,0)
    gpu.uniform('waterMediumParams',1,1,0,0);gpu.uniform('waterScatterColor',*FOG)
    gpu.uniform('voxelOrigin',0,0,0);gpu.uniform('voxelParams',1,0.5,0.25,N)
    gpu.uniform('voxelWaterParams',0.8,0,8)
    camera(gpu);geometry(gpu)
    if dynamic:sources(gpu,[])


def uniform_color(length,incident):
    trans=tuple(math.exp(-s*length*0.98/10) for s in SIGMA)
    return tuple((b**2.2*t+f**2.2*(1-t)+a*j*(1-t))**(1/2.2)
                 for b,f,t,a,j in zip(BASE,FOG,trans,ALBEDO,incident))+(0.37,)


def field_transport(dynamic):
    columns=14 if dynamic else 13
    with ShaderTest(source(dynamic)) as gpu:
        setup(gpu,dynamic)
        direct,bounce=(2,0.3,0.1),(0,0.2,0.4)
        incident=tuple(0.8*(0.5*d+0.25*b) for d,b in zip(direct,bounce))
        optics(gpu,probes(columns,direct,bounce),columns)
        for steps in (4,8,16,32):
            gpu.uniform('voxelWaterParams',0.8,0,steps)
            close(gpu.draw(),uniform_color(20,incident),'homogeneous Beer-Lambert scattering independent of quadrature count')
        gpu.uniform('voxelWaterParams',0.8,0.5,8)
        close(gpu.draw(),uniform_color(20,incident),'normalized baked phase preserves isotropic field')
        geometry(gpu,lambda x,y,z:WATER if z in (4,6) else AIR)
        close(gpu.draw(),uniform_color(10,incident),'air gap has no water scattering or extinction')
        flow=(224/255,0.5,0,0.4,0.8,0.8,0.2,0.2)
        geometry(gpu,lambda x,y,z:flow if (x,y,z)==(8,4,4) else AIR)
        camera(gpu,y=39.8)
        close(gpu.draw(),uniform_color(1/3,incident),'thin sloped interval samples real water when the stratum midpoint is dry')
        camera(gpu);geometry(gpu)
        # A long stratum can end in another pool beyond a wall. Its lighting
        # sample must stay in the traversed interval in front of that wall.
        separated=probes(columns)
        for z in range(N):
            for y in range(N):
                for x in range(N):
                    for group in range(6):
                        cell(separated,columns,group,x,y,z,((2,0,0) if z<=5 else (0,0,2))+(1,))
        optics(gpu,separated,columns)
        projection=[0,0,0,0,0,0,0,0,0,0,320,0,0,0,0,1]
        gpu.matrix('inverseProjection',projection)
        gpu.uniform('voxelWaterParams',0.8,0,4)
        for wall in (SOLID,(0,0,0,0)):
            geometry(gpu,lambda x,y,z:wall if z==5 else WATER)
            close(gpu.draw(),uniform_color(5,(0.8,0,0)),'truncated view samples the front pool rather than water behind solid/unknown geometry')
        camera(gpu);geometry(gpu);optics(gpu,probes(columns,direct,bounce),columns)
        gpu.uniform('voxelWaterParams',0,0,8);gpu.texture(4,(float('nan'),)*4)
        close(gpu.draw(),uniform_color(20,(0,0,0)),'zero local strength restores native medium without atlas reads')
        gpu.uniform('voxelWaterParams',0.8,0,8);gpu.uniform('voxelParams',0,1,1,N)
        close(gpu.draw(),uniform_color(20,(0,0,0)),'unbound voxel atlas retains native water transport')
        gpu.uniform('voxelParams',1,0,0,N)
        close(gpu.draw(),uniform_color(20,(0,0,0)),'zero direct/bounce gains bypass local atlas reads')
        for inside,absorption,ready in ((0,1,1),(1,0,1),(1,1,0)):
            gpu.uniform('waterMediumParams',inside,absorption,0,0);gpu.uniform('waterVolumeParams',ready,N,200,0.7)
            gpu.texture(6,(float('nan'),)*4)
            close(gpu.draw(),BASE+(0.37,),'dry, absent water and zero-absorption bypass precede volume reads')
        print(f'PASS: actual underwater RGB direct/bounce, phase, quadrature, gaps, thin flow, alpha and fallbacks; columns={columns};',gpu.renderer)


def moving_lights():
    with ShaderTest(source(True)) as gpu:
        setup(gpu,True);optics(gpu,probes(14),14)
        gpu.texture(0,(0,0,0,0.37));gpu.uniform('waterScatterColor',0,0,0)
        gpu.uniform('voxelParams',1,1,0,N)
        def expected(source_z,emission,g,water_end=None):
            result=[0,0,0]
            for step in range(8):
                midpoint=(step+0.5)*2.5
                length=abs(source_z-40-midpoint)
                distance=length/10
                cosine=1 if source_z>40+midpoint else -1
                phase=(1-g*g)/(1+g*g-2*g*cosine)**1.5
                weight=phase*(1-distance/16)**2/(6*max(distance*distance,1))
                for c,sigma in enumerate(SIGMA):
                    wet_length=length if water_end is None else min(length,water_end-40-midpoint)
                    incoming=math.exp(-sigma*wet_length*0.98/10)
                    prefix=math.exp(-sigma*step*2.5*0.98/10)
                    interval=1-math.exp(-sigma*2.5*0.98/10)
                    result[c]+=prefix*interval*ALBEDO[c]*0.8*emission[c]*weight*incoming
            return tuple(x**(1/2.2) for x in result)+(0.37,)
        for source_z in (80,0):
            sources(gpu,[((8,4,source_z/10),(2,1,0.5))])
            for g in (-0.5,0,0.5):
                gpu.uniform('voxelWaterParams',0.8,g,8)
                close(gpu.draw(),expected(source_z,(2,1,0.5),g),'source-specific phase and incoming/outgoing RGB water extinction',0.00003)
        sources(gpu,[((8,4,8),(0,0,2))]);gpu.uniform('voxelWaterParams',0.8,0,8)
        close(gpu.draw(),expected(80,(0,0,2),0),'current source recolor without atlas upload')
        geometry(gpu,lambda x,y,z:WATER if z<=6 else AIR)
        close(gpu.draw(),expected(80,(0,0,2),0,water_end=65),'lamp in air attenuates only the wet portion of its incoming ray')
        geometry(gpu)
        blocked=probes(14)
        for x in range(N):
            for y in range(N):cell(blocked,14,13,x,y,6,(1,1,1,0))
        optics(gpu,blocked,14)
        close(gpu.draw(),(0,0,0,0.37),'current voxel wall blocks a moving underwater lamp')
        optics(gpu,probes(14),14)
        for material in (SOLID,(0,0,0,0)):
            geometry(gpu,lambda x,y,z:material if z==6 else WATER)
            close(gpu.draw(),(0,0,0,0.37),'solid/unknown water geometry rejects an otherwise open voxel ray')
        geometry(gpu);sources(gpu,[])
        close(gpu.draw(),(0,0,0,0.37),'removing moving source clears water illumination immediately')
        print('PASS: moving lamps, HG phase, both path extinctions, current recolor/removal and two visibility grids;',gpu.renderer)


if __name__=='__main__':
    field_transport(False);field_transport(True);moving_lights()
