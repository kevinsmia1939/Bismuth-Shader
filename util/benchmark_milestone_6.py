#!/usr/bin/env python3
"""Matched ABBA whole-client costs for milestone 6 at the fixed 1080p baseline."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    'falloff': (['glowing_cave'], {'voxel_light_soft_falloff': 'false'}),
    'foliage': (['forest'], {'enable_translucent_foliage': 'false'}),
    'grain': (['surface_materials'], {'enable_material_sparkle': 'false'}),
    # This measures the complete camera-effects path, not the arithmetic cost
    # of the tone/exposure fixes in isolation. All material/lighting additions
    # remain enabled in both camera conditions.
    'camera': (['forest', 'sunset_river', 'glowing_cave', 'underwater'],
               {'antialiasing': 'none', 'enable_auto_exposure': 'false',
                'enable_bloom': 'false', 'tone_mapping': 'false',
                'enable_camera_vignette': 'false'}),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(output):
    result = []
    for case, (scenes, _) in CASES.items():
        for scene in scenes:
            measurements = {}
            for condition in ('on', 'off'):
                records = []
                for path in sorted((output/case).glob(f'*-{condition}-balanced-1/result.json')):
                    record = json.loads(path.read_text())
                    record['path'] = str(path.relative_to(output))
                    records.append(record)
                assert len(records) == 2, (case, condition, 'Two validated repeats are required')
                samples = [next(v for v in record['results'] if v['scene'] == scene) for record in records]
                frames = sum(v['frames'] for v in samples)
                seconds = sum(v['seconds'] for v in samples)
                measurements[condition] = {
                    'frames': frames, 'seconds': seconds, 'fps': frames/seconds,
                    'mean_ms': seconds*1000/frames,
                    'mean_ms_repeats': [v['seconds']*1000/v['frames'] for v in samples],
                    'p95_ms_range': [min(v['p95_ms'] for v in samples), max(v['p95_ms'] for v in samples)],
                    'records': [record['path'] for record in records],
                }
            result.append({'case': case, 'scene': scene, **measurements,
                           'enabled_minus_control_ms': measurements['on']['mean_ms']-measurements['off']['mean_ms']})
    (output/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    lines = ['# Milestone 6 matched frame costs', '',
             '1080p, view distance 96, balanced preset; ON/OFF/OFF/ON order, two repeats per condition.', '',
             '| Effect | Scene | Enabled FPS | Control FPS | Enabled minus control ms |',
             '| --- | --- | ---: | ---: | ---: |']
    for row in result:
        lines.append(f'| {row["case"]} | {row["scene"]} | {row["on"]["fps"]:.1f} | '
                     f'{row["off"]["fps"]:.1f} | {row["enabled_minus_control_ms"]:+.3f} |')
    lines += ['', 'Camera compares the complete TAA/exposure/bloom/tone/vignette path with its disabled control.',
              'It does not isolate the cost of individual stability fixes. Small or negative deltas can reflect run variation.',
              'The final 60 FPS preset budget remains milestone 7. Raw frame logs, settings and GPU state accompany every run.', '']
    (output/'README.md').write_text('\n'.join(lines))
    return result


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=args.resume)
    original, surface = args.world.resolve(), args.surface_world.resolve()
    for world in (original, surface):
        assert (world/'graphics-scenes.json').is_file() and (world/'map.sqlite').is_file(), world
    pack = (ROOT/'textures/bismuth-minetest-game').resolve()
    environment = os.environ.copy()
    environment.setdefault('__GL_SHADER_DISK_CACHE', '1')
    environment.setdefault('__GL_SHADER_DISK_CACHE_PATH', str(ROOT/'cache/bismuth-gl'))
    plan = {'binary_sha256': digest(ROOT/'bin/luanti'),
            'shader_sha256': hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'client/shaders').rglob('*.glsl')))).hexdigest(),
            'world_map_sha256': digest(original/'map.sqlite'), 'surface_map_sha256': digest(surface/'map.sqlite'),
            'world_manifest_sha256': digest(original/'graphics-scenes.json'),
            'surface_manifest_sha256': digest(surface/'graphics-scenes.json'),
            'profile_sha256': digest(ROOT/'misc/graphics-balanced.conf'),
            'pack_sha256': {p.name: digest(p) for p in sorted(pack.iterdir()) if p.is_file()},
            'duration': args.duration, 'warmup': args.warmup,
            'order': ['on', 'off', 'off', 'on'], 'cases': CASES}
    # JSON turns tuple-based case definitions into arrays; normalize before
    # comparing a resumed plan with its serialized identity.
    plan = json.loads(json.dumps(plan))
    if (output/'plan.json').exists():
        assert json.loads((output/'plan.json').read_text()) == plan, 'Resume inputs changed'
    else:
        (output/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    for case, (scenes, controls) in CASES.items():
        directory = output/case
        directory.mkdir(exist_ok=args.resume)
        target = surface if case == 'grain' else original
        if not (directory/'prepared-world').exists():
            (directory/'prepared-world').symlink_to(target, target_is_directory=True)
        else:
            assert (directory/'prepared-world').resolve() == target
        for index, condition in enumerate(('on', 'off', 'off', 'on'), 1):
            label = f'{index:02}-{condition}'
            command = [sys.executable, str(ROOT/'util/benchmark_graphics.py'), 'run',
                       '--output', str(directory), '--profiles', 'balanced', '--repeats', '1',
                       '--warmup', str(args.warmup), '--duration', str(args.duration),
                       '--timeout', str(args.timeout), '--label', label, '--resume', '--scenes', *scenes,
                       '--set', 'texture_path='+str(pack)]
            if condition == 'off':
                for key, value in controls.items():
                    command += ['--set', key+'='+value]
            print(f'Measuring {case}: {index}/4 {condition}; scenes={scenes}', flush=True)
            with (directory/(label+'-run.log')).open('a') as log:
                result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
            assert result.returncode == 0, f'Inspect {directory/(label+"-run.log")}'
    assert digest(original/'map.sqlite') == plan['world_map_sha256']
    assert digest(surface/'map.sqlite') == plan['surface_map_sha256']
    summarize(output)
    print('PASS: matched milestone 6 costs; '+str(output/'summary.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world', type=Path)
    parser.add_argument('surface_world', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--warmup', type=float, default=8)
    parser.add_argument('--duration', type=float, default=12)
    parser.add_argument('--timeout', type=float, default=900)
    run(parser.parse_args())
