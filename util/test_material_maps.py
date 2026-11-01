#!/usr/bin/env python3
"""Numeric normal-map and metallic/roughness GLSL tests. No image capture or input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest


def run():
    fragment = "#define ENABLE_MATERIAL_MAPS\n" + (
        Path(__file__).resolve().parents[1] / "client/shaders/common/material_maps.glsl").read_text()
    fragment += """
uniform float testMode;
uniform mat4 testUV;
uniform vec3 testView;
uniform vec3 testLight;
uniform vec3 testF0;
uniform float testRoughness;
uniform float testAO;
uniform float testEmission;
void main() {
 vec2 coordinate = gl_FragCoord.xy / 64.0;
 vec2 uv = (testUV * vec4(coordinate, 0.0, 1.0)).xy;
 vec3 p = vec3(coordinate * 2.0 - 1.0, 0.0);
 vec3 normal = readMaterialNormal(vec3(0.0, 0.0, 1.0), p, uv);
 vec3 orm = readMaterialORM(uv, 0.8);
 vec3 result;
 if (testMode < 0.5) result = normal;
 else if (testMode < 1.5) result = orm;
 else if (testMode < 2.5) result = materialSpecular(vec3(0,0,1), testView, testLight, testRoughness, testF0);
 else if (testMode < 3.5) result = materialEnvironment(vec3(0,0,1), testView, testF0, testRoughness, testAO, vec3(0.5), vec3(1.0));
 else result = composeMaterialLighting(vec3(0.25,0.1,0.05), vec3(0.0), vec3(0.0), 1.0, testEmission);
 gl_FragColor = vec4(result, 1.0);
}
"""
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    def close(actual, expected, label, tolerance=2e-5):
        assert max(abs(a - b) for a, b in zip(actual[:3], expected)) < tolerance, (label, actual, expected)

    with ShaderTest(fragment) as gpu:
        gpu.sampler("texture4", 4)
        gpu.sampler("texture5", 5)
        gpu.matrix("testUV", identity)
        gpu.uniform("testView", 0, 0, 1)
        gpu.uniform("testLight", 0, 0, 1)
        gpu.uniform("testRoughness", 0.5)
        gpu.uniform("testF0", 0.04, 0.04, 0.04)
        gpu.uniform("testAO", 1)
        gpu.uniform("materialMapFlags", 1, 1, 1)
        gpu.texture(4, (0.8, 0.5, 0.9, 0))
        gpu.texture(5, (0.3, 0.25, 0.8, 0))
        gpu.uniform("testMode", 0)
        close(gpu.draw(), (0.6, 0, 0.8), "tangent-space normal / ignored alpha")
        mirrored = identity[:]
        mirrored[0] = -1
        gpu.matrix("testUV", mirrored)
        close(gpu.draw(), (-0.6, 0, 0.8), "mirrored UV")
        rotated = identity[:]
        rotated[0], rotated[1], rotated[4], rotated[5] = 0, 1, -1, 0
        gpu.matrix("testUV", rotated)
        close(gpu.draw(), (0, -0.6, 0.8), "rotated UV")
        degenerate = identity[:]
        degenerate[0] = degenerate[5] = 0
        gpu.matrix("testUV", degenerate)
        close(gpu.draw(), (0, 0, 1), "degenerate derivative guard")
        gpu.matrix("testUV", identity)
        gpu.uniform("materialMapFlags", 1, 1, 0)
        close(gpu.draw(), (0, 0, 1), "zero map strength")
        gpu.uniform("materialMapFlags", 1, 1, 1)
        gpu.uniform("testMode", 1)
        close(gpu.draw(), (0.3, 0.25, 0.8), "linear ORM channels / ignored alpha")
        gpu.texture(5, (-1, 0, 2, 1))
        close(gpu.draw(), (0, 0.045, 1), "ORM bounds")
        gpu.texture(4, (float("nan"),) * 4)
        gpu.texture(5, (float("nan"),) * 4)
        gpu.uniform("materialMapFlags", 0, 0, 1)
        close(gpu.draw(), (1, 0.8, 0), "unbound ORM fallback")
        gpu.uniform("testMode", 0)
        close(gpu.draw(), (0, 0, 1), "unbound normal guard")
        gpu.uniform("testMode", 2)
        expected = 0.04 / (4 * math.pi * 0.5 ** 4)
        close(gpu.draw(), (expected,) * 3, "normal incidence GGX dielectric")
        gpu.uniform("testF0", 0.8, 0.2, 0.05)
        close(gpu.draw(), tuple(c / (4 * math.pi * 0.5 ** 4) for c in (0.8, 0.2, 0.05)),
              "colored conductor reflectance")
        gpu.uniform("testRoughness", 1)
        close(gpu.draw(), tuple(c / (4 * math.pi) for c in (0.8, 0.2, 0.05)), "roughness response")
        gpu.uniform("testLight", 0, 0, -1)
        close(gpu.draw(), (0, 0, 0), "below-surface light")
        gpu.uniform("testLight", 0, 0, 1)
        gpu.uniform("testView", 0, 0, -1)
        close(gpu.draw(), (0, 0, 0), "below-surface view")
        view, light = (0.6, 0, 0.8), (0, 0.8, 0.6)
        gpu.uniform("testView", *view)
        gpu.uniform("testLight", *light)
        first = gpu.draw()
        gpu.uniform("testView", *light)
        gpu.uniform("testLight", *view)
        second = gpu.draw()
        close([v / light[2] for v in first[:3]], [v / view[2] for v in second[:3]], "BRDF reciprocity")
        gpu.uniform("testView", 0, 0, 1)
        gpu.uniform("testLight", 0, 0, 1)
        gpu.uniform("testRoughness", 0)
        result = gpu.draw()
        assert all(0 <= v <= 32 for v in result[:3]), ("bounded smooth highlight", result)
        gpu.uniform("testMode", 3)
        gpu.uniform("testAO", 0)
        close(gpu.draw(), (0, 0, 0), "occluded environment")
        gpu.uniform("testAO", 1)
        result = gpu.draw()
        assert result[0] > result[1] > result[2] > 0, ("tinted environment reflection", result)
        gpu.uniform("testMode", 4)
        gpu.uniform("testEmission", 0)
        close(gpu.draw(), (0, 0, 0), "metal diffuse removal")
        gpu.uniform("testEmission", 1)
        close(gpu.draw(), (0.25, 0.1, 0.05), "metallic lamp keeps native emission")
        print(f"Renderer: {gpu.renderer}; GLSL {'330 core' if gpu.core_shader else '120'}")
        print("PASS: material GLSL; high texture units, normal orientation/rotation/mirroring, "
              "derivative guards, linear ORM, absent maps, GGX dielectric/conductor response, "
              "roughness, reciprocity, highlight bounds, occluded environment and preserved emission. No images captured.")


if __name__ == "__main__":
    run()
