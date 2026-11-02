#!/usr/bin/env python3
"""Independent timing controls for frame-window selection and aggregate FPS."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import csv
import json
from pathlib import Path
import tempfile
from benchmark_graphics import summarize, copy_world, world_game


def run():
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'frames.csv'
        rows=[];markers=[]
        for index,scene in enumerate(('forest','sunset_river','glowing_cave','underwater')):
            begin=100000000+index*20000000
            markers.append({'event':'measure_begin','scene':scene,'time_us':begin})
            time=begin
            # These out-of-window and boundary-spanning frames must be excluded.
            rows.extend([(begin-1,10000,1,0,1,1920,1080,1),(begin+10,10000,1,0,1,1920,1080,1)])
            for _ in range(10):
                for duration in (100,400):
                    time+=duration*1000
                    rows.append((time,duration,duration,0,80,1920,1080,1))
            markers.append({'event':'measure_end','scene':scene,'time_us':time,'pose_corrections':0})
        markers.append({'event':'complete','time_us':200000000})
        def write():
            with path.open('w') as output:
                writer=csv.writer(output)
                writer.writerow(('time_us','frame_ms','busy_ms','sleep_ms','draw_cpu_ms','width','height','drawcalls'))
                writer.writerows(rows)
        def log(): return '\n'.join('Graphics benchmark: '+json.dumps(item) for item in markers)
        write()
        results=summarize(log(),path,5)
        for result in results:
            assert result['frames']==20
            assert result['seconds']==5
            assert result['fps']==4 # Not the 6.25 mean of instantaneous FPS.
            assert result['median_ms']==250
            assert result['p95_ms']==400 and result['p99_ms']==400
        markers[1]['pose_corrections']=1
        try: summarize(log(),path,5)
        except AssertionError as error: assert 'Camera correction' in str(error)
        else: raise AssertionError('Camera motion must invalidate a static benchmark')
        markers[1]['pose_corrections']=0
        rows[2]=rows[2][:5]+(1280,720,1);write()
        try: summarize(log(),path,5)
        except AssertionError as error: assert 'dimensions' in str(error)
        else: raise AssertionError('Actual render dimensions must match the declared resolution')
        print('PASS: excludes warmup/spanning frames; duration-weighted FPS and percentiles; camera/dimension gates')

        for game in ('minetest','voxelibre'):
            source=Path(directory)/(game+'-source');source.mkdir()
            (source/'world.mt').write_text(f'gameid = {game}\nload_mod_old_fixture = true\nworld_name = original\n')
            (source/'map.sqlite').write_bytes(b'preserve these map bytes')
            target=Path(directory)/(game+'-copy')
            copy_world(source,target)
            assert world_game(target)==game, 'Copying must never convert a world to a different game'
            assert (target/'map.sqlite').read_bytes()==(source/'map.sqlite').read_bytes()
            assert 'load_mod_old_fixture' not in (target/'world.mt').read_text()
            assert (target/'worldmods/graphics_test_game/init.lua').is_file()
        print('PASS: native copies preserve Minetest Game/legacy game identity and terrain bytes')


if __name__=='__main__': run()
