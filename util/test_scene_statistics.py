#!/usr/bin/env python3
"""Verify the production scalar scene reduction against independent RGB means."""
# SPDX-License-Identifier: LGPL-2.1-or-later
from pathlib import Path
from gl_shader_test import ShaderTest


def run():
    source=(Path(__file__).resolve().parents[1]/'client/shaders/scene_statistics/opengl_fragment.glsl').read_text()
    patterns=[[(0,0,0)]*144,[(0.2,0.4,0.8)]*144,
              [(1,0,0) if i%2 else (0,0.5,0.8) for i in range(144)],
              [(4,2,1) if i==71 else (0.01,0.02,0.03) for i in range(144)]]
    with ShaderTest(source,size=1) as gpu:
        gpu.sampler('texture0',0)
        for pixels in patterns:
            data=[v for rgb in pixels for v in (*rgb,1)]
            gpu.texture(0,data,width=16,height=9,linear=True)
            linear=[[c**2.2 for c in rgb] for rgb in pixels]
            mean=[sum(rgb[c] for rgb in linear)/144 for c in range(3)]
            peak=max(sum(v*w for v,w in zip(rgb,(0.2126,0.7152,0.0722))) for rgb in linear)
            actual=gpu.draw()
            assert max(abs(a-b) for a,b in zip(actual,[*mean,peak]))<max(3e-5,peak*3e-6),(actual,mean,peak)
        print('PASS: scalar scene statistics, black/constant/colored/HDR probes, linear mean and sampled peak;',gpu.renderer)


if __name__=='__main__': run()
