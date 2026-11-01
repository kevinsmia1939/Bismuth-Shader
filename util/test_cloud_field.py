#!/usr/bin/env python3
"""Compare production CPU cloud injection with actual GPU noise/map/receivers."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
import subprocess
import tempfile
from pathlib import Path
from gl_shader_test import ShaderTest
from test_cloud_shadows import DENSITY, GENERATE, SAMPLE

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = r'''#include "client/render/cloud_field.h"
#include <iostream>
#include <iomanip>
int main(int argc, char **) {
 std::cout<<std::setprecision(9);
 if(argc>1) {
  for(int z=0;z<32;++z) for(int y=-1;y<=32;++y) for(int x=-1;x<=32;++x)
   std::cout<<int(cloud_field::noiseValue(x,y,z))<<" ";
  return 0;
 }
 cloud_field::ShadowField f;
 v3f camera,light,p; float radius; int ready;
 while(std::cin>>f.density.bottom>>f.density.thickness>>f.density.coverage>>f.density.extinction
   >>f.density.detail>>f.density.wind.X>>f.density.wind.Y>>f.density.seed.X>>f.density.seed.Y
   >>camera.X>>camera.Y>>camera.Z>>light.X>>light.Y>>light.Z>>radius>>f.resolution
   >>f.strength>>ready>>p.X>>p.Y>>p.Z) {
  f.ready=ready;
  f.frame.prepare(camera,f.density.bottom,f.density.thickness,light,radius,f.resolution);
  cloud_field::ShadowSampler sampler(f);
  std::cout<<cloud_field::noise(p)<<" "<<f.density.at(p)<<" "<<sampler.transmission(p)
   <<" "<<f.frame.origin.X<<" "<<f.frame.origin.Y<<" "<<f.frame.origin.Z<<"\n";
 }
}
'''


def cpu_gpu_agreement():
    cases = []
    # Mixed coverage/detail, both light signs, wind/seed offsets and far origins.
    for camera in ((-13, 30, 27), (309985, 30, -309995), (-309995, 200, 309985)):
        for light in ((0, 1, 0), (0.6, 0.8, 0), (-0.48, -0.64, 0.6), (0.99875, 0.05, 0)):
            for coverage, detail in ((0, 0), (0.43, 0.7), (0.7, 1), (1, 0)):
                for h, offset, strength, ready in ((-0.5, 0, 1, 1), (0.19, 11.7, 0.75, 1),
                                                  (0.55, -37.3, 1, 1), (0.85, 3.25, 1, 1),
                                                  (1.1, 0, 1, 1), (-0.1, 251, 1, 1),
                                                  (-0.1, 0, 0, 1), (-0.1, 0, 1, 0)):
                    bottom, thickness, radius, size = 100, 80, 256, 256
                    p = (camera[0]+offset, bottom+h*thickness, camera[2]-offset*0.3)
                    cases.append((bottom, thickness, coverage, 0.02, detail, -213.25, 157.75,
                                  35.7, 81.3, *camera, *light, radius, size, strength, ready, *p))
    with tempfile.TemporaryDirectory(prefix="luanti-cpu-clouds-") as work:
        binary = str(Path(work)/"field")
        subprocess.run(["c++", "-std=c++17", "-O2", "-I", str(ROOT/"src"),
                        "-I", str(ROOT/"irr/include"), "-x", "c++", "-",
                        str(ROOT/"src/client/render/cloud_field.cpp"), "-o", binary],
                       input=PROGRAM, text=True, check=True, capture_output=True)
        values = subprocess.run([binary], input="\n".join(" ".join(map(str,s)) for s in cases),
                                text=True, check=True, capture_output=True).stdout.splitlines()
        noise = subprocess.run([binary,"--noise"],text=True,check=True,capture_output=True).stdout.split()
    noise = [c for v in noise for c in (int(v)/255,)*3+(1,)]
    gen = GENERATE.replace("void main()", "void generateCloudShadow()")
    for line in ("uniform vec3 cloudShadowOrigin; // absolute center on the entry boundary\n",
                 "uniform vec4 cloudShadowParams; // unused, reciprocal span, unused, unused\n",
                 "uniform vec3 cloudShadowSlab; // unused, unused, reciprocal map resolution\n"):
        gen = gen.replace(line, "")
    fragment = DENSITY+SAMPLE+gen+"""
