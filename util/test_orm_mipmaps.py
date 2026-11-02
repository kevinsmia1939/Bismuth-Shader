#!/usr/bin/env python3
"""Numeric sampling of roughness-aware ORM mips and the production GGX helper."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
from pathlib import Path
from gl_shader_test import ShaderTest

MATERIAL = (Path(__file__).resolve().parents[1] / 'client/shaders/common/material_maps.glsl').read_text()
MAIN = '''
uniform float testScale, testOffset, testMode;
void main() {
 vec2 uv = gl_FragCoord.xy / 64.0 * testScale + vec2(testOffset);
 vec3 orm = readMaterialORM(uv, 0.8);
 if (testMode < 0.5) gl_FragColor = vec4(orm, 1);
 else gl_FragColor = vec4(materialSpecular(vec3(0,0,1), vec3(0,0,1),
  vec3(0,0,1), orm.g, mix(vec3(0.04), vec3(0.8,0.4,0.2), orm.b)), 1);
}
'''


def close(actual, expected, label):
    assert len(actual) == len(expected)
    assert max(abs(a - b) for a, b in zip(actual, expected)) < 3e-5, (label, actual, expected)


def run():
    with ShaderTest('#define ENABLE_MATERIAL_MAPS\n' + MATERIAL + MAIN) as gpu:
        gpu.sampler('texture5', 5)
        gpu.uniform('materialMapFlags', 0, 1, 1)
        gpu.texture(5, (1, 1, 1, 1), width=64, height=64)
        tex = gpu.api('glTexImage2D', None, c.c_uint, c.c_int, c.c_int, c.c_int, c.c_int,
                      c.c_int, c.c_uint, c.c_uint, c.c_void_p)
        # Independent analytic footprint: equal amounts of r=.2 and r=1.
        # The C++ tests verify that the production CPU chain and both driver
        # uploads produce this value; here verify actual mip selection and GGX.
        roughness_byte = round(((0.2**4 + 1) / 2)**0.25 * 255)
        for level in range(7):
            size = 64 >> level
            pixels = []
            for y in range(size):
                for x in range(size):
                    r = 51 if (x + y) % 2 else 255
                    pixels.extend((255, r if level == 0 else roughness_byte, 255, 17))
            data = (c.c_ubyte * len(pixels))(*pixels)
            tex(0x0DE1, level, 0x8058, size, size, 0, 0x1908, 0x1401, data)
        param = gpu.api('glTexParameteri', None, c.c_uint, c.c_uint, c.c_int)
        param(0x0DE1, 0x2802, 0x2901)  # Repeat, including moving subtexel offsets.
        param(0x0DE1, 0x2803, 0x2901)
        for filtering in (0x2700, 0x2703):  # Nearest mip and trilinear.
            param(0x0DE1, 0x2801, filtering)
            for scale in (2, 2.5, 4, 8, 16, 32, 64):
                gpu.uniform('testScale', scale)
                for offset in (0, 0.001, 0.003, 0.007, 0.011, 0.02):
                    gpu.uniform('testOffset', offset)
                    gpu.uniform('testMode', 0)
                    roughness = roughness_byte / 255
                    close(gpu.draw(), (1, roughness, 1, 1), 'stable minified ORM channels')
                    gpu.uniform('testMode', 1)
                    expected = tuple(v / (4 * math.pi * roughness**4) for v in (0.8, 0.4, 0.2)) + (1,)
                    close(gpu.draw(), expected, 'stable bounded minified conductor highlight')
        # At magnification, preserve authored channels and ignore arbitrary alpha.
        gpu.uniform('testScale', 0.25)
        gpu.uniform('testOffset', 0)
        gpu.uniform('testMode', 0)
        param(0x0DE1, 0x2800, 0x2600)
        close(gpu.draw(), (1, 1, 1, 1), 'authored base roughness')
        gpu.uniform('materialMapFlags', 0, 0, 1)
        gpu.texture(5, (float('nan'),) * 4)
        close(gpu.draw(), (1, 0.8, 0, 1), 'ordinary textures keep the matte dielectric default')
        print('PASS: ORM minification, trilinear/subtexel stability, GGX, base data and absent-map fallback;', gpu.renderer)


if __name__ == '__main__':
    run()
