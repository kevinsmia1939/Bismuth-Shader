#!/usr/bin/env python3
"""Exercise the shipped Minetest Game material bytes through production GLSL."""
# SPDX-License-Identifier: LGPL-2.1-or-later
from pathlib import Path
import struct
import zlib
from gl_shader_test import ShaderTest

ROOT = Path(__file__).resolve().parents[1]


def read_map(name):
    data = (ROOT / 'textures/bismuth-minetest-game' / (name + '_orm.png')).read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    offset, stream = 8, b''
    while offset < len(data):
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        if kind == b'IHDR':
            assert struct.unpack('>IIBBBBB', payload) == (1, 1, 8, 6, 0, 0, 0)
        if kind == b'IDAT':
            stream += payload
        offset += size + 12
    pixel = zlib.decompress(stream)
    assert len(pixel) == 5 and pixel[0] == 0
    return tuple(v / 255 for v in pixel[1:])


def run():
    fragment = '#define ENABLE_MATERIAL_MAPS\n' + (ROOT / 'client/shaders/common/material_maps.glsl').read_text()
    fragment += '''
uniform float testEmission;
void main() {
 vec3 orm = readMaterialORM(vec2(0.5), 0.8);
 vec3 direct = materialSpecular(vec3(0,0,1),vec3(0,0,1),vec3(0,0,1),orm.g,
  mix(vec3(0.04),vec3(0.65,0.5,0.3),orm.b));
 gl_FragColor = vec4(testEmission > 0.5 ?
  composeMaterialLighting(vec3(0.4,0.2,0.1),vec3(0),vec3(0),orm.b,1.0) : direct,1);
}
'''
    with ShaderTest(fragment) as gpu:
        gpu.sampler('texture5', 5)
        gpu.uniform('materialMapFlags', 0, 1, 1)
        gpu.uniform('testEmission', 0)
        peaks = {}
        for name in ('default_stone', 'default_cobble', 'default_steel_block', 'default_gold_block',
                     'default_copper_block', 'default_meselamp', 'default_mese_block'):
            pixel = read_map(name)
            gpu.texture(5, pixel)
            result = gpu.draw()
            assert all(0 <= v <= 32 for v in result[:3]), (name, result)
            peaks[name] = result[0]
            if name in ('default_stone', 'default_cobble'):
                assert pixel[1] > 0.85 and pixel[2] == 0, (name, pixel)
            if name in ('default_steel_block', 'default_gold_block', 'default_copper_block'):
                assert 0.25 < pixel[1] < 0.6 and pixel[2] == 1, (name, pixel)
            if name in ('default_meselamp', 'default_mese_block'):
                gpu.uniform('testEmission', 1)
                assert max(abs(a - b) for a, b in zip(gpu.draw(), (0.4, 0.2, 0.1, 1))) < 1e-6
                gpu.uniform('testEmission', 0)
        matte = max(peaks['default_stone'], peaks['default_cobble'])
        for name in ('default_steel_block', 'default_gold_block', 'default_copper_block'):
            assert peaks[name] > matte * 4, (name, peaks)
        print('PASS: shipped material bytes: matte stone, stronger bounded metals and unchanged lamp emission;', gpu.renderer)
        print('Directional red-channel peaks under identical unit illumination:', peaks)


if __name__ == '__main__':
    run()
