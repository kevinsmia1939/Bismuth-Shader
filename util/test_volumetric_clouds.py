#!/usr/bin/env python3
"""Numeric cloud transport, atlas, depth composite and TAA checks. No images/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest

ROOT = Path(__file__).resolve().parents[1] / "client/shaders"


def close(actual, expected, label, tolerance=3e-5):
    assert max(abs(a - b) for a, b in zip(actual, expected)) < tolerance, (label, actual, expected)


def transport():
    fragment = (ROOT / "common/volumetric_clouds.glsl").read_text() + """
uniform float testMode;
uniform vec3 testOrigin;
uniform vec3 testRay;
uniform float testDistance;
uniform float testJitter;
void main() {
 if (testMode < 0.5) gl_FragColor = integrateClouds(testOrigin,testRay,testDistance,testJitter);
 else if (testMode < 1.5) gl_FragColor = vec4(vec3(cloudDensity(testOrigin)),1.0);
 else if (testMode < 2.5) gl_FragColor = vec4(vec3(cloudLightTransmission(testOrigin)),1.0);
 else gl_FragColor = vec4(vec3(cloudNoise3D(testOrigin)),1.0);
}
"""
    with ShaderTest(fragment) as gpu:
        gpu.sampler("texture2", 2)
        n = 4
        width, height = n + 2, (n + 2) * n
        gpu.uniform("cloudTextureSize", width, height)
        gpu.texture(2, (0.5, 0.5, 0.5, 1), True, width, height)
        gpu.uniform("cloudLayer", 0, 10, 1, 0.02)
        gpu.uniform("cloudParams", 1, 32, 100, 0)
        gpu.uniform("cloudWind", 0, 0, 0, 0)
        gpu.uniform("cloudLight", 0, 1, 0, 0)
        gpu.uniform("cloudBright", 0, 0, 0)
        gpu.uniform("cloudAmbient", 0.4, 0.3, 0.2)
        gpu.uniform("cloudShadow", 0, 0, 0)
        gpu.uniform("testMode", 0)
        gpu.uniform("testOrigin", 0, 5, 0)
        gpu.uniform("testRay", 0, 0, 1)
        gpu.uniform("testDistance", 20)
        gpu.uniform("testJitter", 0.5)
        transmission = math.exp(-0.02 * 20)
        expected = [c ** 2.2 * (1 - transmission) for c in (0.4, 0.3, 0.2)] + [transmission]
        close(gpu.draw(), expected, "exact homogeneous single scattering")
        for samples, jitter in ((8, 0.1), (64, 0.9)):
            gpu.uniform("cloudParams", 1, samples, 100, 0)
            gpu.uniform("testJitter", jitter)
            close(gpu.draw(), expected, "sample-count/jitter invariance")
        gpu.uniform("cloudParams", 1, 32, 100, 0)
        gpu.uniform("testJitter", 0.5)
        identity = (0, 0, 0, 1)
        gpu.uniform("testOrigin", 0, -10, 0)
        gpu.uniform("testRay", 0, 1, 0)
        gpu.uniform("testDistance", 8)
        close(gpu.draw(), identity, "opaque surface before cloud entry")
        gpu.uniform("testDistance", 30)
        assert gpu.draw()[3] < 0.9, "Upward ray missed cloud slab"
        gpu.uniform("testOrigin", 0, 20, 0)
        gpu.uniform("testRay", 0, -1, 0)
        gpu.uniform("testDistance", 5)
        close(gpu.draw(), identity, "above-layer occlusion")
        gpu.uniform("testDistance", 30)
        assert gpu.draw()[3] < 0.9, "Downward ray missed cloud slab"
        gpu.uniform("testOrigin", 0, -1, 0)
        gpu.uniform("testRay", 0, 0, 1)
        close(gpu.draw(), identity, "parallel ray outside layer")
        gpu.uniform("testOrigin", 0, 5, 0)
        gpu.uniform("testDistance", 20)
        gpu.uniform("cloudParams", 1, 32, 5, 0)
        close(gpu.draw()[3:], (math.exp(-0.02 * 5),), "maximum range")
        gpu.uniform("cloudParams", 1, 32, 100, 0)
        gpu.uniform("testMode", 1)
        gpu.uniform("testOrigin", 0, -1, 0)
        close(gpu.draw(), (0, 0, 0, 1), "below-layer density")
        gpu.uniform("testOrigin", 0, 11, 0)
        close(gpu.draw(), (0, 0, 0, 1), "above-layer density")
        gpu.uniform("testOrigin", 0, 5, 0)
        close(gpu.draw(), (1, 1, 1, 1), "overcast interior density")
        gpu.uniform("cloudLayer", 0, 10, 0, 0.02)
        close(gpu.draw(), (0, 0, 0, 1), "zero game coverage")
        gpu.uniform("testMode", 0)
        gpu.uniform("cloudLayer", 0, 10, 1, 0.2)
        gpu.uniform("cloudBright", 0.8, 0.8, 0.8)
        gpu.uniform("cloudAmbient", 0, 0, 0)
        gpu.uniform("cloudLight", 0, 1, 0, 1)
        gpu.uniform("testOrigin", 0, 2, 0)
        bottom = gpu.draw()
        gpu.uniform("testOrigin", 0, 6, 0)
        top = gpu.draw()
        assert top[0] > bottom[0] > 0, ("self-shadowed cloud lighting", bottom, top)
        close(top[3:], bottom[3:], "equal view extinction independent of sun occlusion")
        gpu.uniform("cloudLight", 0, -1, 0, 1)
        gpu.uniform("testMode", 2)
        gpu.uniform("testOrigin", 0, 2, 0)
        low = gpu.draw()[0]
        gpu.uniform("testOrigin", 0, 8, 0)
        high = gpu.draw()[0]
        assert low > high, ("custom light below layer", low, high)
        gpu.uniform("testMode", 0)
        gpu.texture(2, (float("nan"),) * 4, True, width, height)
        gpu.uniform("cloudParams", 0, 32, 100, 0)
        close(gpu.draw(), identity, "unavailable noise/hidden sky bypass")
        gpu.uniform("cloudParams", 1, 32, 100, 0)
        for layer in ((0, 10, 0, 0.2), (0, 10, 1, 0), (0, 0, 1, 0.2)):
            gpu.uniform("cloudLayer", *layer)
            close(gpu.draw(), identity, "empty medium bypass")
        values = []

        def value(x, y, z):
            return ((x % n + 2 * (y % n) + 3 * (z % n)) % n) / (n - 1)

        for z in range(n):
            for y in range(-1, n + 1):
                for x in range(-1, n + 1):
                    v = value(x, y, z)
                    values.extend((v, v, v, 1))
        gpu.texture(2, values, True, width, height)
        gpu.uniform("testMode", 3)
        # Binary fractions isolate atlas layout from hardware sampler rounding.
        for point in ((0.25, 0.5, 0.75), (-0.25, 3.875, 3.9375), (4.25, 4.5, 4.75)):
            integral = 0
            for z in (0, 1):
                for y in (0, 1):
                    for x in (0, 1):
                        offset = (x, y, z)
                        weight = math.prod((p - math.floor(p)) if d else (1 - p + math.floor(p))
                                           for p, d in zip(point, offset))
                        integral += value(*(math.floor(p) + d for p, d in zip(point, offset))) * weight
            gpu.uniform("testOrigin", *point)
            close(gpu.draw()[:3], (integral,) * 3, "periodic trilinear atlas / slice seam")
        gpu.uniform("testMode", 1)
        gpu.uniform("cloudLayer", 0, 10, 0.7, 0.02)
        gpu.uniform("cloudParams", 1, 32, 100, 0.35)
        gpu.uniform("testOrigin", 50, 5, 60)
        first = gpu.draw()
        gpu.uniform("testOrigin", 1050, 5, -440)
        gpu.uniform("cloudWind", 1000, -500, 0, 0)
        close(gpu.draw(), first, "world/wind translation stability")
        print(f"Renderer: {gpu.renderer}; cloud transport/atlas GLSL {'330 core' if gpu.core_shader else '120'} PASS")


def composite():
    fragment = (ROOT / "cloud_composite/opengl_fragment.glsl").read_text().replace(
        "CENTROID_ VARYING_ mediump vec2 varTexCoord;", "#define varTexCoord (gl_FragCoord.xy / 64.0)")
    near, far = 1, 1000
    a, b = (far + near) / (far - near), -2 * near * far / (far - near)

    def depth(z):
        return (a + b / z) * 0.5 + 0.5

    with ShaderTest(fragment) as gpu:
        for name, unit in (("texture0", 0), ("texture1", 1), ("texture2", 2)):
            gpu.sampler(name, unit)
        gpu.matrix("inverseProjection", [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1 / b, 0, 0, 1, -a / b])
        gpu.uniform("cloudTextureSize", 2, 2)
        gpu.texture(0, (0.4, 0.5, 0.6, 0.7))
        gpu.texture(1, (depth(100), 0, 0, 1))
        gpu.texture(2, (0.1, 0.05, 0.025, 0.5), width=2, height=2)
        expected = [(v ** 2.2 * 0.5 + scatter) ** (1 / 2.2)
                    for v, scatter in zip((0.4, 0.5, 0.6), (0.1, 0.05, 0.025))] + [0.7]
        close(gpu.draw(), expected, "linear scattering composite / original alpha")
        gpu.texture(2, (0, 0, 0, 1), width=2, height=2)
        close(gpu.draw(), (0.4, 0.5, 0.6, 0.7), "empty cloud composite")
        guide = []
        for _ in range(64):
            for x in range(64):
                guide.extend((depth(5 if x < 32 else 100), 0, 0, 1))
        gpu.texture(1, guide)
        gpu.texture(2, [0, 0, 0, 1, 0.2, 0.2, 0.2, 0.2] * 2, width=2, height=2)
        close(gpu.draw(31, 32), (0.4, 0.5, 0.6, 0.7), "foreground edge rejects distant clouds")
        background = [(v ** 2.2 * 0.2 + 0.2) ** (1 / 2.2) for v in (0.4, 0.5, 0.6)] + [0.7]
        close(gpu.draw(32, 32), background, "background edge keeps cloud opacity")
        guide = []
        for _ in range(64):
            for x in range(64):
                guide.extend((depth(5 if x == 32 else 100), 0, 0, 1))
        gpu.texture(1, guide)
        gpu.texture(2, (0.2, 0.2, 0.2, 0.2), width=2, height=2)
        close(gpu.draw(32, 32), (0.4, 0.5, 0.6, 0.7), "thin foreground fallback")
        close(gpu.draw(33, 32), background, "adjacent cloud remains")
        print(f"Renderer: {gpu.renderer}; depth-aware cloud composite PASS")


def temporal():
    fragment = "#define ENABLE_VOLUMETRIC_CLOUDS\n" + (ROOT / "taa/opengl_fragment.glsl").read_text().replace(
        "CENTROID_ VARYING_ mediump vec2 varTexCoord;", "#define varTexCoord (gl_FragCoord.xy / 64.0)")
    with ShaderTest(fragment) as gpu:
        for name, unit in (("texture0", 0), ("texture1", 1), ("texture2", 2), ("texture4", 4)):
            gpu.sampler(name, unit)
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        for name in ("taaReprojection", "taaSkyReprojection", "taaInverseProjection"):
            gpu.matrix(name, identity)
        gpu.uniform("taaParams", 0, 0, 1, 0.95)
        gpu.uniform("texelSize0", 1 / 64, 1 / 64)
        current = []
        for y in range(64):
            for x in range(64):
                v = 0.2 if (x + y) % 2 == 0 else 0.6
                current.extend((v, v, v, 1))
        gpu.texture(0, current)
        gpu.texture(1, (0.4, 0.4, 0.4, 1))
        gpu.texture(2, (0.75, 0, 0, 1))
        gpu.texture(4, (0, 0, 0, 1))
        clear = gpu.draw()
        gpu.texture(4, (0, 0, 0, 0))
        cloudy = gpu.draw()
        assert 0.2 < cloudy[0] < clear[0], ("moving clouds reduce stale history", clear, cloudy)
        close(cloudy[3:], clear[3:], "reactive mask preserves history depth")
        gpu.texture(4, (0, 0, 0, 1))
        gpu.uniform("taaWaterReactive", 1)
        underwater = gpu.draw()
        assert 0.2 < underwater[0] < clear[0], ("underwater caustics reduce stale history", clear, underwater)
        close(underwater[3:], clear[3:], "water reactive history keeps depth")
        print(f"Renderer: {gpu.renderer}; cloud TAA reactive mask PASS")


if __name__ == "__main__":
    transport()
    composite()
    temporal()
    print("Volumetric cloud GPU tests: PASS. No images captured or input sent.")
