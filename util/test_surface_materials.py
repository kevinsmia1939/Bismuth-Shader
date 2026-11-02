#!/usr/bin/env python3
"""Production foliage/grain shading, including real node composition; numeric probes only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
from pathlib import Path

from gl_shader_test import ShaderTest
import test_surface_directional as node
from test_dark_caves import optional
from test_dynamic_lighting import close
import test_dynamic_lighting as lighting

COMMON = (Path(__file__).resolve().parents[1] /
          'client/shaders/common/surface_material.glsl').read_text()


def foliage_samples(enabled, shadows):
    flags = '#define MATERIAL_FOLIAGE 0.5\n'
    if enabled:
        flags += '#define ENABLE_TRANSLUCENT_FOLIAGE\n'
    result = {}
    with ShaderTest(flags+COMMON+node.source(maps=False, shadows=shadows)) as gpu:
        node.setup(gpu, maps=False)
        gpu.texture(0, (0.2, 0.65, 0.15, 0.6))
        gpu.uniform('varColor', 0.7, 0.7, 0.7, 1)
        if shadows:
            node.shadow_setup(gpu)
        for back in (False, True):
            gpu.uniform('surfaceLight', 0, 0, -1 if back else 1, 1)
            for side in (-1, 1):
                gpu.uniform('cameraPosition', 0, 0, side*10)
                for strength in ((0, 0.25, 1) if shadows else (0,)):
                    if shadows:
                        gpu.uniform('cosLight', 0 if back else 1)
                        gpu.uniform('f_shadow_strength', strength)
                        gpu.uniform('adj_shadow_strength', strength)
                    result[back, side, strength] = gpu.draw()
        gpu.uniform('cameraPosition', 0, 0, 10)
        gpu.uniform('surfaceLight', 0, 0, -1, 1)
        if shadows:
            gpu.uniform('cosLight', 0)
            gpu.uniform('f_shadow_strength', 1)
            gpu.uniform('adj_shadow_strength', 1)
            gpu.texture(3, (0.4, 0, 1, 0))
            close(gpu.draw(), (0, 0, 0, 0.6), 'Opaque shadow blocks foliage transmission')
        gpu.uniform('varColor', 0, 0, 0, 1)
        gpu.uniform('fogColor', 0.6, 0.8, 1, 1)
        gpu.uniform('nightRatio', 1)
        close(gpu.draw(), (0, 0, 0, 0.6), 'Unlit foliage cannot glow beneath a bright sky')
        print('PASS: full node foliage, both sides, disabled/partial/full shadows and dark controls;', gpu.renderer)
    return result


def foliage():
    for shadows in (False, True):
        enabled, disabled = foliage_samples(True, shadows), foliage_samples(False, shadows)
        for back, side, strength in enabled:
            lit, base = enabled[back, side, strength], disabled[back, side, strength]
            if (back and side == 1) or (not back and side == -1):
                assert lit[1] > base[1]+0.01, ('Thin sheet must transmit from either side', back, side, strength)
                assert lit[1] > lit[0] and lit[1] > lit[2], 'Leaf tint must remain visible'
            else:
                close(lit, base, 'Front-lit thin sheet retains ordinary response')
            assert lit[3] == base[3], 'Transmission must preserve cutout alpha'
    fragment = '#define ENABLE_TRANSLUCENT_FOLIAGE\n#define MATERIAL_FOLIAGE 0.5\n'+COMMON+'''
uniform vec3 testView;
void main() {gl_FragColor=vec4(foliageTransmission(vec3(0.2,0.65,0.15),
 vec3(0,0,1),normalize(testView),vec3(0,0,-1)),1);}
'''
    with ShaderTest(fragment) as gpu:
        values = []
        for step in range(-100, 101):
            angle = step/1000
            gpu.uniform('testView', math.cos(angle), 0, math.sin(angle))
            values.append(gpu.draw()[1])
        assert max(abs(b-a) for a, b in zip(values, values[1:])) < 0.0005, 'No foliage pop when crossing its plane'
        assert values[-1]-values[0] > 0.01, 'Grazing transmission must still change visibly'
        print('PASS: continuous transmission through a grazing-angle camera sweep;', gpu.renderer)
    # Exercise the actual production discard, including both static and waving
    # materials. No opaque fill may appear in the holes of a leaf or grass tile.
    for kind in ('static', 'leaves', 'grass'):
        flags = '#define ENABLE_TRANSLUCENT_FOLIAGE\n#define MATERIAL_FOLIAGE 0.5\n#define USE_DISCARD_REF\n'
        fragment = node.source(maps=False)
        if kind != 'static':
            fragment = fragment.replace('#define MATERIAL_TYPE 0', '#define MATERIAL_TYPE '+('6' if kind == 'leaves' else '7'))
        with ShaderTest(flags+COMMON+fragment) as gpu:
            node.setup(gpu, maps=False)
            gpu.uniform('surfaceLight', 0, 0, -1, 1)
            gpu.uniform('varColor', 0.7, 0.7, 0.7, 1)
            gpu.texture(0, (0.2, 0.65, 0.15, 0.4))
            gpu.api('glClearColor', None, c.c_float, c.c_float, c.c_float, c.c_float)(0, 0, 0, 0)
            gpu.api('glClear', None, c.c_uint)(0x4000)
            close(gpu.draw(), (0, 0, 0, 0), 'Translucent foliage preserves actual texture holes')
            gpu.texture(0, (0.2, 0.65, 0.15, 0.6))
            assert gpu.draw()[1] > 0.2, 'Visible leaf/grass texels retain lighting'
            print('PASS: actual cutout discard and lit pixels;', kind, gpu.renderer)


GRAIN_MAIN = '''
uniform vec3 testOffset, testView, testLight, testBase;
uniform float testScale;
void main() {
 vec3 position=vec3(gl_FragCoord.x/64.0,0,gl_FragCoord.y/64.0)*testScale+testOffset;
 vec3 normal=vec3(0,1,0);
 surfaceGrain=sampleSurfaceGrain(position,normal,testBase);
 gl_FragColor=vec4(grainResponse(normal,normalize(testView),normalize(testLight)),1);
}
'''


def grain():
    peaks = []
    positions = {}
    for material in (1, 2):
        flags = f'#define ENABLE_MATERIAL_SPARKLE\n#define MATERIAL_SPARKLE {material}\n'
        with ShaderTest(flags+COMMON+GRAIN_MAIN) as gpu:
            gpu.uniform('testOffset', 0, 0, 0)
            gpu.uniform('testScale', 1)
            gpu.uniform('testView', 0, 1, 0)
            gpu.uniform('testLight', 0, 1, 0)
            optional(gpu, 'testBase', 0.95, 0.95, 0.95)
            samples = [(x, y, gpu.draw(x, y)) for y in range(1, 64, 2) for x in range(1, 64, 2)]
            bright = max(samples, key=lambda p: max(p[2][:3]))
            peak = max(bright[2][:3])
            assert 0.001 < peak <= (0.10 if material == 1 else 0.18), ('Missing or excessive glints', material, peak)
            assert sum(max(rgb[:3])>0.001 for _, _, rgb in samples) < len(samples)*0.1, 'Glints must remain sparse'
            x, y, value = bright
            positions[material] = ((x+0.5)/64, (y+0.5)/64)
            close(gpu.draw(x, y), value, 'Stationary grain is deterministic')
            gpu.uniform('testOffset', 1024, 0, 1024)
            close(gpu.draw(x, y), value, 'Origin wrap preserves the same world grain seed', 0.0002)
            gpu.uniform('testOffset', 0, 0, 0)
            gpu.uniform('testLight', 0, -1, 0)
            close(gpu.draw(x, y), (0, 0, 0, 1), 'No glint through the back of a surface')
            gpu.uniform('testLight', 0, 1, 0)
            gpu.uniform('testView', 1, 0.1, 0)
            assert max(gpu.draw(x, y)[:3]) < peak*0.2, 'Glints respond to view direction'
            gpu.uniform('testView', 0, 1, 0)
            gpu.uniform('testScale', 32)
            for px, py, _ in samples[::97]:
                close(gpu.draw(px, py), (0, 0, 0, 1), 'Distant subpixel grains fade instead of aliasing')
            if material == 2:
                gpu.uniform('testScale', 1)
                gpu.uniform('testBase', 0.4, 0.25, 0.1)
                close(gpu.draw(x, y), (0, 0, 0, 1), 'Snowy dirt side artwork does not sparkle')
            peaks.append(peak)
            print('PASS: sparse bounded grain, world anchoring, view dependence, distance filtering and base mask;', material, gpu.renderer)
    assert abs(peaks[0]-peaks[1]) > 0.0001, 'Sand and snow retain distinct responses'
    return positions


def composed_grain_case(material, position, dynamic, voxel):
    x, z = position
    columns = 14 if dynamic else 13
    results = {}
    for enabled in (False, True):
        flags = f'#define MATERIAL_SPARKLE {material}\n#define ENABLE_VOXEL_LIGHTING\n'
        flags += '#define ENABLE_VOXEL_MATERIAL_SPECULAR\n'
        if dynamic:
            flags += '#define ENABLE_VOXEL_DYNAMIC_DIRECT\n#define MAX_VOXEL_DYNAMIC_LIGHTS 8\n'
        if enabled:
            flags += '#define ENABLE_MATERIAL_SPARKLE\n'
        fragment = flags+node.source().replace(node.MATERIAL, node.MATERIAL+COMMON+voxel)
        with ShaderTest(fragment) as gpu:
            node.setup(gpu)
            gpu.uniform('materialMapFlags', 0, 0, 1)
            gpu.texture(0, (0.95, 0.95, 0.95, 0.6))
            gpu.sampler('texture2', 2)
            lighting.upload(gpu, lighting.atlas(columns), columns)
            gpu.uniform('voxelOrigin', -80, -40, -80)
            gpu.uniform('voxelParams', 1, 1, 0, lighting.N)
            gpu.uniform('vNormal', 0, 1, 0)
            gpu.uniform('worldPosition', x*10, 0, z*10)
            gpu.uniform('cameraPosition', x*10, 10, z*10)
            gpu.uniform('varColor', 0.7, 0.7, 0.7, 1)
            gpu.uniform('surfaceLight', 0, 1, 0, 1)
            if dynamic:
                lighting.sources(gpu, [])
            results[enabled, 'sun'] = gpu.draw()
            gpu.uniform('surfaceLight', 0, 1, 0, 0)
            gpu.uniform('varColor', 0, 0, 0, 1)
            gpu.uniform('nightRatio', 1)
            if dynamic:
                lighting.sources(gpu, [((x+8, 7, z+8), (2, 1, 0.5))])
                results[enabled, 'moving'] = gpu.draw()
                lighting.sources(gpu, [])
            # Independent known single-direction probe field for a placed lamp
            # (also the asynchronous moving-light fallback's representation).
            data = lighting.atlas(columns)
            for pz in range(lighting.N):
                for py in range(lighting.N):
                    for px in range(lighting.N):
                        lighting.cell(data, columns, 2, px, py, pz, (0.1, 0.05, 0.025, 1))
                        lighting.cell(data, columns, 3, px, py, pz, (0.15, 0.075, 0.0375, 1))
            lighting.upload(gpu, data, columns)
            results[enabled, 'placed'] = gpu.draw()
            lighting.upload(gpu, lighting.atlas(columns), columns)
            gpu.uniform('fogColor', 0.6, 0.8, 1, 1)
            close(gpu.draw(), (0, 0, 0, 0.6), 'Grain on unlit terrain cannot emit light')
    for light in (('sun', 'moving', 'placed') if dynamic else ('sun', 'placed')):
        before, after = results[False, light], results[True, light]
        assert max(b-a for a, b in zip(before[:3], after[:3])) > 1e-6, ('Missing grain in full node composition', material, light, columns)
        assert max(after[:3]) < 1.0, 'Grain must not clip an ordinary lit surface'
        assert after[3] == before[3], 'Grain must preserve surface alpha'
    print('PASS: full node sand/snow under sun, placed/moving lamps and darkness;', material, 'columns', columns)


def composed_grain(positions):
    voxel = (Path(__file__).resolve().parents[1] /
             'client/shaders/common/voxel_lighting.glsl').read_text()
    for material, position in positions.items():
        for dynamic in (True, False):
            composed_grain_case(material, position, dynamic, voxel)


if __name__ == '__main__':
    foliage()
    composed_grain(grain())
