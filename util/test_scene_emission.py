#!/usr/bin/env python3
"""Actual emissive coverage and SSAO GLSL, R8 MRT blending/MSAA; no images/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
import os
from pathlib import Path
from gl_shader_test import ShaderTest
from test_surface_ao import BASE, close, corner, setup_ao, source

ROOT=Path(__file__).resolve().parents[1]/"client/shaders"
EMISSION=(ROOT/"common/scene_emission.glsl").read_text()

def api_int(gpu,name):
    value=c.c_int();gpu.api("glGetIntegerv",None,c.c_uint,c.POINTER(c.c_int))(name,c.byref(value));return value.value

def outputs(fragment,surface):
    slot=2 if surface else 1
    if int(os.environ.get("LUANTI_TEST_GLSL","330"))>=330:
        head=f"layout(location={slot}) out vec4 emissionOutput;\n"
        if surface:head+="layout(location=1) out vec4 guideOutput;\n"
        return head+fragment.replace("gl_FragData[SCENE_EMISSION_ATTACHMENT]","emissionOutput").replace("gl_FragData[1]","guideOutput")
    return fragment.replace("gl_FragColor","gl_FragData[0]")

def attach(gpu,surface):
    formats=(0x881A,0x881A,0x8229) if surface else (0x881A,0x8229)
    for slot,fmt in enumerate(formats):
        texture=99-slot
        gpu.api("glActiveTexture",None,c.c_uint)(0x84C0)
        gpu.api("glBindTexture",None,c.c_uint,c.c_uint)(0x0DE1,texture)
        gpu.api("glTexImage2D",None,c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0x0DE1,0,fmt,64,64,0,0x1903 if fmt==0x8229 else 0x1908,0x1406,None)
        gpu.api("glFramebufferTexture2D",None,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_int)(0x8D40,0x8CE0+slot,0x0DE1,texture,0)
    draw_buffers(gpu,len(formats))
    assert gpu.api("glCheckFramebufferStatus",c.c_uint,c.c_uint)(0x8D40)==0x8CD5
    return formats

def draw_buffers(gpu,count):
    gpu.api("glDrawBuffers",None,c.c_int,c.POINTER(c.c_uint))(count,(c.c_uint*count)(*(0x8CE0+i for i in range(count))))

def read(gpu,slot):
    gpu.api("glReadBuffer",None,c.c_uint)(0x8CE0+slot)
    result=(c.c_float*4)()
    gpu.api("glReadPixels",None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(32,32,1,1,0x1908,0x1406,result)
    gpu.api("glReadBuffer",None,c.c_uint)(0x8CE0)
    assert all(math.isfinite(v) for v in result)
    assert gpu.api("glGetError",c.c_uint)()==0
    return list(result)

def clear_mask(gpu,surface,value):
    # Same alias-target sequence as Draw3D: clear only the mask, restore the
    # main MRT without clearing scene color/depth. This also models frame reset.
    original=api_int(gpu,0x8CA6);alias=c.c_uint()
    gpu.api("glGenFramebuffers",None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(alias))
    gpu.api("glBindFramebuffer",None,c.c_uint,c.c_uint)(0x8D40,alias.value)
    slot=2 if surface else 1
    gpu.api("glFramebufferTexture2D",None,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_int)(0x8D40,0x8CE0,0x0DE1,99-slot,0)
    draw_buffers(gpu,1)
    gpu.api("glClearColor",None,*([c.c_float]*4))(value,0,0,0)
    gpu.api("glClear",None,c.c_uint)(0x4000)
    gpu.api("glBindFramebuffer",None,c.c_uint,c.c_uint)(0x8D40,original)
    gpu.api("glDeleteFramebuffers",None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(alias))

def producer(surface,emissive):
    flags=f"#define ENABLE_SCENE_EMISSION_MASK\n#define SCENE_EMISSION_ATTACHMENT {2 if surface else 1}\n"
    if emissive:flags+="#define MATERIAL_EMISSIVE\n"
    nodes=(ROOT/"nodes_shader/opengl_fragment.glsl").read_text()
    start=nodes.index("vec2 encodeSurfaceNormal")
    encoder=nodes[start:nodes.index("\n}",start)+2]
    block=nodes[nodes.rindex("#ifdef ENABLE_SCENE_SURFACE"):nodes.rindex("\n}")]
    if surface:flags+="#define ENABLE_SCENE_SURFACE\n#define MATERIAL_WATER_REFLECTIONS 0\n"
    return outputs(flags+EMISSION+encoder+"\nuniform float testAlpha; void main(){mat4 sceneView=mat4(1);vec3 fNormal=vec3(0,0,1),eyeVec=vec3(0,0,-10);vec4 col=vec4(0.8,0.4,0.2,testAlpha);gl_FragColor=col;\n"+block+"\n}",surface)

def blending():
    for surface in (False,True):
        for emissive,alpha,background in ((True,1,0),(True,0.5,0),(False,0.25,1),(False,1,1)):
            with ShaderTest(producer(surface,emissive)) as gpu:
                attach(gpu,surface)
                gpu.api("glClearColor",None,*([c.c_float]*4))(0.25,0.25,0.25,0.25)
                gpu.api("glClear",None,c.c_uint)(0x4000)
                clear_mask(gpu,surface,background)
                close(read(gpu,0),(0.25,)*4,"mask-only clear preserves scene")
                gpu.uniform("testAlpha",alpha)
                gpu.api("glEnable",None,c.c_uint)(0x0BE2);gpu.api("glBlendFunc",None,c.c_uint,c.c_uint)(0x0302,0x0303)
                color=gpu.draw()
                mask=read(gpu,2 if surface else 1)[0]
                expected=int(emissive)*alpha+background*(1-alpha)
                assert abs(mask-expected)<0.006,("R8 emissive coverage blending",surface,emissive,alpha,mask,expected)
                if surface:close(read(gpu,1),(0.5,0.5,-10,1),"depth/normal validity stays one",0.002)
                close(color,tuple(v*alpha+0.25*(1-alpha) for v in (0.8,0.4,0.2,alpha)),"scene alpha independent of emission",0.002)
                gpu.api("glDisable",None,c.c_uint)(0x0BE2)
                clear_mask(gpu,surface,0)
                close(read(gpu,2 if surface else 1)[:1],(0,),"next frame/source removal clears stale mask")
                close(read(gpu,0),color,"frame mask reset does not erase scene")
    print("PASS: actual node emission, separate R8 MRT, transparency, opaque clearing, guide preservation and frame reset")

def consumer():
    for surface in (False,True):
        flags="#define ENABLE_SCENE_EMISSION_MASK\n"+("#define ENABLE_SCENE_SURFACE\n" if surface else "")
        with ShaderTest(flags+source("ssao")) as gpu:
            setup_ao(gpu);gpu.texture(1,corner())
            slot=3 if surface else 2
            gpu.sampler("texture"+str(slot),slot)
            if surface:
                gpu.sampler("texture2",2);gpu.texture(2,(float("nan"),)*4);gpu.uniform("ssaoSurfaceReady",0)
            gpu.uniform("ssaoEmissionReady",1)
            for coverage in (0,0.5,1):
                gpu.texture(slot,(coverage,0,0,1))
                byte=round(coverage*255)
                pixels=(c.c_ubyte*(64*64))(*([byte]*(64*64)))
                gpu.api("glTexImage2D",None,c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
                    0x0DE1,0,0x8229,64,64,0,0x1903,0x1401,pixels)
                coverage=byte/255
                visibility=0.25+(1-0.25)*coverage
                expected=[v*visibility**(1/2.2) for v in BASE[:3]]+[BASE[3]]
                close(gpu.draw(),expected,"emissive faces and partial coverage preserve authored brightness")
            gpu.uniform("ssaoEmissionReady",0);gpu.texture(slot,(float("nan"),)*4)
            expected=[v*0.25**(1/2.2) for v in BASE[:3]]+[BASE[3]]
            close(gpu.draw(),expected,"unbound emission mask retains ordinary AO")
            gpu.uniform("ssaoEmissionReady",1);gpu.uniform("ssaoParams",5,0)
            close(gpu.draw(),BASE,"zero strength precedes mask reads")
            gpu.uniform("ssaoParams",5,1);gpu.texture(1,(1,0,0,1))
            close(gpu.draw(),BASE,"sky precedes mask reads")
            print(f"PASS: actual SSAO emission receiver with surface={surface}, coverage/alpha and unavailable guards; {gpu.renderer}")

def msaa():
    with ShaderTest(producer(True,True)) as gpu:
        formats=attach(gpu,True);target=api_int(gpu,0x8CA6);multi=c.c_uint()
        gpu.api("glGenFramebuffers",None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(multi))
        gpu.api("glBindFramebuffer",None,c.c_uint,c.c_uint)(0x8D40,multi.value)
        buffers=(c.c_uint*3)();gpu.api("glGenRenderbuffers",None,c.c_int,c.POINTER(c.c_uint))(3,buffers)
        for slot,fmt in enumerate(formats):
            gpu.api("glBindRenderbuffer",None,c.c_uint,c.c_uint)(0x8D41,buffers[slot])
            gpu.api("glRenderbufferStorageMultisample",None,c.c_uint,c.c_int,c.c_uint,c.c_int,c.c_int)(0x8D41,4,fmt,64,64)
            gpu.api("glFramebufferRenderbuffer",None,c.c_uint,c.c_uint,c.c_uint,c.c_uint)(0x8D40,0x8CE0+slot,0x8D41,buffers[slot])
        draw_buffers(gpu,3);assert gpu.api("glCheckFramebufferStatus",c.c_uint,c.c_uint)(0x8D40)==0x8CD5
        gpu.api("glClearColor",None,*([c.c_float]*4))(0,0,0,0);gpu.api("glClear",None,c.c_uint)(0x4000)
        gpu.uniform("testAlpha",1);gpu.api("glEnable",None,c.c_uint)(0x80A0)
        gpu.api("glSampleCoverage",None,c.c_float,c.c_ubyte)(0.5,0)
        if gpu.core_shader:gpu.api("glDrawArrays",None,c.c_uint,c.c_int,c.c_int)(4,0,3)
        else:
            gpu.api("glBegin",None,c.c_uint)(7)
            for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)):gpu.api("glVertex2f",None,c.c_float,c.c_float)(x,y)
            gpu.api("glEnd",None)()
        gpu.api("glDisable",None,c.c_uint)(0x80A0)
        for slot in range(3):
            gpu.api("glBindFramebuffer",None,c.c_uint,c.c_uint)(0x8CA8,multi.value)
            gpu.api("glReadBuffer",None,c.c_uint)(0x8CE0+slot)
            gpu.api("glBindFramebuffer",None,c.c_uint,c.c_uint)(0x8CA9,target)
            gpu.api("glDrawBuffer",None,c.c_uint)(0x8CE0+slot)
            gpu.api("glBlitFramebuffer",None,*([c.c_int]*8),c.c_uint,c.c_uint)(0,0,64,64,0,0,64,64,0x4000,0x2600)
        gpu.api("glBindFramebuffer",None,c.c_uint,c.c_uint)(0x8D40,target);draw_buffers(gpu,3)
        close(read(gpu,2)[:1],(0.5,),"MSAA independently resolves emissive coverage",0.006)
        close(read(gpu,1),(0.25,0.25,-5,0.5),"MSAA guide attachment remains independent",0.002)
        close(read(gpu,0),(0.4,0.2,0.1,0.5),"MSAA scene color is not broadcast into the mask",0.002)
        gpu.api("glDeleteRenderbuffers",None,c.c_int,c.POINTER(c.c_uint))(3,buffers)
        gpu.api("glDeleteFramebuffers",None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(multi))
        print(f"PASS: actual 4x MSAA emissive coverage and independent color/guide/mask resolves; {gpu.renderer}")

if __name__=="__main__":blending();consumer();msaa()
