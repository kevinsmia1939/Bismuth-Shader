#!/usr/bin/env python3
"""Numeric tests for the actual PCSS GLSL. No image capture or input events."""
# SPDX-License-Identifier: LGPL-2.1-or-later
from pathlib import Path
from gl_shader_test import ShaderTest


def close(actual, expected, label, tolerance=2e-5):
    assert max(abs(a - b) for a, b in zip(actual, expected)) < tolerance, (label, actual, expected)


def run(colored, quality):
    source = Path(__file__).resolve().parents[1] / "client/shaders/common/soft_shadows.glsl"
    fragment = f"#define ENABLE_CONTACT_HARDENING_SHADOWS\n#define SHADOW_FILTER {quality}\n"
    if colored:
        fragment += "#define COLORED_SHADOWS\n"
    fragment += source.read_text() + """
uniform sampler2D testMap;
uniform vec2 testUV;
uniform float testReceiver;
uniform vec4 testWarp;
uniform float testMode;
void main() {
 if (testMode < 0.5) gl_FragColor = contactHardeningShadow(testMap, testUV, testReceiver, testWarp, 128.0);
 else if (testMode < 1.5) gl_FragColor = vec4(softShadowWarp(testUV, testWarp), 0, 1);
 else if (testMode < 2.5) gl_FragColor = vec4(softShadowUnwarp(testUV, testWarp), 0, 1);
 else {
  vec2 uv = gl_FragCoord.xy / 128.0;
  float plane = 0.4 + 0.2 * (uv.x - 0.5) * 2.0;
  gl_FragColor = contactHardeningShadow(testMap, uv, plane, testWarp, 128.0);
 }
}
"""
    with ShaderTest(fragment, size=128) as gpu:
        gpu.sampler("testMap", 0)
        gpu.uniform("testMode", 0)
        gpu.uniform("testWarp", 0, 0, 0, 1)
        gpu.uniform("testUV", 0.5, 0.5)
        gpu.uniform("testReceiver", 0.6)
        def params(slope, distance):
            if quality:
                gpu.uniform("shadowPcssParams", slope, distance)
        if quality:
            gpu.uniform("shadowPcssScale", 100, 20)
        params(0.05, 30)
        gpu.texture(0, (0.4, 0, 1, 0))
        close(gpu.draw(), (1, 0, 0, 0), "uniform opaque occlusion")
        gpu.uniform("testReceiver", 0.3)
        close(gpu.draw(), (0, 0, 0, 0), "receiver before caster")
        gpu.uniform("testReceiver", 0.6)
        gpu.texture(0, (1, 0, 1, 0))
        close(gpu.draw(), (0, 0, 0, 0), "no blockers")
        gpu.uniform("testUV", -0.2, 0.5)
        close(gpu.draw(), (0, 0, 0, 0), "outside shadow map is lit")
        gpu.uniform("testUV", 0.51, 0.5)
        edge = [channel for y in range(128) for x in range(128)
                for channel in ((0.4, 0, 1, 0) if x < 64 else (1, 0, 1, 0))]
        gpu.texture(0, edge)
        gpu.uniform("testReceiver", 0.401)
        near = gpu.draw()[0]
        gpu.uniform("testReceiver", 0.6)
        far = gpu.draw()[0]
        if quality:
            assert near == 0 and 0 < far < 0.5, ("contact hardening at lit edge", near, far)
            gpu.uniform("shadowPcssScale", 200, 40)
            params(0.05, 60)
            close(gpu.draw()[:1], (far,), "world-scale invariant penumbra")
            gpu.uniform("shadowPcssScale", 100, 20)
            params(0.1, 30)
            wider = gpu.draw()[0]
            assert wider >= far, ("light angle widens penumbra", far, wider)
            params(0.05, 1)
            close(gpu.draw(), (0, 0, 0, 0), "limited blocker search")
        else:
            assert near == far == 0, ("filter quality zero remains hard", near, far)
        params(0, 30)
        close(gpu.draw(), (0, 0, 0, 0), "zero angular diameter is hard")
        gpu.uniform("testUV", 0.49, 0.5)
        close(gpu.draw(), (1, 0, 0, 0), "zero-angle shadow side")
        params(0.05, 30)
        gpu.uniform("testUV", 0.5, 0.5)
        if colored:
            # Current shadow map format: RGB transmission packed with radix129.
            packed_red = 128 * 129 * 129
            gpu.texture(0, (1, 0, 0.4, packed_red))
            close(gpu.draw(), (1, 1, 0, 0), "red transparent shadow")
            gpu.texture(0, (0.3, 0, 0.4, packed_red))
            close(gpu.draw(), (1, 0, 0, 0), "opaque caster overrides transparent tint")
            edge = [channel for y in range(128) for x in range(128)
                    for channel in ((1, 0, 0.4, packed_red) if x < 64 else (1, 0, 1, 0))]
            gpu.texture(0, edge)
            gpu.uniform("testUV", 0.51, 0.5)
            mixed = gpu.draw()
            if quality:
                assert 0 < mixed[0] < 0.5, ("colored penumbra coverage", mixed)
                close(mixed[1:], (1, 0, 0), "conditional tint avoids double coverage attenuation")
        if quality:
            # A compressed shadow texture must still filter a circle in world/light space.
            gpu.uniform("testUV", 0.51, 0.5)
            gpu.uniform("testWarp", 0, 0, 0, 1)
            gpu.texture(0, edge if not colored else [channel for y in range(128) for x in range(128)
                for channel in ((0.4, 0, 1, 0) if x < 64 else (1, 0, 1, 0))])
            unwarped = gpu.draw()[0]
            gpu.uniform("testWarp", 0, 0, 0.8, 0.20001)
            gpu.uniform("testUV", 0.5 + 0.01 / (0.02 * 0.8 + 0.20001), 0.5)
            warped = gpu.draw()[0]
            close([warped], [unwarped], "warped-map world-space filter footprint", 0.1)
            gpu.uniform("testMode", 3)
            gpu.uniform("testWarp", 0, 0, 0, 1)
            plane = [channel for y in range(128) for x in range(128)
                     for channel in (0.405 + 0.4 * ((x + 0.5) / 128 - 0.5), 0, 1, 0)]
            gpu.texture(0, plane)
            close(gpu.draw(), (0, 0, 0, 0), "receiver-plane correction prevents sloped self-shadow")
        gpu.uniform("testWarp", 0.2, -0.3, 0.8, 0.20001)
        for position in ((0, 0), (0.2, -0.3), (-0.7, 0.8), (0.9, -0.8), (0.2, 0.6)):
            gpu.uniform("testMode", 1)
            gpu.uniform("testUV", *position)
            uv = gpu.draw()[:2]
            gpu.uniform("testMode", 2)
            gpu.uniform("testUV", *uv)
            close(gpu.draw()[:2], position, "perspective warp inversion", 2e-5)
        print(f"PASS: PCSS quality={quality}, colored={colored}; {gpu.renderer}; "
              f"GLSL {'330 core' if gpu.core_shader else '120'}")


if __name__ == "__main__":
    for quality in (0, 1, 2):
        for colored in (False, True):
            run(colored, quality)
    foliage = "#define ENABLE_CONTACT_HARDENING_SHADOWS\n#define SHADOW_FILTER 2\n"
    foliage += "#define ENABLE_TRANSLUCENT_FOLIAGE\n#define MATERIAL_TYPE 1\n#define TILE_MATERIAL_WAVING_LEAVES 1\n"
    foliage += (Path(__file__).resolve().parents[1] / "client/shaders/common/soft_shadows.glsl").read_text()
    foliage += "uniform float difference; void main(){gl_FragColor=vec4(softShadowOcclusion(difference));}"
    with ShaderTest(foliage) as gpu:
        for delta, expected in ((-0.001, 0), (0, 0), (0.0005, 0.15625),
                                (0.001, 0.5), (0.0015, 0.84375), (0.002, 1)):
            gpu.uniform("difference", delta)
            close(gpu.draw(), (expected,) * 4, "translucent foliage smoothing")
        print("PASS: preserved translucent foliage smoothing")
