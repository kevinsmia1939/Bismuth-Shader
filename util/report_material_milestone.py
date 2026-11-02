#!/usr/bin/env python3
"""Re-audit and archive the material milestone's numeric/runtime/performance evidence."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from audit_material_runtime import audit as audit_runtime
from benchmark_graphics import ROOT, digest, summarize
from test_graphics_milestones import audit as audit_native


def report(args):
    validation=args.validation.resolve();native=args.native.resolve();performance=args.performance.resolve()
    records=json.loads((performance/'material-comparison.json').read_text())
    expected=['material-on-a','material-off-a','material-off-b','material-on-b']
    assert [r['condition'] for r in records]==expected, 'Expected repeated enabled/disabled/disabled/enabled runs'
    scenes=json.loads((native/'scenes.json').read_text())
    assert scenes['game']=='minetest', 'Milestone 5 targets native Minetest Game terrain'
    replay=audit_native((native/'client.log').read_text(),native/'frames.csv',native/'scene.csv')
    assert replay==json.loads((native/'results.json').read_text()), 'Native results disagree with raw evidence'
    assert 'Material maps: normal=0 ORM=1' in (native/'client.log').read_text()
    runtime={}
    for name in ('runtime-core','runtime-legacy','runtime-forward-base','runtime-disabled'):
        text=(validation/(name+'.log')).read_text()
        assert 'Material shading integration: PASS' in text, name
        runtime[name]=audit_runtime(text)
    numeric=[]
    for driver in ('nvidia330','nvidia120','mesa330'):
        for suite in ('material_maps','specular_filter','normal_mipmaps','orm_mipmaps',
                      'point_materials','native_emission','surface_directional','minetest_materials'):
            file=validation/f'{driver}-{suite}.log'
            text=file.read_text()
            assert 'PASS:' in text and not any(error in text for error in ('Traceback','AssertionError','FAIL:')), file
            numeric.append(file)
    assert '0 / 353 failed individual tests' in (validation/'cpp.log').read_text()
    assert '54 test cases' in (validation/'cpp.log').read_text()
    assert 'All tests passed' in (validation/'uploads.log').read_text()
    assert 'GLSL shader program failed' not in (validation/'uploads.log').read_text()
    assert 'PASS: native copies preserve' in (validation/'benchmark-runner.log').read_text()
    pack=ROOT/'textures/bismuth-minetest-game'
    pack_hash={p.name:digest(p) for p in sorted(pack.iterdir()) if p.is_file()}
    environment=json.loads((native/'environment.json').read_text())
    assert environment['texture_pack_sha256']==pack_hash, 'Material pack changed after replay'
    assert digest(ROOT/'bin/luanti')==environment['binary_sha256'], 'Current executable differs from replay'
    assert digest(ROOT/'util/graphics_acceptance/init.lua')==environment['fixture_sha256']
    assert digest(ROOT/'util/graphics_test_game/init.lua')==environment['game_adapter_sha256']
    shaders=sorted((ROOT/'client/shaders').rglob('*.glsl'))
    assert hashlib.sha256(b''.join(p.read_bytes() for p in shaders)).hexdigest()==environment['shader_sha256']
    timing_shader_hash=hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes() for p in shaders)).hexdigest()
    for record in records:
        directory=performance/(record['condition']+'-balanced-1')
        assert digest(directory/'launch.conf')==record['launch_config_sha256']
        assert digest(directory/'client.conf')==record['config_sha256']
        settings=dict(line.split('=',1) for line in (directory/'launch.conf').read_text().splitlines()
                      if '=' in line and not line.lstrip().startswith('#'))
        settings={k.strip():v.strip() for k,v in settings.items()}
        assert settings['enable_material_shading']==str(record['materials_enabled']).lower()
        for key,value in {'screen_w':'1920','screen_h':'1080','fov':'70','viewing_range':'96'}.items():
            assert settings[key]==value, (key,settings[key])
        assert not settings.get('benchmark_scene_log'), 'Scene readback must be absent during timing'
        assert record['game']=='minetest'
        assert record['profile_sha256']==digest(ROOT/'misc/graphics-balanced.conf')
        assert record['fixture_sha256']==digest(ROOT/'util/graphics_benchmark/init.lua')
        assert record['shader_sha256']==timing_shader_hash
        assert record['binary_sha256']==environment['binary_sha256']
        assert record['game_adapter_sha256']==environment['game_adapter_sha256']
        assert record['scene_manifest_sha256']==digest(native/'scenes.json')
        log=(directory/'client.log').read_text()
        actual=summarize(log,directory/'frames.csv',12)
        assert actual==record['results'], 'Timing results disagree with raw frames'
        for error in ('ERROR[','GL_INVALID','failed to generate shaders'):
            assert error not in log, (directory,error)
        if record['materials_enabled']:
            assert 'Material maps: normal=0 ORM=1' in log
        else:
            assert 'Material ORM mipmaps:' not in log and 'Material maps:' not in log

    totals=[]
    for scene in ('forest','sunset_river','glowing_cave','underwater'):
        row={'scene':scene}
        for enabled,label in ((True,'enabled'),(False,'disabled')):
            selected=[s for r in records if r['materials_enabled']==enabled for s in r['results'] if s['scene']==scene]
            assert len(selected)==2
            frames=sum(s['frames'] for s in selected);seconds=sum(s['seconds'] for s in selected)
            row[label]={'frames':frames,'seconds':seconds,'fps':frames/seconds,'mean_ms':seconds*1000/frames,
                        'p95_ms_by_run':[s['p95_ms'] for s in selected]}
        row['added_mean_ms']=row['enabled']['mean_ms']-row['disabled']['mean_ms']
        totals.append(row)

    cave_fps=[s['fps'] for r in records if r['materials_enabled'] for s in r['results'] if s['scene']=='glowing_cave']
    temperatures=[float(next(csv.reader([r[key]]))[2]) for r in records for key in ('gpu_before','gpu_after') if r[key]]

    destination=args.destination.resolve();destination.mkdir(parents=True,exist_ok=False)
    def archive(source,target):
        target=destination/target;target.parent.mkdir(parents=True,exist_ok=True)
        if target.suffix=='.gz':
            with target.open('wb') as output:
                with gzip.GzipFile(fileobj=output,mode='wb',mtime=0) as compressed:compressed.write(source.read_bytes())
        else:shutil.copy2(source,target)
    for file in numeric+[validation/(name+'.log') for name in ('cpp','uploads','build','benchmark-runner',*runtime)]:
        archive(file,Path('validation')/(file.name+'.gz'))
    for file in ('environment.json','results.json','scenes.json','launch.conf','client.conf','client.log','frames.csv','scene.csv'):
        # Preserve the engine's original JSON formatting, including whitespace.
        compressed=file.endswith(('.log','.csv')) or file=='scenes.json'
        archive(native/file,Path('native')/(file+'.gz' if compressed else file))
    for record in records:
        name=record['condition'];directory=performance/(name+'-balanced-1')
        for file in ('result.json','launch.conf','client.conf','client.log','frames.csv'):
            archive(directory/file,Path('timings')/name/(file+'.gz' if file.endswith(('.log','.csv')) else file))
    archive(performance/'source.json',Path('terrain-source.json'))
    archive(performance/'prepared-world/map_meta.txt',Path('map_meta.txt'))
    if args.playground:
        playground=args.playground.resolve()
        assert json.loads((playground/'result.json').read_text())['status']=='PASS'
        for file in ('result.json','launch.conf','client.log','frames.csv'):
            archive(playground/file,Path('playground')/(file+'.gz' if file.endswith(('.log','.csv')) else file))
    (destination/'summary.json').write_text(json.dumps({'timings':totals,'native':replay,'runtime':runtime},indent=2)+'\n')
    # Fingerprint production sources, fixtures, numeric tests and settings without
    # creating a self-reference through this generated evidence directory.
    paths=set()
    for directory in ('src/client','src/test/client','client/shaders','util'):
        paths.update(p for p in (ROOT/directory).rglob('*') if p.suffix in ('.cpp','.h','.glsl','.lua','.py','.sh','.conf'))
    paths.update((ROOT/'misc').glob('graphics-*.conf'));paths.update(p for p in pack.iterdir() if p.is_file())
    (destination/'source-sha256.json').write_text(json.dumps({str(p.relative_to(ROOT)):digest(p) for p in sorted(paths)},indent=2)+'\n')
    lines=['# Milestone 5: measured material response','',
           'Minetest Game is the primary integration target. These runs use fresh native',
           'terrain with seed 13371337 and the optional Bismuth ORM companions. Earlier',
           'VoxeLibre timings describe different terrain and are not a direct comparison.','',
           'The Release build, 353 legacy tests, 54 default Catch cases, actual GL 3/legacy',
           'mip uploads, 24 numeric suite/driver combinations and four runtime configurations',
           'passed. Every runtime material state has at least two completed-client frame',
           'checkpoints. The eleven-stage native replay passed source, medium, brightness',
           'and removal checks. No screenshots or input-device events were generated.','',
           '| Native scene | Materials enabled FPS | Disabled FPS | Added whole-frame mean ms |',
           '| --- | ---: | ---: | ---: |']
    for row in totals:lines.append(f'| {row["scene"]} | {row["enabled"]["fps"]:.1f} | {row["disabled"]["fps"]:.1f} | {row["added_mean_ms"]:+.2f} |')
    lines+=['','Two runs per condition in enabled/disabled/disabled/enabled order. Each scene',
            'has 12 seconds of settling and 12 seconds of measurement at 1920×1080, FOV 70',
            'and view distance 96. The control changes only material shading; both use the',
            'same frozen terrain, balanced effects and texture-pack setting. Scalar scene',
            'readback is disabled during timings. The NVIDIA shader disk cache is enabled',
            'for all timing conditions; compilation/settling are outside measured windows.','',
            'These are whole-client frame-delivery measurements, including submission and',
            'waiting, rather than isolated GPU pass timers. Two repeats still have system',
            'and worker variation. The small negative forest difference is within that',
            'variation. Enabled cave repeats measured '+' and '.join(f'{fps:.1f}' for fps in cave_fps)+' FPS.',
            (f'Run endpoint GPU temperatures ranged from {min(temperatures):g} to {max(temperatures):g} C;'
             if temperatures else 'GPU temperature telemetry was unavailable;'),
            'clocks were not held constant. Treat the added',
            'times as approximate configuration costs. The final preset/performance budget',
            'remains milestone 7. None of these enabled scene averages meets 60 FPS.','',
            'Raw CSV/log bytes are gzip-compressed. Launch settings and settings saved at',
            'shutdown are preserved separately. Source/binary/game/pack hashes and actual',
            'driver names identify the tested state. The native scalar probes do not inspect',
            'every pixel; controlled GLSL patterns cover normal/roughness minification.','',
            'See [scope and reproduction](../graphics-milestone-5.md) for acceptance criteria',
            'and commands. The stopped input world remains local; terrain-source.json records',
            'its fingerprint and the Minetest Game checkout revision.','']
    (destination/'README.md').write_text('\n'.join(lines))
    (destination/'sha256.json').write_text(json.dumps({str(p.relative_to(destination)):digest(p) for p in sorted(destination.rglob('*')) if p.is_file()},indent=2)+'\n')
    print(f'PASS: re-audited material checkpoint and archived evidence in {destination}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('validation','native','performance','destination'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--playground',type=Path)
    report(parser.parse_args())
