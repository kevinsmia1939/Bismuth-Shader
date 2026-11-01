#!/bin/bash
# Native generated terrain, held torch hue/removal and water transitions.
# Pass an existing stopped VoxeLibre world; all writes use a temporary copy.
set -euo pipefail
native_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
native_source="${1:?Usage: util/test_voxelibre_lighting.sh /path/to/stopped/voxelibre/world}"
native_test_dir=$(mktemp -d /tmp/luanti-native-light-test.XXXXXX)
trap 'rm -rf "$native_test_dir"' EXIT
python3 - "$native_root" "$native_test_dir" "$native_source" <<'PY'
from pathlib import Path
import shutil
import sys
root, test, source = map(Path, sys.argv[1:])
assert (source/'world.mt').is_file() and (source/'map.sqlite').is_file(), 'Expected a VoxeLibre SQLite world'
world=test/'world'
shutil.copytree(source,world,ignore=shutil.ignore_patterns('worldmods'))
mods=world/'worldmods'
if mods.is_symlink(): mods.unlink()
elif mods.exists(): shutil.rmtree(mods)
mods.mkdir()
(mods/'voxelibre_water_test').symlink_to(root/'util/voxelibre_water_test',target_is_directory=True)
settings=(world/'world.mt').read_text().splitlines()
settings=[s for s in settings if not s.startswith(('load_mod_', 'gameid'))]
(world/'world.mt').write_text('\n'.join(settings)+'\ngameid = voxelibre\nload_mod_voxelibre_water_test = true\n')
(test/'client.conf').write_text((root/'misc/graphics-quality.conf').read_text()+'''
video_driver = opengl3
screen_w = 256
screen_h = 256
fps_max = 30
enable_sound = false
enable_damage = false
creative_mode = true
active_block_range = 1
mcl_mobspawning = false
mcl_weather = false
time_speed = 0
enable_cloud_denoising = true
enable_fog_denoising = true
native_water_test_clouds = true
native_water_test_dynamic_light = true
''')
PY
native_status=0
timeout --kill-after=5 "${LUANTI_TEST_TIMEOUT:-180}" "$native_root/bin/luanti" \
 --config "$native_test_dir/client.conf" --go --world "$native_test_dir/world" \
 --gameid voxelibre --name Landscape --info > "$native_test_dir/run.log" 2>&1 || native_status=$?
cat "$native_test_dir/run.log"
if [ "$native_status" -ne 0 ]; then exit "$native_status"; fi
python3 - "$native_test_dir/run.log" <<'PY'
from pathlib import Path
import re
import sys
log=Path(sys.argv[1]).read_text()
for required in ('SSAO: emission mask bound', 'SSAO: surface guide bound',
                 'Voxel fog: atlas bound at texture4',
                 'Voxel fog: phase bound=0.35',
                 'Voxel water: atlas bound at texture4 phase=0.5 steps=8',
                 'Voxel water: moving sources bound',
                 'atlas columns=14', 'Voxel dynamic direct: shader bound',
                 'Native water compatibility: submerged mcl_core:water_source',
                 'Native water compatibility: above', 'Native water compatibility: submerged again',
                 'Native dynamic lighting: held torch', 'Native dynamic lighting: removed torch',
                 'Irrlicht: Quit SDL'):
    assert required in log,required
for error in ('ERROR[', 'GL_INVALID', 'failed to generate shaders'):
    assert error not in log,error
held=False
warm=False
warm_direct=False
removed=False
cleared=False
cleared_direct=False
wet=False
submerged_source=False
for line in log.splitlines():
    if 'Water volume: underwater medium active' in line: wet=True
    if 'Water volume: underwater medium inactive' in line: wet=False
    if 'Native dynamic lighting: held torch' in line: held=True
    if 'Native dynamic lighting: removed torch' in line: removed=True
    match=re.search(r'Voxel GI: dynamic sources=1 held=1 emission=([\d.e+-]+),([\d.e+-]+),([\d.e+-]+)',line)
    if held and not removed and match:
        red,green,blue=map(float,match.groups())
        warm |= red > green > blue > 0
    direct=re.search(r'Voxel dynamic direct: sources=1 held=1 emission=([\d.e+-]+),([\d.e+-]+),([\d.e+-]+)',line)
    if held and not removed and direct:
        red,green,blue=map(float,direct.groups())
        warm_direct |= red > green > blue > 0
        submerged_source |= wet and red > green > blue > 0
    if removed and 'Voxel GI: dynamic sources=0 held=0 emission=0,0,0' in line: cleared=True
    if removed and 'Voxel dynamic direct: sources=0 held=0 emission=0,0,0' in line: cleared_direct=True
assert warm,'Native animated torch must infer a warm hue rather than neutral strip-sampling aliasing'
assert warm_direct,'Native held torch must reach the current-frame direct source list'
assert submerged_source,'A warm current-frame torch source must bind while the camera is underwater'
assert cleared,'Held torch removal must reach a completed worker upload'
assert cleared_direct,'Held torch removal must clear current-frame direct light'
print('Native VoxeLibre lighting integration: PASS')
PY
