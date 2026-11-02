#!/usr/bin/env python3
"""Production shaders must not reveal unlit cave geometry under an outdoor sky."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import re
from gl_shader_test import ShaderTest
import test_surface_directional as node
from test_fog_denoise import source, mrt, attach_second, pair, IDENTITY, INVERSE, PROJECTION, A, B


def close(actual, expected, label, tolerance=2e-5):
    assert max(abs(a-b) for a,b in zip(actual,expected)) < tolerance, (label,actual,expected)


def optional(gpu, name, *value):
    if gpu.api('glGetUniformLocation', c.c_int, c.c_uint, c.c_char_p)(gpu.program,name.encode()) >= 0:
        gpu.uniform(name,*value)


def surfaces():
    for maps in (False,True):
        with ShaderTest(node.source(maps=maps)) as gpu:
            node.setup(gpu,maps=maps)
            gpu.uniform('nightRatio',1)
            gpu.uniform('fogColor',0.6,0.8,1,1)
            for distance in (0,10,200,1000):
                gpu.uniform('eyeVec',0,0,distance)
                close(gpu.draw(),(0,0,0,0.6),'unlit nodes stay black with bright sky and distance fog')
            # A lamp-lit wall cannot acquire sky radiance from its artificial bank.
            if maps:gpu.texture(5,(1,0.8,0,1)) # Ordinary dielectric stone.
            gpu.uniform('eyeVec',0,0,1000)
            gpu.uniform('varColor',0.25,0.25,0.25,1)
            lit=gpu.draw()
            gpu.uniform('fogColor',0,0,0,1)
            close(gpu.draw(),lit,'artificial light is independent of outdoor fog tint')
            assert min(lit[:3])>0,lit
            if maps:
                gpu.uniform('nightRatio',0)
                gpu.uniform('eyeVec',0,0,0)
                gpu.uniform('surfaceLight',0,0,1,0)
                gpu.uniform('fogColor',0.6,0.8,1,1)
                skylit=gpu.draw()
                gpu.uniform('fogColor',0,0,0,1)
                assert max(skylit[:3])>max(gpu.draw()[:3]),'Real skylight still reflects the environment'
    body=source('object_shader')
    body=re.sub(r'(?:CENTROID_ )?VARYING_ (?:lowp |mediump |highp )?(\w+) (\w+);',r'uniform \1 \2;',body)
    body=body.replace('uniform lowp vec4','uniform vec4')
    with ShaderTest(body) as gpu:
        gpu.sampler('baseTexture',0);gpu.texture(0,(0.8,0.4,0.2,0.6))
        gpu.uniform('varColor',0,0,0,1);gpu.uniform('nightRatio',1)
        gpu.uniform('fogColor',0.6,0.8,1,1);gpu.uniform('fogDistance',1000);gpu.uniform('fogShadingParameter',1)
        optional(gpu,'vIDiff',1)
        for distance in (0,200,1000):
            gpu.uniform('eyeVec',0,0,distance)
            close(gpu.draw(),(0,0,0,0.6),'unlit objects stay black under outdoor fog')
    print('PASS: mapped/unmapped cave walls and objects stay black; lamps and real skylight remain visible')


def atmosphere(volumetric, separated=False, shadows=False):
    flags='#define ENABLE_ATMOSPHERE\n#define ENABLE_SCENE_SURFACE\n'
    if volumetric:flags+='#define ENABLE_VOLUMETRIC_FOG\n'
    if separated:flags+='#define ENABLE_FOG_DENOISING\n#define FOG_TRANSPORT_PASS\n'
    if shadows:flags+='#define ENABLE_DYNAMIC_SHADOWS\n'
    fragment=flags+source('scene_lighting')
    with ShaderTest(mrt(fragment) if separated else fragment) as gpu:
        if separated:attach_second(gpu,half=True)
        gpu.sampler('texture1',1);gpu.sampler('texture2',2)
        if not separated:gpu.sampler('texture0',0);gpu.texture(0,(0,0,0,0.7))
        gpu.matrix('inverseProjection',INVERSE);gpu.matrix('inverseView',IDENTITY)
        gpu.uniform('cameraPosition',0,-1000,0);gpu.uniform('fogColor',0.6,0.8,1,1)
        gpu.uniform('sceneParams',0.01,0,0,0);gpu.uniform('atmosphereEnabled',1)
        if volumetric:
            gpu.uniform('cameraOffset',0,0,0);gpu.uniform('volumeParams',600,1000,0,24)
            gpu.uniform('volumeLightDirection',0,0,1);gpu.uniform('volumeLightColor',1,1,1)
            if shadows:
                gpu.sampler('ShadowMapSampler',3);gpu.texture(3,(0,0,0,0)) # Solid roof.
                matrix=IDENTITY.copy();matrix[0]=matrix[5]=matrix[10]=0.0001
                gpu.matrix('m_ShadowViewProj',matrix)
                gpu.uniform('CameraPos',0,0,0,0);gpu.uniform('xyPerspectiveBias0',0)
                gpu.uniform('xyPerspectiveBias1',1);gpu.uniform('zPerspectiveBias',1)
                gpu.uniform('volumeShadowReady',1)
        else:
            gpu.uniform('surfaceLight',0,0,1,1);gpu.uniform('surfaceLightColor',1,1,1)
        for distance in (10,100,600):
            gpu.texture(1,((A+B/distance)*0.5+0.5,0,0,1))
            gpu.texture(2,(0.5,0.5,-distance,1)) # Valid geometry, zero local sky.
            if separated:close(pair(gpu)[0][:3],(0,0,0),'roofed fog has no sky scattering')
            else:close(gpu.draw(),(0,0,0,0.7),'fog cannot trace the outline of an unlit cave')
        if shadows:
            gpu.texture(3,(1,0,1,0))
            value=pair(gpu)[0] if separated else gpu.draw()
            close(value[:3],(0,0,0),'local zero skylight rejects incomplete shadow-map occlusion')
        gpu.texture(2,(0.5,0.5,-600,2)) # Same depth but genuine outdoor skylight.
        value=pair(gpu)[0] if separated else gpu.draw()
        assert min(value[:3])>0.05,value
        gpu.texture(2,(0.5,0.5,-600,1.25))
        partial=pair(gpu)[0] if separated else gpu.draw()
        expected=[v*0.25 for v in value[:3]] if separated else [v*0.25**(1/2.2) for v in value[:3]]
        close(partial[:3],expected,'partial skylight remains continuous',0.001)
        print('PASS: dark daylight cave and lit outdoor fog; volumetric=',volumetric,
              'separated=',separated,'shadowed=',shadows,';',gpu.renderer)


def tone_mapping():
    fragment=source('second_stage')
    with ShaderTest('#define ENABLE_TONE_MAPPING 1\n'+fragment) as gpu:
        gpu.sampler('texture0',0);gpu.texture(0,(0,0,0,1))
        gpu.uniform('exposureParams.compensationFactor',1);gpu.uniform('saturation',1)
        close(gpu.draw(),(0,0,0,1),'tone mapping preserves exact black',1e-7)
        gpu.texture(0,(0.2,0.1,0.05,1))
        assert min(gpu.draw()[:3])>0,'Do not crush real dim lighting'
    print('PASS: final production tone mapping preserves black and nonzero light')


def water_fallback():
    with ShaderTest('#define ENABLE_SCENE_SURFACE\n#define ENABLE_SCREEN_SPACE_REFLECTIONS\n'+source('scene_lighting')) as gpu:
        gpu.sampler('texture0',0);gpu.texture(0,(0,0,0,0.7))
        gpu.sampler('texture1',1);gpu.texture(1,((A+B/100)*0.5+0.5,0,0,1))
        gpu.sampler('texture2',2);gpu.texture(2,(0.5,0.5,100,1))
        gpu.matrix('inverseProjection',INVERSE);gpu.matrix('inverseView',IDENTITY)
        gpu.matrix('sceneProjection',PROJECTION)
        gpu.uniform('fogColor',0.6,0.8,1,1);gpu.uniform('sceneParams',0,0.7,0,0)
        gpu.uniform('waterCameraInside',0)
        close(gpu.draw(),(0,0,0,0.7),'unlit cave water cannot reflect an inaccessible sky fallback')
        gpu.texture(2,(0.5,0.5,100,2))
        assert min(gpu.draw()[:3])>0.01,'Skylit outdoor water retains its sky fallback'
    print('PASS: water sky fallback respects local skylight; outdoor reflections remain')


def surface_metadata():
    for divisor in (1,8,16,32):
        with ShaderTest(mrt(f'#define SCENE_SKY_DIVISOR {divisor}.0\n#define ENABLE_SCENE_SURFACE\n'+node.source())) as gpu:
            attach_second(gpu,half=True);node.setup(gpu);gpu.matrix('sceneView',IDENTITY)
            gpu.uniform('eyeVec',0,0,-100)
            gpu.api('glEnable',None,c.c_uint)(0x0BE2)
            gpu.api('glBlendFunc',None,c.c_uint,c.c_uint)(0x0302,0x0303)
            # Production materials disable this attachment independently; the C++
            # surface-blend test verifies the driver state and emission coverage.
            gpu.api('glDisablei',None,c.c_uint,c.c_uint)(0x0BE2,1)
            for light,night in ((0,1),(0.25,0),(1,0),(1,1)):
                gpu.uniform('varColor',light,light,light,1);gpu.uniform('nightRatio',night)
                close(pair(gpu)[1],(0.5,0.5,-100,1+light*(1-night)/divisor),
                      'translucent HDR surface retains normal, depth and local skylight',0.001)
        with ShaderTest(f'#define SCENE_SKY_DIVISOR {divisor}.0\n#define ENABLE_SCENE_SURFACE\n#define ENABLE_ATMOSPHERE\n'+source('scene_lighting')) as gpu:
            gpu.sampler('texture0',0);gpu.texture(0,(0,0,0,1))
            gpu.sampler('texture1',1);gpu.texture(1,((A+B/100)*0.5+0.5,0,0,1))
            gpu.sampler('texture2',2)
            gpu.matrix('inverseProjection',INVERSE);gpu.matrix('inverseView',IDENTITY)
            gpu.uniform('sceneParams',0.01,0,0,0);gpu.uniform('atmosphereEnabled',1)
            gpu.uniform('cameraPosition',0,0,0);gpu.uniform('fogColor',1,1,1,1)
            gpu.uniform('surfaceLight',0,0,1,1);gpu.uniform('surfaceLightColor',1,1,1)
            gpu.texture(2,(0.5,0.5,-100,1+1/divisor))
            assert min(gpu.draw()[:3])>0.05
            if divisor>1:
                # Worst partial coverage after MSAA resolve: one uncovered sample.
                samples=divisor//2;coverage=(samples-1)/samples
                gpu.texture(2,(0.5*coverage,0.5*coverage,-100*coverage,(1+1/divisor)*coverage))
                close(gpu.draw(),(0,0,0,1),'MSAA partial coverage cannot masquerade as full skylight')
    print('PASS: actual node MRT and MSAA tags retain geometry, local skylight and coverage')


if __name__=='__main__':
    surfaces()
    surface_metadata()
    water_fallback()
    for volumetric,separated,shadows in ((False,False,False),(True,False,False),
                                       (True,True,False),(True,False,True),(True,True,True)):
        atmosphere(volumetric,separated,shadows)
    tone_mapping()
