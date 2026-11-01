#!/usr/bin/env python3
"""GPU query timing of actual water-caustic GLSL; no screenshots or input events."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
import statistics
from gl_shader_test import ShaderTest
from test_water_volume import WAVES, VOLUME, cells, WATER, AIR


def measure(size):
    fragment = '#define ENABLE_WATER_VOLUME\n' + WAVES + VOLUME + '''
void main() {
 vec2 p = vec2(45.0) + gl_FragCoord.xy * (50.0 / ''' + str(float(size)) + ''');
 gl_FragColor = vec4(applyWaterCaustics(vec3(0.5),vec3(p.x,25,p.y),vec3(0,1,0),0.0,vec3(1)),1);
}
'''
    with ShaderTest(fragment, size=size) as gpu:
        gpu.sampler('texture6', 6)
        gpu.texture(6, cells(16,lambda x,y,z: WATER if 1<=y<=9 else AIR), width=32,height=256)
        gpu.uniform('waterVolumeOrigin',0,0,0)
        gpu.uniform('waterAbsoluteOrigin',0,0,0)
        gpu.uniform('waterVolumeParams',1,16,240,0.7)
        gpu.uniform('waterWaves',1,20,0.3)
        gpu.uniform('waterLight',0.3,math.sqrt(0.87),0.2,1)
        gpu.uniform('waterLightColor',1,1,1)
        gpu.uniform('waterMediumParams',0,1,0,0)
        for _ in range(3):
            gpu.draw()  # Compile/warm before timing; numeric finite/error check.
        query = c.c_uint()
        gpu.api('glGenQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
        begin = gpu.api('glBeginQuery',None,c.c_uint,c.c_uint)
        end = gpu.api('glEndQuery',None,c.c_uint)
        result = gpu.api('glGetQueryObjectui64v',None,c.c_uint,c.c_uint,c.POINTER(c.c_ulonglong))
        timings = {0.0:[],0.7:[]}
        try:
            for _ in range(9):
                for strength in timings:
                    gpu.uniform('waterVolumeParams',1,16,240,strength)
                    begin(0x88BF,query.value)  # GL_TIME_ELAPSED
                    if gpu.core_shader:
                        gpu.api('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(4,0,3)
                    else:
                        gpu.api('glBegin',None,c.c_uint)(7)
                        for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)):
                            gpu.api('glVertex2f',None,c.c_float,c.c_float)(x,y)
                        gpu.api('glEnd',None)()
                    end(0x88BF)
                    elapsed = c.c_ulonglong()
                    result(query.value,0x8866,c.byref(elapsed))  # GL_QUERY_RESULT
                    timings[strength].append(elapsed.value/1e6)
        finally:
            gpu.api('glDeleteQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
        assert gpu.api('glGetError',c.c_uint)()==0,'GPU timing query failed'
        baseline,enabled = (statistics.median(timings[s]) for s in (0.0,0.7))
        print(f'{gpu.renderer}; {size}x{size}: off={baseline:.3f} ms, '
              f'on={enabled:.3f} ms, delta={enabled-baseline:.3f} ms (median of 9)')


if __name__ == '__main__':
    print('GPU shader draw only: seven-node pool depth, native waves, fixed light/phase; not full-frame FPS.')
    for size in (64,128,256):
        measure(size)
