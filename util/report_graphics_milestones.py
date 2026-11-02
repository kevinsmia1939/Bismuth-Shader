#!/usr/bin/env python3
"""Audit and export native replay and matched local-light timing evidence."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from benchmark_graphics import ROOT, digest, summarize
from test_graphics_milestones import audit


def shader_hash(with_paths):
    result=hashlib.sha256()
    for path in sorted((ROOT/'client/shaders').rglob('*.glsl')):
        if with_paths: result.update(str(path.relative_to(ROOT)).encode()+b'\0')
        result.update(path.read_bytes())
    return result.hexdigest()


def archive(source,destination):
    destination.mkdir(parents=True,exist_ok=True)
    for name in ('client.log','frames.csv','scene.csv','client.conf','launch.conf','result.json','environment.json','scenes.json'):
        path=source/name
        if not path.is_file(): continue
        if name.endswith(('.csv','.log')):
            with path.open('rb') as data, (destination/(name+'.gz')).open('wb') as target:
                with gzip.GzipFile(filename='',mode='wb',fileobj=target,mtime=0) as compressed:
                    shutil.copyfileobj(data,compressed)
        else: shutil.copy2(path,destination/name)


def report(args):
    replay=args.replay.resolve();timings=args.timings.resolve();out=args.destination.resolve()
    environment=json.loads((replay/'environment.json').read_text())
    assert environment['binary_sha256']==digest(ROOT/'bin/luanti'), 'Replay binary differs from the current build'
    assert environment['shader_sha256']==shader_hash(False), 'Replay shaders changed'
    assert environment['fixture_sha256']==digest(ROOT/'util/graphics_acceptance/init.lua'), 'Replay fixture changed'
    assert environment['config_sha256']==digest(replay/'launch.conf'), 'Replay launch config changed'
    assert environment['saved_config_sha256']==digest(replay/'client.conf'), 'Replay saved config changed'
    phases=audit((replay/'client.log').read_text(),replay/'frames.csv',replay/'scene.csv')
    assert phases==json.loads((replay/'results.json').read_text()), 'Replay result no longer matches raw evidence'
    records=[]
    for label in ('balanced','control'):
        for repeat in (1,2):
            directory=timings/f'{label}-balanced-{repeat}'
            record=json.loads((directory/'result.json').read_text())
            assert record['binary_sha256']==environment['binary_sha256'], 'Mixed binaries'
            assert record['shader_sha256']==shader_hash(True), 'Mixed shaders'
            assert record['config_sha256']==digest(directory/'client.conf'), 'Timing config changed'
            assert record['profile_sha256']==digest(ROOT/'misc/graphics-balanced.conf'), 'Balanced preset changed'
            assert record['fixture_sha256']==digest(ROOT/'util/graphics_benchmark/init.lua'), 'Timing fixture changed'
            assert record['scene_manifest_sha256']==digest(timings/'scenes.json'), 'Timing scenes changed'
            assert record['scenes'] is None
            assert record['overrides']==([] if label=='balanced' else ['enable_voxel_lighting=false'])
            config=(directory/'client.conf').read_text()
            assert 'benchmark_scene_log' not in config and 'benchmark_frame_progress' not in config, 'Readback/progress instrumentation must be off during timings'
            samples=summarize((directory/'client.log').read_text(),directory/'frames.csv',args.duration)
            assert samples==record['results'], 'Timing results do not match raw frames'
            record['condition']=label;records.append(record)
    assert digest(timings/'prepared-world/map.sqlite')==environment['source_map_sha256'], 'Input world changed'
    assert digest(timings/'scenes.json')==digest(replay/'scenes.json'), 'Replay and timing scene manifests differ'
    rows=[]
    for scene in ('forest','sunset_river','glowing_cave','underwater'):
        row={'scene':scene}
        for condition in ('balanced','control'):
            samples=[s for r in records if r['condition']==condition for s in r['results'] if s['scene']==scene]
            row[condition]={'fps':sum(s['frames'] for s in samples)/sum(s['seconds'] for s in samples),
                            'frames':sum(s['frames'] for s in samples),'seconds':sum(s['seconds'] for s in samples)}
            for metric in ('fps','median_ms','p95_ms','p99_ms'):
                row[condition][metric+'_range']=[min(s[metric] for s in samples),max(s[metric] for s in samples)]
        row['added_mean_frame_ms']=1000/row['balanced']['fps']-1000/row['control']['fps']
        rows.append(row)
    out.mkdir(parents=True,exist_ok=True)
    archive(replay,out/'raw/native')
    (out/'raw/native/results.json').write_text(json.dumps(phases,indent=2)+'\n')
    for condition in ('balanced','control'):
        for repeat in (1,2):
            name=f'{condition}-balanced-{repeat}'
            archive(timings/name,out/'raw'/name)
    validation=out/'validation';validation.mkdir(exist_ok=True)
    for name in ('build','unit'):
        shutil.copy2(Path(str(args.validation_prefix)+'-'+name+'.log'),validation/(name+'.log'))
    assert 'Unit Test Results: PASSED' in (validation/'unit.log').read_text()
    for backend in ('native','legacy','mesa'):
        for name in ('scene_statistics','atmosphere','soft_shadows','water_reflections','water_refraction',
                     'water_volume','dynamic_lighting','point_materials','surface_directional','fog_denoise'):
            path=Path(f'{args.validation_prefix}-{name}-{backend}.log')
            text=path.read_text()
            assert 'PASS:' in text and 'Traceback' not in text, path
            shutil.copy2(path,validation/path.name)
    # This standalone shadowed-fog fixture intentionally uses GLSL 120.
    for backend in ('native','mesa'):
        path=Path(f'{args.validation_prefix}-volumetric_fog-{backend}.log')
        text=path.read_text()
        assert 'PASS:' in text and 'Traceback' not in text, path
        shutil.copy2(path,validation/path.name)
    sources=list((ROOT/'client/shaders').rglob('*.glsl'))+list((ROOT/'src/client/render').glob('*.cpp'))+list((ROOT/'src/client/render').glob('*.h'))
    sources += [ROOT/p for p in ('src/client/game.cpp','src/client/shadows/dynamicshadows.cpp',
                                 'src/client/shadows/shadow_basis.h','util/graphics_acceptance/init.lua',
                                 'util/graphics_benchmark/init.lua','misc/graphics-balanced.conf')]
    source_hashes={str(p.relative_to(ROOT)):digest(p) for p in sorted(sources)}
    metadata={'replay':environment,'runs':records,'world_preparation':json.loads((timings/'source.json').read_text()),
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True)),
              'source_files':source_hashes,
              'protocol':{'resolution':[1920,1080],'view_distance_nodes':96,'fov':70,'warmup_seconds':12,
                          'duration_seconds':args.duration,'order':['balanced1','control1','control2','balanced2'],
                          'vsync':False,'frame_cap':1000,'scene_readback':False}}
    (out/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'timings.json').write_text(json.dumps(rows,indent=2)+'\n')
    (out/'native.json').write_text(json.dumps(phases,indent=2)+'\n')
    shutil.copy2(timings/'scenes.json',out/'scenes.json')
    shutil.copy2(ROOT/'misc/graphics-balanced.conf',out/'graphics-balanced.conf')
    def span(values): return f'{values[0]:.2f}–{values[1]:.2f}'
    lines=['# Milestones 2–4: validation and lighting cost','',
           f'CPU: {metadata["world_preparation"]["cpu"]}. GPU/driver: {environment["gpu"].split(", ")[0]}, {environment["gpu"].split(", ")[1]}.',
           'Native VoxeLibre replay: eleven phases at 640×360 and a 30 FPS cap, with scalar scene readback.',
           'Timing comparison: 1920×1080, view distance 96, FOV 70°, VSync off, 1000 FPS cap; no readback or progress logging.',
           'Both timing conditions use the same binary, shaders, preset and frozen terrain. The control overrides only `enable_voxel_lighting=false`.',
           'Order: balanced, control, control, balanced. Each scene settles for 12 seconds and samples for 12 seconds.',
           'Startup/compilation and incomplete/spanning frames are excluded. Whole-client timing includes the local server, driver and presentation.','',
           '| Scene | Balanced FPS (range) | Control FPS (range) | Added mean frame ms |',
           '| --- | ---: | ---: | ---: |']
    for row in rows:
        a,b=row['balanced'],row['control']
        lines.append(f'| {row["scene"]} | {a["fps"]:.1f} ({span(a["fps_range"])}) | {b["fps"]:.1f} ({span(b["fps_range"])}) | {row["added_mean_frame_ms"]:+.2f} |')
    lines+=['','FPS combines frame counts and sampled durations, not instantaneous FPS. The cost difference covers the entire local-light path (worker, direct lights and bounce), not diffuse GI alone or isolated GPU execution. Run-to-run variation remains visible in the ranges.','',
            '| Scene | Condition | Median ms range | p95 ms range | p99 ms range |',
            '| --- | --- | ---: | ---: | ---: |']
    for row in rows:
        for condition in ('balanced','control'):
            data=row[condition]
            lines.append(f'| {row["scene"]} | {condition} | {span(data["median_ms_range"])} | {span(data["p95_ms_range"])} | {span(data["p99_ms_range"])} |')
    lines+=['','The proposed full-renderer budget is 60 FPS with p95 ≤22.2 ms. Its final preset/performance gate belongs to milestone 7.','']
    for row in rows:
        a=row['balanced'];passed=a['fps']>=60 and a['p95_ms_range'][1]<=22.2
        lines.append(f'- {row["scene"]}: {"meets" if passed else "misses"} the proposed budget.')
    lines+=['','## Native transition checks','',
            'Statistics sample a fixed 16×9 grid of the composed scene before TAA/exposure. Only mean linear RGB and sampled peak luminance leave the GPU. No images or input-device events are produced.',
            'The replay requires real frame coverage, completed-client warmup, correct source/medium states, darker caves, warm lamp brightening/removal and no frame-to-frame sampled mean-luminance jump ≥0.1 linear white. Removed lamps must return the sampled scene to darkness for three consecutive frames within one second. These scalar probes detect broad brightness failures; per-pixel numeric shader tests cover reflection edges, shorelines and the TIR limit. They do not establish visual parity with another shader pack.','',
            '| Phase | Completed frames | Mean luminance | Largest adjacent-sample luminance change |',
            '| --- | ---: | ---: | ---: |']
    for p in phases: lines.append(f'| {p["id"]} | {p["frames"]} | {p["mean_luminance"]:.6f} | {p["max_frame_luminance_change"]:.6f} |')
    by_id={p['id']:p for p in phases}
    lines+=['',f'Placed-glowstone removal reached three consecutive dark samples in {by_id["cave_removed"]["clear_latency_ms"]:.1f} ms; held-torch removal took {by_id["held_removed"]["clear_latency_ms"]:.1f} ms.']
    lines+=['','The controlled replay covers forest rotation past the shadow-frustum recapture threshold, sunset, river motion, entry/exit, underwater torch, placed glowstone and held-lamp removal.',
            'The Release build and C++ suite passed. [Validation logs](validation) include production-shader numeric checks on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330.',
            'Exact launch/saved configs, raw CSV/logs and per-run records are in [raw](raw). Hardware, binary/shader/source hashes and protocol are in [environment.json](environment.json).',
            'The initial [Milestone 1 baseline](../graphics-baseline/README.md) predates these changes. Interrupted earlier runs are excluded.','',
            'Reproduce the replay with `util/test_graphics_milestones.py`; prepare/measure terrain with `util/benchmark_graphics.py`. Export this report with `util/report_graphics_milestones.py --replay ... --timings ... --validation-prefix ... --destination ...`.','']
    (out/'README.md').write_text('\n'.join(lines))
    hashes={str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='sha256.json'}
    (out/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(f'Audited and exported evidence to {out}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('replay','timings','destination','validation-prefix'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--duration',type=float,default=12)
    report(parser.parse_args())
