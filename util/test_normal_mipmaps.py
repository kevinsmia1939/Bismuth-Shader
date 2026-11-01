#!/usr/bin/env python3
"""Actual mip sampling and node roughness/GGX integration; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
from gl_shader_test import ShaderTest
from test_point_materials import FLAGS, MATERIAL, VOXEL, NODE_COMPOSE, close
from test_specular_filter import FILTER, SUN
from test_dynamic_lighting import atlas, upload, sources, falloff, N

MAIN='''
uniform float testScale, testMode, testRoughness;
uniform vec3 cameraPosition, cameraOffset;
void main() {
 vec2 uv=gl_FragCoord.xy/64.0*testScale;
 vec3 geometricNormal=vec3(0,0,1), materialFilterNormal;
 float materialMipVariance;
 vec3 fNormal=readMaterialNormal(geometricNormal,vec3(gl_FragCoord.xy/64.0,0),uv,
  materialFilterNormal,materialMipVariance);
 vec3 materialData=vec3(1,testRoughness,1);
'''+FILTER+'''
 if(testMode<0.5) { gl_FragColor=vec4(materialData.g,materialMipVariance,fNormal.x,1); return; }
 vec3 materialSun=vec3(0),materialPoint=vec3(0),surfaceView=normalize(fNormal);
 vec3 surfaceLightColor=vec3(1),surfaceSunVisibility=vec3(1);
 vec4 surfaceLight=vec4(normalize(fNormal),1);
 float naturalShare=1.0;
 vec3 f0=vec3(0.04),dayLight=vec3(1),shadow_color=vec3(0);
 float adjusted_night_ratio=0.0,shadow_int=0.0,f_adj_shadow_strength=1.0;
 if(testMode<1.5) {
'''+SUN+'''
  gl_FragColor=vec4(materialSun,1); return;
 }
 vec3 worldPosition=vec3(40,40,80),vNormal=vec3(0,0,1);
 vec4 base=vec4(0.8,0.4,0.2,1),col=vec4(0,0,0,0.4),fogColor=vec4(0);
 float nightRatio=0.0;
 bool authoredMaterial=true;
'''+NODE_COMPOSE+'''
 gl_FragColor=col;
}
'''


def run():
    with ShaderTest(FLAGS+MATERIAL+VOXEL+MAIN) as gpu:
        gpu.sampler('texture4',4);gpu.sampler('texture2',2)
        gpu.uniform('voxelParams',1,1,0,N);gpu.uniform('voxelOrigin',0,0,0)
        gpu.uniform('cameraPosition',40,40,140);gpu.uniform('cameraOffset',0,0,0)
        upload(gpu,atlas());sources(gpu,[((4,4,14),(2,2,2))])
        gpu.uniform('testRoughness',0.1);gpu.uniform('testMode',0)
        gpu.uniform('materialMapFlags',1,0,1);gpu.uniform('materialNormalMipmaps',1)
        # Unit normals at +/-45 degrees cancel in XY at the first mip. Every
        # coarser mip keeps the same mean and variance, rather than renormalizing.
        angle=math.pi/4
        encoded_z=round((math.cos(angle)*0.5+0.5)*255)
        alpha=round(math.sin(angle)*255)
        gpu.texture(4,(0.5,0.5,1,0),width=64,height=64)
        tex=gpu.api('glTexImage2D',None,c.c_uint,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)
        for level in range(7):
            size=64>>level
            pixel=(128,128,255,0) if level==0 else (128,128,encoded_z,alpha)
            data=(c.c_ubyte*(size*size*4))(*(pixel*(size*size)))
            tex(0x0DE1,level,0x8058,size,size,0,0x1908,0x1401,data)
        param=gpu.api('glTexParameteri',None,c.c_uint,c.c_uint,c.c_int)
        param(0x0DE1,0x2801,0x2700);param(0x0DE1,0x2800,0x2600)
        for scale in (2,4,8,16,32,64):
            gpu.uniform('testScale',scale)
            for strength in (0,0.5,1,2):
                gpu.uniform('materialMapFlags',1,0,strength)
                variance=min(0.5*(alpha/255)**2*strength**2,0.25)
                roughness=(0.1**4+variance)**0.25
                tangent=((128/255*2-1)*strength,(128/255*2-1)*strength,max(encoded_z/255*2-1,0.001))
                nx=tangent[0]/math.sqrt(sum(v*v for v in tangent))
                gpu.uniform('testMode',0)
                close(gpu.draw(),(roughness,variance,nx,1),'actual coarse mip variance, normal strength and node roughness',0.00004)
                gpu.uniform('testMode',1)
                peak=min(32,0.04/(4*math.pi*roughness**4))
                close(gpu.draw(),(peak,peak,peak,1),'coarse normal variance reaches directional GGX',max(0.00004,peak*0.00001))
                gpu.uniform('testMode',2)
                nz=tangent[2]/math.sqrt(sum(v*v for v in tangent))
                a2=roughness**4
                distribution=a2/(math.pi*((1-nz*nz)+nz*nz*a2)**2)
                visibility=0.25/(nz*math.sqrt(nz*nz*(1-a2)+a2))
                expected=tuple((2*falloff(6)*min(32,b**2.2*distribution*visibility*nz))**(1/2.2)
                               for b in (0.8,0.4,0.2))+(0.4,)
                close(gpu.draw(),expected,'coarse normal variance reaches actual node moving-lamp composition',0.00004)
        gpu.uniform('testScale',1);gpu.uniform('testMode',0)
        close(gpu.draw(),(0.1,0,0.00784265,1),'base level retains authored roughness',0.00004)
        gpu.uniform('testScale',16);gpu.uniform('materialNormalMipmaps',0)
        close(gpu.draw()[:2],(0.1,0),'raw normal alpha remains ignored')
        gpu.uniform('materialNormalMipmaps',1);gpu.uniform('materialMapFlags',0,0,1)
        gpu.texture(4,(float('nan'),)*4)
        close(gpu.draw(),(0.1,0,0,1),'missing map avoids invalid variance reads')
        print('PASS: real mip minification retains roughness, live strength, directional GGX, base level and raw/missing-map guards;',gpu.renderer)


if __name__=='__main__': run()
