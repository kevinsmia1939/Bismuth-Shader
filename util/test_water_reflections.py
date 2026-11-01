#!/usr/bin/env python3
"""Actual water SSR hits, first-crossing rejection and smooth sky fallback."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest

SOURCE = (Path(__file__).resolve().parents[1] /
          'client/shaders/scene_lighting/opengl_fragment.glsl').read_text().replace(
    'CENTROID_ VARYING_ mediump vec2 varTexCoord;',
    '#define varTexCoord (gl_FragCoord.xy/64.0)')
FLAGS = '#define ENABLE_SCENE_SURFACE\n#define ENABLE_SCREEN_SPACE_REFLECTIONS\n'
A, B = 1001/999, -2000/999
PROJECTION = [1,0,0,0,0,1,0,0,0,0,A,1,0,0,B,0]
INVERSE = [1,0,0,0,0,1,0,0,0,0,0,1/B,0,0,1,-A/B]


def close(actual, expected, label, tolerance=5e-5):
    assert max(abs(a-b) for a,b in zip(actual,expected)) < tolerance, (label,actual,expected)


def depth(z): return (A+B/z)*0.5+0.5


def setup(gpu):
    for name, unit in (('texture0',0),('texture1',1),('texture2',2)):
        gpu.sampler(name,unit)
    gpu.matrix('sceneProjection',PROJECTION)
    gpu.matrix('inverseProjection',INVERSE)
    gpu.texture(0,(0.2,0.8,0.4,1))
    gpu.texture(1,(depth(40),0,0,1))
    gpu.texture(2,(0.5,0.5,-40,1))


def tracing():
    fragment = FLAGS+SOURCE.replace('void main(void)','void unusedMain(void)')+'''
uniform vec3 testPosition, testNormal;
void main(){gl_FragColor=traceReflection(testPosition,testNormal);}
'''
    with ShaderTest(fragment) as gpu:
        setup(gpu)
        p=(0,0,20)
        gpu.uniform('testPosition',*p)
        # Construct N as the half-vector taking the incident +Z ray to a
        # chosen outgoing ray. The plane intersection is known analytically.
        def ray_to(x,y):
            d=[(x*2-1)*40, (y*2-1)*40, 20]
            length=math.sqrt(sum(v*v for v in d));d=[v/length for v in d]
            n=[-d[0],-d[1],1-d[2]]
            length=math.sqrt(sum(v*v for v in n));n=[v/length for v in n]
            gpu.uniform('testNormal',*n)
            travel=(40-20-n[2]*0.3)/d[2]
            hit=[(n[axis]*0.3+d[axis]*travel)/80+0.5 for axis in (0,1)]
            edge=min(*hit,1-hit[0],1-hit[1])
            confidence=max(0,min(1,edge/0.08))
            confidence=confidence*confidence*(3-2*confidence)
            return gpu.draw(),confidence
        rgb=tuple(v**2.2 for v in (0.2,0.8,0.4))
        center,_=ray_to(0.5,0.75)
        close(center,rgb+(1,),'surrounding opaque terrain supplies actual reflection radiance')
        # Include the normal-offset correction in the independent hit location.
        for y in (0.95,0.96,0.97,0.98,0.99):
            sample,reference=ray_to(0.5,y)
            assert 0 <= sample[3] <= 1
            close(sample[:3],rgb,'valid edge hit retains donor radiance')
            close((sample[3],),(reference,),'edge confidence matches analytic plane hit',0.015)
            if y>0.95: assert sample[3] < previous, ('fallback confidence must fade',y,sample,previous)
            previous=sample[3]
        assert previous < 0.15, previous
        miss,_=ray_to(0.5,1.1)
        close(miss,(0,0,0,0),'offscreen reflection uses fallback')
        ray_to(0.5,0.75)
        foreground=[channel for y in range(64) for x in range(64)
                    for channel in (depth(5 if 33 <= y <= 40 else 40),0,0,1)]
        gpu.texture(1,foreground)
        close(gpu.draw(),(0,0,0,0),'first foreground crossing cannot reveal terrain behind it')
        gpu.texture(1,(depth(40),0,0,1));gpu.texture(2,(0.5,0.5,40,1))
        close(gpu.draw(),(0,0,0,0),'water cannot reflect its own surface buffer')
        print('PASS: production SSR terrain hit, edge fade, offscreen fallback and foreground/water rejection;',gpu.renderer)


def critical_angle():
    fragment=SOURCE.replace('void main(void)','void unusedMain(void)')+'''
uniform vec2 testWeight;
void main(){gl_FragColor=vec4(waterInternalReflectionWeight(testWeight.x,testWeight.y));}
'''
    with ShaderTest(fragment) as gpu:
        for strength in (0.2,0.7,1):
            previous=0
            for fresnel in (0,0.02,0.2,0.5,0.6,0.8,0.99,0.999,0.999999,1):
                gpu.uniform('testWeight',fresnel,strength)
                value=gpu.draw()[0]
                assert previous<=value<=1.000001
                if fresnel<=0.5: close((value,),(fresnel*strength,),'ordinary-angle reflection gain')
                if fresnel>=0.999999: close((value,),(1,),'continuous approach to full TIR',0.00001)
                previous=value
        print('PASS: underwater reflection gain tends continuously to full TIR without a critical-angle flash;',gpu.renderer)


if __name__ == '__main__':
    tracing()
    critical_angle()
