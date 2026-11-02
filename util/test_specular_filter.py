#!/usr/bin/env python3
"""Numeric pixel-footprint roughness and actual node light composition; no images/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
import re
from gl_shader_test import ShaderTest
from test_point_materials import FLAGS, MATERIAL, VOXEL, NODES, NODE_COMPOSE, close
from test_dynamic_lighting import atlas, upload, sources, falloff, N

FILTER = re.search(r'materialData\.g = filterMaterialRoughness\([^;]+;', NODES).group()
begin = NODES.index('materialSun = materialSpecular(')
SUN = NODES[begin:NODES.index(';', begin) + 1]
MAIN = '''
uniform float testMode, testRoughness, testCutout;
uniform vec2 testSlope;
uniform vec3 cameraPosition, cameraOffset;
void main() {
 vec3 fNormal = normalize(vec3(testSlope * (gl_FragCoord.xy - vec2(32.5)), 1.0));
 vec3 geometricNormal = vec3(0,0,1), materialFilterNormal = fNormal;
 if (testMode > 2.5 && testMode < 3.5)
  fNormal = readMaterialNormal(geometricNormal, vec3(gl_FragCoord.xy / 64.0,0),
   gl_FragCoord.xy / 64.0, materialFilterNormal);
 if (testMode > 3.5) { geometricNormal = fNormal; materialFilterNormal = vec3(0,0,1); }
 vec3 materialData = vec3(1.0, testRoughness, 1.0);
 float materialMipVariance = 0.0;
''' + FILTER + '''
 if (testMode > 2.5) { gl_FragColor = vec4(materialData.g, materialFilterNormal.x, fNormal.x, 1); return; }
 // A neighboring cutout lane must participate in derivatives before discard.
 if (testCutout > 0.5 && gl_FragCoord.x > 33.0) discard;
 vec3 materialSun = vec3(0), materialPoint = vec3(0);
 vec3 surfaceView = vec3(0,0,1), surfaceLightColor = vec3(1), surfaceSunVisibility = vec3(1);
 vec4 surfaceLight = vec4(0,0,1,1);
 float naturalShare = 1.0;
 vec3 f0 = vec3(0.04), dayLight = vec3(1), shadow_color = vec3(0);
 float adjusted_night_ratio = 0.0, shadow_int = 0.0, f_adj_shadow_strength = 1.0;
 if (testMode < 0.5) { gl_FragColor = vec4(vec3(materialData.g),1); return; }
 if (testMode < 1.5) {
''' + SUN + '''
  gl_FragColor = vec4(materialSun,1); return;
 }
 vec3 worldPosition = vec3(40,40,80), vNormal = vec3(0,0,1);
 vec4 base = vec4(0.8,0.4,0.2,1), col = vec4(0,0,0,0.4), fogColor = vec4(0);
 float nightRatio = 0.0;
 float nativeSky = 1.0;
 bool authoredMaterial = true;
''' + NODE_COMPOSE + '''
 gl_FragColor = col;
}
'''


def filtered_roughness(roughness, sx, sy):
    variance = min(sum(2 - 2 / math.sqrt(1 + slope * slope) for slope in (sx, sy)) / 12, 0.25)
    return min(max(roughness, 0.045) ** 4 + variance, 1) ** 0.25


def run():
    # Production cutout code must remain after the filter and retain pre-crack alpha.
    assert NODES.index('float cutoutAlpha = base.a') < NODES.index('base = mix(base, crack, crack.a)')
    assert NODES.index(FILTER) < NODES.index('if (cutoutAlpha == 0.0)')
    assert NODES.index(FILTER) < NODES.index('if (cutoutAlpha < 0.5)')
    assert 'surfaceRoughness = materialData.g;' in NODES
    assert 'dielectricHighlight(fNormal, surfaceView, surfaceLight.xyz, surfaceRoughness)' in NODES
    with ShaderTest(FLAGS + MATERIAL + VOXEL + MAIN) as gpu:
        gpu.sampler('texture2', 2)
        gpu.sampler('texture4', 4)
        gpu.uniform('materialMapFlags', 1, 0, 1)
        gpu.texture(4, (0.5, 0.5, 1, 1))
        gpu.uniform('voxelParams', 1, 1, 0, N)
        gpu.uniform('voxelOrigin', 0, 0, 0)
        gpu.uniform('cameraPosition', 40, 40, 140)
        gpu.uniform('cameraOffset', 0, 0, 0)
        gpu.uniform('testCutout', 0)
        gpu.uniform('testMode', 0)
        upload(gpu, atlas())
        sources(gpu, [((4, 4, 14), (2, 2, 2))])
        for roughness in (0, 0.1, 0.5, 1, 2):
            gpu.uniform('testRoughness', roughness)
            previous = 0
            for sx, sy in ((0, 0), (0.1, 0), (0.1, 0.2), (1, 1), (100, 100)):
                gpu.uniform('testSlope', sx, sy)
                expected = filtered_roughness(roughness, sx, sy)
                close(gpu.draw(), (expected, expected, expected, 1), 'pixel-footprint normal variance')
                assert previous <= expected <= 1
                previous = expected
        gpu.uniform('testRoughness', 0.1)
        for slope in (0, 0.1, 0.5, 2):
            gpu.uniform('testSlope', slope, 0)
            roughness = filtered_roughness(0.1, slope, 0)
            gpu.uniform('testMode', 1)
            peak = min(32, 0.04 / (4 * math.pi * roughness ** 4))
            close(gpu.draw(), (peak, peak, peak, 1), 'filtered actual directional GGX',
                  tol=max(0.00002, peak * 0.000002))
            gpu.uniform('testMode', 2)
            irradiance = 2 * falloff(6)
            expected = tuple((irradiance * min(32, v ** 2.2 / (4 * math.pi * roughness ** 4))) ** (1 / 2.2)
                             for v in (0.8, 0.4, 0.2)) + (0.4,)
            close(gpu.draw(), expected, 'filtered actual local conductor composition')
        gpu.uniform('testSlope', 0.5, 0.5)
        gpu.uniform('testMode', 1)
        solid = gpu.draw()
        gpu.uniform('testCutout', 1)
        close(gpu.draw(), solid, 'cutout neighbor retains footprint filtering')
        gpu.uniform('testCutout', 0)
        gpu.uniform('testMode', 3)
        for slope in (0, 0.1, 0.5, 2):
            pixels = []
            for y in range(64):
                for x in range(64):
                    normal = (slope * (x - 32), slope * (y - 32), 1)
                    length = math.sqrt(sum(v * v for v in normal))
                    pixels.extend(tuple(v / length * 0.5 + 0.5 for v in normal) + (1,))
            gpu.texture(4, pixels)
            for strength in (0, 0.5, 1, 2):
                gpu.uniform('materialMapFlags', 1, 0, strength)
                expected = filtered_roughness(0.1, slope * strength, slope * strength)
                close(gpu.draw(), (expected, 0, 0, 1), 'sampled tangent normal variance and map strength')
        gpu.uniform('materialMapFlags', 0, 0, 1)
        gpu.texture(4, (float('nan'),) * 4)
        close(gpu.draw(), (0.1, 0, 0, 1), 'missing map does not sample invalid variance')
        gpu.uniform('testMode', 4)
        gpu.uniform('testSlope', 0.5, 0.5)
        expected = filtered_roughness(0.1, 0.5, 0.5)
        close(gpu.draw(), (expected, 0, 0, 1), 'independent geometric-normal variance')
        print('PASS: flat roughness, monotonic/bounded pixel variance, directional/local GGX, '
              'conductor composition, cutout ordering, sampled normals/map strength and missing-map guards;', gpu.renderer)


if __name__ == '__main__':
    run()
