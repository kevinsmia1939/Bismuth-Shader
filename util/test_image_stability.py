#!/usr/bin/env python3
"""Production post-processing over repeatable light/animation transitions; scalar probes."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math

from gl_shader_test import ShaderTest
from test_fog_denoise import source, IDENTITY, INVERSE, A, B
from test_dynamic_lighting import close


def tone():
    fragment = '#define ENABLE_TONE_MAPPING 1\n#define ENABLE_AUTO_EXPOSURE\n#define ENABLE_BLOOM\n#define ENABLE_DITHERING\n'
    fragment += source('second_stage').replace('VARYING_ float exposure;', 'uniform float exposure;')
    with ShaderTest(fragment) as gpu:
        gpu.sampler('texture0', 0)
        gpu.sampler('texture1', 1)
        gpu.texture(1, (0, 0, 0, 1))
        gpu.uniform('exposureParams.compensationFactor', 1)
        gpu.uniform('exposure', 1)
        gpu.uniform('bloomIntensity', 0.05)
        gpu.uniform('bloomStrength', 1)
        gpu.uniform('saturation', 1)
        results = []
        for intensity in (0, 0.05, 0.2, 0.5, 1, 2, 4, 16):
            gpu.texture(0, (intensity, intensity*0.7, intensity*0.3, 1))
            results.append(gpu.draw())
        close(results[0], (0, 0, 0, 1), 'Final black survives exposure, bloom and tone mapping')
        gpu.texture(0, (0, 0, 0, 1))
        for y in range(0,64,7):
            for x in range(0,64,7):
                close(gpu.draw(x,y), (0,0,0,1), 'Dithering preserves exact black across the output', 1e-7)
        assert all(a[0] < b[0] for a, b in zip(results, results[1:])), 'HDR highlights must retain separation before the tone curve'
        assert all(0 <= min(v[:3]) <= max(v[:3]) <= 1 for v in results)
        assert results[5][0] > results[5][1] > results[5][2], 'Bright light must retain color'
        gpu.texture(0, (0,0,0,1))
        gpu.texture(1, (0.1,0.05,0.025,1))
        gain_outputs = []
        for strength in (0,1,4):
            gpu.uniform('bloomStrength',strength)
            gain_outputs.append(gpu.draw())
        close(gain_outputs[0], (0,0,0,1), 'Zero bloom gain adds no halo light', 1e-7)
        assert 0 < gain_outputs[1][0] < gain_outputs[2][0], 'Bloom gain still controls real highlights'
        print('PASS: HDR lamp/grain highlight separation, bounded tone output, color and exact black;', gpu.renderer)


def linear_meter_input():
    # The same extraction is installed for auto exposure with bloom enabled or
    # disabled. It must retain the unscaled metering signal, including zero gain.
    for enabled in (False,True):
        flags = '#define ENABLE_AUTO_EXPOSURE\n'+('#define ENABLE_BLOOM\n' if enabled else '')
        fragment = source('extract_bloom').replace('VARYING_ float exposure;', 'uniform float exposure;')
        with ShaderTest(flags+fragment) as gpu:
            gpu.sampler('texture0',0)
            gpu.texture(0,(0.25,0.15,0.1,1))
            gpu.uniform('exposure',2)
            gpu.uniform('exposureParams.compensationFactor',1.5)
            close(gpu.draw(), tuple(3*v**2.2 for v in (0.25,0.15,0.1))+(1,),
                  'Meter input is linear and independent of downstream bloom gain')
            gpu.texture(0,(0,0,0,1))
            close(gpu.draw(), (0,0,0,1), 'Linear extraction retains exact black', 1e-7)
            print('PASS: independent linear exposure-meter input; bloom enabled=',enabled,gpu.renderer)


def bloom():
    with ShaderTest(source('bloom_downsample')) as gpu:
        gpu.sampler('texture0', 0)
        gpu.uniform('texelSize0', 1/64, 1/64)
        gpu.texture(0, (0, 0, 0, 1))
        close(gpu.draw(), (0, 0, 0, 1), 'Bloom reduction must not create a brightness floor', 1e-7)
        gpu.texture(0, (0.2, 0.1, 0.05, 1))
        close(gpu.draw(), (0.2, 0.1, 0.05, 1), 'Normalized bloom reduction preserves constant radiance')
        for x, y in ((31,31), (33,31), (31,33), (33,33)):
            data = [0,0,0,1]*(64*64)
            data[(y*64+x)*4] = 1
            gpu.texture(0, data)
            close(gpu.draw(32,32), (0.125,0,0,1), 'All four inner bloom taps must be symmetric')
        print('PASS: production bloom reduction preserves black, energy and kernel symmetry;', gpu.renderer)
    with ShaderTest(source('bloom_upsample')) as gpu:
        for unit in range(2):
            gpu.sampler('texture'+str(unit), unit)
            gpu.texture(unit, (0,0,0,1))
        gpu.uniform('texelSize0', 1/64, 1/64)
        gpu.uniform('bloomRadius', 1)
        close(gpu.draw(), (0,0,0,1), 'Bloom reconstruction preserves black through every level', 1e-7)
        gpu.texture(0, (0.2,0.1,0.05,1))
        gpu.texture(1, (0.1,0.05,0.025,1))
        close(gpu.draw(), (0.3,0.15,0.075,1), 'Bloom reconstruction retains real light')
        print('PASS: production bloom reconstruction preserves darkness and real highlights;', gpu.renderer)


def exposure():
    with ShaderTest(source('update_exposure')) as gpu:
        gpu.sampler('texture0', 0)
        gpu.sampler('texture1', 1)
        for key, value in [('luminanceMin', 0.005), ('luminanceMax', 1),
                           ('exposureCorrection', 0), ('centerWeightPower', 1),
                           ('compensationFactor', 1), ('speedDarkBright', 3), ('speedBrightDark', 1)]:
            gpu.uniform('exposureParams.'+key, value)

        def adapt(previous, luminance, dt):
            gpu.uniform('animationTimerDelta', dt)
            gpu.texture(0, (previous, previous, previous, 1))
            # Exposure metering consumes the exposed linear downsample chain.
            measured = luminance * 2**previous
            gpu.texture(1, (measured, measured, measured, 1))
            return gpu.draw()[0]

        for luminosity in (0, 0.005, 0.1, 1):
            paths = []
            for rate in (30, 60, 120):
                value = 0
                path = []
                for _ in range(rate):
                    value = adapt(value, luminosity, 1/rate)
                    path.append(value)
                assert max(abs(b-a) for a, b in zip([0]+path, path)) < 0.4, 'Exposure must adapt over several frames'
                assert all(a*b >= -1e-6 for a, b in zip(path, path[1:])), 'No exposure direction reversal'
                paths.append(value)
            close(paths, (paths[0],)*3, 'Exposure adaptation is independent of frame rate', 0.0001)
        print('PASS: bright/dark exposure ramps at 30/60/120 FPS without flashes;', gpu.renderer)


def temporal():
    with ShaderTest(source('taa')) as gpu:
        for unit in range(3):
            gpu.sampler('texture'+str(unit), unit)
        gpu.matrix('taaReprojection', IDENTITY)
        gpu.matrix('taaSkyReprojection', IDENTITY)
        gpu.matrix('taaInverseProjection', INVERSE)
        gpu.uniform('taaParams', 0, 0, 0, 0.9)
        gpu.uniform('texelSize0', 1/64, 1/64)
        gpu.uniform('taaWaterReactive', 0)
        gpu.texture(1, (float('nan'),)*4)

        def frame(offset, peak, valid=True):
            values = []
            depths = []
            for y in range(64):
                for x in range(64):
                    leaf = 20+offset <= x < 27+offset and 25 <= y < 40
                    glint = peak > 0 and x == 40+offset and y == 32
                    values.extend((0.1, 0.5, 0.08, 1) if leaf else
                                  ((peak, peak*0.9, peak*0.7, 1) if glint else (0.04, 0.03, 0.02, 1)))
                    d = 50 if leaf else 100
                    depths.extend(((A+B/d)*0.5+0.5, 0, 0, 1))
            gpu.texture(0, values)
            gpu.texture(2, depths)
            gpu.uniform('taaParams', 0, 0, int(valid), 0.9)
            result = gpu.draw(22, 32)
            glint_value = gpu.draw(40+offset, 32)
            old_glint = gpu.draw(40, 32)
            # Retain the actual GPU history with no image readback or export.
            gpu.api('glActiveTexture', None, c.c_uint)(0x84C1)
            gpu.api('glBindTexture', None, c.c_uint, c.c_uint)(0x0DE1, 2)
            gpu.api('glCopyTexSubImage2D', None, c.c_uint, *([c.c_int]*7))(
                0x0DE1, 0, 0, 0, 0, 0, 64, 64)
            if peak > 0:
                assert glint_value[0] >= peak*0.7, 'TAA must retain visible glints'
            else:
                close(old_glint[:3], (0.04, 0.03, 0.02), 'Removed glint leaves no persistent bright trail')
            return result

        close(frame(0, 0.6, False)[:3], (0.1, 0.5, 0.08), 'First-frame history is never sampled')
        for _ in range(8):
            close(frame(0, 0.6)[:3], (0.1, 0.5, 0.08), 'Stationary foliage remains stable')
        close(frame(12, 0)[:3], (0.04, 0.03, 0.02), 'Moving foliage leaves no persistent silhouette')
        for _ in range(8):
            close(frame(12, 0)[:3], (0.04, 0.03, 0.02), 'Cleared history remains clean')
        close(frame(0, 0.6, False)[:3], (0.1, 0.5, 0.08), 'Resize/cut history reset accepts the current frame')
        # An animated material changes color while retaining its geometry and
        # YCoCg brightness. Neighborhood bounds contain both large color tiles,
        # so depth rejection and luminance-only reactivity cannot clear it.
        old_energy = []
        gpu.texture(2, ((A+B/100)*0.5+0.5,0,0,1))
        for index in range(5):
            values = []
            for y in range(64):
                for x in range(64):
                    red = (x//8+y//8+int(index>0))%2 == 0
                    values.extend((0.7,0,0,1) if red else (0,0.7*0.5**(1/2.2),0,1))
            gpu.texture(0, values)
            gpu.uniform('taaParams',0,0,int(index>0),0.9)
            value = gpu.draw(32,32)
            old_energy.append((value[0]/0.7)**2.2)
            gpu.api('glActiveTexture',None,c.c_uint)(0x84C1)
            gpu.api('glBindTexture',None,c.c_uint,c.c_uint)(0x0DE1,2)
            gpu.api('glCopyTexSubImage2D',None,c.c_uint,*([c.c_int]*7))(0x0DE1,0,0,0,0,0,64,64)
        assert old_energy[-1] < 0.1, ('Persistent obsolete hue in an animated texture',old_energy)
        print('PASS: equal-brightness animated material clears stale hue; four-frame energy ratio',old_energy[-1])
        print('PASS: actual GPU temporal feedback over moving foliage, glints and history reset;', gpu.renderer)


if __name__ == '__main__':
    bloom()
    linear_meter_input()
    tone()
    exposure()
    temporal()
