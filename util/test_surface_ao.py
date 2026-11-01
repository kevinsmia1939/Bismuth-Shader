#!/usr/bin/env python3
"""Actual SSAO and volume compositing GLSL, numeric pixels without images/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
import ctypes as c
from pathlib import Path
from gl_shader_test import ShaderTest
from test_water_volume import WAVES, VOLUME, WATER, cells
from test_fog_denoise import mrt,attach_second,pair

ROOT=Path(__file__).resolve().parents[1]/"client/shaders"
A,B=1001/999,-2000/999
INVERSE=[1,0,0,0,0,1,0,0,0,0,0,1/B,0,0,1,-A/B]
BASE=(0.4,0.5,0.6,0.37)

def source(name):
    return (ROOT/name/"opengl_fragment.glsl").read_text().replace(
        "CENTROID_ VARYING_ mediump vec2 varTexCoord;","#define varTexCoord (gl_FragCoord.xy/64.0)")

def close(actual,expected,label,tolerance=3e-4):
    assert max(abs(a-b) for a,b in zip(actual,expected))<tolerance,(label,actual,expected)

def depth(z):return (A+B/z)*0.5+0.5

def setup_ao(gpu):
    gpu.sampler("texture0",0);gpu.sampler("texture1",1)
    gpu.texture(0,BASE);gpu.matrix("inverseProjection",INVERSE)
    gpu.uniform("texelSize0",1/64,1/64);gpu.uniform("projectionScale",1,1);gpu.uniform("ssaoParams",5,1)

def corner():
    return [v for y in range(64) for x in range(64)
            for v in (depth(10 if 31<=x<=33 and 31<=y<=33 else 8),0,0,1)]

def occlusion():
    with ShaderTest(source("ssao")) as gpu:
        setup_ao(gpu);gpu.texture(1,(depth(10),0,0,1))
        close(gpu.draw(),BASE,"coplanar surfaces stay unchanged")
        gpu.texture(1,corner());shaded=gpu.draw()
        visibility=(shaded[0]/BASE[0])**2.2
        assert 0.249<=visibility<0.9,("corner occlusion",visibility,shaded)
        close(shaded[3:],BASE[3:],"occlusion preserves scene alpha")
        gpu.uniform("ssaoParams",5,0)
        close(gpu.draw(),BASE,"zero strength preserves color")
        gpu.uniform("ssaoParams",5,1);gpu.texture(1,(1,0,0,1))
        close(gpu.draw(),BASE,"sky stays unchanged")
        print(f"PASS: actual SSAO flat/sky/zero guards, corner attenuation and alpha; visibility={visibility:.6f}; {gpu.renderer}")
        return shaded,visibility

def water_guard(shaded):
    with ShaderTest("#define ENABLE_SCENE_SURFACE\n"+source("ssao")) as gpu:
        setup_ao(gpu);gpu.texture(1,corner());gpu.sampler("texture2",2);gpu.uniform("ssaoSurfaceReady",1)
        gpu.texture(2,(0,0,5,1))
        close(gpu.draw(),BASE,"refracted/scattered water color is not shaded as the floor behind it")
        gpu.texture(2,(0,0,0.5,1))
        close(gpu.draw(),BASE,"water near the camera retains its optical shading")
        for marker in ((0,0,-5,1),(0,0,20,1),(0,0,5,0.5),(0,0,0,0)):
            gpu.texture(2,marker)
            close(gpu.draw(),shaded,"solid/nearer-object/invalid metadata retains surface SSAO")
        gpu.uniform("ssaoSurfaceReady",0);gpu.texture(2,(float("nan"),)*4)
        close(gpu.draw(),shaded,"unbound surface guide is never sampled")
        gpu.uniform("ssaoSurfaceReady",1);gpu.texture(1,(1,0,0,1))
        close(gpu.draw(),BASE,"sky bypass precedes missing surface metadata")
        gpu.texture(1,corner());gpu.uniform("ssaoParams",5,0)
        close(gpu.draw(),BASE,"zero strength bypass precedes missing surface metadata")
        print(f"PASS: actual water-surface guard, closer-object rejection, binding/alpha guards and fallback; {gpu.renderer}")

def surface_metadata():
    nodes=(ROOT/"nodes_shader/opengl_fragment.glsl").read_text()
    start=nodes.index("vec2 encodeSurfaceNormal")
    encoder=nodes[start:nodes.index("\n}",start)+2]
    block=nodes[nodes.rindex("#ifdef ENABLE_SCENE_SURFACE"):nodes.rindex("\n}")]
    for emissive in (False,True):
        for water in (False,True):
            flags="#define ENABLE_SCENE_SURFACE\n#define MATERIAL_WATER_REFLECTIONS "+str(int(water))+"\n"
            if emissive:flags+="#define MATERIAL_EMISSIVE\n"
            fragment=flags+encoder+"\nvoid main(){\nmat4 sceneView=mat4(1);vec3 fNormal=vec3(0,0,1),eyeVec=vec3(0,0,-10);gl_FragColor=vec4(0.8,0.4,0.2,0.5);\n"+block+"\n}"
            with ShaderTest(mrt(fragment)) as gpu:
                attach_second(gpu,half=True)
                # Global alpha blending applies separately to each MRT. Guides
                # must keep alpha one, including for emissive/translucent nodes.
                gpu.api("glClearColor",None,*([c.c_float]*4))(0.25,0.25,0.25,0.25)
                gpu.api("glClear",None,c.c_uint)(0x4000)
                gpu.api("glEnable",None,c.c_uint)(0x0BE2)
                gpu.api("glBlendFunc",None,c.c_uint,c.c_uint)(0x0302,0x0303)
                color,guide=pair(gpu)
                close(guide,(0.5,0.5,10 if water else -10,1),"actual node MRT guide survives alpha blending",0.002)
                close(color,(0.525,0.325,0.225,0.375),"metadata preserves scene alpha blending",0.002)
    print("PASS: actual node normal/depth/validity through RGBA16F MRT alpha blending, including emissive materials")

def clouds_then_fog(shaded,visibility):
    cloud_t=0.6;cloud_s=(0.2,0.1,0.05);fog_t=(0.7,0.6,0.5);fog_s=(0.03,0.04,0.05)
    with ShaderTest(source("cloud_composite")) as gpu:
        for unit in range(3):gpu.sampler("texture"+str(unit),unit)
        gpu.matrix("inverseProjection",INVERSE);gpu.uniform("cloudTextureSize",1,1)
        gpu.texture(0,shaded);gpu.texture(1,(depth(10),0,0,1));gpu.texture(2,cloud_s+(cloud_t,),width=1,height=1)
        cloudy=gpu.draw()
        expected=[(v**2.2*cloud_t+s)**(1/2.2) for v,s in zip(shaded,cloud_s)]+[BASE[3]]
        close(cloudy,expected,"cloud scattering added after SSAO")
        gpu.texture(2,(0,0,0,1),width=1,height=1)
        close(gpu.draw(),shaded,"empty clouds preserve surface shading")
    with ShaderTest(source("fog_composite")) as gpu:
        for unit in range(4):gpu.sampler("texture"+str(unit),unit)
        gpu.matrix("inverseProjection",INVERSE);gpu.uniform("fogTextureSize",1,1);gpu.uniform("atmosphereEnabled",1)
        gpu.texture(0,cloudy);gpu.texture(1,fog_s+(3,),width=1,height=1)
        gpu.texture(2,fog_t+(10*math.sqrt(1+2*(1/64)**2),),width=1,height=1);gpu.texture(3,(depth(10),0,0,1))
        result=gpu.draw()
        expected=[((base**2.2*visibility*cloud_t+cs)*ft+fs)**(1/2.2)
                  for base,cs,ft,fs in zip(BASE,cloud_s,fog_t,fog_s)]+[BASE[3]]
        close(result,expected,"only surface radiance inherits SSAO; cloud/fog source terms remain independent")
        old=[(((base**2.2*cloud_t+cs)*ft+fs)*visibility)**(1/2.2)
             for base,cs,ft,fs in zip(BASE,cloud_s,fog_t,fog_s)]
        assert max(abs(a-b) for a,b in zip(result,old))>0.03,("volume-radiance regression control",result,old)
        gpu.uniform("atmosphereEnabled",0)
        gpu.texture(1,(float("nan"),)*4,width=1,height=1);gpu.texture(2,(float("nan"),)*4,width=1,height=1)
        close(gpu.draw(),cloudy,"fog bypass retains cloud/surface radiance")
        print(f"PASS: actual SSAO->cloud->fog linear transport, independent scattering, alpha and bypass; {gpu.renderer}")

def underwater(shaded):
    fragment="#define ENABLE_WATER_VOLUME\n"+WAVES+VOLUME+source("water_volume")
    with ShaderTest(fragment) as gpu:
        for unit in (0,1,6):gpu.sampler("texture"+str(unit),unit)
        gpu.texture(0,shaded);gpu.texture(1,(depth(10),0,0,1));gpu.matrix("inverseProjection",INVERSE)
        view=[1,0,0,0,0,1,0,0,0,0,1,0,20,20,20,1];gpu.matrix("inverseView",view)
        gpu.uniform("waterVolumeOrigin",0,0,0);gpu.uniform("waterAbsoluteOrigin",0,0,0)
        gpu.uniform("waterVolumeParams",1,8,200,0);gpu.uniform("waterMediumParams",1,1,0,0)
        gpu.uniform("waterWaves",0,20,0);gpu.uniform("waterScatterColor",0.1,0.4,0.8)
        gpu.texture(6,cells(8,lambda x,y,z:WATER),width=16,height=64)
        distance=10*math.sqrt(1+2*(1/64)**2)
        trans=[math.exp(-sigma*distance*0.98/10) for sigma in (0.32,0.085,0.035)]
        expected=[(base**2.2*t+scatter**2.2*(1-t))**(1/2.2)
                  for base,t,scatter in zip(shaded,trans,(0.1,0.4,0.8))]+[BASE[3]]
        close(gpu.draw(),expected,"actual underwater scattering added after surface SSAO")
        gpu.uniform("waterMediumParams",0,1,0,0)
        close(gpu.draw(),shaded,"inactive medium preserves surface shading")
        print(f"PASS: actual loaded-water absorption/scattering after surface SSAO; {gpu.renderer}")

if __name__=="__main__":
    shaded,visibility=occlusion();water_guard(shaded);surface_metadata();clouds_then_fog(shaded,visibility);underwater(shaded)
