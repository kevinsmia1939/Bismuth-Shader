#!/usr/bin/env python3
"""Prepare native Minetest Game scenes and measure whole-client frames; legacy VoxeLibre is supported."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import csv
import hashlib
import json
import os
import gzip
import platform
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
PROFILES={'basic':'graphics-basic.conf','quality':'graphics-quality.conf','balanced':'graphics-balanced.conf'}
COMMON='''
video_driver = opengl3
3d_mode = none
screen_w = 1920
screen_h = 1080
fullscreen = true
window_maximized = false
vsync = false
fps_max = 1000
fps_max_unfocused = 1000
pause_on_lost_focus = false
viewing_range = 96
fov = 70
mip_map = true
trilinear_filter = true
bilinear_filter = true
anisotropic_filter = false
enable_sound = false
enable_damage = false
creative_mode = true
time_speed = 0
liquid_update = 1000
active_block_range = 1
movement_gravity = 0
movement_liquid_sink = 0
mcl_mobspawning = false
mcl_weather = false
mobs_spawn = false
mcl_doWeatherCycle = false
show_debug = false
profiler_print_interval = 0
'''


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def gpu_state():
    if not shutil.which('nvidia-smi'): return None
    result=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,temperature.gpu,clocks.gr,clocks.mem,power.draw',
                           '--format=csv,noheader'],text=True,capture_output=True)
    return result.stdout.strip() if result.returncode==0 else result.stderr.strip()


def revision(path):
    result=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],text=True,capture_output=True)
    return result.stdout.strip() if result.returncode==0 else None


def world_game(world):
    match=re.search(r'^gameid\s*=\s*(\S+)\s*$',(world/'world.mt').read_text(),re.M)
    assert match and match[1] in ('minetest','voxelibre'), 'Expected Minetest Game or a legacy VoxeLibre world'
    return match[1]


def copy_game_adapter(mods):
    shutil.copytree(ROOT/'util/graphics_test_game',mods/'graphics_test_game')


def copy_world(source,destination):
    assert (source/'map.sqlite').is_file() and (source/'world.mt').is_file(), 'Expected a stopped native SQLite world'
    game=world_game(source)
    shutil.copytree(source,destination,ignore=shutil.ignore_patterns('worldmods','graphics-client-ready'))
    mods=destination/'worldmods';mods.mkdir()
    shutil.copytree(ROOT/'util/graphics_benchmark',mods/'graphics_benchmark')
    copy_game_adapter(mods)
    settings=[line for line in (destination/'world.mt').read_text().splitlines()
              if not line.startswith(('load_mod_','gameid'))]
    (destination/'world.mt').write_text('\n'.join(settings)+f'\ngameid = {game}\nload_mod_graphics_benchmark = true\nload_mod_graphics_test_game = true\n')


def launch(world,config,log_path,timeout):
    command=[str(ROOT/'bin/luanti'),'--config',str(config),'--go','--world',str(world),
             '--gameid',world_game(world),'--name','GraphicsBench','--info']
    start=time.monotonic()
    with log_path.open('w') as output:
        process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if time.monotonic()-start>timeout: raise TimeoutError(f'Client timeout; inspect {log_path}')
                if not (world/'graphics-client-ready').exists():
                    if 'Frame benchmark: active time_us=' in log_path.read_text(errors='replace'):
                        (world/'graphics-client-ready').write_text('ready\n')
                time.sleep(0.5)
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill();process.wait()
    assert process.returncode==0, f'Client exited {process.returncode}; inspect {log_path}'
    log=log_path.read_text(errors='replace')
    for error in ('ERROR[','GL_INVALID','failed to generate shaders'):
        assert error not in log, f'{error}; inspect {log_path}'
    assert 'Irrlicht: Quit SDL' in log, f'Incomplete teardown; inspect {log_path}'
    return log


def events(log):
    return [json.loads(line.split('Graphics benchmark: ',1)[1]) for line in log.splitlines()
            if 'Graphics benchmark: {' in line]


def percentile(values,fraction):
    ordered=sorted(values);index=(len(ordered)-1)*fraction
    lo=int(index);hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(index-lo)


def summarize(log,frames,minimum_duration,expected_scenes=('forest','sunset_river','glowing_cave','underwater')):
    markers=events(log);starts={};results=[]
    assert any(e['event']=='complete' for e in markers), 'Fixture did not complete all scenes'
    with frames.open() as source: rows=list(csv.DictReader(source))
    for event in markers:
        if event['event']=='measure_begin': starts[event['scene']]=event['time_us']
        if event['event']!='measure_end': continue
        assert event.get('pose_corrections',0)==0, f'Camera correction contaminated {event["scene"]}'
        begin=starts[event['scene']];end=event['time_us']
        selected=[row for row in rows if float(row['time_us'])<=end and
                  float(row['time_us'])-float(row['frame_ms'])*1000>=begin]
        assert len(selected)>=10, f'Insufficient frames for {event["scene"]}'
        dimensions={(int(row['width']),int(row['height'])) for row in selected}
        assert dimensions=={(1920,1080)}, f'Unexpected actual render dimensions: {dimensions}'
        times=[float(row['frame_ms']) for row in selected]
        elapsed=sum(times)/1000
        assert elapsed>=minimum_duration*0.85, f'Insufficient measured coverage: {elapsed}'
        assert max(float(row['sleep_ms']) for row in selected)<2, 'Frame cap contaminated benchmark'
        results.append({'scene':event['scene'],'frames':len(times),'seconds':elapsed,
                        'fps':len(times)/elapsed,'median_ms':percentile(times,0.5),
                        'p95_ms':percentile(times,0.95),'p99_ms':percentile(times,0.99),
                        'mean_draw_cpu_ms':sum(float(r['draw_cpu_ms']) for r in selected)/len(selected),
                        'mean_drawcalls':sum(int(r['drawcalls']) for r in selected)/len(selected),
                        'width':1920,'height':1080})
    assert {r['scene'] for r in results}==set(expected_scenes)
    return results


def prepare(args):
    source=args.source.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    world=output/'prepared-world'
    before=digest(source/'map.sqlite')
    if args.reuse_world:
        assert world.is_dir() and not (world/'graphics-scenes.json').exists(), 'Reuse only an incomplete preparation'
        assert re.search(r'^seed = (.+)$',(source/'map_meta.txt').read_text(),re.M).group(1)==re.search(
            r'^seed = (.+)$',(world/'map_meta.txt').read_text(),re.M).group(1), 'World seed mismatch'
        shutil.rmtree(world/'worldmods')
        (world/'worldmods').mkdir()
        shutil.copytree(ROOT/'util/graphics_benchmark',world/'worldmods/graphics_benchmark')
        copy_game_adapter(world/'worldmods')
        if (output/'prepare.log').exists(): shutil.copy2(output/'prepare.log',output/'prepare-previous.log')
    else:
        assert not world.exists(), f'Prepared world already exists: {world}'
        copy_world(source,world)
    config=output/'prepare.conf'
    config.write_text((ROOT/'misc/graphics-basic.conf').read_text()+COMMON+'''
fullscreen = false
screen_w = 480
screen_h = 320
fps_max = 30
fps_max_unfocused = 30
graphics_benchmark_prepare = true
''')
    log=launch(world,config,output/'prepare.log',args.timeout)
    assert any(e['event']=='prepared' for e in events(log)), 'Scene preparation incomplete'
    assert digest(source/'map.sqlite')==before, 'Source world changed during preparation'
    shutil.copy2(world/'graphics-scenes.json',output/'scenes.json')
    (output/'source.json').write_text(json.dumps({'source':str(source),'source_map_sha256':before,
        'prepared_map_sha256':digest(world/'map.sqlite'),'engine_revision':revision(ROOT),
        'engine_binary_sha256':digest(ROOT/'bin/luanti'),
        'game':world_game(world),'game_revision':revision(ROOT/'games'/('minetest_game' if world_game(world)=='minetest' else 'voxelibre')),
        'cpu':next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                    if line.startswith('model name')),None)},indent=2)+'\n')
    print(f'Prepared fixed scenes in {output}',flush=True)


def run(args):
    output=args.output.resolve();prepared=output/'prepared-world'
    assert (prepared/'graphics-scenes.json').is_file(), 'Prepare scenes first'
    before=digest(prepared/'map.sqlite')
    binary=digest(ROOT/'bin/luanti')
    shader=hashlib.sha256()
    for path in sorted((ROOT/'client/shaders').rglob('*.glsl')):
        shader.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes())
    shader_hash=shader.hexdigest()
    profile_hashes={name:digest(ROOT/'misc'/file) for name,file in PROFILES.items()}
    fixture_hash=digest(ROOT/'util/graphics_benchmark/init.lua')
    adapter_hash=digest(ROOT/'util/graphics_test_game/init.lua')
    game=world_game(prepared)
    records=[]
    for repetition in range(args.repeats):
        profiles=args.profiles if repetition%2==0 else list(reversed(args.profiles))
        for profile in profiles:
            directory=output/f'{args.label+"-" if args.label else ""}{profile}-{repetition+1}'
            if args.resume and (directory/'result.json').is_file():
                saved=json.loads((directory/'result.json').read_text())
                assert saved['profile']==profile and saved['repeat']==repetition+1, 'Resume identity mismatch'
                assert digest(directory/'client.conf')==saved['config_sha256'], 'Saved settings changed'
                assert saved['binary_sha256']==binary and saved['shader_sha256']==shader_hash, 'Resume source mismatch'
                assert saved['fixture_sha256']==fixture_hash and saved['profile_sha256']==profile_hashes[profile], 'Resume fixture/profile mismatch'
                assert saved.get('game_adapter_sha256')==adapter_hash, 'Resume game adapter mismatch'
                assert saved.get('overrides',[])==args.set and saved.get('scenes')==args.scenes, 'Resume selection mismatch'
                if not args.scenes:
                    assert saved['scene_manifest_sha256']==digest(prepared/'graphics-scenes.json'), 'Resume scene mismatch'
                saved['results']=summarize((directory/'client.log').read_text(),directory/'frames.csv',args.duration,
                    args.scenes or ('forest','sunset_river','glowing_cave','underwater'))
                records.append(saved)
                print(f'Reusing validated {profile}, repeat {repetition+1}',flush=True)
                continue
            if args.resume and directory.exists():
                rejected=output/'rejected';rejected.mkdir(exist_ok=True)
                shutil.move(directory,rejected/f'{directory.name}-{int(time.time())}')
            directory.mkdir()
            world=directory/'world';copy_world(prepared,world)
            if args.scenes:
                manifest=json.loads((world/'graphics-scenes.json').read_text())
                manifest['scenes']=[scene for scene in manifest['scenes'] if scene['id'] in args.scenes]
                (world/'graphics-scenes.json').write_text(json.dumps(manifest,indent=2)+'\n')
            config=directory/'client.conf';frames=directory/'frames.csv'
            config.write_text((ROOT/'misc'/PROFILES[profile]).read_text()+COMMON+
                f'\nbenchmark_frame_log = {frames}\ngraphics_benchmark_warmup = {args.warmup}\n'
                f'graphics_benchmark_duration = {args.duration}\n'+
                ''.join(setting+'\n' for setting in args.set))
            shutil.copy2(config,directory/'launch.conf')
            launch_hash=digest(config)
            print(f'Running {profile}, repeat {repetition+1}',flush=True)
            assert digest(ROOT/'misc'/PROFILES[profile])==profile_hashes[profile], 'Profile changed during measurement'
            gpu_before=gpu_state()
            log=launch(world,config,directory/'client.log',args.timeout)
            assert digest(ROOT/'bin/luanti')==binary, 'Engine binary changed during measurement'
            assert digest(directory/'launch.conf')==launch_hash, 'Launch settings changed during measurement'
            assert digest(ROOT/'misc'/PROFILES[profile])==profile_hashes[profile], 'Profile changed during measurement'
            result=summarize(log,frames,args.duration,args.scenes or ('forest','sunset_river','glowing_cave','underwater'))
            record={'profile':profile,'repeat':repetition+1,'config_sha256':digest(config),
                    'launch_config_sha256':launch_hash,
                    'profile_sha256':profile_hashes[profile],
                    'scene_manifest_sha256':digest(world/'graphics-scenes.json'),
                    'fixture_sha256':fixture_hash,
                    'game':game,'game_adapter_sha256':adapter_hash,
                    'overrides':args.set,'scenes':args.scenes,
                    'binary_sha256':binary,'shader_sha256':shader_hash,'results':result,
                    'gpu_before':gpu_before,'gpu_after':gpu_state(),
                    'driver_environment':{key:os.environ.get(key) for key in ('DISPLAY','WAYLAND_DISPLAY',
                        'SDL_VIDEODRIVER','LIBGL_ALWAYS_SOFTWARE','__NV_PRIME_RENDER_OFFLOAD','__GL_SYNC_TO_VBLANK',
                        '__GL_SHADER_DISK_CACHE','__GL_SHADER_DISK_CACHE_PATH')}}
            (directory/'result.json').write_text(json.dumps(record,indent=2)+'\n')
            records.append(record)
            print(json.dumps(record),flush=True)
            # Keep settings, raw samples and logs; disposable run worlds are unnecessary.
            shutil.rmtree(world)
    assert digest(prepared/'map.sqlite')==before, 'Prepared baseline world changed'
    final_shader=hashlib.sha256()
    for path in sorted((ROOT/'client/shaders').rglob('*.glsl')):
        final_shader.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes())
    assert final_shader.hexdigest()==shader_hash, 'Shaders changed during measurement'
    assert digest(ROOT/'util/graphics_benchmark/init.lua')==fixture_hash, 'Fixture changed during measurement'
    assert digest(ROOT/'util/graphics_test_game/init.lua')==adapter_hash, 'Game adapter changed during measurement'
    (output/'results.json').write_text(json.dumps(records,indent=2)+'\n')


def report(args):
    output=args.output.resolve();destination=args.destination.resolve()
    records=[];directories=[]
    for directory in sorted(output.glob(f'{args.label}-*')):
        path=directory/'result.json'
        if path.is_file():
            record=json.loads(path.read_text());records.append(record);directories.append(directory)
    assert records, 'No completed runs with the requested label'
    assert len({r['binary_sha256'] for r in records})==1, 'Mixed engine binaries'
    assert len({r['shader_sha256'] for r in records})==1, 'Mixed shader sources'
    assert len({r['scene_manifest_sha256'] for r in records})==1, 'Mixed scene manifests'
    assert len({r['fixture_sha256'] for r in records})==1, 'Mixed fixtures'
    for profile in PROFILES:
        group=[r for r in records if r['profile']==profile]
        assert len(group)>=2, f'Two repeats required for {profile}'
        assert all(not r.get('overrides') and not r.get('scenes') for r in group), 'Final report must use full unmodified profiles and all four scenes'
        assert {r['profile_sha256'] for r in group}=={digest(ROOT/'misc'/PROFILES[profile])}, 'Profile changed since measurement'
    destination.mkdir(parents=True,exist_ok=True)
    rows=[]
    for profile in PROFILES:
        for scene in ('forest','sunset_river','glowing_cave','underwater'):
            samples=[s for r in records if r['profile']==profile for s in r['results'] if s['scene']==scene]
            rows.append({'profile':profile,'scene':scene,'repeats':len(samples),
                         'frames':sum(s['frames'] for s in samples),
                         'seconds':sum(s['seconds'] for s in samples),
                         'fps':sum(s['frames'] for s in samples)/sum(s['seconds'] for s in samples),
                         'fps_range':[min(s['fps'] for s in samples),max(s['fps'] for s in samples)],
                         'median_ms_range':[min(s['median_ms'] for s in samples),max(s['median_ms'] for s in samples)],
                         'p95_ms_range':[min(s['p95_ms'] for s in samples),max(s['p95_ms'] for s in samples)],
                         'p99_ms_range':[min(s['p99_ms'] for s in samples),max(s['p99_ms'] for s in samples)]})
    source=json.loads((output/'source.json').read_text())
    environment={'source':source,'platform':platform.platform(),'runs':records,
                 'protocol':{'resolution':[1920,1080],'view_distance_nodes':96,'fov':70,
                             'vsync':False,'frame_cap':1000,'fps_metric':'total frames / total sampled seconds',
                             'p95_budget_ms':22.2,'fps_target':60,'includes':'client, local server, driver and presentation'}}
    (destination/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    (destination/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    shutil.copy2(output/'scenes.json',destination/'scenes.json')
    for profile,file in PROFILES.items(): shutil.copy2(ROOT/'misc'/file,destination/file)
    if args.include_world:
        def keep(member):
            parts=Path(member.name).parts
            return None if 'worldmods' in parts or member.name.endswith('/graphics-client-ready') else member
        with tarfile.open(destination/'prepared-world.tar.gz','w:gz') as archive:
            archive.add(output/'prepared-world',arcname='prepared-world',filter=keep)
            archive.add(ROOT/'util/graphics_benchmark',arcname='prepared-world/worldmods/graphics_benchmark')
    samples_dir=destination/'raw';samples_dir.mkdir(exist_ok=True)
    for directory in directories:
        for filename in ('frames.csv','client.log'):
            with (directory/filename).open('rb') as source_file, gzip.open(samples_dir/f'{directory.name}-{filename}.gz','wb') as target:
                shutil.copyfileobj(source_file,target)
        shutil.copy2(directory/'client.conf',samples_dir/f'{directory.name}.conf')
        shutil.copy2(directory/'result.json',samples_dir/f'{directory.name}.json')
    lines=['# Milestone 1 measured baseline','',
           f'CPU: {source["cpu"]}. GPU/driver/clock/temperature observations are in [environment.json](environment.json).',
           'Resolution: 1920×1080; view distance: 96 nodes; FOV: 70°; VSync off; frame cap: 1000 FPS.',
           'Fixed cameras, weather, time of day and lamp state; local server included. Startup and settling frames are excluded.',
           'No screenshots or input-device automation. These static scenes do not establish exploration or all-game performance.','',
           '| Scene | Profile | Aggregate FPS | Median ms range | p95 ms range | p99 ms range | Frames |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    def span(values): return f'{values[0]:.2f}–{values[1]:.2f}'
    for row in rows:
        lines.append(f'| {row["scene"]} | {row["profile"]} | {row["fps"]:.1f} | '
                     f'{span(row["median_ms_range"])} | {span(row["p95_ms_range"])} | '
                     f'{span(row["p99_ms_range"])} | {row["frames"]} |')
    lines+=['','FPS combines frame counts and sampled durations across repeats. Percentile ranges show the individual repeats; they are not averaged percentiles.',
            'The proposed balanced budget is 60 FPS (16.67 ms average) with p95 ≤22.2 ms.','']
    for row in rows:
        if row['profile']=='balanced':
            passed=row['fps']>=60 and row['p95_ms_range'][1]<=22.2
            lines.append(f'- {row["scene"]}: {"meets" if passed else "misses"} the proposed budget.')
    lines+=['','Exact per-run settings, result records and compressed frame CSV/logs are in [raw](raw).',
            'Prepared world: `'+str(output/'prepared-world')+'`; its source and map hashes are recorded in the environment file.',
            'Use the same stopped prepared world for exact reruns; scene preparation can also be repeated from the recorded source world.','']
    if args.include_world: lines+=['A frozen input copy is included as [prepared-world.tar.gz](prepared-world.tar.gz).','']
    (destination/'README.md').write_text('\n'.join(lines))
    print(f'Wrote measured baseline report to {destination}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    setup=commands.add_parser('prepare');setup.add_argument('source',type=Path)
    setup.add_argument('--output',type=Path,required=True);setup.add_argument('--timeout',type=float,default=1800)
    setup.add_argument('--reuse-world',action='store_true',help='reuse generated chunks from an incomplete, stopped preparation')
    measure=commands.add_parser('run');measure.add_argument('--output',type=Path,required=True)
    measure.add_argument('--profiles',nargs='+',choices=PROFILES,default=list(PROFILES))
    measure.add_argument('--repeats',type=int,default=2);measure.add_argument('--warmup',type=float,default=20)
    measure.add_argument('--duration',type=float,default=20);measure.add_argument('--timeout',type=float,default=1200)
    measure.add_argument('--label',default='',help='optional output prefix for pilot or tuning runs')
    measure.add_argument('--resume',action='store_true',help='revalidate completed runs and preserve/retry incomplete runs')
    measure.add_argument('--scenes',nargs='+',choices=('forest','sunset_river','glowing_cave','underwater','surface_materials'),help='isolate scenes for tuning; surface_materials requires the milestone 6 prepared fixture; omit for final comparison')
    measure.add_argument('--set',action='append',default=[],help='key=value override for isolated tuning runs')
    summary=commands.add_parser('report');summary.add_argument('--output',type=Path,required=True)
    summary.add_argument('--label',default='baseline');summary.add_argument('--destination',type=Path,required=True)
    summary.add_argument('--include-world',action='store_true',help='archive the frozen input world for exact reruns')
    args=parser.parse_args()
    if args.command=='report': report(args);raise SystemExit(0)
    assert args.timeout>0
    if args.command=='run':
        assert args.repeats>=1 and args.warmup>=1 and args.duration>=5
        assert not args.label or re.fullmatch(r'[A-Za-z0-9_-]+',args.label), 'Invalid run label'
        assert all(re.fullmatch(r'[A-Za-z0-9_]+\s*=\s*[^\r\n]+',value) for value in args.set), 'Invalid setting override'
        run(args)
    else: prepare(args)
