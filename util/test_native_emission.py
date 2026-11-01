#!/usr/bin/env python3
"""Full production node/object fragments: native glow independent of stale voxel classification."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import re
from pathlib import Path
from gl_shader_test import ShaderTest
from test_dynamic_lighting import atlas, cell, upload, sources, falloff, N, close

ROOT=Path(__file__).resolve().parents[1]/'client/shaders'
VOXEL=(ROOT/'common/voxel_lighting.glsl').read_text()
BASE=(0.8,0.4,0.2)
NATIVE=(0.4,0.1,0.025)


def source(kind,emissive,dynamic):
    flags='''#define ENABLE_VOXEL_LIGHTING
#define MATERIAL_TYPE 0
#define MATERIAL_WATER_REFLECTIONS 0
#define TILE_MATERIAL_WAVING_LEAVES 6
#define TILE_MATERIAL_WAVING_PLANTS 7
'''
    if emissive: flags+='#define MATERIAL_EMISSIVE\n'
    if dynamic: flags+='#define ENABLE_VOXEL_DYNAMIC_DIRECT\n#define MAX_VOXEL_DYNAMIC_LIGHTS 8\n'
    body=(ROOT/(kind+'_shader')/'opengl_fragment.glsl').read_text()
    body=body.replace('CENTROID_ VARYING_ mediump vec2 varTexCoord;',
                      '#define varTexCoord (gl_FragCoord.xy/64.0)')
    body=re.sub(r'(?:CENTROID_ )?VARYING_ (?:lowp |mediump |highp )?(\w+) (\w+);',r'uniform \1 \2;',body)
    body=body.replace('uniform lowp vec4','uniform vec4')
    return flags+VOXEL+body


def optional(gpu,name,*values):
    if gpu.api('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)(gpu.program,name.encode())>=0:
        gpu.uniform(name,*values)


def setup(gpu,kind,dynamic):
    gpu.sampler('baseTexture',0);gpu.texture(0,BASE+(0.6,))
    if kind=='nodes':
        gpu.sampler('texture1',1);gpu.texture(1,(0,0,0,0))
        gpu.uniform('crackLevel',-1);gpu.uniform('crackAnimationLength',1);gpu.uniform('crackTextureScale',1)
    else: gpu.uniform('vIDiff',1)
    gpu.sampler('texture2',2)
    gpu.uniform('voxelParams',1,1,0,N);gpu.uniform('voxelOrigin',0,0,0)
    gpu.uniform('worldPosition',80,40,80);gpu.uniform('vNormal',0,0,1)
    gpu.uniform('varColor',0.5,0.25,0.125,1);gpu.uniform('eyeVec',0,0,0)
    optional(gpu,'nightRatio',1);optional(gpu,'dayLight',1,1,1)
    gpu.uniform('fogColor',0,0,0,1);gpu.uniform('fogDistance',10000);gpu.uniform('fogShadingParameter',1)
    if dynamic: sources(gpu,[])


def field(columns,marker,direct=(0,0,0),bounce=(0,0,0)):
    data=atlas(columns)
    for z in range(N):
        for y in range(N):
            for x in range(N):
                for group in range(12):
                    cell(data,columns,group,x,y,z,(direct if group<6 else bounce)+(1,))
                cell(data,columns,12,x,y,z,(1,1,1,marker))
    return data


def preservation(kind,emissive,dynamic):
    columns=14 if dynamic else 13
    with ShaderTest(source(kind,emissive,dynamic)) as gpu:
        setup(gpu,kind,dynamic)
        expected=NATIVE if emissive else (0,0,0)
        for marker in (0,1):
            upload(gpu,field(columns,marker),columns)
            close(gpu.draw(),expected+(0.6,),
                  f'{kind} native emission={emissive} ignores stale marker={marker}')
        # Emissive classification protects native light, while reflected light still adds.
        direct,bounce=(0.125,0.0625,0.03125),(0.03,0.06,0.09)
        gpu.uniform('voxelParams',1,1,0.5,N)
        upload(gpu,field(columns,0,direct,bounce),columns)
        added=tuple((native**2.2+(base**2.2)*(a+0.5*b))**(1/2.2)
                    for native,base,a,b in zip(expected,BASE,direct,bounce))+(0.6,)
        close(gpu.draw(),added,f'{kind} native light and colored direct/bounce coexist')
        if dynamic:
            gpu.uniform('voxelParams',1,1,0,N);upload(gpu,field(columns,0),columns)
            sources(gpu,[((8,4,12),(2,1,0.5))])
            strength=falloff(4)
            added=tuple((native**2.2+(base**2.2)*strength*e)**(1/2.2)
                        for native,base,e in zip(expected,BASE,(2,1,0.5)))+(0.6,)
            close(gpu.draw(),added,f'{kind} moving lamp adds independently of native glow')
            if kind=='object':
                gpu.uniform('vNormal',0,0,0)
                added=tuple((native**2.2+(base**2.2)*strength*e/6)**(1/2.2)
                            for native,base,e in zip(expected,BASE,(2,1,0.5)))+(0.6,)
                close(gpu.draw(),added,'sprite native glow plus current moving illumination')
        # Unbound or disabled voxel direct lighting must restore the native draw.
        gpu.uniform('voxelParams',0,1,0,N);gpu.texture(2,(float('nan'),)*4)
        close(gpu.draw(),NATIVE+(0.6,),f'{kind} absent-atlas native fallback')
        upload(gpu,field(columns,1),columns);gpu.uniform('voxelParams',1,0,0,N)
        close(gpu.draw(),NATIVE+(0.6,),f'{kind} zero-strength native fallback')
        print(f'PASS: full {kind} fragment, emission={emissive}, columns={columns}, '
              'stale classification, native/direct/bounce, alpha and fallback;',gpu.renderer)


if __name__=='__main__':
    for kind in ('nodes','object'):
        for dynamic in (False,True):
            for emissive in (True,False):
                preservation(kind,emissive,dynamic)
