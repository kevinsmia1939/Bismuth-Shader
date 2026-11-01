#!/usr/bin/env python3
"""Actual voxel/fog GLSL: colored emission/bounce, moving lamps and transport; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest
from test_dynamic_lighting import atlas, cell, sources, falloff, N
from test_fog_denoise import source, mrt, attach_second, pair, INVERSE, IDENTITY, A, B
from test_water_volume import close

VOXEL = (Path(__file__).resolve().parents[1]/'client/shaders/common/voxel_lighting.glsl').read_text()
FLAGS = '#define ENABLE_VOXEL_LIGHTING\n#define ENABLE_VOXEL_FOG_LIGHTING\n'
DYNAMIC = '#define ENABLE_VOXEL_DYNAMIC_DIRECT\n#define MAX_VOXEL_DYNAMIC_LIGHTS 8\n'
HELPER_MAIN = '''
uniform vec3 testPosition, testView;
void main() {
 vec3 viewRay=normalize(testView),positive,negative;
 voxelFogPhaseWeights(viewRay,positive,negative);
 gl_FragColor=vec4(voxelFogRadiance(testPosition,viewRay,positive,negative),1);
}
'''


def probes(direct=(0,0,0), bounce=(0,0,0), columns=14):
    data = atlas(columns)
    for z in range(N):
        for y in range(N):
            for x in range(N):
                for group in range(12):
                    cell(data,columns,group,x,y,z,(direct if group<6 else bounce)+(1,))
    return data


def upload(gpu, data, columns=14):
    gpu.texture(4,data,width=columns*N,height=N*N,linear=True)


def helper():
    fragment = FLAGS+DYNAMIC+VOXEL+HELPER_MAIN
    with ShaderTest(fragment) as gpu:
        gpu.sampler('texture4',4)
        gpu.uniform('voxelOrigin',0,0,0)
        gpu.uniform('voxelParams',1,0.5,0.25,N)
        gpu.uniform('voxelFogStrength',0.8)
        gpu.uniform('voxelFogAnisotropy',0)
        gpu.uniform('testView',0,0,-1)
        gpu.uniform('testPosition',40,40,80)
        sources(gpu,[])
        direct,bounce=(2,0.3,0.1),(0,0.2,0.4)
        upload(gpu,probes(direct,bounce))
        expected=tuple(0.8*(0.5*d+0.25*b) for d,b in zip(direct,bounce))+(1,)
        close(gpu.draw(),expected,'colored map emission and indirect irradiance in fog')
        gpu.uniform('voxelOrigin',-2000,0,3000)
        gpu.uniform('testPosition',-1960,40,3080)
        close(gpu.draw(),expected,'fog light follows camera-relative atlas origin')
        gpu.uniform('voxelOrigin',0,0,0)
        gpu.uniform('testPosition',10,40,80)
        close(gpu.draw(),tuple(v*0.5 for v in expected[:3])+(1,),'local fog coverage fades at grid edge')
        gpu.uniform('testPosition',-10,40,80)
        close(gpu.draw(),(0,0,0,1),'out-of-grid fog does not clamp light into uncovered space')
        gpu.uniform('testPosition',40,40,80)
        invalid=probes(direct,bounce)
        cell(invalid,14,0,4,4,8,(float('nan'),)*3+(1,))
        cell(invalid,14,13,4,4,8,(1,1,1,0))
        upload(gpu,invalid)
        close(gpu.draw(),(0,0,0,1),'solid/unknown fog sample rejects interpolated radiance')
        gpu.texture(4,(float('nan'),)*4)
        gpu.uniform('voxelParams',0,1,1,N)
        close(gpu.draw(),(0,0,0,1),'absent atlas guard before sampler access')
        gpu.uniform('voxelParams',1,1,1,N)
        gpu.uniform('voxelFogStrength',0)
        close(gpu.draw(),(0,0,0,1),'zero local fog strength avoids invalid sampling')
        gpu.uniform('voxelFogStrength',1)
        gpu.uniform('voxelParams',1,1,0,N)
        upload(gpu,probes())
        sources(gpu,[((4,4,2),(2,1,0.5))])
        expected=tuple(v*falloff(6)/6 for v in (2,1,0.5))+(1,)
        close(gpu.draw(),expected,'current moving lamp contributes isotropic incident light')
        filtered=probes()
        for x in range(N):
            for y in range(N):
                cell(filtered,14,13,x,y,5,(0.8,0.5,0.25,1))
        upload(gpu,filtered)
        close(gpu.draw(),tuple(v*t for v,t in zip(expected[:3],(0.8,0.5,0.25)))+(1,),
              'moving fog light follows RGB path transmission')
        for x in range(N):
            for y in range(N):
                cell(filtered,14,13,x,y,5,(1,1,1,0))
        upload(gpu,filtered)
        close(gpu.draw(),(0,0,0,1),'wall blocks a moving fog light')
        upload(gpu,probes())
        sources(gpu,[((4,4,3),(0,2,0))])
        close(gpu.draw(),(0,2*falloff(5)/6,0,1),'moving lamp updates position and color without a field upload')
        sources(gpu,[])
        close(gpu.draw(),(0,0,0,1),'removed moving light leaves no fog illumination')
        print('PASS: map emission/bounce, coverage, occupancy, missing-data guards, moving lights and RGB visibility;',gpu.renderer)


def transport(filtered=False,dynamic=True):
    columns=14 if dynamic else 13
    flags=FLAGS+(DYNAMIC if dynamic else '')+'#define ENABLE_ATMOSPHERE\n#define ENABLE_VOLUMETRIC_FOG\n'
    if filtered: flags+='#define ENABLE_FOG_DENOISING\n#define FOG_TRANSPORT_PASS\n'
    fragment=flags+VOXEL+source('scene_lighting')
    with ShaderTest(mrt(fragment) if filtered else fragment) as gpu:
        if filtered: attach_second(gpu)
        gpu.sampler('texture1',1)
        gpu.texture(1,((A+B/100)*0.5+0.5,0,0,1))
        if not filtered:
            gpu.sampler('texture0',0)
            gpu.texture(0,(0.4,0.5,0.6,0.7))
        gpu.sampler('texture4',4)
        direct,bounce=(0.8,0.2,0.1),(0.1,0.3,0.5)
        upload(gpu,probes(direct,bounce,columns),columns)
        gpu.uniform('voxelOrigin',0,0,0)
        gpu.uniform('voxelParams',1,0.7,0.2,N)
        gpu.uniform('voxelFogStrength',0.5)
        gpu.uniform('voxelFogAnisotropy',0)
        if dynamic: sources(gpu,[])
        inverse=IDENTITY.copy();inverse[12:15]=[40,40,20]
        gpu.matrix('inverseView',inverse)
        gpu.matrix('inverseProjection',INVERSE)
        gpu.uniform('cameraPosition',40,40,20)
        gpu.uniform('cameraOffset',0,0,0)
        gpu.uniform('sceneParams',0.02,0,0,0)
        gpu.uniform('volumeParams',60,1e30,0,24)
        gpu.uniform('volumeLightDirection',0,1,0)
        gpu.uniform('volumeLightColor',0,0,0)
        gpu.uniform('fogColor',0,0,0,1)
        gpu.uniform('atmosphereEnabled',1)
        if filtered: gpu.uniform('animationTimer',0)
        transmission=tuple(math.exp(-0.02*60*v) for v in (0.65,0.9,1.25))
        incident=tuple(0.5*(0.7*d+0.2*b) for d,b in zip(direct,bounce))
        scatter=tuple((1-t)*light for t,light in zip(transmission,incident))
        expected=tuple((base**2.2*t+s)**(1/2.2) for base,t,s in zip((0.4,0.5,0.6),transmission,scatter))+(0.7,)
        for steps in (8,24,64):
            gpu.uniform('volumeParams',60,1e30,0,steps)
            if filtered:
                s,t=pair(gpu)
                close(s[:3],scatter,'actual MRT colored fog analytic single scattering')
                close(t[:3],transmission,'colored lighting does not modify RGB extinction')
                assert 0<s[3]<60
                close(t[3:],(100*math.sqrt(1+2*(1/64)**2),),'MRT endpoint remains geometric',0.02)
            else:
                close(gpu.draw(),expected,'actual inline colored fog analytic integration and alpha')
        for anisotropy in (-0.85,-0.35,0.35,0.85):
            gpu.uniform('voxelFogAnisotropy',anisotropy)
            if filtered:
                s,t=pair(gpu)
                close(s[:3],scatter,'MRT phase normalization preserves isotropic field energy')
                close(t[:3],transmission,'phase does not change extinction')
            else:
                close(gpu.draw(),expected,'inline phase normalization preserves isotropic field energy')
        shifted=inverse.copy();shifted[12:15]=[-1960,40,3020]
        gpu.matrix('inverseView',shifted)
        gpu.uniform('cameraOffset',2000,0,-3000)
        gpu.uniform('voxelOrigin',-2000,0,3000)
        if filtered:
            s,t=pair(gpu)
            close(s[:3],scatter,'actual MRT colored fog survives camera-origin rebasing')
            close(t[:3],transmission,'rebasing preserves volume extinction')
        else:
            close(gpu.draw(),expected,'actual inline colored fog survives camera-origin rebasing')
        gpu.uniform('voxelFogStrength',0)
        if filtered:
            s,t=pair(gpu)
            close(s[:3],(0,0,0),'zero local strength retains only existing fog sources')
            close(t[:3],transmission,'zero local strength retains extinction')
        else:
            close(gpu.draw(),tuple(base*t**(1/2.2) for base,t in zip((0.4,0.5,0.6),transmission))+(0.7,),
                  'disabled local scattering retains original scene attenuation')
        gpu.uniform('atmosphereEnabled',0)
        if filtered:
            s,t=pair(gpu)
            close(s,(0,0,0,0),'MRT bypass has no local scattering')
            close(t,(1,1,1,-1),'MRT bypass does not revive volume history')
        else:
            close(gpu.draw(),(0.4,0.5,0.6,0.7),'inline bypass preserves scene and alpha')
        print(f'PASS: actual fog transport, filtered={filtered}, atlas columns={columns}, analytic RGB/step/alpha/bypass checks;',gpu.renderer)


def phase(g,cosine):
    g=max(-0.85,min(0.85,g))
    return (1-g*g)/(1+g*g-2*g*cosine)**1.5


def phase_response():
    with ShaderTest(FLAGS+DYNAMIC+VOXEL+HELPER_MAIN) as gpu:
        gpu.sampler('texture4',4)
        gpu.uniform('voxelOrigin',0,0,0);gpu.uniform('voxelParams',1,1,0,N)
        gpu.uniform('voxelFogStrength',1);gpu.uniform('testPosition',80,80,80)
        gpu.uniform('voxelFogAnisotropy',0);gpu.uniform('testView',0,0,1)
        upload(gpu,probes())
        color=(2,1,0.5)
        directions=((1,0,0),(0,1,0),(0,0,1),(-1,0,0),
                    (1/math.sqrt(2),1/math.sqrt(2),0),(1/math.sqrt(3),)*3)
        for g in (0,0.35,-0.35,0.85,-0.85,100,-100):
            gpu.uniform('voxelFogAnisotropy',g)
            for direction in directions:
                sources(gpu,[(tuple(8+6*d for d in direction),color)])
                for sign in (-1,1):
                    gpu.uniform('testView',*(sign*d for d in direction))
                    expected=tuple(c*falloff(6)*phase(g,sign)/6 for c in color)+(1,)
                    close(gpu.draw(),expected,'actual per-lamp HG phase and rotation invariance')
        gpu.uniform('voxelFogAnisotropy',0.5);gpu.uniform('testView',0,0,1)
        sources(gpu,[((8,8,14),color)])
        for g in (-0.85,-0.35,0.35,0.85):
            gpu.uniform('voxelFogAnisotropy',g)
            for cosine in (-0.6,-0.25,0,0.25,0.6):
                gpu.uniform('testView',math.sqrt(1-cosine*cosine),0,cosine)
                close(gpu.draw(),tuple(c*falloff(6)*phase(g,cosine)/6 for c in color)+(1,),
                      'per-source phase follows intermediate scattering angles')
        gpu.uniform('voxelFogAnisotropy',0.5);gpu.uniform('testView',0,0,1)
        for distance in (0,0.01,0.25,0.5,1):
            sources(gpu,[((8,8,8+distance),color)])
            t=min(distance,1);blend=t*t*(3-2*t)
            effective=1+(phase(0.5,1)-1)*blend
            close(gpu.draw(),tuple(c*falloff(distance)*effective/6 for c in color)+(1,),
                  'finite continuous isotropic core at coincident/nearby source')
        sources(gpu,[((8,8,14),color)]*8,count=99)
        close(gpu.draw(),tuple(8*c*falloff(6)*phase(0.5,1)/6 for c in color)+(1,),
              'all eight sources use phase independently and count remains bounded')
        sources(gpu,[])
        gpu.uniform('voxelFogAnisotropy',0.35);gpu.uniform('testView',0,0,1)
        filtered=probes()
        for x in range(N):
            for y in range(N):cell(filtered,14,13,x,y,11,(0.8,0.5,0.25,1))
        upload(gpu,filtered)
        sources(gpu,[((8,8,14),color)])
        close(gpu.draw(),tuple(c*t*falloff(6)*phase(0.35,1)/6 for c,t in zip(color,(0.8,0.5,0.25)))+(1,),
              'anisotropic moving light retains RGB visibility')
        for x in range(N):
            for y in range(N):cell(filtered,14,13,x,y,11,(1,1,1,0))
        upload(gpu,filtered)
        close(gpu.draw(),(0,0,0,1),'forward-scattering phase cannot illuminate through a wall')
        sources(gpu,[])
        for direct,bounce,gains,expected in (((float('nan'),)*3,color,(0,1),color),
                                             (color,(float('nan'),)*3,(1,0),color)):
            upload(gpu,probes(direct,bounce))
            gpu.uniform('voxelParams',1,*gains,N)
            close(gpu.draw(),expected+(1,),'disabled direct/bounce lobe is not sampled')
        gpu.uniform('voxelParams',1,1,0,N)
        field=probes()
        for z in range(N):
            for y in range(N):
                for x in range(N):cell(field,14,4,x,y,z,color+(1,))
        upload(gpu,field)
        for g in (0,0.35,-0.35,0.85):
            gpu.uniform('voxelFogAnisotropy',g)
            total=4*phase(g,0)+phase(g,1)+phase(g,-1)
            for sign in (-1,1):
                gpu.uniform('testView',0,0,sign)
                close(gpu.draw(),tuple(c*phase(g,sign)/total for c in color)+(1,),
                      'directional probe quadrature follows view and medium phase')
        gpu.texture(4,(float('nan'),)*4)
        gpu.uniform('voxelParams',1,0,0,N)
        close(gpu.draw(),(0,0,0,1),'inactive direct and bounce skip atlas sampling')
        print('PASS: HG forward/back scattering, rotation invariance, finite core, eight-source bounds and phase-weighted probes;',gpu.renderer)


if __name__=='__main__':
    helper()
    phase_response()
    transport()
    transport(filtered=True)
    transport(dynamic=False)