uniform vec3 testPosition;
uniform float testMode;
void main() {
 if(testMode<0.5) generateCloudShadow();
 else gl_FragColor=vec4(cloudNoise3D(testPosition),cloudDensity(testPosition),cloudSunTransmission(testPosition),1);
}
"""
    with ShaderTest(fragment, size=256) as gpu:
        # The actual renderer generates the map in RGBA16F, including quantization.
        gpu.api("glActiveTexture", None, c.c_uint)(0x84C0)
        gpu.api("glBindTexture", None, c.c_uint, c.c_uint)(0x0DE1,99)
        gpu.api("glTexImage2D", None, c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
            0x0DE1,0,0x881A,256,256,0,0x1908,0x1406,None)
        gpu.sampler("texture2",2);gpu.texture(2,noise,True,width=34,height=1088)
        noise_bytes=(c.c_ubyte*len(noise))(*(round(v*255) for v in noise))
        gpu.api("glTexImage2D",None,c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
            0x0DE1,0,0x8058,34,1088,0,0x1908,0x1401,noise_bytes)
        gpu.uniform("cloudTextureSize",34,1088)
        gpu.sampler("texture7",7);gpu.texture(7,(1,1,1,1),True)
        last_map = None
        errors = [0.0]*3
        for case, result in zip(cases,values):
            bottom,thickness,coverage,extinction,detail,wx,wz,sx,sz,cx,cy,cz,lx,ly,lz,radius,size,strength,ready,x,y,z = case
            cpu = list(map(float,result.split()))
            length=math.sqrt(lx*lx+ly*ly+lz*lz)
            direction=(lx/length,ly/length,lz/length)
            origin=cpu[3:6]
            gpu.uniform("cloudLayer",bottom,thickness,coverage,extinction)
            gpu.uniform("cloudParams",1,32,1000,detail)
            gpu.uniform("cloudWind",wx,wz,sx,sz)
            gpu.uniform("cloudLight",*direction,1)
            gpu.uniform("cloudShadowOrigin",*origin)
            gpu.uniform("cloudShadowDirection",*direction)
            gpu.uniform("cloudShadowSlab",thickness,1 if ly>0 else -1,1/size)
            horizon=max(0,min(1,(abs(direction[1])-0.02)/0.06))
            gpu.uniform("cloudShadowParams",ready,1/(radius*2),strength,horizon*horizon*(3-2*horizon))
            gpu.uniform("testPosition",x,y,z)
            key=(bottom,thickness,coverage,extinction,detail,wx,wz,sx,sz,*origin,*direction)
            if key!=last_map:
                gpu.uniform("testMode",0);gpu.draw()
                gpu.api("glActiveTexture",None,c.c_uint)(0x84C0+7)
                gpu.api("glCopyTexSubImage2D",None,c.c_uint,*([c.c_int]*7))(0x0DE1,0,0,0,0,0,size,size)
                last_map=key
            gpu.uniform("testMode",1)
            actual=gpu.draw()
            # Hardware bilinear filtering quantizes subtexel weights; the CPU
            # evaluates the mathematical interpolation. The shape threshold
            # amplifies noise error, so bound density separately from final T.
            for a,b,tolerance in zip(actual,cpu,(0.0025,0.015,0.01)):
                assert abs(a-b)<tolerance,("CPU/GPU field agreement",case,actual,cpu)
            errors=[max(e,abs(a-b)) for e,a,b in zip(errors,actual,cpu)]
        print(f"PASS: {len(cases)} production CPU/GPU cloud density and transmission comparisons, max errors={errors}; {gpu.renderer}")


if __name__ == "__main__":
    cpu_gpu_agreement()
