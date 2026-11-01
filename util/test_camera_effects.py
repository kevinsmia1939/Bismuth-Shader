#!/usr/bin/env python3
"""Numeric tests for actual camera GLSL. No image capture or input events."""
# SPDX-License-Identifier: LGPL-2.1-or-later
from pathlib import Path
from gl_shader_test import ShaderTest

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def fragment(name):
    source = (ROOT / "client/shaders" / name / "opengl_fragment.glsl").read_text()
    return source.replace("CENTROID_ VARYING_ mediump vec2 varTexCoord;",
                          "#define varTexCoord (gl_FragCoord.xy / 64.0)")


def close(actual, expected, label, tolerance=2e-5):
    assert max(abs(a - b) for a, b in zip(actual, expected)) < tolerance, (label, actual, expected)


def image(pixel):
    return [c for y in range(64) for x in range(64) for c in pixel(x, y)]


STRIPE = image(lambda x, y: (1 if x == 32 else 0,) * 3 + (0.37,))


def setup(gpu):
    gpu.sampler("texture0", 0)
    gpu.sampler("texture1", 1)
    gpu.uniform("texelSize0", 1/64, 1/64)
    gpu.uniform("cameraDepthJitter", 0, 0)
    gpu.uniform("cameraPixelScale", 1, 1)
    gpu.matrix("cameraInverseProjection", IDENTITY)


def test_motion():
    with ShaderTest(fragment("camera_motion")) as gpu:
        setup(gpu)
        gpu.matrix("cameraReprojection", IDENTITY)
        gpu.matrix("cameraSkyReprojection", IDENTITY)
        gpu.uniform("cameraMotionParams", 1, 0.5, 24, 12)
        gpu.texture(0, STRIPE, linear=True)
        gpu.texture(1, (0.75, 0, 0, 1))
        close(gpu.draw(), (1, 1, 1, 0.37), "stationary camera preserves sharp pixels")
        moved = IDENTITY[:]
        moved[12] = 0.5
        gpu.matrix("cameraReprojection", moved)
        blurred = gpu.draw()
        assert 0.05 < blurred[0] < 0.8, ("camera translation blur", blurred)
        close(blurred[3:], (0.37,), "motion preserves scene alpha")
        moved[12] = 1
        gpu.matrix("cameraReprojection", moved)
        gpu.uniform("cameraMotionParams", 1, 0.25, 24, 12)
        close(gpu.draw(), blurred, "frame-duration normalization")
        gpu.uniform("cameraMotionParams", 1, 0.5, 2, 12)
        clamped = gpu.draw()
        assert clamped[0] > blurred[0], ("bounded shutter length", clamped, blurred)
        gpu.uniform("cameraPixelScale", 2, 2)
        assert gpu.draw()[0] < clamped[0], "maximum blur follows output-pixel scale"
        gpu.uniform("cameraPixelScale", 1, 1)
        for params in ((0, 0.5, 24, 12), (1, 0, 24, 12), (1, 0.5, 0, 12)):
            gpu.uniform("cameraMotionParams", *params)
            gpu.texture(1, (float("nan"),) * 4)
            close(gpu.draw(), (1, 1, 1, 0.37), "cut/zero-strength bypass before depth access")
        gpu.uniform("cameraMotionParams", 1, 0.5, 24, 12)
        gpu.texture(1, (1, 0, 0, 1))
        close(gpu.draw(), (1, 1, 1, 0.37), "sky ignores camera translation")
        gpu.matrix("cameraSkyReprojection", moved)
        assert gpu.draw()[0] < 0.8, "sky follows camera rotation"
        behind = IDENTITY[:]
        behind[15] = -1
        gpu.matrix("cameraReprojection", behind)
        gpu.texture(1, (0.75, 0, 0, 1))
        close(gpu.draw(), (1, 1, 1, 0.37), "behind-camera reprojection bypass")
        gpu.matrix("cameraReprojection", moved)
        gpu.texture(0, (1.2, 0.5, 0.2, 0.37), linear=True)
        close(gpu.draw(0, 0), (1.2, 0.5, 0.2, 0.37), "border normalization / HDR color")
        # A sky pixel may not gather foreground objects during rotational blur.
        gpu.texture(0, image(lambda x, y: ((1, 0, 0, 0.37) if x < 30 else (0, 0, 1, 0.37))))
        gpu.texture(1, image(lambda x, y: ((0.6, 0, 0, 1) if x < 30 else (1, 0, 0, 1))))
        close(gpu.draw(), (0, 0, 1, 0.37), "sky/foreground depth rejection")
        print(f"PASS: camera motion GLSL; {gpu.renderer}; GLSL {'330 core' if gpu.core_shader else '120'}")


def test_dof():
    with ShaderTest(fragment("camera_dof")) as gpu:
        setup(gpu)
        gpu.uniform("cameraDOFParams", 0.5, 0.05, 6)
        gpu.texture(0, STRIPE, linear=True)
        gpu.texture(1, (0.75, 0, 0, 1))
        close(gpu.draw(), (1, 1, 1, 0.37), "focus plane remains sharp")
        for depth in (0.55, 0.99, 1):
            gpu.texture(1, (depth, 0, 0, 1))
            result = gpu.draw()
            assert 0.05 < result[0] < 0.9, ("near/far/sky defocus", depth, result)
            close(result[3:], (0.37,), "DOF preserves scene alpha")
        gpu.texture(1, (0.99, 0, 0, 1))
        normal_scale = gpu.draw()[0]
        gpu.uniform("cameraPixelScale", 2, 2)
        assert gpu.draw()[0] < normal_scale, "DOF radius follows output-pixel scale"
        gpu.uniform("cameraPixelScale", 1, 1)
        gpu.uniform("cameraDOFParams", 0.5, 0.5, 6)
        gpu.texture(1, (0.99, 0, 0, 1))
        close(gpu.draw(), (1, 1, 1, 0.37), "manual sharp range")
        gpu.uniform("cameraDOFParams", 0.5, 0.05, 0)
        gpu.texture(1, (float("nan"),) * 4)
        close(gpu.draw(), (1, 1, 1, 0.37), "zero radius bypass before depth access")
        gpu.uniform("cameraDOFParams", 0.5, 0.05, 6)
        gpu.texture(0, (1.2, 0.5, 0.2, 0.37), linear=True)
        gpu.texture(1, (0.55, 0, 0, 1))
        close(gpu.draw(0, 0), (1.2, 0.5, 0.2, 0.37), "normalized disk at border / HDR color")
        gpu.texture(0, STRIPE, linear=True)
        gpu.texture(1, image(lambda x, y: (0.75 if x == 32 else 0.99, 0, 0, 1)))
        close(gpu.draw(), (1, 1, 1, 0.37), "unjittered focus sample")
        gpu.uniform("cameraDepthJitter", 1/64, 0)
        assert gpu.draw()[0] < 0.9, "TAA-jittered depth coordinate"
        gpu.uniform("cameraDepthJitter", 0, 0)
        gpu.texture(0, image(lambda x, y: ((1, 0, 0, 0.37) if x < 33 else (0, 0, 1, 0.37))))
        gpu.texture(1, image(lambda x, y: ((0.55, 0, 0, 1) if x < 33 else (0.99, 0, 0, 1))))
        result = gpu.draw()
        assert result[0] > 0.95 and result[2] < 0.05, ("foreground silhouette protection", result)
        print(f"PASS: camera DOF GLSL; {gpu.renderer}; GLSL {'330 core' if gpu.core_shader else '120'}")


if __name__ == "__main__":
    test_motion()
    test_dof()
