#!/usr/bin/env python3
"""Actual shared GGX/voxel GLSL and node composition; numeric pixels, no images/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
import ctypes as c
from pathlib import Path
from gl_shader_test import ShaderTest
from test_dynamic_lighting import atlas, cell, upload, sources, falloff, N

ROOT=Path(__file__).resolve().parents[1]/'client/shaders'
FLAGS='''#define ENABLE_MATERIAL_MAPS
#define ENABLE_VOXEL_LIGHTING
#define ENABLE_VOXEL_DYNAMIC_DIRECT
#define ENABLE_VOXEL_MATERIAL_SPECULAR
#define MAX_VOXEL_DYNAMIC_LIGHTS 8
#define MATERIAL_WATER_REFLECTIONS 0
#define MATERIAL_TYPE 0
#define TILE_MATERIAL_WAVING_LEAVES 6
#define TILE_MATERIAL_WAVING_PLANTS 7
'''
MATERIAL=(ROOT/'common/material_maps.glsl').read_text()
VOXEL=(ROOT/'common/voxel_lighting.glsl').read_text()
NODES=(ROOT/'nodes_shader/opengl_fragment.glsl').read_text()
start=NODES.rindex('\n#ifdef ENABLE_VOXEL_LIGHTING\n')
NODE_COMPOSE=NODES[start:NODES.index('\n\tfloat outputAlpha',start)]
MAIN='''
uniform vec3 testPosition, testNormal, testGeometric, testF0, testBase, testNative;
uniform vec3 cameraPosition, cameraOffset;
uniform float testMode, testRoughness, testEnabled, testNight;
void main() {
 vec2 uv=gl_FragCoord.xy/64.0;
 vec3 worldPosition=testPosition+vec3((gl_FragCoord.xy-vec2(32.5))*0.1,0);
 vec3 fNormal=readMaterialNormal(testNormal,worldPosition,uv);
 vec3 vNormal=testGeometric;
 vec3 view=cameraPosition-cameraOffset-worldPosition;
 if(testMode<1.5) {
  vec3 specular;
  vec3 diffuse=voxelDynamicIrradiance((worldPosition-voxelOrigin)/10.0,
   fNormal,vNormal,true,view,testRoughness,testF0,testEnabled>0.5,specular);
  gl_FragColor=vec4(testMode<0.5 ? diffuse : specular,1);
 } else {
  vec4 base=vec4(testBase,1),col=vec4(testNative,0.4);
  vec3 materialData=readMaterialORM(uv,0.8),materialSun=vec3(0),materialPoint=vec3(0);
  bool authoredMaterial=materialMapFlags.x>0.5 || materialMapFlags.y>0.5;
  vec4 fogColor=vec4(0);
  vec3 dayLight=vec3(0);
  float nightRatio=testNight;
  float nativeSky=1.0;
'''+NODE_COMPOSE+'''
  gl_FragColor=col;
 }
}
'''

def close(actual,expected,label,tol=0.00002):
    assert all(abs(a-b)<=tol for a,b in zip(actual,expected)),(label,actual,expected)

def set_night(gpu,value):
    # Current emissive variants eliminate the native-light replacement ratio.
    if gpu.api('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)(gpu.program,b'testNight')>=0:
        gpu.uniform('testNight',value)

def setup(gpu):
    for name,slot in (('texture2',2),('texture4',4),('texture5',5)):gpu.sampler(name,slot)
    gpu.uniform('voxelParams',1,1,0,N);gpu.uniform('voxelOrigin',0,0,0)
    gpu.uniform('testPosition',40,40,80);gpu.uniform('testNormal',0,0,-1)
    gpu.uniform('testGeometric',0,0,-1);gpu.uniform('cameraPosition',40,40,20)
    gpu.uniform('cameraOffset',0,0,0);gpu.uniform('testF0',0.04,0.04,0.04)
    gpu.uniform('testRoughness',0.5);gpu.uniform('testMode',1);gpu.uniform('testEnabled',1)
    gpu.uniform('testBase',0.8,0.4,0.2);gpu.uniform('testNative',0,0,0);set_night(gpu,0)
    gpu.uniform('materialMapFlags',0,1,1)
    gpu.texture(4,(0.5,0.5,1,1));gpu.texture(5,(1,0.5,0,1))
    upload(gpu,atlas());sources(gpu,[((4,4,2),(2,2,2))])

def response():
    with ShaderTest(FLAGS+MATERIAL+VOXEL+MAIN) as gpu:
        setup(gpu)
        irradiance=2*falloff(6)
        expected=irradiance*0.04/(4*math.pi*0.5**4)
        close(gpu.draw(),(expected,expected,expected,1),'dielectric lamp GGX at normal incidence')
        f0=(0.8,0.2,0.05);gpu.uniform('testF0',*f0)
        close(gpu.draw(),tuple(irradiance*v/(4*math.pi*0.5**4) for v in f0)+(1,),
              'conductor RGB reflectance under white lamp')
        gpu.uniform('testRoughness',0.8)
        close(gpu.draw(),tuple(irradiance*v/(4*math.pi*0.8**4) for v in f0)+(1,),
              'roughness controls local highlight')
        gpu.uniform('testRoughness',0.5);gpu.uniform('testMode',0)
        close(gpu.draw(),(irradiance,irradiance,irradiance,1),'diffuse shares incident radiance')
        gpu.uniform('testMode',1);gpu.uniform('cameraPosition',76,40,32)
        moved=gpu.draw()
        assert 0<moved[0]<irradiance*f0[0]/(4*math.pi*0.5**4),'view-dependent highlight'
        # Reciprocity removes exactly one incident cosine, catching double NL.
        sources(gpu,[((4,8.8,4.4),(2,2,2))]);first=gpu.draw()
        sources(gpu,[((7.6,4,3.2),(2,2,2))]);gpu.uniform('cameraPosition',40,88,44)
        second=gpu.draw()
        close(tuple(v/0.6 for v in first[:3]),tuple(v/0.8 for v in second[:3]),
              'local BRDF reciprocity, one incident cosine',0.000001)
        print('PASS: local dielectric/conductor GGX, roughness, view response, shared diffuse and reciprocity;',gpu.renderer)

def filtered():
    with ShaderTest(FLAGS+MATERIAL+VOXEL+MAIN) as gpu:
        setup(gpu);gpu.uniform('testF0',0.8,0.2,0.05)
        base=gpu.draw();data=atlas()
        for y in range(N):
            for x in range(N):cell(data,14,13,x,y,5,(0.8,0.5,0.25,1))
        upload(gpu,data)
        close(gpu.draw(),tuple(v*t for v,t in zip(base[:3],(0.8,0.5,0.25)))+(1,),
              'colored transmission filters specular source spectrum')
        for y in range(N):
            for x in range(N):cell(data,14,13,x,y,5,(1,1,1,0))
        upload(gpu,data)
        close(gpu.draw(),(0,0,0,1),'opaque wall blocks local highlight')
        upload(gpu,atlas());sources(gpu,[((4,4,3),(2,2,2))])
        close(gpu.draw(),tuple(v*falloff(5)/falloff(6) for v in base[:3])+(1,),
              'moving source updates highlight without field upload')
        sources(gpu,[((4,4,3),(0,2,0))]);green=gpu.draw()
        assert green[0]==0 and green[1]>0 and green[2]==0,'current source hue'
        sources(gpu,[]);close(gpu.draw(),(0,0,0,1),'removal clears specular')
        lights=[((4,4,2+i*0.125),(0.25+i*0.1,0.5,1-i*0.1)) for i in range(8)]
        sources(gpu,lights,count=99)
        expected=tuple(sum(color[channel]*falloff(8-position[2]) for position,color in lights)*f0/
                       (4*math.pi*0.5**4) for channel,f0 in enumerate((0.8,0.2,0.05)))+(1,)
        close(gpu.draw(),expected,'all eight local GGX contributions share the bounded source loop')
        print('PASS: spectrum filtering, opaque visibility, current positions/colors and removal;',gpu.renderer)

def bounds():
    with ShaderTest(FLAGS+MATERIAL+VOXEL+MAIN) as gpu:
        setup(gpu);gpu.uniform('testRoughness',0)
        result=gpu.draw()
        assert all(0<=v<=32*2*falloff(6)+0.00001 for v in result[:3]),result
        gpu.uniform('testRoughness',0.5);gpu.uniform('cameraPosition',40,40,80)
        close(gpu.draw(),(0,0,0,1),'zero view remains finite')
        gpu.uniform('cameraPosition',40,40,140)
        close(gpu.draw(),(0,0,0,1),'below-surface view')
        gpu.uniform('cameraPosition',40,40,20);gpu.uniform('testEnabled',0)
        close(gpu.draw(),(0,0,0,1),'disabled specular preserves zero output')
        gpu.uniform('testEnabled',1);sources(gpu,[((8,4,9),(2,2,2))])
        gpu.uniform('testNormal',0.995037,0,-0.0995037)
        close(gpu.draw(),(0,0,0,1),'mapped normal cannot see through the back of its geometric face')
        gpu.uniform('testMode',0)
        close(gpu.draw(),(0,0,0,1),'same geometric visibility protects diffuse')
        gpu.uniform('testMode',1);sources(gpu,[]);gpu.texture(2,(float('nan'),)*4)
        close(gpu.draw(),(0,0,0,1),'no-source guard initializes specular before texture access')
        sources(gpu,[((4,4,2),(2,2,2))]);gpu.uniform('voxelParams',0,1,0,N)
        close(gpu.draw(),(0,0,0,1),'unbound atlas guard')
        gpu.uniform('voxelParams',1,0,0,N)
        close(gpu.draw(),(0,0,0,1),'zero-strength guard')
        print('PASS: finite highlight bound, view/geometry hemisphere, disabled and missing-data guards;',gpu.renderer)

def node_composition(emissive=False):
    flags=FLAGS+('#define MATERIAL_EMISSIVE\n' if emissive else '')
    with ShaderTest(flags+MATERIAL+VOXEL+MAIN) as gpu:
        setup(gpu);gpu.uniform('testMode',2)
        base=(0.8,0.4,0.2);linear=tuple(v**2.2 for v in base)
        gpu.texture(5,(1,0.5,1,1))
        irradiance=2*falloff(6)
        expected=tuple((irradiance*v/(4*math.pi*0.5**4))**(1/2.2) for v in linear)+(0.4,)
        if not emissive:
            close(gpu.draw(),expected,'actual node composition keeps metallic local specular')
            stale=atlas()
            for z in range(N):
                for y in range(N):
                    for x in range(N):
                        for group in range(12):
                            cell(stale,14,group,x,y,z,(0,0,0,0))
            upload(gpu,stale)
            close(gpu.draw(),expected,'metallic lamp reflection survives stale solid probe metadata')
            upload(gpu,atlas())
            gpu.texture(5,(0,0.5,1,1))
            close(gpu.draw(),expected,'ORM occlusion does not darken direct specular')
            gpu.uniform('materialMapFlags',1,1,1);gpu.texture(4,(0.8,0.5,0.9,1))
            tilted=gpu.draw()
            assert 0<tilted[0]<expected[0],'authored mapped normal controls lamp highlight'
            gpu.uniform('materialMapFlags',0,0,1)
            fallback=(irradiance*(linear[0]+0.04/(4*math.pi*0.8**4)))**(1/2.2)
            close(gpu.draw()[:1],(fallback,),'unmapped rough dielectric fallback')
            gpu.uniform('materialMapFlags',0,1,1);gpu.texture(5,(1,0.5,1,1))
            sources(gpu,[((1,4,2),(2,2,2))])
            gpu.uniform('testPosition',10,40,80);gpu.uniform('cameraPosition',10,40,20)
            close(gpu.draw(),tuple(v*0.5**(1/2.2) for v in expected[:3])+(0.4,),
                  'local specular shares volume-edge coverage')
            gpu.uniform('voxelParams',1,2,0,N)
            close(gpu.draw(),expected,'local specular shares direct strength')
            gpu.uniform('voxelParams',1,0,0,N)
            close(gpu.draw(),(0,0,0,0.4),'node material zero-strength path')
            gpu.uniform('voxelParams',1,1,0,N);sources(gpu,[((4,4,2),(2,2,2))])
            gpu.uniform('voxelOrigin',10000,-2000,3000);gpu.uniform('testPosition',10040,-1960,3080)
            gpu.uniform('cameraPosition',10040,-1960,3020)
            close(gpu.draw(),expected,'node camera-origin rebase')
            gpu.uniform('cameraOffset',10000,-2000,3000);gpu.uniform('voxelOrigin',0,0,0)
            gpu.uniform('testPosition',40,40,80)
            close(gpu.draw(),expected,'camera-relative positions and absolute camera convention')
        else:
            sources(gpu,[]);gpu.uniform('testNative',0.25,0.1,0.05);set_night(gpu,1)
            close(gpu.draw(),(0.25,0.1,0.05,0.4),'metallic emissive node keeps authored lighting without lamps')
            sources(gpu,[((4,4,2),(2,2,2))])
            lit=gpu.draw()
            assert all(lit[i]>v for i,v in enumerate((0.25,0.1,0.05))),'emission and local specular coexist'
        print('PASS: actual node material composition, mapped/unmapped response, alpha and emission='+str(emissive)+';',gpu.renderer)

def directional_spectrum():
    begin=NODES.index('materialSun = materialSpecular(')
    expression=NODES[begin:NODES.index(';',begin)+1]
    begin=NODES.index('surfaceSunVisibility = clamp(')
    visibility=NODES[begin:NODES.index(';',begin)+1]
    main='''
uniform float testShadow;
uniform vec3 testShadowColor;
void main() {
 vec3 materialSun,fNormal=vec3(0,0,1),surfaceView=vec3(0,0,1),surfaceSunVisibility;
 vec4 surfaceLight=vec4(0,0,1,1);
 vec3 surfaceLightColor=vec3(1);
 vec3 materialData=vec3(1,0.5,0),f0=vec3(0.04),dayLight=vec3(1),shadow_color=testShadowColor;
 float adjusted_night_ratio=0.0,shadow_int=testShadow,f_adj_shadow_strength=1.0;
 float naturalShare=1.0;
'''+visibility+expression+'''
 gl_FragColor=vec4(materialSun,1);
}'''
    with ShaderTest('#define ENABLE_MATERIAL_MAPS\n'+MATERIAL+main) as gpu:
        peak=0.04/(4*math.pi*0.5**4)
        gpu.uniform('testShadow',0);gpu.uniform('testShadowColor',0,0,0)
        close(gpu.draw(),(peak,peak,peak,1),'unshadowed directional GGX')
        gpu.uniform('testShadow',1)
        close(gpu.draw(),(0,0,0,1),'opaque directional shadow')
        gpu.uniform('testShadowColor',0,0.5,0)
        close(gpu.draw(),(0,peak*0.5,0,1),'actual directional material highlight retains colored-glass visibility')
        gpu.uniform('testShadow',0.5);gpu.uniform('testShadowColor',0.25,0.5,0.75)
        close(gpu.draw(),tuple(peak*v for v in (0.625,0.75,0.875))+(1,),
              'fractional colored directional visibility')
        print('PASS: actual directional GGX expression with clear, opaque and colored/fractional visibility;',gpu.renderer)

if __name__=='__main__':
    response();filtered();bounds();node_composition();node_composition(True);directional_spectrum()
