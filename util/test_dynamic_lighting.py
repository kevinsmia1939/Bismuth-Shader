#!/usr/bin/env python3
"""Actual voxel GLSL: frame-direct movement, visibility and RGB transport; no images/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
from pathlib import Path
from gl_shader_test import ShaderTest

HELPER=(Path(__file__).resolve().parents[1]/'client/shaders/common/voxel_lighting.glsl').read_text()
FLAGS='#define ENABLE_VOXEL_LIGHTING\n#define ENABLE_VOXEL_DYNAMIC_DIRECT\n#define MAX_VOXEL_DYNAMIC_LIGHTS 8\n'
MAIN='''
uniform vec3 testPosition, testNormal, testGeometric;
uniform float testNode, testCompose;
void main() {
 vec3 result;
 if(testCompose>1.5) result=voxelProbe(testPosition,0.0).rgb;
 else if(testCompose>0.5) result=applyVoxelLighting(vec3(0),vec3(1),testPosition,
   testNormal,testGeometric,0.0,vec3(0),testNode>0.5);
 else result=voxelDynamicIrradiance(testPosition,testNormal,testGeometric,testNode>0.5);
 gl_FragColor=vec4(result,1);
}
'''
N=16

def close(actual,expected,label,tol=0.00005):
    assert all(abs(a-b)<=tol for a,b in zip(actual,expected)),(label,actual,expected)

def atlas(columns=14):
    data=[0.0]*(N*N*N*columns*4)
    for z in range(N):
        for y in range(N):
            for x in range(N):
                for group in range(columns):
                    value=(1,1,1,0) if group==12 else ((1,1,1,1) if group==13 else (0,0,0,1))
                    cell(data,columns,group,x,y,z,value)
    return data

def cell(data,columns,group,x,y,z,value):
    offset=((z*N+y)*(N*columns)+group*N+x)*4
    data[offset:offset+4]=value

def upload(gpu,data,columns=14):
    gpu.texture(2,data,linear=True,width=N*columns,height=N*N)

def sources(gpu,lights,count=None):
    positions=[0.0]*32
    emission=[0.0]*32
    for i,(position,color) in enumerate(lights):
        positions[i*4:i*4+3]=position
        emission[i*4:i*4+3]=color
    for name,values in (('voxelDynamicPosition[0]',positions),('voxelDynamicEmission[0]',emission)):
        gpu.api('glUniform4fv',None,c.c_int,c.c_int,c.POINTER(c.c_float))(
            gpu.location(name),8,(c.c_float*32)(*values))
    gpu.uniform('voxelDynamicCount',len(lights) if count is None else count)

def setup(gpu):
    gpu.sampler('texture2',2)
    gpu.uniform('voxelParams',1,1,0,N)
    gpu.uniform('voxelOrigin',0,0,0)
    gpu.uniform('testPosition',8,4,4)
    gpu.uniform('testNormal',-1,0,0)
    gpu.uniform('testGeometric',0,0,0)
    gpu.uniform('testNode',0)
    gpu.uniform('testCompose',0)

def falloff(distance): return max(0,1-(distance/16)**4)**2/(distance*distance+4)

def movement():
    with ShaderTest(FLAGS+HELPER+MAIN) as gpu:
        setup(gpu);upload(gpu,atlas())
        # Only uniforms change; no worker/texture upload follows these moves.
        for x in (2.25,3.25,4.5):
            sources(gpu,[((x,4,4),(2,0,0))])
            close(gpu.draw(),(2*falloff(8-x),0,0,1),'fractional movement without worker upload')
        sources(gpu,[((4.5,4,4),(0,2,0))])
        close(gpu.draw(),(0,2*falloff(3.5),0,1),'immediate recolor')
        sources(gpu,[])
        close(gpu.draw(),(0,0,0,1),'immediate removal')
        sources(gpu,[((2,4,4),(2,0,0)),((3,4,4),(0,0,2))],count=99)
        close(gpu.draw(),(2*falloff(6),0,2*falloff(5),1),'bounded array and independent lights')
        lights=[((2+i*0.125,4,4),(0.25+i*0.1,0.5,1-i*0.1)) for i in range(8)]
        sources(gpu,lights,count=99)
        expected=tuple(sum(color[channel]*falloff(8-position[0]) for position,color in lights)
                       for channel in range(3))+(1,)
        close(gpu.draw(),expected,'all eight uniform-array entries contribute within the bound')
        sources(gpu,[((2,4,4),(2,0,0))]);gpu.uniform('testNormal',0,0,0)
        close(gpu.draw(),(2*falloff(6)/6,0,0,1),'sprite isotropic convention')
        sources(gpu,[((8,4,4),(2,0,0))])
        close(gpu.draw(),(0.5,0,0,1),'coincident point remains finite without a hotspot')
        print('PASS: per-frame positions/colors/count with unchanged atlas, bounded light array;',gpu.renderer)

def visibility():
    with ShaderTest(FLAGS+HELPER+MAIN) as gpu:
        setup(gpu);data=atlas();sources(gpu,[((2,4,4),(2,2,2))])
        for y in range(N):
            for z in range(N):cell(data,14,13,5,y,z,(1,1,1,0))
        upload(gpu,data)
        close(gpu.draw(),(0,0,0,1),'sealed opaque wall')
        data=atlas();cell(data,14,13,2,4,4,(1,1,1,0));upload(gpu,data)
        close(gpu.draw(),(0,0,0,1),'source inside stale solid/unknown cell')
        upload(gpu,atlas());sources(gpu,[((-1,4,4),(2,2,2))])
        close(gpu.draw(),(0,0,0,1),'outside-volume source rejected')
        sources(gpu,[((8,4,4),(2,0,0))]);gpu.uniform('testPosition',4.25,4,4)
        gpu.uniform('testNormal',1,0,0);gpu.uniform('testGeometric',1,0,0)
        data=atlas();cell(data,14,13,4,4,4,(0,0,0,0));upload(gpu,data)
        close(gpu.draw(),(0,0,0,1),'embedded object receiver cannot open a wall')
        gpu.uniform('testNode',1)
        close(gpu.draw(),(2*falloff(3.75),0,0,1),'node receiver ignores only its own coarse cell')
        cell(data,14,13,6,4,4,(1,1,1,0));upload(gpu,data)
        close(gpu.draw(),(0,0,0,1),'other wall remains opaque after receiver exception')
        print('PASS: opaque/unknown/outside guards, receiver-cell exception and independent blocker;',gpu.renderer)

def transmission():
    with ShaderTest(FLAGS+HELPER+MAIN) as gpu:
        setup(gpu);data=atlas();sources(gpu,[((2,4,4),(2,2,2))])
        for x in (5,6):
            for y in range(N):
                for z in range(N):cell(data,14,13,x,y,z,(0.8,0.5,0.25,1))
            upload(gpu,data)
            close(gpu.draw(),tuple(2*falloff(6)*t**(x-4) for t in (0.8,0.5,0.25))+(1,),
                  'RGB path length through one/two layers')
        for y in range(N):
            for z in range(N):cell(data,14,13,6,y,z,(1,1,1,1))
        upload(gpu,data);gpu.uniform('testPosition',8,7,4)
        d=math.sqrt(45)
        close(gpu.draw(),tuple(2*falloff(d)*(6/d)*t**(d/6) for t in (0.8,0.5,0.25))+(1,),
              'oblique Beer-Lambert path')
        gpu.uniform('testPosition',5.25,4,4);gpu.uniform('testNormal',1,0,0)
        sources(gpu,[((8,4,4),(2,2,2))])
        close(gpu.draw(),tuple(2*falloff(2.75)*t**0.25 for t in (0.8,0.5,0.25))+(1,),
              'partial first cell')
        cell(data,14,13,5,4,4,(0,0.5,1,1));upload(gpu,data)
        close(gpu.draw(),(0,2*falloff(2.75)*0.5**0.25,2*falloff(2.75),1),'zero channel remains finite')
        print('PASS: actual colored voxel transmission, thickness, slanted/partial paths and zero channels;',gpu.renderer)

def composition():
    with ShaderTest(FLAGS+HELPER+MAIN) as gpu:
        setup(gpu);data=atlas()
        for z in range(N):
            for y in range(N):
                for x in range(N):
                    cell(data,14,1,x,y,z,(0.125,0,0,1))
                    cell(data,14,7,x,y,z,(0,0.0625,0,1))
                    cell(data,14,12,x,y,z,(0.5,1,1,0))
        upload(gpu,data);sources(gpu,[((2,4,4),(2,0,0))])
        gpu.uniform('voxelParams',1,1,0.5,N)
        gpu.uniform('testPosition',80,40,40);gpu.uniform('testGeometric',-1,0,0)
        gpu.uniform('testNode',1);gpu.uniform('testCompose',1)
        expected=((0.5*(0.125+2*falloff(6)))**(1/2.2),(0.0625*0.5)**(1/2.2),0,1)
        close(gpu.draw(),expected,'static/frame direct plus bounce and palette bands in 14-column atlas')
        gpu.uniform('voxelOrigin',10000,-2000,3000);gpu.uniform('testPosition',10080,-1960,3040)
        close(gpu.draw(),expected,'camera origin rebasing preserves world light')
        gpu.uniform('voxelParams',1,0,0,N)
        close(gpu.draw(),(0,0,0,1),'zero direct strength')
        gpu.texture(2,(float('nan'),)*4)
        close(gpu.draw(),(0,0,0,1),'inactive local lighting avoids all probe and material samples')
        gpu.uniform('voxelParams',1,1,0,N)
        gpu.uniform('testPosition',-10000,-2000,3000)
        close(gpu.draw(),(0,0,0,1),'outside local field avoids invalid atlas samples')
        gpu.uniform('testCompose',0);gpu.uniform('voxelParams',0,1,0,N)
        gpu.texture(2,(float('nan'),)*4)
        close(gpu.draw(),(0,0,0,1),'unavailable atlas guard precedes sampling')
        gpu.uniform('voxelParams',1,1,0,N);sources(gpu,[])
        close(gpu.draw(),(0,0,0,1),'no-source guard precedes sampling')
        print('PASS: actual atlas/material composition, origin rebase, strength and absent-binding guards;',gpu.renderer)

def fallback():
    main='''void main(){gl_FragColor=vec4(applyVoxelLighting(vec3(0),vec3(1),vec3(80,40,40),
     vec3(-1,0,0),vec3(-1,0,0),0.0,vec3(0),true),1);}'''
    with ShaderTest('#define ENABLE_VOXEL_LIGHTING\n'+HELPER+main) as gpu:
        gpu.sampler('texture2',2);gpu.uniform('voxelOrigin',0,0,0);gpu.uniform('voxelParams',1,1,0,N)
        data=atlas(13)
        for z in range(N):
            for y in range(N):
                for x in range(N):cell(data,13,1,x,y,z,(0.25,0,0,1))
        upload(gpu,data,13)
        close(gpu.draw(),(0.25**(1/2.2),0,0,1),'13-column asynchronous fallback')
        print('PASS: original 13-column atlas fallback without frame-direct shader feature;',gpu.renderer)

def live_geometry():
    with ShaderTest(FLAGS+HELPER+MAIN) as gpu:
        setup(gpu);sources(gpu,[((2,4,4),(2,2,2))]);gpu.uniform('testGeometric',-1,0,0)
        data=atlas()
        # A pending worker still regards the newly opened receiver cell as solid.
        # Its old radiance is deliberately nonzero and must stay in the atlas.
        for z in range(N):
            for y in range(N):
                for x in range(N):
                    for group in range(12):cell(data,14,group,x,y,z,(0.02,0.03,0.04,0))
        upload(gpu,data);gpu.uniform('testCompose',1);gpu.uniform('testPosition',80,40,40)
        level=2*falloff(6)
        close(gpu.draw(),(level**(1/2.2),)*3+(1,), 'current direct light survives stale solid probe metadata')

        def edit(value):
            gpu.api('glActiveTexture',None,c.c_uint)(0x84C0+2)
            gpu.api('glBindTexture',None,c.c_uint,c.c_uint)(0x0DE1,3)
            gpu.api('glTexSubImage2D',None,c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,
                    c.c_uint,c.c_uint,c.c_void_p)(0x0DE1,0,13*N+5,4*N+4,1,1,0x1908,0x1406,
                                                  (c.c_float*4)(*value))
        edit((1,1,1,0))
        close(gpu.draw(),(0,0,0,1),'wall update blocks current light without a worker upload')
        edit((0.5,1,0.25,1))
        close(gpu.draw(),tuple((level*t)**(1/2.2) for t in (0.5,1,0.25))+(1,),
              'current glass transmission replaces the wall before the worker finishes')
        edit((1,1,1,1))
        close(gpu.draw(),(level**(1/2.2),)*3+(1,), 'removing the filter restores direct lighting immediately')
        gpu.uniform('testCompose',2);gpu.uniform('testPosition',8,4,4)
        close(gpu.draw(),(0.02,0.03,0.04,1),'optics subregion updates preserve old worker radiance')
        print('PASS: live wall/filter/removal updates, unchanged radiance and stale-probe independence;',gpu.renderer)


if __name__=='__main__':
    movement();visibility();transmission();composition();fallback();live_geometry()
