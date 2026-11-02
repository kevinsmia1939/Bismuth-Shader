#!/usr/bin/env python3
"""Actual separated fog transport/filter/composite GLSL; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
import os
import random
from pathlib import Path
from gl_shader_test import ShaderTest
from test_cloud_shadows import close

ROOT=Path(__file__).resolve().parents[1]/"client/shaders"
IDENTITY=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
A,B=1001/999,-2000/999
PROJECTION=[1,0,0,0,0,1,0,0,0,0,A,1,0,0,B,0]
INVERSE=[1,0,0,0,0,1,0,0,0,0,0,1/B,0,0,1,-A/B]

def source(name):
    return (ROOT/name/"opengl_fragment.glsl").read_text().replace(
        "CENTROID_ VARYING_ mediump vec2 varTexCoord;", "#define varTexCoord (gl_FragCoord.xy/64.0)")

def mrt(fragment):
    if int(os.environ.get("LUANTI_TEST_GLSL","330"))>=330:
        return "layout(location=1) out vec4 fogSecond;\n"+fragment.replace("gl_FragData[1]","fogSecond")
    return fragment.replace("gl_FragColor","gl_FragData[0]")

def attach_second(gpu,half=False):
    gpu.api("glActiveTexture",None,c.c_uint)(0x84C0)
    if half:
        gpu.api("glBindTexture",None,c.c_uint,c.c_uint)(0x0DE1,99)
        gpu.api("glTexImage2D",None,c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
            0x0DE1,0,0x881A,gpu.size,gpu.size,0,0x1908,0x1406,None)
    gpu.api("glBindTexture",None,c.c_uint,c.c_uint)(0x0DE1,98)
    gpu.api("glTexImage2D",None,c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
        0x0DE1,0,0x881A if half else 0x8814,gpu.size,gpu.size,0,0x1908,0x1406,None)
    gpu.api("glFramebufferTexture2D",None,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_int)(0x8D40,0x8CE1,0x0DE1,98,0)
    gpu.api("glDrawBuffers",None,c.c_int,c.POINTER(c.c_uint))(2,(c.c_uint*2)(0x8CE0,0x8CE1))
    assert gpu.api("glCheckFramebufferStatus",c.c_uint,c.c_uint)(0x8D40)==0x8CD5

def pair(gpu):
    first=gpu.draw()
    gpu.api("glReadBuffer",None,c.c_uint)(0x8CE1)
    second=(c.c_float*4)()
    gpu.api("glReadPixels",None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(32,32,1,1,0x1908,0x1406,second)
    gpu.api("glReadBuffer",None,c.c_uint)(0x8CE0)
    assert all(math.isfinite(v) for v in second),list(second)
    assert gpu.api("glGetError",c.c_uint)()==0
    return first,list(second)

def transport():
    fragment="#define ENABLE_ATMOSPHERE\n#define ENABLE_SCENE_SURFACE\n#define ENABLE_VOLUMETRIC_FOG\n#define ENABLE_FOG_DENOISING\n#define FOG_TRANSPORT_PASS\n"+source("scene_lighting")
    with ShaderTest(mrt(fragment)) as gpu:
        attach_second(gpu,half=True)
        gpu.sampler("texture1",1);gpu.texture(1,((A+B/100)*0.5+0.5,0,0,1))
        gpu.sampler("texture2",2);gpu.texture(2,(0.5,0.5,-100,2))
        gpu.matrix("inverseProjection",INVERSE);gpu.matrix("inverseView",IDENTITY)
        gpu.uniform("sceneParams",0.1,0,0,0);gpu.uniform("volumeParams",10,100,0,24)
        gpu.uniform("volumeLightDirection",0,1,0);gpu.uniform("volumeLightColor",0.8,0.6,0.4)
        gpu.uniform("fogColor",0.2,0.3,0.4,1);gpu.uniform("cameraPosition",0,-1000,0)
        gpu.uniform("cameraOffset",0,0,0);gpu.uniform("atmosphereEnabled",1);gpu.uniform("animationTimer",0)
        s,t=pair(gpu)
        cosine=(1/64)/math.sqrt(1+2*(1/64)**2)
        phase=(1-0.55**2)/(1+0.55**2-2*0.55*cosine)**1.5
        expected_t=[math.exp(-v) for v in (0.65,0.9,1.25)]
        expected_s=[(fog**2.2*0.65+sun*phase*0.25)*(1-v) for fog,sun,v in zip((0.2,0.3,0.4),(0.8,0.6,0.4),expected_t)]
        close(s[:3],expected_s,"separated RGBA16F physical fog scattering",0.001)
        close(t[:3],expected_t,"separated RGBA16F RGB Beer-Lambert transmission",0.001)
        assert 0<s[3]<10
        close(t[3:],(100*math.sqrt(1+2*(1/64)**2),),"RGBA16F actual geometry endpoint",0.1)
        gpu.uniform("atmosphereEnabled",0)
        close(pair(gpu)[0],(0,0,0,0),"bypassed fog has no scattering/history anchor")
        close(pair(gpu)[1],(1,1,1,-1),"bypassed fog retains scene light")
        print(f"PASS: actual MRT fog transport, independent RGB transmission and bypass identity; {gpu.renderer}")

def filter_setup(gpu):
    attach_second(gpu)
    for unit in range(4): gpu.sampler("texture"+str(unit),unit)
    gpu.matrix("fogInverseProjection",INVERSE);gpu.matrix("fogInverseView",IDENTITY)
    gpu.matrix("fogReprojection",PROJECTION);gpu.uniform("fogPreviousCamera",0,0,0)
    gpu.uniform("fogHistoryParams",0,0.9);gpu.uniform("texelSize0",1/64,1/64)

def filtering():
    with ShaderTest(mrt(source("fog_denoise"))) as gpu:
        filter_setup(gpu)
        checker=[v for y in range(64) for x in range(64) for v in ((0.08 if (x+y)%2==0 else 0.12),)*3+(100,)]
        gpu.texture(0,checker);gpu.texture(1,(0.7,0.6,0.5,500))
        gpu.texture(2,(float("nan"),)*4);gpu.texture(3,(float("nan"),)*4)
        s,t=pair(gpu)
        close(s,(0.1,0.1,0.1,100),"spatial filtering before initialized history")
        close(t,(0.7,0.6,0.5,500),"RGB transmission and guide metadata preserved")
        gpu.texture(2,(0.09,0.09,0.09,100));gpu.texture(3,(0.7,0.6,0.5,500))
        gpu.uniform("fogHistoryParams",1,0.9)
        expected=0.1-0.01*0.9*math.exp(-0.4)
        close(pair(gpu)[0],(expected,expected,expected,100),"bounded temporal fog history")
        for old_s,old_t in (((0.09,)*3+(100,),(0.7,0.6,0.5,5)),((0.09,)*3+(300,),(0.7,0.6,0.5,500)),
                             ((0.09,)*3+(100,),(0.7,0.6,0.5,0))):
            gpu.texture(2,old_s);gpu.texture(3,old_t)
            close(pair(gpu)[0],(0.1,0.1,0.1,100),"occlusion, mean-depth and sky disocclusion rejection")
        old_s=[v for y in range(64) for x in range(64) for v in ((1,1,1,0) if x<32 else (0.09,0.09,0.09,100))]
        old_t=[v for y in range(64) for x in range(64) for v in ((0.7,0.6,0.5,5) if x<32 else (0.7,0.6,0.5,500))]
        gpu.texture(2,old_s);gpu.texture(3,old_t)
        shifted=PROJECTION.copy();shifted[8]=-1/64;gpu.matrix("fogReprojection",shifted)
        expected=0.1-0.01*0.9*math.exp(-0.4-0.5*0.02)
        close(pair(gpu)[0],(expected,expected,expected,100),"partial bilinear footprint rejects foreground before filtering")
        gpu.matrix("fogReprojection",PROJECTION)
        gpu.uniform("fogHistoryParams",0,0.9)
        shaft=[v for y in range(64) for x in range(64) for v in ((0.1 if x<32 else 1.0),)*3+(100,)]
        gpu.texture(0,shaft)
        close(gpu.draw(31,32),(0.1,0.1,0.1,100),"bright shaft does not bleed into adjacent shadowed fog")
        close(gpu.draw(32,32),(1,1,1,100),"shaft edge retains its direct scattering")
        gpu.uniform("fogHistoryParams",1,0.9)
        gpu.texture(0,(1,0.5,0.25,100));gpu.texture(2,(0,0,0,100));gpu.texture(3,(0.7,0.6,0.5,500))
        close(pair(gpu)[0],(1,0.5,0.25,100),"lighting jump cannot retain old darkness")
        gpu.texture(0,(0,0,0,0));gpu.texture(1,(1,1,1,-1))
        gpu.texture(2,(float("nan"),)*4);gpu.texture(3,(float("nan"),)*4)
        close(pair(gpu)[0],(0,0,0,0),"current bypass never inherits fog")
        close(pair(gpu)[1],(1,1,1,-1),"current bypass preserves transmission")
        print(f"PASS: actual fog filter, NaN guards, RGB payloads, depth/sky rejection and lighting/bypass changes; {gpu.renderer}")

def variance():
    with ShaderTest(mrt(source("fog_denoise"))) as gpu:
        filter_setup(gpu)
        gpu.texture(2,(float("nan"),)*4);gpu.texture(3,(float("nan"),)*4)
        rng=random.Random(5342);raw_s=[];raw_t=[];out_s=[];out_t=[]
        for frame in range(40):
            s=[];t=[]
            for _ in range(64*64):
                ds=(rng.random()-0.5)*0.08;dt=(rng.random()-0.5)*0.04
                s.extend((0.1+ds,0.2+ds,0.3+ds,100));t.extend((0.7+dt,0.6+dt,0.5+dt,500))
            raw_s.append(s[(32+32*64)*4]);raw_t.append(t[(32+32*64)*4])
            gpu.texture(0,s);gpu.texture(1,t);gpu.uniform("fogHistoryParams",0 if frame==0 else 1,0.9)
            s,t=pair(gpu);out_s.append(s[0]);out_t.append(t[0])
            for unit,attachment in ((2,0),(3,1)):
                gpu.api("glReadBuffer",None,c.c_uint)(0x8CE0+attachment)
                gpu.api("glActiveTexture",None,c.c_uint)(0x84C0+unit)
                gpu.api("glCopyTexSubImage2D",None,c.c_uint,*([c.c_int]*7))(0x0DE1,0,0,0,0,0,64,64)
            gpu.api("glReadBuffer",None,c.c_uint)(0x8CE0)
        rmse=lambda values,target:math.sqrt(sum((v-target)**2 for v in values)/len(values))
        for raw,out,target in ((raw_s,out_s,0.1),(raw_t,out_t,0.7)):
            assert rmse(out,target)<rmse(raw,target)*0.4,("fog noise reduction",rmse(raw,target),rmse(out,target))
            assert abs(sum(out)/len(out)-target)<0.005
        print(f"PASS: 40-frame fog RMSE scattering {rmse(raw_s,0.1):.5f}->{rmse(out_s,0.1):.5f}, transmission {rmse(raw_t,0.7):.5f}->{rmse(out_t,0.7):.5f}; {gpu.renderer}")

def composite():
    with ShaderTest(source("fog_composite")) as gpu:
        for unit in range(4):gpu.sampler("texture"+str(unit),unit)
        gpu.matrix("inverseProjection",INVERSE);gpu.uniform("fogTextureSize",32,32);gpu.uniform("atmosphereEnabled",1)
        gpu.texture(0,(0.4,0.5,0.6,0.7))
        depth=lambda z:(A+B/z)*0.5+0.5
        zmap=[v for y in range(64) for x in range(64) for v in (depth(5 if x<32 else 100),0,0,1)]
        gpu.texture(3,zmap)
        scatter=[];trans=[]
        for y in range(32):
            for x in range(32):
                z=5 if x<16 else 100
                d=z*math.sqrt(1+(2*(x+0.5)/32-1)**2+(2*(y+0.5)/32-1)**2)
                scatter.extend((0,0,0,2) if x<16 else (0.1,0.05,0.02,40))
                trans.extend((1,1,1,d) if x<16 else (0.7,0.6,0.5,d))
        gpu.texture(1,scatter,width=32,height=32);gpu.texture(2,trans,width=32,height=32)
        close(gpu.draw(31,32),(0.4,0.5,0.6,0.7),"terrain silhouette rejects background fog scattering")
        expected=[(base**2.2*t+s)**(1/2.2) for base,t,s in zip((0.4,0.5,0.6),(0.7,0.6,0.5),(0.1,0.05,0.02))]+[0.7]
        close(gpu.draw(32,32),expected,"linear RGB fog composition and original alpha")
        gpu.uniform("atmosphereEnabled",0)
        gpu.texture(1,(float("nan"),)*4,width=32,height=32);gpu.texture(2,(float("nan"),)*4,width=32,height=32)
        close(gpu.draw(),(0.4,0.5,0.6,0.7),"underwater/disabled composite bypass before volume reads")
        print(f"PASS: actual fog composite, depth-aware upsampling, RGB transmission, sharp scene and alpha; {gpu.renderer}")

def surface_endpoint():
    with ShaderTest("#define ENABLE_SCENE_SURFACE\n"+source("fog_composite")) as gpu:
        for unit in range(5):gpu.sampler("texture"+str(unit),unit)
        gpu.matrix("inverseProjection",INVERSE);gpu.uniform("fogTextureSize",1,1);gpu.uniform("atmosphereEnabled",1)
        gpu.texture(0,(0.4,0.5,0.6,0.7));gpu.texture(1,(0.1,0.05,0.02,10),width=1,height=1)
        length=40*math.sqrt(1+2*(1/64)**2)
        gpu.texture(2,(0.7,0.6,0.5,length),width=1,height=1)
        gpu.texture(3,((A+B/100)*0.5+0.5,0,0,1))
        expected=[(base**2.2*t+s)**(1/2.2) for base,t,s in zip((0.4,0.5,0.6),(0.7,0.6,0.5),(0.1,0.05,0.02))]+[0.7]
        for z in (40,-40):
            gpu.texture(4,(0,0,z,1))
            close(gpu.draw(),expected,"water/node surface guide overrides background depth")
        gpu.texture(3,((A+B/10)*0.5+0.5,0,0,1))
        close(gpu.draw(),(0.4,0.5,0.6,0.7),"foreground object rejects stale farther node/water guide")
        print(f"PASS: fog water/node endpoint compatibility and closer-object rejection; {gpu.renderer}")

def taa_reactive():
    for clouds in (False,True):
        flags="#define ENABLE_FOG_DENOISING\n"+("#define ENABLE_VOLUMETRIC_CLOUDS\n" if clouds else "")
        with ShaderTest(flags+source("taa")) as gpu:
            for name in ("taaReprojection","taaSkyReprojection","taaInverseProjection"):gpu.matrix(name,IDENTITY)
            for unit in (0,1,2,5 if clouds else 4):gpu.sampler("texture"+str(unit),unit)
            if clouds:gpu.sampler("texture4",4);gpu.texture(4,(0,0,0,1))
            gpu.uniform("taaParams",0,0,1,0.95);gpu.uniform("texelSize0",1/64,1/64);gpu.uniform("taaWaterReactive",0)
            pixels=[v for y in range(64) for x in range(64) for v in ((0.2,)*3+(1,) if (x+y)%2==0 else (0.6,)*3+(1,))]
            gpu.texture(0,pixels);gpu.texture(1,(0.4,0.4,0.4,1));gpu.texture(2,(0.75,0,0,1))
            unit=5 if clouds else 4
            gpu.texture(unit,(1,1,1,500));clear=gpu.draw()
            gpu.texture(unit,(0,0,0,500));foggy=gpu.draw()
            assert 0.2<foggy[0]<clear[0],("fog avoids double accumulation in TAA",clouds,clear,foggy)
            close(foggy[3:],clear[3:],"fog reactive mask preserves history depth")
            gpu.texture(unit,(0,0,0,-1))
            close(gpu.draw(),foggy,"fog opacity reads RGB transmission rather than guide alpha")
            print(f"PASS: fog-aware final TAA with clouds={clouds}; {gpu.renderer}")

if __name__=="__main__":
    transport();filtering();variance();composite();surface_endpoint();taa_reactive()
