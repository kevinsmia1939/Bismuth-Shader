#!/usr/bin/env python3
"""Actual sloping-water photon solver and solved-path visibility; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from gl_shader_test import ShaderTest
from test_water_volume import WAVES, VOLUME, cells, close, AIR, SOLID, WATER

FIELD = '''
#define ENABLE_WATER_VOLUME
uniform vec2 testGradient;
uniform float testCurvature, testOffset, testVertical;
float waterWaveHeight(vec3 p, vec3 waves) {
 vec2 q = p.xz - vec2(75.0);
 return waves.x * clamp(testOffset + dot(testGradient,q) + testCurvature*dot(q,q) + testVertical*(p.y-90.0), -5.0, 0.0);
}
'''
MAIN = '''
uniform float testMode;
uniform vec3 testPosition, testSurface;
uniform vec2 testSlope;
void main() {
 if (testMode < 0.5) {
  vec3 rest = vec3(0); vec2 slope = vec2(0);
  bool valid = waterRestSurface(testPosition,rest,slope);
  gl_FragColor = valid ? vec4(slope,rest.y,1) : vec4(0); return;
 }
 if (testMode < 1.5) {
  vec3 animated = vec3(0);
  bool valid = waterAnimatedSurface(testSurface,testSlope,animated);
  gl_FragColor = valid ? vec4(animated,1) : vec4(0); return;
 }
 if (testMode < 2.5) {
  vec3 solved; float focus = waterFocusing(testPosition,testSurface,testSlope,solved);
  gl_FragColor = vec4(focus,solved); return;
 }
 if (testMode < 3.5) {
  gl_FragColor = vec4(waterCausticNormal(testSurface,testSlope),1); return;
 }
 if (testMode < 4.5) {
  gl_FragColor = vec4(applyWaterCaustics(vec3(0.5),testPosition,vec3(0,1,0),0.0,vec3(1)),1); return;
 }
 // Compare the initial search and solved visibility without bypassing production helpers.
 vec3 start = testPosition + vec3(0,0.1,0);
 vec3 up = -refract(-waterLight.xyz,vec3(0,1,0),1.0/1.333);
 float exit; vec4 seed = traceWaterVolume(start,up,waterVolumeParams.z,exit,true);
 vec3 rest,solved,animated; vec2 slope;
 if (exit < 0.0 || !waterRestSurface(start+up*exit,rest,slope)) { gl_FragColor=vec4(0); return; }
 waterFocusing(testPosition,rest,slope,solved);
 if (!waterAnimatedSurface(solved,slope,animated)) { gl_FragColor=vec4(0); return; }
 vec3 delta=animated-start; float distance=length(delta);
 vec4 path=traceWaterVolume(start,delta/distance,distance-0.1,exit,true);
 gl_FragColor=vec4(seed.x,path.x,path.z,distance);
}
'''


def setup(gpu):
    gpu.sampler('texture6', 6)
    gpu.uniform('waterVolumeOrigin', 0, 0, 0)
    gpu.uniform('waterAbsoluteOrigin', 0, 0, 0)
    gpu.uniform('waterVolumeParams', 1, 16, 240, 1)
    gpu.uniform('waterWaves', 1, 20, 0)
    gpu.uniform('waterLight', 0, 1, 0, 1)
    gpu.uniform('waterLightColor', 1, 1, 1)
    gpu.uniform('waterMediumParams', 0, 0, 0, 0)
    gpu.uniform('testGradient', 0, 0)
    gpu.uniform('testCurvature', 0)
    gpu.uniform('testOffset', -0.1)
    gpu.uniform('testVertical', 0)
    gpu.uniform('testPosition', 75, 55, 75)
    gpu.uniform('testSurface', 75, 92, 75)
    gpu.uniform('testSlope', 0.2, -0.2)
    gpu.uniform('testMode', 0)


def upload(gpu, function):
    gpu.texture(6, cells(16, function), width=32, height=256)


def test_interfaces():
    with ShaderTest(FIELD + WAVES[WAVES.index('// Plane of'):] + VOLUME + MAIN) as gpu:
        setup(gpu)
        flow = (240/255, 0.7, 0, 0.4, 0.7, 0.9, 0.5, 0.7)
        pool = lambda x,y,z: flow if y == 9 else (WATER if 1 <= y < 9 else AIR)
        upload(gpu, pool)
        gpu.uniform('testPosition', 75, 91.9, 75)
        close(gpu.draw(), (0.2,-0.2,92,1), 'waving sloped-flow exit recovers its rest plane')
        gpu.uniform('testMode', 1)
        close(gpu.draw(), (75,91.9,75,1), 'sloped flow root projects onto the actual displaced mesh')
        gpu.uniform('testSlope', 0.4, -0.2)
        close(gpu.draw(), (0,0,0,0), 'a root cannot extend its plane into another slope')
        gpu.uniform('testSlope', 0.2, -0.2)
        gpu.uniform('testSurface', 75, 91, 75)
        close(gpu.draw(), (0,0,0,0), 'a root cannot extend to a different liquid level')
        gpu.uniform('testMode', 0)
        for material in ((224/255,) + flow[1:], SOLID, (0,0,0,0), AIR):
            upload(gpu, lambda x,y,z: material if y == 9 else pool(x,y,z))
            close(gpu.draw(), (0,0,0,0), 'static flow, opaque, unknown and absent interfaces reject caustic roots')
        # Nonplanar flow has a different rest plane on each actual mesh triangle.
        corners = (0.2, 0.8, 0.6, 0.4)
        nonplanar = flow[:4] + corners
        upload(gpu, lambda x,y,z: nonplanar if (x,y,z) == (7,9,7) else AIR)
        gpu.uniform('testPosition', 67.5, 89.4, 67.5)
        close(gpu.draw(), (0.6,0.4,89.5,1), 'lower flowing triangle rest slope')
        gpu.uniform('testPosition', 72.5, 90.4, 72.5)
        close(gpu.draw(), (-0.2,-0.4,90.5,1), 'upper flowing triangle rest slope')
        print('PASS: displaced flow/source rest planes, both triangles and invalid/cross-face roots;', gpu.renderer)


def test_photon_map():
    with ShaderTest(FIELD + WAVES[WAVES.index('// Plane of'):] + VOLUME + MAIN) as gpu:
        setup(gpu)
        gpu.uniform('waterWaves', 0, 20, 0)
        gpu.uniform('testMode', 2)
        for gx,gz in ((0,0), (0.2,-0.2), (-0.4,0.1)):
            for light in ((0,1,0), (0.3,math.sqrt(0.87),0.2)):
                gpu.uniform('testSlope', gx,gz)
                gpu.uniform('waterLight', *light, 1)
                normal = (-gx,1,-gz)
                length = math.sqrt(sum(v*v for v in normal))
                normal = tuple(v/length for v in normal)
                dot = -sum(n*l for n,l in zip(normal,light))
                eta = 1/1.333
                k = 1-eta*eta*(1-dot*dot)
                ray = tuple(-eta*l-(eta*dot+math.sqrt(k))*n for n,l in zip(normal,light))
                jacobian = 1-(ray[0]*gx+ray[2]*gz)/ray[1]
                incident = (light[1]-gx*light[0]-gz*light[2])/light[1]
                focus = min(4,incident/abs(jacobian))
                result = gpu.draw()
                close(result[:1], (focus,), 'analytic planar Snell photon density', 0.001)
                # The recovered rest point must remain on the same affine plane.
                close(result[2:3], (92+gx*(result[1]-75)+gz*(result[3]-75),), 'Newton solve follows the rest slope', 0.001)
        gpu.uniform('waterWaves', 1,20,0)
        gpu.uniform('testMode', 3)
        gpu.uniform('testSlope', 0.2,-0.2)
        gpu.uniform('testVertical', 0.2)
        gpu.uniform('testOffset', -2)
        # Wave Y derivatives follow each sloped rest coordinate (chain rule).
        normal = (-0.24,1,0.24)
        length = math.sqrt(sum(v*v for v in normal))
        close(gpu.draw(), tuple(v/length for v in normal)+(1,), 'normal includes sloped wave sampling height')
        print('PASS: analytic planar photon flux, oblique incidence, sloped Newton solve and wave chain rule;', gpu.renderer)


def test_solved_visibility():
    with ShaderTest(FIELD + WAVES[WAVES.index('// Plane of'):] + VOLUME + MAIN) as gpu:
        setup(gpu)
        gpu.uniform('waterWaves', 4,20,0)
        gpu.uniform('testGradient', 0.3,0)
        gpu.uniform('testOffset', -1)
        gpu.uniform('testPosition', 76,25,76)
        pool = lambda x,y,z: WATER if 1 <= y <= 9 else AIR
        upload(gpu, pool)
        gpu.uniform('testMode', 4)
        clear = gpu.draw()
        assert max(abs(v-0.5) for v in clear[:3]) > 0.01, ('unblocked solved caustic must modulate the receiver',clear)
        gpu.uniform('testMode', 5)
        complete = gpu.draw()
        assert complete[0] > 20 and abs(complete[1]-(complete[3]-0.1)) < 0.01, complete
        gpu.uniform('testMode', 2)
        gpu.uniform('testSurface', 76,95,76)
        gpu.uniform('testSlope', 0,0)
        focused = gpu.draw()
        gpu.uniform('testMode', 1)
        gpu.uniform('testSurface', *focused[1:])
        animated = gpu.draw()
        cosine = (animated[1]-25.1)/complete[3]
        gpu.uniform('testMode', 4)
        gpu.uniform('waterMediumParams', 0,1,0,0)
        expected = tuple(0.5*(1+(focused[0]-1)*cosine*math.exp(-coefficient*0.98*complete[1]/10))**(1/2.2)
                         for coefficient in (0.32,0.085,0.035))+(1,)
        close(gpu.draw(), expected, 'RGB attenuation uses solved liquid length and receiver direction')
        gpu.uniform('waterMediumParams', 0,0,0,0)
        upload(gpu, lambda x,y,z: (224/255,1,0,0.4) if y==12 else pool(x,y,z))
        close(gpu.draw(), (0.5,0.5,0.5,1), 'another water layer on the air-side ray rejects single-interface caustics')
        upload(gpu, pool)
        gpu.uniform('testMode', 5)
        for obstacle in (SOLID,(0,0,0,0)):
            upload(gpu, lambda x,y,z: obstacle if (x,y,z)==(7,5,8) else pool(x,y,z))
            blocked = gpu.draw()
            close(blocked[:1],complete[:1], 'obstacle leaves the initial search ray open')
            assert blocked[2] < blocked[3]-1, ('actual solved ray hits the obstacle',blocked)
            gpu.uniform('testMode', 4)
            close(gpu.draw(), (0.5,0.5,0.5,1), 'solid/unknown on solved path rejects caustic leakage')
            gpu.uniform('testMode', 5)
        upload(gpu, lambda x,y,z: AIR if x==7 else pool(x,y,z))
        separated = gpu.draw()
        assert separated[1] < separated[3]-1, ('actual solved ray contains a dry gap', separated)
        gpu.uniform('testMode', 4)
        close(gpu.draw(), (0.5,0.5,0.5,1), 'solved path cannot cross a dry gap')
        print('PASS: actual solved-ray wall/unknown/dry-gap rejection with an open search ray;', gpu.renderer)


def test_flow_application():
    with ShaderTest(FIELD + WAVES[WAVES.index('// Plane of'):] + VOLUME + MAIN) as gpu:
        setup(gpu)
        flow = (240/255,0.7,0,0.4,0.7,0.9,0.5,0.7)
        pool = lambda x,y,z: flow if (x,y,z)==(7,9,7) else (WATER if 1<=y<9 else AIR)
        upload(gpu, pool)
        gpu.uniform('testPosition', 70,55,70)
        gpu.uniform('testMode', 4)
        gpu.uniform('testCurvature', -0.002)
        focused = gpu.draw()
        assert max(abs(v-0.5) for v in focused[:3]) > 0.001, ('waving sloped flow must receive caustics',focused)
        gpu.uniform('waterMediumParams', 0,1,0,0)
        absorbed = gpu.draw()
        assert all(abs(v-0.5) < abs(f-0.5) for v,f in zip(absorbed[:3],focused[:3])), ('flow path attenuates caustics',absorbed,focused)
        gpu.uniform('waterVolumeOrigin', -2000,0,3000)
        gpu.uniform('testPosition', -1930,55,3070)
        close(gpu.draw(), absorbed, 'flow caustics survive camera-origin rebasing',0.001)
        gpu.uniform('waterVolumeOrigin', 0,0,0)
        gpu.uniform('testPosition', 70,55,70)
        static = (224/255,) + flow[1:]
        upload(gpu, lambda x,y,z: static if (x,y,z)==(7,9,7) else pool(x,y,z))
        close(gpu.draw(), (0.5,0.5,0.5,1), 'static overlayer rejects an unsupported second interface')
        print('PASS: actual sloped-flow caustic composition, path absorption, origin rebasing and static fallback;',gpu.renderer)


if __name__ == '__main__':
    test_interfaces()
    test_photon_map()
    test_solved_visibility()
    test_flow_application()
