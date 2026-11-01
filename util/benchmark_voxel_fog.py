#!/usr/bin/env python3
"""GPU draw timing of actual voxel/fog GLSL; no screenshots or input events."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import os
import statistics
from gl_shader_test import ShaderTest
from test_voxel_fog import FLAGS, DYNAMIC, VOXEL, probes, upload, sources, N
from test_fog_denoise import source, INVERSE, IDENTITY, A, B


def run():
    phases=tuple(dict.fromkeys(max(-0.85,min(0.85,float(value)))
                 for value in os.environ.get('LUANTI_BENCH_FOG_ANISOTROPY','0.35').split(',')))
    print(f'Local scattering anisotropy values={phases}',flush=True)
    flags=FLAGS+DYNAMIC+'#define ENABLE_ATMOSPHERE\n#define ENABLE_VOLUMETRIC_FOG\n'
    # Use the same full world-space view patch for each draw resolution.
    scene=source('scene_lighting')
    for size in (64,128,256):
        fragment=flags+VOXEL+scene.replace('gl_FragCoord.xy/64.0',f'gl_FragCoord.xy/{float(size)}')
        with ShaderTest(fragment,size=size) as gpu:
            gpu.sampler('texture0',0);gpu.texture(0,(0.4,0.5,0.6,0.7))
            gpu.sampler('texture1',1);gpu.texture(1,((A+B/100)*0.5+0.5,0,0,1))
            gpu.sampler('texture4',4);upload(gpu,probes((0.8,0.2,0.1),(0.1,0.3,0.5)))
            gpu.uniform('voxelOrigin',0,0,0);gpu.uniform('voxelParams',1,0.7,0.2,N)
            gpu.uniform('voxelFogStrength',0.5)
            gpu.uniform('voxelFogAnisotropy',phases[0])
            inverse=IDENTITY.copy();inverse[12:15]=[40,40,20]
            gpu.matrix('inverseView',inverse);gpu.matrix('inverseProjection',INVERSE)
            gpu.uniform('cameraPosition',40,40,20);gpu.uniform('cameraOffset',0,0,0)
            gpu.uniform('sceneParams',0.02,0,0,0);gpu.uniform('volumeParams',60,1e30,0,24)
            gpu.uniform('volumeLightDirection',0,1,0);gpu.uniform('volumeLightColor',0,0,0)
            gpu.uniform('fogColor',0,0,0,1);gpu.uniform('atmosphereEnabled',1)
            lights=[((4+i*0.2,4+(i%3)*0.2,10+i*0.1),(1,0.5,0.2)) for i in range(8)]
            cases=[('off',0,0.7,0.2,[]),('field',0.5,0.7,0.2,[]),
                   ('direct only',0.5,0.7,0,[]),('bounce only',0.5,0,0.2,[]),
                   ('one lamp',0.5,0.7,0.2,lights[:1]),('eight lamps',0.5,0.7,0.2,lights)]
            sources(gpu,lights)
            for phase in phases:
                gpu.uniform('voxelFogAnisotropy',phase)
                for _ in range(3):gpu.draw()
            query=c.c_uint()
            gpu.api('glGenQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
            begin=gpu.api('glBeginQuery',None,c.c_uint,c.c_uint)
            end=gpu.api('glEndQuery',None,c.c_uint)
            result=gpu.api('glGetQueryObjectui64v',None,c.c_uint,c.c_uint,c.POINTER(c.c_ulonglong))
            times={(label,phase):[] for label,_,_,_,_ in cases for phase in phases}
            try:
                for repetition in range(9):
                    for label,strength,direct,bounce,active in cases:
                        gpu.uniform('voxelFogStrength',strength);sources(gpu,active)
                        gpu.uniform('voxelParams',1,direct,bounce,N)
                        # Pair phases in one program/context and reverse their
                        # order, avoiding a comparison of separate GPU clock ramps.
                        for phase in (phases if repetition%2==0 else tuple(reversed(phases))):
                            gpu.uniform('voxelFogAnisotropy',phase)
                            begin(0x88BF,query.value)
                            if gpu.core_shader:
                                gpu.api('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(4,0,3)
                            else:
                                gpu.api('glBegin',None,c.c_uint)(7)
                                for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)):
                                    gpu.api('glVertex2f',None,c.c_float,c.c_float)(x,y)
                                gpu.api('glEnd',None)()
                            end(0x88BF)
                            elapsed=c.c_ulonglong();result(query.value,0x8866,c.byref(elapsed))
                            times[(label,phase)].append(elapsed.value/1e6)
            finally:
                gpu.api('glDeleteQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
            assert gpu.api('glGetError',c.c_uint)()==0
            for phase in phases:
                report=', '.join(f'{label}={statistics.median(times[(label,phase)]):.3f} ms' for label,_,_,_,_ in cases)
                print(f'{gpu.renderer}; {size}x{size}; g={phase}: {report} (median of 9)',flush=True)


if __name__=='__main__':
    print('GPU draw only: 24 samples, 6-node ray, open 16^3 field, fixed lamps; not full-scene FPS.',flush=True)
    run()
