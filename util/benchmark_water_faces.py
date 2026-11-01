#!/usr/bin/env python3
"""Paired old/current caustic GPU queries in one context; no screenshots or input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import ctypes as c
import hashlib
import math
import re
import statistics
import time
from pathlib import Path
from gl_shader_test import ShaderTest
from test_water_volume import WAVES, VOLUME, cells, WATER, AIR, close


def measure(baseline,size,flow):
    names=set(re.findall(r'^(?:float|vec[234]|bool|void) (\w+)\(',baseline,re.M))
    old=re.sub(r'\b('+ '|'.join(sorted(names))+r')\b',lambda m:'baseline_'+m[0],baseline)
    old=re.sub(r'^uniform[^\n]*\n','',old,flags=re.M)
    source='#define ENABLE_WATER_VOLUME\n'+WAVES+VOLUME+old+f'''
uniform float testBaseline;
void main() {{
 vec2 p=vec2(45.0)+gl_FragCoord.xy*(50.0/{float(size)});
 vec3 color=testBaseline>0.5 ? baseline_applyWaterCaustics(vec3(0.5),vec3(p.x,25,p.y),vec3(0,1,0),0.0,vec3(1)) :
  applyWaterCaustics(vec3(0.5),vec3(p.x,25,p.y),vec3(0,1,0),0.0,vec3(1));
 gl_FragColor=vec4(color,1);
}}
'''
    with ShaderTest(source,size=size) as gpu:
        def pool(x,y,z):
            if y==9 and flow:
                h=0.2+0.02*x+0.01*z
                return (240/255,h,0,0.4,h,h+0.02,h+0.01,h+0.03)
            return WATER if 1<=y<=9 else AIR
        gpu.sampler('texture6',6);gpu.texture(6,cells(16,pool),width=32,height=256)
        gpu.uniform('waterVolumeOrigin',0,0,0);gpu.uniform('waterAbsoluteOrigin',0,0,0)
        gpu.uniform('waterVolumeParams',1,16,240,0.7);gpu.uniform('waterMediumParams',0,1,0,0)
        gpu.uniform('waterWaves',1,20,0.3);gpu.uniform('waterLight',0.3,math.sqrt(0.87),0.2,1)
        gpu.uniform('waterLightColor',1,1,1)
        gpu.uniform('testBaseline',1);expected=gpu.draw()
        gpu.uniform('testBaseline',0);close(gpu.draw(),expected,'paired solver pixel control',0.0005)
        # Both branches warm in the same context before alternating/reversing order.
        until=time.monotonic()+0.75
        while time.monotonic()<until:
            for mode in (0,1):
                gpu.uniform('testBaseline',mode);gpu.draw()
        query=c.c_uint();gpu.api('glGenQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
        timings={0:[],1:[]}
        try:
            for iteration in range(12):
                for mode in ((0,1) if iteration%2==0 else (1,0)):
                    gpu.uniform('testBaseline',mode)
                    gpu.api('glBeginQuery',None,c.c_uint,c.c_uint)(0x88BF,query.value)
                    if gpu.core_shader:gpu.api('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(4,0,3)
                    else:
                        gpu.api('glBegin',None,c.c_uint)(7)
                        for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)):gpu.api('glVertex2f',None,c.c_float,c.c_float)(x,y)
                        gpu.api('glEnd',None)()
                    gpu.api('glEndQuery',None,c.c_uint)(0x88BF)
                    elapsed=c.c_ulonglong()
                    gpu.api('glGetQueryObjectui64v',None,c.c_uint,c.c_uint,c.POINTER(c.c_ulonglong))(
                        query.value,0x8866,c.byref(elapsed))
                    timings[mode].append(elapsed.value/1e6)
        finally:gpu.api('glDeleteQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
        assert gpu.api('glGetError',c.c_uint)()==0
        before,after=(statistics.median(timings[x]) for x in (1,0))
        print(f'{gpu.renderer}; {size}x{size}; flow={flow}: before={before:.3f} ms, '
              f'current={after:.3f} ms, delta={after-before:.3f} ms (12 paired queries)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path,help='water_volume.glsl saved before editing')
    parser.add_argument('--sizes',type=int,nargs='+',default=(64,128,256))
    args=parser.parse_args();baseline=args.baseline.read_text()
    print('Baseline SHA256:',hashlib.sha256(baseline.encode()).hexdigest()[:16],flush=True)
    print('Current SHA256:',hashlib.sha256(VOLUME.encode()).hexdigest()[:16],flush=True)
    print('GPU draw only; fixed pool/light/waves, paired same-context branches; not full-frame FPS.',flush=True)
    for flow in (False,True):
        for size in args.sizes:measure(baseline,size,flow)
