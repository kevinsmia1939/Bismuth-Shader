#!/usr/bin/env python3
"""Actual cloud filter/moment GLSL, float-pixel tests without screenshots/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
import random
from pathlib import Path
from gl_shader_test import ShaderTest
from test_cloud_shadows import close

ROOT = Path(__file__).resolve().parents[1]/"client/shaders"
FILTER = (ROOT/"cloud_denoise/opengl_fragment.glsl").read_text().replace(
    "CENTROID_ VARYING_ mediump vec2 varTexCoord;", "#define varTexCoord (gl_FragCoord.xy/64.0)")
IDENTITY = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
A, B = 1001/999, -2000/999
PROJECTION = [1,0,0,0,0,1,0,0,0,0,A,1,0,0,B,0]
INVERSE = [1,0,0,0,0,1,0,0,0,0,0,1/B,0,0,1,-A/B]


def setup(gpu):
    for unit in range(4): gpu.sampler("texture"+str(unit),unit)
    gpu.matrix("cloudInverseProjection",INVERSE)
    gpu.matrix("cloudInverseView",IDENTITY)
    gpu.matrix("cloudReprojection",PROJECTION)
    gpu.uniform("cloudPreviousCamera",0,0,0)
    gpu.uniform("cloudWindDelta",0,0)
    gpu.uniform("texelSize0",1/64,1/64)
    gpu.uniform("cloudHistoryParams",0,0.9)
    gpu.texture(1,(100,0,10,0.4))
    gpu.texture(3,(100,0,10,0.4))


def checker():
    return [c for y in range(64) for x in range(64)
            for c in ((0.3,0.3,0.3,0.6) if (x+y)%2==0 else (0.5,0.5,0.5,0.6))]


def rejection():
    with ShaderTest(FILTER) as gpu:
        setup(gpu);gpu.texture(0,checker())
        gpu.texture(2,(float("nan"),)*4);gpu.texture(3,(float("nan"),)*4)
        close(gpu.draw(),(0.4,0.4,0.4,0.6),"first frame spatial filtering never reads uninitialized history")
        gpu.texture(2,(0.35,0.35,0.35,0.6));gpu.texture(3,(100,0,10,0.4))
        gpu.uniform("cloudHistoryParams",1,0.9)
        close(gpu.draw(),(0.355,0.355,0.355,0.6),"independent cloud history reduces noise")
        for guide in ((0,0,0,0),(100,5,10,0.4),(300,0,10,0.4)):
            gpu.texture(3,guide)
            close(gpu.draw(),(0.4,0.4,0.4,0.6),"empty, occluded or different-depth history rejected")
        gpu.texture(3,(100,0,10,0.4));gpu.uniform("cloudHistoryParams",1,0)
        close(gpu.draw(),(0.4,0.4,0.4,0.6),"zero temporal strength retains spatial filtering")
        gpu.uniform("cloudHistoryParams",1,0.9)
        # Half the bilinear history footprint is occluded. It must neither poison
        # valid cloud history nor be averaged into it before the depth check.
        old_color=[c for y in range(64) for x in range(64)
                   for c in ((1,1,1,0.6) if x<32 else (0.35,0.35,0.35,0.6))]
        old_guide=[c for y in range(64) for x in range(64)
                   for c in ((0,5,0,0) if x<32 else (100,0,10,0.4))]
        gpu.texture(2,old_color);gpu.texture(3,old_guide)
        shifted=PROJECTION.copy();shifted[8]=-1/64;gpu.matrix("cloudReprojection",shifted)
        expected=0.4+(0.35-0.4)*0.9*math.exp(-0.5*0.01)
        close(gpu.draw(),(expected,expected,expected,0.6),"per-tap depth rejection before bilinear history filtering")
        gpu.matrix("cloudReprojection",PROJECTION)
        gradient=[c for y in range(64) for x in range(64)
                  for c in (0.35+0.1*(x+0.5)/64,)*3+(0.6,)]
        gpu.texture(2,gradient);gpu.texture(3,(100,0,10,0.4));gpu.uniform("cloudWindDelta",12.5,0)
        uv=32.5/64
        ray_z=100/math.sqrt(1+2*(uv*2-1)**2)
        old_uv=uv-12.5/(2*ray_z)
        old_color=0.35+0.1*old_uv
        expected=0.4+(old_color-0.4)*0.9*math.exp(-abs(old_uv-uv)*64*0.01)
        close(gpu.draw(),(expected,expected,expected,0.6),"wind follows the advected cloud rather than the sky")
        gpu.uniform("cloudWindDelta",0,0)
        # A newly exposed clear ray stays exactly clear even beside dense clouds.
        gpu.texture(0,(0,0,0,1));gpu.texture(1,(0,5,0,0))
        gpu.texture(2,(float("nan"),)*4);gpu.texture(3,(float("nan"),)*4)
        close(gpu.draw(),(0,0,0,1),"new foreground/empty ray cannot inherit cloud radiance")
        print(f"PASS: actual cloud spatial/temporal filter, uninitialized guards, per-tap occlusion, partial footprints and empty rays; {gpu.renderer}")


def variance():
    with ShaderTest(FILTER) as gpu:
        setup(gpu)
        gpu.texture(2,(float("nan"),)*4)
        raw,filtered=[],[]
        rng=random.Random(4951)
        for frame in range(40):
            pixels=[]
            for y in range(64):
                for x in range(64):
                    value=rng.random()-0.5
                    color=0.4+value*0.2
                    pixels.extend((color,color,color,0.6))
            raw.append(pixels[(32+32*64)*4])
            gpu.texture(0,pixels)
            gpu.uniform("cloudHistoryParams",0 if frame==0 else 1,0.9)
            filtered.append(gpu.draw()[0])
            gpu.api("glActiveTexture",None,c.c_uint)(0x84C0+2)
            gpu.api("glCopyTexSubImage2D",None,c.c_uint,*([c.c_int]*7))(0x0DE1,0,0,0,0,0,64,64)
        rmse=lambda samples: math.sqrt(sum((v-0.4)**2 for v in samples)/len(samples))
        assert rmse(filtered)<rmse(raw)*0.4,("volume noise reduction",rmse(raw),rmse(filtered))
        assert abs(sum(filtered)/len(filtered)-0.4)<0.015,("radiance bias",filtered)
        print(f"PASS: stationary noisy cloud RMSE {rmse(raw):.5f} -> {rmse(filtered):.5f} over 40 frames; {gpu.renderer}")


def moments():
    source=(ROOT/"common/volumetric_clouds.glsl").read_text()
    fragment=source+"""
