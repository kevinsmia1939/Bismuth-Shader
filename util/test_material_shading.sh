#!/bin/bash
# Runtime validation of explicit/companion maps, animation, fallback and transport.
# Optional: LUANTI_TEST_DRIVER=opengl, LUANTI_TEST_AA=fsaa, LUANTI_TEST_STEREO=sidebyside.
# LUANTI_TEST_POST_PROCESSING=false checks forward shading without the post pipeline.
# LUANTI_TEST_DYNAMIC_DIRECT=true/false exercises a held lamp with GPU/fallback lighting.
# LUANTI_TEST_SHADOWS=false compiles without shadow maps.
# LUANTI_TEST_DIRECTIONAL=true checks live source controls.
set -euo pipefail
material_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
material_test_dir=$(mktemp -d /tmp/luanti-material-test.XXXXXX)
trap 'rm -rf "$material_test_dir"' EXIT
material_mod="$material_test_dir/world/worldmods/material_shading_test"
mkdir -p "$material_mod"
cp "$material_root/util/material_shading_test/init.lua" "$material_root/util/material_shading_test/mod.conf" "$material_mod/"
python3 "$material_root/util/material_shading_test/generate_textures.py" "$material_mod/textures"
mkdir -p "$material_test_dir/texturepack"
mv "$material_mod/textures/material_test_auto_normal.png" "$material_mod/textures/material_test_auto_orm.png" "$material_test_dir/texturepack/"
cp "$material_root/misc/graphics-quality.conf" "$material_test_dir/client.conf"
cat >> "$material_test_dir/client.conf" <<EOF_CONFIG
video_driver = ${LUANTI_TEST_DRIVER:-opengl3}
3d_mode = ${LUANTI_TEST_STEREO:-none}
antialiasing = ${LUANTI_TEST_AA:-taa}
fsaa = 4
screen_w = 480
screen_h = 320
fps_max = 30
mip_map = ${LUANTI_TEST_MIPMAPS:-true}
trilinear_filter = true
enable_sound = false
enable_post_processing = ${LUANTI_TEST_POST_PROCESSING:-true}
enable_material_shading = ${LUANTI_TEST_MATERIALS:-true}
enable_dynamic_shadows = ${LUANTI_TEST_SHADOWS:-true}
texture_path = $material_test_dir/texturepack
mg_name = singlenode
time_speed = 0
benchmark_frame_log = $material_test_dir/frames.csv
benchmark_frame_progress = true
material_test_wait_client = true
EOF_CONFIG
if [ -n "${LUANTI_TEST_DYNAMIC_DIRECT:-}" ]; then
 printf '%s\n' "enable_voxel_dynamic_direct=$LUANTI_TEST_DYNAMIC_DIRECT" material_test_dynamic_light=true >> "$material_test_dir/client.conf"
fi
if [ "${LUANTI_TEST_DIRECTIONAL:-false}" = true ]; then
 printf '%s\n' material_test_directional=true >> "$material_test_dir/client.conf"
fi
material_status=0
# Allow cold compilation of authored-map and combined quality variants.
python3 - "$material_root" "$material_test_dir" "${LUANTI_TEST_TIMEOUT:-180}" <<'PY' || material_status=$?
from pathlib import Path
import subprocess
import json
import re
import sys
import time
root,test=map(Path,sys.argv[1:3])
log=test/'run.log'
with log.open('w') as output:
    process=subprocess.Popen(['timeout','--kill-after=5',sys.argv[3],str(root/'bin/luanti'),
        '--config',str(test/'client.conf'),'--go','--world',str(test/'world'),
        '--gameid','devtest','--name','MaterialTest','--info'],stdout=output,stderr=subprocess.STDOUT)
    phase=None;prepared_at=0;progress=0;offset=0
    try:
        while process.poll() is None:
            text=log.read_text(errors='replace');complete=text.rfind('\n')+1
            for line in text[offset:complete].splitlines():
                if 'Material stage: {' in line:
                    stage=json.loads(line.split('Material stage: ',1)[1])
                    phase=stage['index'];prepared_at=stage['time_us'];progress=0
                match=re.search(r'Frame benchmark: progress time_us=(\d+)',line)
                if match and phase is not None and int(match[1])>prepared_at+500000:
                    progress+=1
                    if progress>=2: (test/f'world/material-stage-{phase}-ready').touch()
            offset=complete
            time.sleep(0.1)
    finally:
        if process.poll() is None: process.terminate();process.wait()
