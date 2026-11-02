#!/usr/bin/env python3
"""Actual node and camera shaders over a low lamp's floor; numeric scalar probes."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import json
import math
from pathlib import Path

from gl_shader_test import ShaderTest
import test_dynamic_lighting as light
import test_surface_directional as node
from test_fog_denoise import source


def field(dynamic, corrected=True, bounce=False):
    columns = 14 if dynamic else 13
    data = light.atlas(columns)
    for z in range(light.N):
        for y in range(light.N):
            for x in range(light.N):
                if y == 3:
                    for band in range(12):
                        light.cell(data,columns,band,x,y,z,(0,0,0,0))
                    if dynamic:
                        light.cell(data,columns,13,x,y,z,(1,1,1,0))
                elif not dynamic:
                    # The worker's adjacent-floor +Y lobe is evaluated on the
                    # actual exposed face, before albedo and sunlight injection.
                    sample_y = 3.501 if corrected and y == 4 else y
                    delta = (3-x,4-sample_y,4-z)
                    distance = math.sqrt(sum(v*v for v in delta))
                    cosine = 1 if distance < 0.01 else max(0,delta[1]/distance)
                    value = light.falloff(distance)*cosine
                    light.cell(data,columns,2,x,y,z,(2*value,value,value/2,1))
                if bounce and y > 3:
                    light.cell(data,columns,8,x,y,z,(0.002,0.001,0.0005,1))
    return data


def floor(dynamic, corrected=True):
    columns = 14 if dynamic else 13
    flags = '#define ENABLE_VOXEL_LIGHTING\n#define ENABLE_VOXEL_MATERIAL_SPECULAR\n'
    if dynamic:
        flags += '#define ENABLE_VOXEL_DYNAMIC_DIRECT\n#define MAX_VOXEL_DYNAMIC_LIGHTS 8\n'
    helper = (Path(__file__).resolve().parents[1]/'client/shaders/common/voxel_lighting.glsl').read_text()
    fragment = flags+node.source().replace(node.MATERIAL,node.MATERIAL+helper)
    data = field(dynamic,corrected)
    with ShaderTest(fragment) as gpu:
        node.setup(gpu)
        gpu.texture(0,(0.6,0.6,0.6,0.6))
        gpu.uniform('materialMapFlags',0,0,1)
        gpu.sampler('texture2',2)
        light.upload(gpu,data,columns)
        gpu.uniform('voxelOrigin',0,0,0)
        gpu.uniform('voxelParams',1,1,0,light.N)
        gpu.uniform('vNormal',0,1,0)
        gpu.uniform('surfaceLight',0,1,0,0)
        gpu.uniform('nightRatio',1)
        gpu.uniform('fogColor',0.6,0.8,1,1)
        if dynamic:
            light.sources(gpu,[((3,4,4),(2,1,0.5))])
        values = []
        for step in range(16*32+1):
            x = 3+step/32
            gpu.uniform('worldPosition',x*10,35,40)
            gpu.uniform('cameraPosition',x*10,85,-10)
            # Deliberately discontinuous native artificial-light colors must
            # not leave node seams after local light replacement.
            poison = (0.9,0.2,0.4,1) if math.floor(x+0.5)%2 else (0.1,0.8,0.2,1)
            gpu.uniform('varColor',*poison)
            values.append(gpu.draw()[:3])
        if corrected:
            assert min(values[64])>0.01, 'Low lamp must illuminate the floor two nodes away'
            assert max(values[-1])<1e-7, 'Light range must end in darkness'
            assert all(a[0]>=b[0]-1e-6 for a,b in zip(values,values[1:])), 'Complete floor shading must fall smoothly'
            assert max(abs(a[0]-b[0]) for a,b in zip(values,values[1:]))<0.025, 'Native bank or probe interpolation seam'
            # Independently vary the real diffuse-bounce band and its strength.
            light.upload(gpu,field(dynamic,True,True),columns)
            gpu.uniform('worldPosition',70,35,40)
            gpu.uniform('cameraPosition',70,85,-10)
            gpu.uniform('voxelParams',1,1,0.35,light.N)
            bounced = gpu.draw()
            assert all(bounced[c]>values[128][c] for c in range(3)), 'Real indirect contribution must remain visible'
            light.upload(gpu,light.atlas(columns),columns)
            if dynamic:
                light.sources(gpu,[])
            light.close(gpu.draw(),(0,0,0,0.6),'Cleared direct/bounce restores black despite stale native light',1e-7)
        print('PASS: full floor node fragment;', 'dynamic' if dynamic else 'static/fallback',
              'surface corrected',corrected,gpu.renderer)
    return values


def adaptive_exposure(values):
    mean = [sum(rgb[c]**2.2 for rgb in values)/len(values) for c in range(3)]
    with ShaderTest(source('update_exposure')) as gpu:
        gpu.sampler('texture0',0)
        gpu.sampler('texture1',1)
        for key,value in [('luminanceMin',0.005),('luminanceMax',1),('exposureCorrection',0),
                          ('centerWeightPower',1),('compensationFactor',1),
                          ('speedDarkBright',3),('speedBrightDark',1)]:
            gpu.uniform('exposureParams.'+key,value)
        gpu.uniform('animationTimerDelta',1/60)
        ev = 0
        for _ in range(60):
            gpu.texture(0,(ev,ev,ev,1))
            gpu.texture(1,tuple(v*2**ev for v in mean)+(1,))
            ev = gpu.draw()[0]
        return 2**ev


def camera(values):
    factors = [1,adaptive_exposure(values)]
    fragment = '#define ENABLE_TONE_MAPPING 1\n#define ENABLE_AUTO_EXPOSURE\n'+source('second_stage')
    fragment = fragment.replace('VARYING_ float exposure;','uniform float exposure;')
    metrics = []
    with ShaderTest(fragment) as gpu:
        gpu.sampler('texture0',0)
        gpu.uniform('exposureParams.compensationFactor',1)
        gpu.uniform('saturation',1)
        for factor in factors:
            gpu.uniform('exposure',factor)
            output = []
            for rgb in values:
                gpu.texture(0,tuple(rgb)+(1,))
                output.append(gpu.draw()[:3])
            red = [v[0] for v in output]
            assert all(a>=b-1e-6 for a,b in zip(red,red[1:])), 'Final floor gradient must remain monotonic'
            assert max(abs(a-b) for a,b in zip(red,red[1:]))<0.04, 'Abrupt final-image floor step'
            assert 0 < red[64] < red[0] < 1, 'Ground light must retain gradient without clipping'
            assert max(output[-1])<1e-7, 'Exposure must not reveal an unlit floor'
            metrics.append({'exposure_factor':factor,'near_rgb':output[0],'two_nodes_rgb':output[64],
                            'largest_step_1_32_node':max(abs(a-b) for a,b in zip(red,red[1:]))})
    print('PASS: fixed/adaptive exposure and production tone mapping retain the smooth ground gradient')
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    light.N = 32
    dynamic = floor(True)
    static = floor(False)
    legacy = floor(False,False)
    assert max(legacy[64])<1e-7 and min(static[64])>0.01, 'Regression must reproduce the missing floor lobe'
    result = {'dynamic':camera(dynamic),'static_fallback':camera(static),
              'old_air_probe_two_nodes_rgb':legacy[64],'corrected_two_nodes_rgb':static[64]}
    if args.report:
        args.report.write_text(json.dumps(result,indent=2)+'\n')
