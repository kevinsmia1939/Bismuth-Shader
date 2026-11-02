#!/usr/bin/env python3
"""Replay native sunlight, water and material integration scenes. No images/input."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time
from benchmark_graphics import ROOT, COMMON, digest, gpu_state, world_game, copy_game_adapter


def audit(log, frames, statistics=None):
    current=None;ready={};begins={};prepared={};ends=[]
    sources=None;source_rgb=None;held=None;warm=False;wet=False
    for line in log.splitlines():
        match=re.search(r'Voxel GI: sources=(\d+)',line)
        if match: sources=int(match[1])
        match=re.search(r'Voxel GI: sources=\d+ emission=([\d.e+-]+),([\d.e+-]+),([\d.e+-]+)',line)
        if match: source_rgb=list(map(float,match.groups()))
        match=re.search(r'Voxel dynamic direct: sources=\d+ held=(\d+) emission=([\d.e+-]+),([\d.e+-]+),([\d.e+-]+)',line)
        if match:
            held=int(match[1]);r,g,b=map(float,match.groups()[1:]);warm=held>0 and r>g>b>0
        if 'Water volume: underwater medium active' in line: wet=True
        if 'Water volume: underwater medium inactive' in line: wet=False
        match=re.search(r'Frame benchmark: progress time_us=(\d+)',line)
        if match and current:
            ready[current]=ready.get(current,0)+1
        if 'Graphics acceptance: {' not in line: continue
        event=json.loads(line.split('Graphics acceptance: ',1)[1])
        if event['event']=='prepare':
            current=event['id'];ready[current]=0;prepared[current]=event['time_us']
        if event['event']=='begin':
            assert ready.get(current,0)>=2, f'Client did not finish warmup frames for {current}'
            begins[current]=event['time_us']
        if event['event']=='end':
            event.update({'begin_us':begins[event['id']],'prepare_us':prepared[event['id']],
                          'sources':sources,'emission_rgb':source_rgb,'held':held,'warm':warm,'wet':wet})
            ends.append(event)
    assert '"event":"complete"' in log.replace(' ',''), 'Fixture did not complete'
    by_id={e['id']:e for e in ends}
    expected={'forest_movement','sunset_transition','river_reflections','water_entry','underwater_lamp',
              'water_exit','cave_dark','cave_placed','cave_removed','held_movement','held_removed'}
    assert set(by_id)==expected, 'Incomplete replay stages'
    assert by_id['cave_placed']['sources']>by_id['cave_dark']['sources'], 'Placed glowstone did not reach the worker field'
    assert by_id['cave_removed']['sources']==by_id['cave_dark']['sources'], 'Removed glowstone left stale source state'
    for stage in ('underwater_lamp','held_movement'):
        assert by_id[stage]['held']==1 and by_id[stage]['warm'], f'Native warm held torch missing in {stage}'
    assert by_id['held_removed']['held']==0, 'Removed held torch left frame-direct light'
    assert by_id['water_entry']['wet'] and by_id['underwater_lamp']['wet'], 'Native water entry/underwater state missing'
    assert not by_id['water_exit']['wet'], 'Water exit did not clear the medium'
    assert abs(by_id['sunset_transition']['timeofday']-0.86)<0.002
    with frames.open() as file: rows=list(csv.DictReader(file))
    for event in ends:
        selected=[r for r in rows if float(r['time_us'])<=event['time_us'] and
                  float(r['time_us'])-float(r['frame_ms'])*1000>=event['begin_us']]
        assert len(selected)>=30, f'Insufficient completed frames for {event["id"]}'
        assert {(int(r['width']),int(r['height'])) for r in selected}=={(640,360)}
        seconds=sum(float(r['frame_ms']) for r in selected)/1000
        assert seconds>=4.8, f'Insufficient frame coverage for {event["id"]}'
        event.update({'frames':len(selected),'sampled_seconds':seconds})
    for required in ('Surface shadow visibility: map bound','Water refraction: bound opaque scene',
                     'Voxel dynamic direct: shader bound','Fog denoising: history active','Irrlicht: Quit SDL'):
        assert required in log, required
    for error in ('ERROR[','GL_INVALID','failed to generate shaders'):
        assert error not in log, error
    if statistics is not None:
        with statistics.open() as file: probes=list(csv.DictReader(file))
        for event in ends:
            selected=[r for r in probes if event['begin_us']+1000000<=int(r['time_us'])<=event['time_us']]
            assert len(selected)>=60, f'Missing scene brightness coverage for {event["id"]}'
            channels=[[float(r[f'mean_{c}']) for c in 'rgb'] for r in selected]
            luminance=[sum(v*w for v,w in zip(rgb,(0.2126,0.7152,0.0722))) for rgb in channels]
            change=max(abs(a-b) for a,b in zip(luminance,luminance[1:]))
            event.update({'mean_rgb':[sum(rgb[c] for rgb in channels)/len(channels) for c in range(3)],
                          'mean_luminance':sum(luminance)/len(luminance),
                          'max_frame_luminance_change':change,
                          'peak_sampled_luminance':max(float(r['peak_luminance']) for r in selected)})
            assert change<0.1, f'Abrupt composed-scene brightness change in {event["id"]}: {change}'
        dark=by_id['cave_dark']['mean_luminance'];outdoors=by_id['forest_movement']['mean_luminance']
        assert dark<outdoors*0.3, f'Cave must remain substantially darker than outdoors: {dark}, {outdoors}'
        assert by_id['cave_placed']['mean_luminance']>dark+1e-5, 'Placed light did not brighten actual terrain'
        assert by_id['held_movement']['mean_luminance']>dark+1e-5, 'Held light did not brighten actual terrain'
        assert abs(by_id['cave_removed']['mean_luminance']-dark)<max(0.0001,dark*0.1), 'Removed placed light left visible radiance'
        assert abs(by_id['held_removed']['mean_luminance']-dark)<max(0.0001,dark*0.1), 'Removed held light left visible radiance'
        dark_rgb=by_id['cave_dark']['mean_rgb']
        for stage in ('cave_placed','held_movement'):
            delta=[a-b for a,b in zip(by_id[stage]['mean_rgb'],dark_rgb)]
            if stage=='held_movement':
                assert delta[0]>delta[1]>delta[2]>0, f'Native warm torch hue lost: {delta}'
            else:
                # Mese lamps are yellow-green; VoxeLibre glowstone is orange.
                # Compare with the actual emitted packet rather than imposing
                # the previous game's R>G>B ordering on every placed lamp.
                source_delta=[a-b for a,b in zip(by_id[stage]['emission_rgb'],by_id['cave_dark']['emission_rgb'])]
                cosine=sum(a*b for a,b in zip(delta,source_delta))/max(
                    math.sqrt(sum(v*v for v in delta)*sum(v*v for v in source_delta)),1e-12)
                assert min(delta)>0 and cosine>0.95, f'Placed lamp color disagrees with native emission: {delta}, {source_delta}'
                by_id[stage]['emission_color_cosine']=cosine
        for stage in ('cave_removed','held_removed'):
            event=by_id[stage]
            after=[r for r in probes if event['prepare_us']<=int(r['time_us'])<=event['time_us']]
            dark_frames=0
            for row in after:
                light=sum(float(row[f'mean_{c}'])*w for c,w in zip('rgb',(0.2126,0.7152,0.0722)))
                dark_frames=dark_frames+1 if light<=dark+0.0001 else 0
                if dark_frames>=3:
                    event['clear_latency_ms']=(int(row['time_us'])-event['prepare_us'])/1000
                    break
            assert event.get('clear_latency_ms',float('inf'))<1000, f'Lamp removal must clear actual radiance within one second: {stage}'
    return ends


def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    source=args.world.resolve();before=digest(source/'map.sqlite')
    game=world_game(source)
    assert (source/'graphics-scenes.json').is_file(), 'Use the frozen prepared world from benchmark_graphics.py prepare'
    world=output/'world'
    shutil.copytree(source,world,ignore=shutil.ignore_patterns('worldmods','graphics-client-ready','graphics-phase-*-ready'))
    (world/'worldmods').mkdir()
    shutil.copytree(ROOT/'util/graphics_acceptance',world/'worldmods/graphics_acceptance')
    copy_game_adapter(world/'worldmods')
    settings=[s for s in (world/'world.mt').read_text().splitlines() if not s.startswith(('load_mod_','gameid'))]
    (world/'world.mt').write_text('\n'.join(settings)+f'\ngameid = {game}\nload_mod_graphics_acceptance = true\nload_mod_graphics_test_game = true\n')
    shutil.copy2(source/'graphics-scenes.json',output/'scenes.json')
    config=output/'client.conf';frames=output/'frames.csv';log=output/'client.log'
    config.write_text((ROOT/'misc/graphics-balanced.conf').read_text()+COMMON+f'''
screen_w = 640
screen_h = 360
fullscreen = false
fps_max = 30
fps_max_unfocused = 30
enable_volumetric_fog = true
enable_fog_denoising = true
volumetric_fog_steps = 8
volumetric_fog_variation = 0.15
volumetric_fog_distance = 64
atmosphere_density = 0.0015
shadow_update_frames = 4
benchmark_frame_log = {frames}
benchmark_frame_progress = true
benchmark_scene_log = {output/'scene.csv'}
''')
    if args.texture_pack:
        pack=args.texture_pack.resolve()
        assert pack.is_dir(), 'Texture-pack directory is missing'
        with config.open('a') as file: file.write(f'texture_path = {pack}\n')
    # The client can save additional settings/reformat this file at shutdown.
    # Keep its exact launch input as well as the resulting saved configuration.
    shutil.copy2(config,output/'launch.conf')
    metadata={'binary_sha256':digest(ROOT/'bin/luanti'),'gpu':gpu_state(),'game':game,
              'game_adapter_sha256':digest(ROOT/'util/graphics_test_game/init.lua'),
              'config_sha256':digest(config),'source_map_sha256':before,
              'fixture_sha256':digest(ROOT/'util/graphics_acceptance/init.lua'),
              'shader_sha256':hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'client/shaders').rglob('*.glsl')))).hexdigest()}
    if args.texture_pack:
        metadata['texture_pack_sha256']={p.name:digest(p) for p in sorted(pack.iterdir()) if p.is_file()}
    (output/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
    start=time.monotonic();phase=None;prepared_at=0;progress=0;offset=0
    command=[str(ROOT/'bin/luanti'),'--config',str(config),'--go','--world',str(world),
             '--gameid',game,'--name','GraphicsAcceptance','--info']
    with log.open('w') as file:
        process=subprocess.Popen(command,stdout=file,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                assert time.monotonic()-start<args.timeout, f'Runtime timeout; inspect {log}'
                text=log.read_text(errors='replace');complete=text.rfind('\n')+1
                for line in text[offset:complete].splitlines():
                    if 'Graphics acceptance: {' in line:
                        event=json.loads(line.split('Graphics acceptance: ',1)[1])
                        if event['event']=='prepare':
                            phase=event['index'];prepared_at=event['time_us'];progress=0
                            print('Preparing '+event['id'],flush=True)
                    match=re.search(r'Frame benchmark: progress time_us=(\d+)',line)
                    if match and phase is not None and int(match[1])>prepared_at+500000:
                        progress+=1
                        if progress>=2: (world/f'graphics-phase-{phase}-ready').touch()
                offset=complete
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
    assert process.returncode==0, f'Client exit {process.returncode}; inspect {log}'
    assert digest(source/'map.sqlite')==before, 'Original prepared world changed'
    assert digest(ROOT/'bin/luanti')==metadata['binary_sha256'], 'Binary changed during replay'
    assert digest(output/'launch.conf')==metadata['config_sha256'], 'Launch settings changed during replay'
    assert digest(ROOT/'util/graphics_acceptance/init.lua')==metadata['fixture_sha256'], 'Fixture changed during replay'
    assert digest(ROOT/'util/graphics_test_game/init.lua')==metadata['game_adapter_sha256'], 'Game adapter changed during replay'
    if args.texture_pack:
        assert metadata['texture_pack_sha256']=={p.name:digest(p) for p in sorted(pack.iterdir()) if p.is_file()}, 'Material pack changed during replay'
    metadata['saved_config_sha256']=digest(config)
    (output/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
    results=audit(log.read_text(),frames,output/'scene.csv')
    if args.texture_pack:
        text=log.read_text()
        assert 'Material maps: normal=0 ORM=1' in text, 'Native ORM companions never bound'
        assert 'Material ORM mipmaps: default_stone_orm.png' in text, 'Native stone material not prepared'
        # Several native assets use _normal for color variants. They are not maps.
        assert 'Material normal mipmaps:' not in text, 'Unexpected normal map from server color media'
    (output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    shutil.rmtree(world)
    print(f'PASS: 11 native {game} transition stages; evidence in {output}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=1200)
    parser.add_argument('--texture-pack',type=Path,help='Optional ORM-only pack for native material compatibility checks')
    run(parser.parse_args())
