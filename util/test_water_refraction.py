#!/usr/bin/env python3
"""Numeric refraction/absorption tests of actual GLSL; no input or image capture."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest
from test_water_volume import cells


def run(volume=False):
    root = Path(__file__).resolve().parents[1] / "client/shaders/common"
    fragment = "#define ENABLE_WATER_REFRACTION\n"
    if volume:
        fragment += "#define ENABLE_WATER_VOLUME\n" + (root/"water_waves.glsl").read_text() + (root/"water_volume.glsl").read_text()
    fragment += (
        Path(__file__).resolve().parents[1] / "client/shaders/common/water_refraction.glsl").read_text()
    fragment += """
uniform sampler2D testColor;
uniform sampler2D testDepth;
uniform float testSurfaceDepth;
uniform float testOpacity;
uniform vec3 testNormal;
uniform vec3 testScatter;
void main() {
 vec2 uv = gl_FragCoord.xy * waterTexelSize;
 vec3 p = waterViewPosition(uv, testSurfaceDepth);
 gl_FragColor = refractWater(testColor, testDepth, p, testNormal, testScatter, testOpacity);
}
"""
    near, far = 1, 1000
    a, b = (far + near) / (far - near), -2 * far * near / (far - near)

    def depth(z):
        return (a + b / z) * 0.5 + 0.5

    def close(actual, expected, label, tolerance=4e-5):
        assert max(abs(v - w) for v, w in zip(actual, expected)) < tolerance, (label, actual, expected)

    with ShaderTest(fragment) as gpu:
        gpu.sampler("testColor", 0)
        gpu.sampler("testDepth", 1)
        if volume:
            gpu.sampler("texture6",6)
            gpu.uniform("waterVolumeParams",0,8,320,0)
            gpu.uniform("waterVolumeOrigin",-30,-30,0)
            gpu.matrix("inverseView",[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])
        gpu.matrix("sceneProjection", [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, a, 1, 0, 0, b, 0])
        gpu.matrix("inverseProjection", [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1 / b, 0, 0, 1, -a / b])
        gpu.uniform("waterTexelSize", 1 / gpu.size, 1 / gpu.size)
        gpu.uniform("waterParams", 1, 1, 320, 0)
        gpu.uniform("testNormal", 0, 0, -1)
        gpu.uniform("testScatter", 0, 0, 0)
        gpu.uniform("testOpacity", 0.5)
        gpu.uniform("testSurfaceDepth", depth(10))
        gpu.texture(0, (0.8, 0.8, 0.8, 1), linear=True)
        gpu.texture(1, (depth(30), 0, 0, 1))
        # Perspective ray at the center pixel has a small, known XY component.
        uv = (gpu.size // 2 + 0.5) / gpu.size
        ray_scale = math.sqrt(1 + 2 * (uv * 2 - 1) ** 2)
        distance = 20 * ray_scale

        def expected(path=distance, strength=1, opacity=0.5, scatter=(0, 0, 0)):
            result = []
            for extinction, equilibrium in zip((0.32, 0.085, 0.035), scatter):
                transmission = math.exp(-extinction * strength * (0.3 + 1.7 * opacity) * path / 10)
                result.append((0.8 ** 2.2 * transmission + equilibrium ** 2.2 * (1 - transmission)) ** (1 / 2.2))
            return result + [1]

        close(gpu.draw(), expected(), "Beer-Lambert transmission")
        result = gpu.draw()
        assert result[0] < result[1] < result[2], "Wavelength-dependent absorption missing"
        gpu.uniform("testOpacity", 1)
        close(gpu.draw(), expected(opacity=1), "texture turbidity")
        gpu.uniform("testOpacity", 0.5)
        gpu.uniform("testScatter", 0.2, 0.3, 0.4)
        close(gpu.draw(), expected(scatter=(0.2, 0.3, 0.4)), "equilibrium color")
        gpu.uniform("testScatter", 0, 0, 0)
        # A foreground rejection tolerance must not turn genuine thin water
        # back into opaque/tinted native rendering at a shoreline. Positive
        # thickness tends continuously to the unattenuated scene sample.
        for thickness in (0.1,0.04,0.01,0.002):
            gpu.texture(1,(depth(10+thickness),0,0,1))
            close(gpu.draw(),expected(path=thickness*ray_scale),
                  'shallow shoreline retains transmission down to the depth-precision limit',0.0001)
        gpu.texture(1,(depth(30),0,0,1))
        gpu.uniform("waterParams", 1, 0, 320, 0)
        close(gpu.draw(), (0.8, 0.8, 0.8, 1), "zero absorption")
        gpu.uniform("waterParams", 1, 1, 5, 0)
        close(gpu.draw(), expected(path=5), "path cap")
        gpu.uniform("waterParams", 1, 1, 320, 0)
        gpu.texture(1, (1, 0, 0, 1))
        close(gpu.draw(), expected(path=320), "deep water sky fallback")
        gpu.texture(1, (depth(5), 0, 0, 1))
        close(gpu.draw(), (0, 0, 0, 0), "foreground rejection")
        gpu.texture(1, (float("nan"),) * 4)
        gpu.texture(0, (float("nan"),) * 4)
        gpu.uniform("waterParams", 0, 1, 320, 1)
        close(gpu.draw(), (0, 0, 0, 0), "unbound material bypass")
        gradient = []
        for _ in range(gpu.size):
            for x in range(gpu.size):
                gradient.extend(((x + 0.5) / gpu.size, 0.4, 0.2, 1))
        gpu.texture(0, gradient, linear=True)
        gpu.texture(1, (depth(30), 0, 0, 1))
        gpu.uniform("waterParams", 1, 0, 320, 0)
        straight = gpu.draw()
        close(straight, (uv, 0.4, 0.2, 1), "straight ray")
        gpu.uniform("testNormal", 0.6, 0, -0.8)
        gpu.uniform("waterParams", 1, 0, 320, 1)
        bent = gpu.draw()
        assert bent[0] < straight[0] - 0.04, ("Snell bending", straight, bent)
        incident = [(uv * 2 - 1) / ray_scale, (uv * 2 - 1) / ray_scale, 1 / ray_scale]
        normal = [0.6, 0, -0.8]
        cosine = sum(v * n for v, n in zip(incident, normal))
        eta = 1 / 1.333
        root = math.sqrt(1 - eta * eta * (1 - cosine * cosine))
        ray = [eta * v - (eta * cosine + root) * n for v, n in zip(incident, normal)]
        hit_x = (uv * 2 - 1) * 10 + ray[0] * 20 / ray[2]
        close(bent, (hit_x / 30 * 0.5 + 0.5, 0.4, 0.2, 1),
              "analytic Snell intersection", tolerance=5e-4)
        close(bent[1:], (0.4, 0.2, 1), "color channels")
        gpu.uniform("testNormal", -0.6, 0, 0.8)
        close(gpu.draw(), bent, "two-sided normal orientation")
        foreground = []
        for _ in range(gpu.size):
            for x in range(gpu.size):
                foreground.extend((depth(5 if x < gpu.size // 2 else 30), 0, 0, 1))
        gpu.texture(1, foreground)
        close(gpu.draw(), straight, "foreground silhouette along refracted ray")
        gpu.texture(1, (depth(30), 0, 0, 1))
        gpu.uniform("waterCameraInside", 1)
        gpu.uniform("testNormal", *normal)
        exiting = gpu.draw()
        eta = 1.333
        root = math.sqrt(1 - eta * eta * (1 - cosine * cosine))
        ray = [eta * v - (eta * cosine + root) * n for v, n in zip(incident, normal)]
        hit_x = (uv * 2 - 1) * 10 + ray[0] * 20 / ray[2]
        close(exiting, (hit_x / 30 * 0.5 + 0.5, 0.4, 0.2, 1),
              "water-to-air Snell intersection", tolerance=5e-4)
        gpu.uniform("testNormal", 0.9, 0, -math.sqrt(1-0.9**2))
        close(gpu.draw(), (0,0,0,0), "total internal reflection has no transmission")
        gpu.uniform("waterParams", 1, 0, 320, 0)
        close(gpu.draw(), straight, "disabled bending preserves straight transmission")
        # At a screen edge, two valid blue samples straddle a red texture strip.
        # A confidence fade must blend the two colors, not sample the intervening
        # UV (which would invent a red shoreline streak). Locate the bent hit
        # independently with analytic Snell refraction onto the depth-30 plane.
        edge_x = 4
        edge_uv = (edge_x+0.5)/gpu.size
        p = [(edge_uv*2-1)*10, (uv*2-1)*10, 10]
        magnitude = math.sqrt(sum(v*v for v in p))
        incident_edge = [v/magnitude for v in p]
        edge_normal = None
        for i in range(2001):
            sx = i/2000
            n = [sx,0,-math.sqrt(1-sx*sx)]
            cos_edge = sum(v*w for v,w in zip(incident_edge,n))
            eta = 1/1.333
            root = math.sqrt(1-eta*eta*(1-cos_edge*cos_edge))
            ray = [eta*v-(eta*cos_edge+root)*w for v,w in zip(incident_edge,n)]
            if ray[2] <= 0: continue
            hit_uv = (p[0]+ray[0]*20/ray[2])/60+0.5
            if 0.024 < hit_uv < 0.026:
                edge_normal = n
                break
        assert edge_normal, 'Independent edge intersection fixture must be reachable'
        strip = [channel for y in range(gpu.size) for x in range(gpu.size)
                 for channel in ((1,0,0,1) if 0.045 < (x+0.5)/gpu.size < 0.06 else (0,0.3,0.8,1))]
        gpu.texture(0,strip,linear=True)
        gpu.texture(1,(depth(30),0,0,1))
        gpu.uniform('waterCameraInside',0)
        gpu.uniform('waterParams',1,0,320,1)
        gpu.uniform('testNormal',*edge_normal)
        close(gpu.draw(x=edge_x),(0,0.3,0.8,1),'edge fallback crossfades radiance, not texture coordinates',0.0002)
        gpu.texture(0,gradient,linear=True)
        for target in (0.05,0.04,0.03,0.025,0.02,0.017,0.016):
            best=None
            for i in range(4001):
                sx=i/4000;n=[sx,0,-math.sqrt(1-sx*sx)]
                c=sum(v*w for v,w in zip(incident_edge,n));eta=1/1.333
                root=math.sqrt(1-eta*eta*(1-c*c))
                ray=[eta*v-(eta*c+root)*w for v,w in zip(incident_edge,n)]
                if ray[2]<=0:continue
                hit=(p[0]+ray[0]*20/ray[2])/60+0.5
                if best is None or abs(hit-target)<abs(best[0]-target):best=(hit,n)
            hit,n=best
            assert abs(hit-target)<0.0004
            confidence=max(0,min(1,(hit-1/gpu.size)/0.04))
            confidence=confidence*confidence*(3-2*confidence)
            red=(edge_uv**2.2*(1-confidence)+hit**2.2*confidence)**(1/2.2)
            gpu.uniform('testNormal',*n)
            close(gpu.draw(x=edge_x),(red,0.4,0.2,1),
                  'refraction continues to the last usable screen segment and fades without a pop',0.0007)
        if volume:
            gpu.uniform("waterCameraInside",0)
            gpu.uniform("waterParams",1,1,320,0)
            gpu.uniform("testNormal",0,0,-1)
            gpu.texture(0,(0.8,0.8,0.8,1),linear=True)
            gpu.uniform("waterVolumeParams",1,8,320,0)
            atlas=cells(8,lambda x,y,z:(1,1,0,0.4) if z==1 else (64/255,0,1,0))
            gpu.texture(6,atlas,width=16,height=64)
            close(gpu.draw(),expected(path=5*ray_scale-0.02),"front transmission stops absorption at rear exit")
            gpu.texture(6,(64/255,0,1,0),width=16,height=64)
            gpu.uniform("waterCameraInside",1)
            close(gpu.draw(),(0.8,0.8,0.8,1),"underwater interface does not absorb the air beyond it")
        print(f"Renderer: {gpu.renderer}; GLSL {'330 core' if gpu.core_shader else '120'}")
        print("PASS: water GLSL; Beer-Lambert/RGB absorption, turbidity, scattered color, "
              "zero absorption, path cap, deep fallback, foreground rejection, binding guard "
              f"Snell entry/exit and TIR; volume={volume}. No images captured.")


if __name__ == "__main__":
    run()
    run(volume=True)