uniform vec3 testOrigin;
uniform float testDistance;
void main(){vec2 moments;vec4 c=integrateCloudsWithMoments(testOrigin,vec3(0,0,1),testDistance,0.5,moments);
 gl_FragColor=vec4(moments,c.a,1);}
"""
    with ShaderTest(fragment) as gpu:
        gpu.sampler("texture2",2);gpu.texture(2,(1,1,1,1),True,width=6,height=24)
        gpu.uniform("cloudTextureSize",6,24);gpu.uniform("cloudLayer",0,10,1,0.02)
        gpu.uniform("cloudWind",0,0,0,0);gpu.uniform("cloudParams",1,32,100000,0)
        gpu.uniform("testOrigin",0,5,0);gpu.uniform("testDistance",100)
        weights=[math.exp(-0.02*100*i/32)*(1-math.exp(-0.02*100/32)) for i in range(32)]
        distances=[(i+0.5)*100/32 for i in range(32)]
        mean=sum(t*w for t,w in zip(distances,weights))/sum(weights)
        spread=math.sqrt(sum((t-mean)**2*w for t,w in zip(distances,weights))/sum(weights))
        close(gpu.draw(),(mean,spread,math.exp(-2),1),"extinction-event mean and spread",0.001)
        gpu.uniform("cloudLayer",0,10,0,0.02)
        close(gpu.draw(),(0,0,1,1),"cleared layer has no temporal anchor")
        print(f"PASS: actual integrated cloud depth moments and empty-layer identity; {gpu.renderer}")


if __name__=="__main__":
    rejection()
    variance()
    moments()
