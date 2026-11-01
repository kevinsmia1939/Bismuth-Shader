#!/bin/bash
# Water transport/caustics without dependent atmosphere, MRT, bloom or voxel lighting.
# LUANTI_TEST_QUALITY=true adds the full quality preset. DRIVER/AA/STEREO use LUANTI_TEST_ prefix.
# LUANTI_TEST_TIMEOUT allows extra time for cold combined shader compilation.
# LUANTI_TEST_SHADOWS=false checks water glints without a shadow-map renderer.
# LUANTI_TEST_WATER_LIGHTING=true/false overrides colored water scattering.
set -euo pipefail
water_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
water_test_dir=$(mktemp -d /tmp/luanti-water-test.XXXXXX)
trap 'rm -rf "$water_test_dir"' EXIT
mkdir -p "$water_test_dir/world/worldmods"
ln -s "$water_root/util/water_volume_test" "$water_test_dir/world/worldmods/water_volume_test"
if [ "${LUANTI_TEST_QUALITY:-false}" = true ]; then
 cp "$water_root/misc/graphics-quality.conf" "$water_test_dir/client.conf"
fi
cat >> "$water_test_dir/client.conf" <<EOF_CONFIG
video_driver = ${LUANTI_TEST_DRIVER:-opengl3}
3d_mode = ${LUANTI_TEST_STEREO:-none}
antialiasing = ${LUANTI_TEST_AA:-none}
fsaa = 4
screen_w = 480
screen_h = 320
fps_max = 30
enable_sound = false
opengl_debug = true
mg_name = singlenode
time_speed = 0
liquid_update = 1000
enable_post_processing = true
enable_dynamic_shadows = ${LUANTI_TEST_SHADOWS:-true}
enable_water_volume = true
enable_waving_water = true
water_wave_height = 1.0
EOF_CONFIG
if [ -n "${LUANTI_TEST_WATER_LIGHTING:-}" ]; then
 printf 'enable_voxel_water_lighting=%s\n' "$LUANTI_TEST_WATER_LIGHTING" >> "$water_test_dir/client.conf"
fi
water_status=0
timeout --kill-after=5 "${LUANTI_TEST_TIMEOUT:-95}" "$water_root/bin/luanti" --config "$water_test_dir/client.conf" --go \
 --world "$water_test_dir/world" --gameid devtest --name WaterTest --info > "$water_test_dir/run.log" 2>&1 || water_status=$?
cat "$water_test_dir/run.log"
if [ "$water_status" -ne 0 ]; then exit "$water_status"; fi
rg -q 'Water volume: uploaded 48\^3 cells' "$water_test_dir/run.log"
if [ "${LUANTI_TEST_QUALITY:-false}" = true ]; then
 rg -q 'Water surface directional light: shader bound' "$water_test_dir/run.log"
 if [ "${LUANTI_TEST_WATER_LIGHTING:-true}" = true ]; then
  rg -q 'Voxel water: atlas bound at texture4' "$water_test_dir/run.log"
 fi
fi
if [ "${LUANTI_TEST_WATER_LIGHTING:-}" = false ]; then
 if rg -q 'Voxel water:' "$water_test_dir/run.log"; then exit 1; fi
fi
awk '
 /Water volume: water cells=[1-9]/ { if (!wet) wet=1; else if (drained) restored=1 }
 wet && /Water volume: water cells=0$/ { drained=1 }
 /Water volume: underwater medium active$/ { active=1 }
 active && /Water volume: underwater medium inactive$/ { dry=1 }
 END { exit wet && drained && restored && active && dry ? 0 : 1 }
' "$water_test_dir/run.log"
for phase in submerged roof above shoreline drained restored 'wave submerged' 'wave gap' 'wave submerged again'; do
 rg -q "Water integration: $phase" "$water_test_dir/run.log"
done
awk '
 /Water volume: underwater medium active$/ { active=1; if (phase==1) wet=1; if (phase==3) restored=1 }
 /Water volume: underwater medium inactive$/ { active=0; if (phase==2) dry=1 }
 /Water integration: wave submerged$/ { phase=1; wet=active }
 /Water integration: wave gap$/ { phase=2 }
 /Water integration: wave submerged again$/ { phase=3; restored=active }
 END { exit wet && dry && restored ? 0 : 1 }
' "$water_test_dir/run.log"
rg -q 'Water volume: flowing cells=25$' "$water_test_dir/run.log"
awk '
 /Water volume: underwater medium active$/ { active=1 }
 /Water volume: underwater medium inactive$/ { active=0 }
 /Water integration: flow submerged held$/ { a=active }
 /Water integration: flow slope gap held$/ { b=!active }
 /Water integration: waving flow submerged held$/ { c=active }
 /Water integration: waving flow gap held$/ { d=!active }
 /Water integration: waving flow submerged again held$/ { e=active }
 END { if (!(a && b && c && d && e)) print "Flow held-pose failure: wet="a" slope-gap="b" wave-wet="c" wave-gap="d" recovered="e; exit a && b && c && d && e ? 0 : 1 }
' "$water_test_dir/run.log"
if rg -q 'ERROR\[|failed to generate shaders|GL_INVALID' "$water_test_dir/run.log"; then exit 1; fi
printf 'Water volume integration: PASS\n'
