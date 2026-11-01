#!/usr/bin/env python3
"""Production haze integration and daylight composition; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest

SOURCE = (Path(__file__).resolve().parents[1] /
          'client/shaders/scene_lighting/opengl_fragment.glsl').read_text().replace(
    'CENTROID_ VARYING_ mediump vec2 varTexCoord;',
    '#define varTexCoord (gl_FragCoord.xy/64.0)')
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def close(actual, expected, label, tolerance=3e-5):
    assert max(abs(a-b) for a, b in zip(actual, expected)) < tolerance, (label, actual, expected)


def integration():
    fragment = SOURCE.replace('void main(void)', 'void unusedMain(void)') + '''
uniform vec3 testSegment;
void main() {
 gl_FragColor = vec4(hazeDensityIntegral(testSegment.x,testSegment.y,testSegment.z));
}
'''
    with ShaderTest(fragment) as gpu:
        for start, end, distance in ((0, 0, 100), (-200, -10, 400), (0, 640, 640),
                                     (-640, 640, 1280), (640, -640, 1280),
                                     (1000, 1000.001, 500), (1e-4, -1e-4, 0.01),
                                     (5000, 6000, 1500), (640, 0, 1000)):
            # Independent midpoint quadrature, not a copy of the GLSL formula.
            n = 20000
            reference = sum(math.exp(-max(start+(end-start)*(i+0.5)/n, 0)/640)
                            for i in range(n))*distance/n
            gpu.uniform('testSegment', start, end, distance)
            close(gpu.draw(), (reference,)*4, 'integrated/clamped height density',
                  max(4e-4, reference*3e-6))
        print('PASS: haze integral matches independent quadrature, including sea-level crossings;', gpu.renderer)


def composition():
    with ShaderTest('#define ENABLE_ATMOSPHERE\n'+SOURCE) as gpu:
        gpu.sampler('texture0', 0);gpu.texture(0, (0.4, 0.5, 0.6, 0.7))
        gpu.sampler('texture1', 1)
        near, far = 1, 2000
        a, b = (far+near)/(far-near), -2*far*near/(far-near)
        gpu.matrix('inverseProjection', [1,0,0,0,0,1,0,0,0,0,0,1/b,0,0,1,-a/b])
        gpu.matrix('inverseView', IDENTITY)
        gpu.uniform('cameraPosition', 0, 0, 0)
        gpu.uniform('fogColor', 0.2, 0.3, 0.4, 1)
        gpu.uniform('sceneParams', 0.0002, 0, 0, 0)
        gpu.uniform('surfaceLight', 0, 0, 1, 1)
        gpu.uniform('surfaceLightColor', 1, 0.7, 0.45)
        gpu.uniform('atmosphereEnabled', 1)

        def depth(z):
            gpu.texture(1, ((a+b/z)*0.5+0.5, 0, 0, 1))

        depth(10)  # One node; preserve nearby texture contrast.
        near_color = gpu.draw()
        close(near_color, (0.4,0.5,0.6,0.7), 'one-node detail preservation', 0.002)
        depth(600)
        distant = gpu.draw()
        assert max(abs(x-y) for x,y in zip(near_color,distant)) > 0.01
        gpu.uniform('sceneParams', 0, 0, 0, 0)
        close(gpu.draw(), (0.4,0.5,0.6,0.7), 'density zero preserves source')
        gpu.uniform('sceneParams', 0.0002, 0, 0, 0)
        gpu.uniform('atmosphereEnabled', 0)
        close(gpu.draw(), (0.4,0.5,0.6,0.7), 'underwater/solid bypass')
        gpu.uniform('atmosphereEnabled', 1)
        gpu.uniform('surfaceLight', 0, 0, 1, 0)
        dark = gpu.draw()
        gpu.uniform('surfaceLightColor', 20, 20, 20)
        close(gpu.draw(), dark, 'zero/hidden/horizon source has no directional haze')
        gpu.uniform('surfaceLightColor', 1, 0.7, 0.45)
        previous = dark
        for i in range(1,101):
            gpu.uniform('surfaceLight', 0, 0, 1, i/100)
            current = gpu.draw()
            assert max(abs(x-y) for x,y in zip(current,previous)) < 0.002
            previous = current
        close(previous, distant, 'continuous daylight transition endpoint')
        # The game's cave sky tint and hidden source cannot create an outdoor
        # brightness floor, even along a long view in a dark interior.
        gpu.texture(0, (0.01,0.01,0.01,0.7))
        gpu.uniform('surfaceLight', 0,0,1,0)
        gpu.uniform('fogColor', 0.005,0.005,0.005,1)
        cave = gpu.draw()
        assert max(cave[:3]) <= 0.01 and max(cave[:3]) < min(distant[:3])*0.05
        print('PASS: actual haze composition, nearby detail, sunset continuity, dark interior and medium guards;',gpu.renderer)


if __name__ == '__main__':
    integration()
    composition()
