#!/usr/bin/env python3
"""Dense production-lighting probes across floor nodes and the finite light range."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import json
import math
from pathlib import Path

from gl_shader_test import ShaderTest
import test_dynamic_lighting as light

MAIN = '''
uniform vec3 testPosition;
uniform float testMode;
void main() {
 vec3 q=testPosition;
 vec3 irradiance;
 if(testMode<0.5)
  irradiance=voxelDynamicIrradiance(q,vec3(0,1,0),vec3(0,1,0),true);
 else
  irradiance=voxelIrradiance(q,vec3(0,1,0),0.0);
 gl_FragColor=vec4(irradiance,1);
}
'''


def probe(gpu, position):
    gpu.uniform('testPosition', *position)
    return gpu.draw()[:3]


def run():
    light.N = 32
    n = light.N
    report = {}
    helper = (Path(__file__).resolve().parents[1] /
              'client/shaders/common/voxel_lighting.glsl').read_text()
    with ShaderTest(light.FLAGS + helper + MAIN) as gpu:
        gpu.sampler('texture2', 2)
        gpu.uniform('voxelParams', 1, 1, 0, n)
        data = light.atlas()
        light.upload(gpu, data)
        gpu.uniform('testMode', 0)
        light.sources(gpu, [((3, 4.6, 4), (2, 1, 0.5))])
        values = [probe(gpu, (3+x/64, 4, 4)) for x in range(16*64+1)]
        red = [v[0] for v in values]
        assert 0 < red[0] <= 0.5, 'Near-source floor must avoid the old clipped hotspot'
        assert all(a >= b-1e-6 for a, b in zip(red, red[1:])), 'Falloff must be monotonic'
        assert red[0]/red[128] < 8, 'First two nodes must avoid the old 18x brightness drop'
        assert max(abs(a-b) for a, b in zip(red, red[1:])) < 0.008, 'Abrupt ground-light step'
        for rgb in values:
            light.close(rgb, (rgb[0], rgb[0]/2, rgb[0]/4), 'Attenuation preserves source hue')
        for boundary in (3.5, 4.5, 5.5, 6.5, 8.5, 12.5):
            a = probe(gpu, (boundary-0.0001, 4, 4))
            b = probe(gpu, (boundary+0.0001, 4, 4))
            assert max(abs(x-y) for x, y in zip(a, b)) < 0.0001, 'Node boundary seam'
        # A source and receiver move across a node boundary with no geometry edit.
        for x in (3.4999, 3.5001):
            light.sources(gpu, [((x, 4.6, 4), (2, 1, 0.5))])
            light.close(probe(gpu, (x+1, 4, 4)), values[64], 'Continuous moving source')
        light.sources(gpu, [((3, 4.6, 4), (2, 1, 0.5)), ((3, 4.6, 4), (2, 1, 0.5))])
        light.close(probe(gpu, (4, 4, 4)), [v*2 for v in values[64]], 'Overlapping lights add linearly')
        light.sources(gpu, [])
        light.close(probe(gpu, (4, 4, 4)), (0, 0, 0), 'Removed light leaves no brightness floor')
        light.sources(gpu, [((3, 4.6, 4), (2, 1, 0.5))])
        for z in range(n):
            for y in range(n):
                light.cell(data, 14, 13, 5, y, z, (1, 1, 1, 0))
        light.upload(gpu, data)
        light.close(probe(gpu, (7, 4, 4)), (0, 0, 0), 'Broader falloff retains solid-wall occlusion')
        light.upload(gpu, light.atlas())
        light.sources(gpu, [((3, 22, 4), (2, 1, 0.5))])
        axial = [probe(gpu, (3, 22-d, 4))[0] for d in
                 (0, 0.999, 1, 1.001, 8, 15.9, 15.99, 16, 16.01)]
        assert all(a >= b for a, b in zip(axial, axial[1:])), axial
        assert axial[-1] == axial[-2] == 0, 'Finite range must remain dark'
        assert 0 < axial[-3] < 1e-7, 'Range must approach zero smoothly'
        left, right = axial[1]-axial[2], axial[2]-axial[3]
        assert abs(left-right) < 1e-6, 'The old one-node derivative kink must be absent'
        report['renderer'] = gpu.renderer
        report['ground'] = [{'offset': x/64, 'rgb': values[x]} for x in
                            (0, 16, 32, 48, 64, 96, 128, 192, 256, 384, 512)]
        report['first_two_nodes_ratio'] = red[0]/red[128]
        report['maximum_step_at_1_64_node'] = max(abs(a-b) for a, b in zip(red, red[1:]))
        print('PASS: dense floor gradient, node/source boundaries, overlap, removal and occlusion;', gpu.renderer)

    # Probe interpolation is also used by static map lamps and the asynchronous
    # moving-light fallback. Populate a known smooth field, independently of the
    # production sampler.
    with ShaderTest('#define ENABLE_VOXEL_LIGHTING\n'+helper+MAIN.replace(
            'irradiance=voxelDynamicIrradiance(q,vec3(0,1,0),vec3(0,1,0),true);',
            'irradiance=vec3(0);')) as gpu:
        gpu.sampler('texture2', 2)
        gpu.uniform('voxelParams', 1, 1, 0, n)
        gpu.uniform('testMode', 1)
        data = light.atlas(13)
        for z in range(n):
            for y in range(n):
                for x in range(n):
                    d = math.sqrt((x-3)**2+(y-4.6)**2+(z-4)**2)
                    value = light.falloff(d)*max(0, (4.6-y)/max(d, 1e-6))
                    light.cell(data, 13, 2, x, y, z, (2*value, value, value/2, 1))
        light.upload(gpu, data, 13)
        values = [probe(gpu, (3+x/64, 4, 4)) for x in range(16*64+1)]
        red = [v[0] for v in values]
        assert red[0]/red[128] < 8
        assert all(a >= b-1e-6 for a, b in zip(red, red[1:]))
        assert max(abs(a-b) for a, b in zip(red, red[1:])) < 0.008
        report['fallback_first_two_nodes_ratio'] = red[0]/red[128]
        print('PASS: static/asynchronous atlas falloff remains continuous across node boundaries;', gpu.renderer)
    with ShaderTest('#define VOXEL_LIGHT_SOFT_FALLOFF 0\n'+light.FLAGS+helper+MAIN) as gpu:
        gpu.sampler('texture2', 2)
        gpu.uniform('voxelParams', 1, 1, 0, n)
        light.upload(gpu, light.atlas())
        gpu.uniform('testMode', 0)
        light.sources(gpu, [((3, 4.6, 4), (2, 1, 0.5))])
        near = probe(gpu, (3, 4, 4))[0]
        far = probe(gpu, (5, 4, 4))[0]
        assert near/report['ground'][0]['rgb'][0] > 3.5, 'Soft core must reduce the actual old hotspot'
        assert near/far > report['first_two_nodes_ratio']*2, 'New floor gradient must improve over the legacy shader'
        report['legacy_first_two_nodes_ratio'] = near/far
        report['legacy_peak'] = near
        print('PASS: disabled soft falloff reproduces legacy lighting; measured near-source gradient improves')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = run()
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
