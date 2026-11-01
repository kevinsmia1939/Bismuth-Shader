#!/usr/bin/env python3
"""Time the complete underwater shader in one context, without images or input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import argparse
import hashlib
import math
import re
import statistics
import time
from pathlib import Path
from gl_shader_test import ShaderTest
from test_water_lighting import source, setup, optics, probes, uniform_color, close, N, VOLUME, LIGHT, BODY, geometry, camera
from test_water_volume import WATER, AIR
from test_dynamic_lighting import sources


def paired_source(baseline):
    """Both complete passes share uniforms, inputs, draw and driver clock."""
    old='\n'.join((baseline/name).read_text() for name in ('water_volume.glsl','water_lighting.glsl'))
    names=set(re.findall(r'^(?:float|vec[234]|bool|void) (\w+)\(',old,re.M))
    def rename(text):
        return re.sub(r'\b('+ '|'.join(sorted(names))+r')\b',lambda m:'baseline_'+m[0],text)
    old=rename(re.sub(r'^uniform[^\n]*\n','',old,flags=re.M))
    old_main=rename(BODY[BODY.index('void main()'):]).replace('void main()', 'void baselineMain()')
    combined=source(True).replace('void main()', 'void currentMain()')
    combined+='\n'+old+'\n'+old_main+'''
uniform float testBaseline;
void main() { if(testBaseline>0.5) baselineMain(); else currentMain(); }
'''
    return combined


def run(baseline=None,sizes=(64,128,256),flow=False):
    direct, bounce = (2, 0.3, 0.1), (0, 0.2, 0.4)
    incident = tuple(0.5*(0.5*d+0.25*b) for d, b in zip(direct, bounce))
    lights = [((8+i*0.1, 4+(i%3)*0.1, 12+i*0.1), (2, 1, 0.5)) for i in range(8)]
    cases = [('native', 0, []), ('field', 0.5, []),
             ('one lamp', 0.5, lights[:1]), ('eight lamps', 0.5, lights)]
    modes=(0,1) if baseline else (0,)
    combined=paired_source(baseline) if baseline else source(True)
    for size in sizes:
        fragment = combined.replace('gl_FragCoord.xy/64.0', f'gl_FragCoord.xy/{float(size)}')
        with ShaderTest(fragment, size=size) as gpu:
            setup(gpu, True)
            if flow:
                def pool(x,y,z):
                    if y==6:
                        h=0.2+0.01*x+0.02*z
                        return (240/255,h,0,0.4,h,h+0.01,h+0.02,h+0.03)
                    return WATER if y<6 else AIR
                geometry(gpu,pool);camera(gpu,y=56)
            optics(gpu, probes(14, direct, bounce), 14)
            projection = [0,0,0,0,0,0,0,0,0,0,120,0,0,0,0,1]
            gpu.matrix('inverseProjection', projection)
            def select(case):
                _, strength, active = case
                gpu.uniform('voxelWaterParams', strength, 0.5, 8)
                sources(gpu, active)
            def mode(value):
                if baseline: gpu.uniform('testBaseline',value)
            mode(0)
            select(cases[0])
            close(gpu.draw(), uniform_color(60, (0,0,0)), 'native timing control')
            select(cases[1])
            expected = uniform_color(60, incident)
            close(gpu.draw(), expected, 'uniform RGB analytic timing control')
            for case in cases[2:]:
                select(case)
                value = gpu.draw()
                assert all(math.isfinite(v) for v in value)
                assert all(a>b for a,b in zip(value[:3], expected[:3])), (case[0], value, expected)
            if baseline:
                for case in cases:
                    select(case);mode(1);before=gpu.draw()
                    mode(0);close(gpu.draw(),before,'paired full-pass RGB/alpha control',0.00003)
            # Warm every runtime branch and the GPU clock before paired queries.
            deadline = time.monotonic()+0.75
            while time.monotonic()<deadline:
                for case in cases:
                    select(case)
                    for value in modes:
                        mode(value);gpu.draw()
            query = c.c_uint()
            gpu.api('glGenQueries', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(query))
            begin = gpu.api('glBeginQuery', None, c.c_uint, c.c_uint)
            end = gpu.api('glEndQuery', None, c.c_uint)
            result = gpu.api('glGetQueryObjectui64v', None, c.c_uint, c.c_uint, c.POINTER(c.c_ulonglong))
            times = {(case[0],value): [] for case in cases for value in modes}
            try:
                for repetition in range(12):
                    for case in (cases if repetition%2==0 else list(reversed(cases))):
                        select(case)
                        for value in (modes if repetition%2==0 else tuple(reversed(modes))):
                            mode(value)
                            begin(0x88BF, query.value)
                            if gpu.core_shader:
                                gpu.api('glDrawArrays', None, c.c_uint, c.c_int, c.c_int)(4, 0, 3)
                            else:
                                gpu.api('glBegin', None, c.c_uint)(7)
                                for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)):
                                    gpu.api('glVertex2f', None, c.c_float, c.c_float)(x,y)
                                gpu.api('glEnd', None)()
                            end(0x88BF)
                            elapsed = c.c_ulonglong()
                            result(query.value, 0x8866, c.byref(elapsed))
                            times[(case[0],value)].append(elapsed.value/1e6)
            finally:
                gpu.api('glDeleteQueries', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(query))
            assert gpu.api('glGetError', c.c_uint)()==0
            report = ', '.join(f'{label}={statistics.median(values):.3f} ms' for (label,value),values in times.items()
                               if value==0) if not baseline else ', '.join(
                f'{case[0]} before/current={statistics.median(times[(case[0],1)]):.3f}/{statistics.median(times[(case[0],0)]):.3f} ms'
                for case in cases)
            print(f'{gpu.renderer}; {size}x{size}: {report} (median of 12)', flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,help='directory with saved water_volume.glsl and water_lighting.glsl')
    parser.add_argument('--sizes',type=int,nargs='+',default=(64,128,256))
    parser.add_argument('--flow',action='store_true',help='use a shallow sloping flow layer instead of interior source water')
    args=parser.parse_args()
    print('Current SHA256:',hashlib.sha256((VOLUME+LIGHT).encode()).hexdigest()[:16],flush=True)
    if args.baseline:
        old=''.join((args.baseline/name).read_text() for name in ('water_volume.glsl','water_lighting.glsl'))
        print('Baseline SHA256:',hashlib.sha256(old.encode()).hexdigest()[:16],flush=True)
    print(f'GPU underwater draw only: 8 strata, 6-node pool, flow={args.flow}, 16^3 optics; fixed rays, g=0.5; not full-scene FPS.', flush=True)
    run(args.baseline,args.sizes,args.flow)
