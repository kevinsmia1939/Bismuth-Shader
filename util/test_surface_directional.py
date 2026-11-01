#!/usr/bin/env python3
"""Full production node fragment: illumination independent of shadow controls; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
import re
from pathlib import Path
from gl_shader_test import ShaderTest
from test_water_volume import close

ROOT=Path(__file__).resolve().parents[1]/'client/shaders'
NODES=(ROOT/'nodes_shader/opengl_fragment.glsl').read_text()
MATERIAL=(ROOT/'common/material_maps.glsl').read_text()
FLAGS='''#define ENABLE_MATERIAL_SHADING
#define ENABLE_MATERIAL_MAPS
#define MATERIAL_NORMAL_STRENGTH 0.0
#define MATERIAL_ROUGHNESS 0.8
#define MATERIAL_TYPE 0
#define TILE_MATERIAL_WAVING_LEAVES 6
#define TILE_MATERIAL_WAVING_PLANTS 7
#define ENABLE_WATER_REFLECTIONS
#define ENABLE_WAVING_WATER 1
#define SHADOW_FILTER 0
#define SOFTSHADOWRADIUS 1.0
'''


def source(shadows=False,water=False,emissive=False,clouds=False,maps=True):
    flags=FLAGS+f'#define MATERIAL_WATER_REFLECTIONS {int(water)}\n'
    if not maps: flags=flags.replace('#define ENABLE_MATERIAL_MAPS\n','')
    if shadows: flags+='#define ENABLE_DYNAMIC_SHADOWS\n#define COLORED_SHADOWS\n'
    if emissive: flags+='#define MATERIAL_EMISSIVE\n'
    # A controlled cloud lookup isolates actual node composition from cloud-map generation.
    if clouds:
        flags+='''#define ENABLE_CLOUD_SHADOWS
uniform float testCloud;
float cloudSunTransmission(vec3 p) { return testCloud; }
vec3 cloudShadeNative(vec3 color,float transmission,vec3 normal,float night,vec3 visible) { return color; }
'''
    body=NODES.replace('CENTROID_ VARYING_ mediump vec2 varTexCoord;',
                       '#define varTexCoord (gl_FragCoord.xy/64.0)')
    body=re.sub(r'(?:CENTROID_ )?VARYING_ (?:lowp |mediump |highp )?(\w+) (\w+);',r'uniform \1 \2;',body)
    body=body.replace('uniform lowp vec4','uniform vec4')
    return flags+MATERIAL+body


def setup(gpu,water=False,maps=True):
    gpu.sampler('baseTexture',0);gpu.texture(0,(0.8,0.4,0.2,0.6))
    gpu.sampler('texture1',1);gpu.texture(1,(0,0,0,0))
    gpu.uniform('crackLevel',-1);gpu.uniform('crackAnimationLength',1);gpu.uniform('crackTextureScale',1)
    # Water without native shadow filtering uses the independent light packet.
    if gpu.api('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)(gpu.program,b'dayLight') >= 0:
        gpu.uniform('dayLight',1,1,1)
    gpu.uniform('cameraPosition',0,0,10);gpu.uniform('cameraOffset',0,0,0)
    gpu.uniform('worldPosition',0,0,0);gpu.uniform('vNormal',0,0,1)
    gpu.uniform('eyeVec',0,0,0);gpu.uniform('varColor',0,0,0,1)
    gpu.uniform('nightRatio',0);gpu.uniform('fogColor',0,0,0,1)
    gpu.uniform('fogDistance',10000);gpu.uniform('fogShadingParameter',1)
    gpu.uniform('surfaceLight',0,0,1,1);gpu.uniform('surfaceLightColor',1,1,1)
    if not water and maps:
        gpu.sampler('texture4',4);gpu.texture(4,(0.5,0.5,1,1))
        gpu.sampler('texture5',5);gpu.texture(5,(1,0.5,1,1))
        gpu.uniform('materialMapFlags',0,1,1)


def shadow_setup(gpu):
    gpu.sampler('ShadowMapSampler',3);gpu.texture(3,(1,0,1,0))
    gpu.uniform('f_shadow_strength',1);gpu.uniform('adj_shadow_strength',1)
    gpu.uniform('shadow_position',0,0,0);gpu.uniform('cosLight',1);gpu.uniform('f_normal_length',1)
    gpu.uniform('shadow_tint',0,0,0)


def materials(shadows):
    with ShaderTest(source(shadows=shadows)) as gpu:
        setup(gpu)
        if shadows: shadow_setup(gpu)
        expected=tuple(v*(1/(4*math.pi*0.5**4))**(1/2.2) for v in (0.8,0.4,0.2))+(0.6,)
        close(gpu.draw(),expected,'full node mapped conductor sunlight',0.0001)
        if shadows:
            # A disabled or faded shadow changes occlusion, not emitted radiance.
            for strength in (0,0.2,0.65,1):
                gpu.uniform('f_shadow_strength',strength);gpu.uniform('adj_shadow_strength',strength)
                close(gpu.draw(),expected,'unoccluded sunlight independent of shadow intensity',0.0001)
            gpu.uniform('f_shadow_strength',0);gpu.texture(3,(float('nan'),)*4)
            close(gpu.draw(),expected,'zero-shadow path does not sample an invalid map',0.0001)
            gpu.uniform('f_shadow_strength',1);gpu.uniform('adj_shadow_strength',1)
            gpu.texture(3,(0.4,0,1,0))
            close(gpu.draw(),(0,0,0,0.6),'opaque shadow attenuates reflected sunlight')
            gpu.uniform('adj_shadow_strength',0.5)
            close(gpu.draw(),tuple(v*0.5**(1/2.2) for v in expected[:3])+(0.6,),
                  'partial shadow strength changes visibility only',0.0001)
            gpu.uniform('adj_shadow_strength',1)
            gpu.texture(3,(1,0,0.4,64*129))
            close(gpu.draw(),(0,expected[1]*0.5**(1/2.2),0,0.6),'colored shadow visibility remains RGB',0.0001)
            gpu.uniform('shadow_position',0,0,1.2)
            close(gpu.draw(),expected,'depth fade retains material illumination',0.0001)
            gpu.uniform('shadow_position',1.1,0,0)
            close(gpu.draw(),expected,'outside XY shadow coverage retains material illumination',0.0001)
            gpu.uniform('f_shadow_strength',0)
        # Unmapped assets use the same linear GGX composition with a rough dielectric.
        gpu.uniform('materialMapFlags',0,0,1)
        fallback=(0.04/(4*math.pi*0.8**4))**(1/2.2)
        close(gpu.draw(),(fallback,fallback,fallback,0.6),'unmapped linear dielectric fallback',0.0001)
        gpu.uniform('materialMapFlags',0,1,1)
        gpu.uniform('surfaceLight',0,0,1,0)
        close(gpu.draw(),(0,0,0,0.6),'hidden source has no directional highlight')
        gpu.uniform('surfaceLight',0,0,1,0.5)
        close(gpu.draw(),tuple(v*0.5**(1/2.2) for v in expected[:3])+(0.6,), 'moon/source strength is independent',0.0001)
        gpu.uniform('surfaceLight',0,0,1,1);gpu.uniform('nightRatio',1)
        close(gpu.draw(),(0,0,0,0.6),'native artificial-light dominance suppresses directional reflection')
        gpu.uniform('nightRatio',0);gpu.uniform('cameraPosition',0,0,0)
        close(gpu.draw(),(0,0,0,0.6),'coincident view is finite and has no highlight')
        gpu.uniform('cameraPosition',0,0,10)
        gpu.uniform('surfaceLight',0.8,0,-0.6,1)
        gpu.uniform('materialMapFlags',1,1,1);gpu.texture(4,(1,0.5,0.55,1))
        close(gpu.draw(),(0,0,0,0.6),'mapped normal cannot expose the back of the real face')
        print(f'PASS: actual node material illumination, shadow enable/fade/visibility, hidden source and geometric guards; shadows={shadows};',gpu.renderer)


def limited_material():
    with ShaderTest(source(maps=False)) as gpu:
        setup(gpu,maps=False)
        fallback=(0.04/(4*math.pi*0.8**4))**(1/2.2)
        close(gpu.draw(),(fallback,fallback,fallback,0.6),'no-map-capability linear dielectric fallback',0.0001)
        gpu.uniform('surfaceLight',0,0,1,0)
        close(gpu.draw(),(0,0,0,0.6),'hidden source without map capability')
        gpu.uniform('surfaceLight',0,0,1,1);gpu.uniform('cameraPosition',0,0,-10)
        close(gpu.draw(),(0,0,0,0.6),'opposing light and view fallback is finite')
        print('PASS: actual node dielectric fallback without material-map capability;',gpu.renderer)


def water(shadows):
    with ShaderTest(source(shadows=shadows,water=True)) as gpu:
        setup(gpu,water=True)
        # The water normal comes from derivatives of actual mesh geometry.
        # A constant position has degenerate derivatives and retains vNormal.
        if shadows: shadow_setup(gpu)
        clear=gpu.draw()
        close(clear,(2.4,2.4,2.4,0.6),'white source produces a white water glint independent of base tint')
        if shadows:
            gpu.uniform('f_shadow_strength',0);gpu.texture(3,(float('nan'),)*4)
            close(gpu.draw(),clear,'water glint remains with shadow intensity zero')
            gpu.uniform('f_shadow_strength',1);gpu.texture(3,(0.4,0,1,0))
            close(gpu.draw(),(0,0,0,0.6),'opaque shadow hides water glint')
            gpu.uniform('shadow_position',0,0,1.2)
            close(gpu.draw(),clear,'water glint persists outside depth shadow fade')
        gpu.uniform('surfaceLight',0,0,1,0)
        close(gpu.draw(),(0,0,0,0.6),'hidden light removes glint')
        gpu.uniform('nightRatio',1);gpu.uniform('varColor',0.25,0.25,0.25,1)
        close(gpu.draw(),(0.2,0.1,0.05,0.6),'legacy sky fallback does not halve artificial water lighting')
        print(f'PASS: actual node water sun glint, disabled/faded shadows and native light preservation; shadows={shadows};',gpu.renderer)


def clouds():
    with ShaderTest(source(emissive=True,clouds=True)) as gpu:
        setup(gpu);gpu.uniform('varColor',0.25,0.25,0.25,1)
        gpu.uniform('testCloud',0)
        close(gpu.draw(),(0.2,0.1,0.05,0.6),'clouds preserve metallic native emission')
        gpu.uniform('testCloud',1);sun=gpu.draw()
        assert all(sun[i]>v for i,v in enumerate((0.2,0.1,0.05))),sun
        gpu.uniform('testCloud',0.5);half=gpu.draw()
        expected=tuple(((v**2.2+s**2.2)*0.5)**(1/2.2) for v,s in zip((0.2,0.1,0.05),sun[:3]))+(0.6,)
        close(half,expected,'clouds attenuate reflected sunlight separately from self emission',0.0001)
        print('PASS: actual emissive material/cloud composition separates native glow and directional reflections;',gpu.renderer)


if __name__=='__main__':
    materials(False)
    materials(True)
    limited_material()
    water(False)
    water(True)
    clouds()