raise SystemExit(process.returncode)
PY
cat "$material_test_dir/run.log"
if [ "$material_status" -ne 0 ]; then exit "$material_status"; fi
python3 "$material_root/util/audit_material_runtime.py" "$material_test_dir/run.log"
if [ "${LUANTI_TEST_MATERIALS:-true}" = true ]; then
rg -q 'Material maps: normal=1 ORM=1' "$material_test_dir/run.log"
rg -q 'Material normal mipmaps: shader bound' "$material_test_dir/run.log"
rg -q 'Material ORM mipmaps: material_test_metal.png' "$material_test_dir/run.log"
rg -q 'Material ORM mipmaps: material_test_auto_orm.png' "$material_test_dir/run.log"
rg -q 'Material ORM mipmaps: material_test_animated_orm.png\^\[verticalframe:2:0' "$material_test_dir/run.log"
rg -q 'Material ORM mipmaps: material_test_animated_orm.png\^\[verticalframe:2:1' "$material_test_dir/run.log"
rg -q 'Material normal mipmaps: material_test_animated_normal.png\^\[verticalframe:2:0' "$material_test_dir/run.log"
rg -q 'Material normal mipmaps: material_test_animated_normal.png\^\[verticalframe:2:1' "$material_test_dir/run.log"
rg -q 'texturepack/material_test_auto_normal.png' "$material_test_dir/run.log"
rg -q 'texturepack/material_test_auto_orm.png' "$material_test_dir/run.log"
elif rg -q 'Material maps:|Material normal mipmaps:|Material ORM mipmaps:' "$material_test_dir/run.log"; then
 exit 1
fi
rg -q 'nodes_shader .*MATERIAL_EMISSIVE=1' "$material_test_dir/run.log"
rg -q 'Material integration: authored, companion and animated nodes placed' "$material_test_dir/run.log"
rg -q 'Material integration: cutout normal/ORM node placed' "$material_test_dir/run.log"
if [ "${LUANTI_TEST_DIRECTIONAL:-false}" = true ]; then
 for phase in 'zero shadow strength' 'hidden sky lights' 'visible sun' 'visible moon' 'custom light restored'; do
  rg -q "Material directional integration: $phase" "$material_test_dir/run.log"
 done
 for state in 'source=0 active=0' 'source=1 active=1' 'source=2 active=1' 'source=3 active=1'; do
  rg -q "Surface directional light: $state" "$material_test_dir/run.log"
 done
 if [ "${LUANTI_TEST_SHADOWS:-true}" = true ]; then
  rg -q 'Surface shadow visibility: map bound' "$material_test_dir/run.log"
 fi
fi
if rg -q 'ERROR\[|failed to generate shaders|GL_INVALID|Material map .* frames; expected' "$material_test_dir/run.log"; then exit 1; fi
if [ "${LUANTI_TEST_STEREO:-none}" = sidebyside ] && [ "${LUANTI_TEST_MATERIALS:-true}" = true ]; then
 awk -F'eye offset=' '
  /Material camera: eye offset=/ { if ($2 < -0.001) left=1; if ($2 > 0.001) right=1 }
  END { exit left && right ? 0 : 1 }
 ' "$material_test_dir/run.log"
fi
if [ "${LUANTI_TEST_DYNAMIC_DIRECT:-false}" = true ]; then
 rg -q 'Voxel dynamic direct: shader bound' "$material_test_dir/run.log"
 rg -q 'Material integration: held light' "$material_test_dir/run.log"
 rg -q 'Material integration: removed held light' "$material_test_dir/run.log"
 awk '
  /Voxel dynamic direct: sources=1 held=1/ { active=1 }
  active && /Voxel dynamic direct: sources=0 held=0/ { removed=1 }
  END { exit removed ? 0 : 1 }
 ' "$material_test_dir/run.log"
elif [ "${LUANTI_TEST_DYNAMIC_DIRECT:-}" = false ]; then
 rg -q 'atlas columns=13' "$material_test_dir/run.log"
 rg -q 'Voxel GI: dynamic sources=1 held=1' "$material_test_dir/run.log"
 rg -q 'Material integration: removed held light' "$material_test_dir/run.log"
 if rg -q 'Voxel dynamic direct:' "$material_test_dir/run.log"; then exit 1; fi
fi
printf 'Material shading integration: PASS\n'
