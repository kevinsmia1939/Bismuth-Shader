#!/bin/bash
# Exercise colored nodedef transport, asynchronous atlas updates and shader binding.
# Requires a display. Optional: LUANTI_TEST_DRIVER=opengl for legacy OpenGL,
# LUANTI_TEST_QUALITY=true for all quality effects, LUANTI_TEST_AA=fsaa for MSAA.
# LUANTI_TEST_STEREO=sidebyside or anaglyph exercises stereo captures/history.
# LUANTI_TEST_SHADOW_COLOR=false or LUANTI_TEST_SHADOW_POISSON=false selects shadow variants.
# LUANTI_TEST_CAMERA_EFFECTS=true enables motion blur and depth of field together.
# LUANTI_TEST_WATER_VOLUME=true enables loaded-water transport and caustics.
# LUANTI_TEST_WATER_LIGHTING=true/false overrides colored water scattering; true also submerges held lamps.
# LUANTI_TEST_CLOUD_GI=true checks overcast/clear/restored sunlight injection.
# LUANTI_TEST_FOG_DENOISING=true checks fog reset/restoration and water transitions.
# LUANTI_TEST_SSAO=true/false overrides the preset to check surface/volume ordering.
# LUANTI_TEST_EMISSION_MASK=true/false checks the separate emissive receiver mask.
# LUANTI_TEST_MATERIAL_SHADING=false checks emission without authored material maps.
# LUANTI_TEST_DYNAMIC_LIGHTING=true/false exercises held/moving node lights or opt-out.
# LUANTI_TEST_TRANSMISSION=true/false checks authored/inferred glass filters or opt-out.
# LUANTI_TEST_DYNAMIC_DIRECT=true/false selects per-frame GPU direct light or worker fallback.
# LUANTI_TEST_VOXEL_FOG=true/false checks local fog binding/hidden-sky transport or opt-out.
# LUANTI_TEST_FOG_ANISOTROPY overrides the local scattering phase for integration.
# LUANTI_TEST_GEOMETRY=true checks wall/filter edits during pending solves (use DYNAMIC_LIGHTING=true).
# LUANTI_TEST_VOXEL_SIZE/BOUNCES/FPS/WIDTH/HEIGHT vary coverage and scheduling pressure.
# LUANTI_TEST_NATIVE_EMISSION=true checks glow classification with maps/AO/cloud shadows disabled.
set -euo pipefail
voxel_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
voxel_test_dir=$(mktemp -d /tmp/luanti-voxel-test.XXXXXX)
trap 'rm -rf "$voxel_test_dir"' EXIT
mkdir -p "$voxel_test_dir/world/worldmods"
ln -s "$voxel_root/util/voxel_lighting_test" "$voxel_test_dir/world/worldmods/voxel_lighting_test"
if [ "${LUANTI_TEST_QUALITY:-false}" = true ]; then
 cp "$voxel_root/misc/graphics-quality.conf" "$voxel_test_dir/client.conf"
fi
cat >> "$voxel_test_dir/client.conf" <<EOF_CONFIG
video_driver = ${LUANTI_TEST_DRIVER:-opengl3}
3d_mode = ${LUANTI_TEST_STEREO:-none}
screen_w = ${LUANTI_TEST_WIDTH:-480}
screen_h = ${LUANTI_TEST_HEIGHT:-320}
fps_max = ${LUANTI_TEST_FPS:-30}
fps_max_unfocused = ${LUANTI_TEST_FPS:-30}
enable_sound = false
mg_name = singlenode
enable_voxel_lighting = true
voxel_lighting_size = ${LUANTI_TEST_VOXEL_SIZE:-32}
voxel_gi_bounces = ${LUANTI_TEST_BOUNCES:-2}
enable_post_processing = true
antialiasing = ${LUANTI_TEST_AA:-taa}
fsaa = 4
enable_bloom = true
time_speed = 0
EOF_CONFIG
if [ -n "${LUANTI_TEST_SHADOW_COLOR:-}" ]; then
 printf 'shadow_map_color = %s\n' "$LUANTI_TEST_SHADOW_COLOR" >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_SHADOW_POISSON:-}" ]; then
 printf 'shadow_poisson_filter = %s\n' "$LUANTI_TEST_SHADOW_POISSON" >> "$voxel_test_dir/client.conf"
fi
voxel_status=0
if [ "${LUANTI_TEST_WATER_VOLUME:-false}" = true ]; then
 printf '%s\n' enable_water_volume=true >> "$voxel_test_dir/client.conf"
fi
if [ "${LUANTI_TEST_CAMERA_EFFECTS:-false}" = true ]; then
 printf '%s\n' enable_camera_motion_blur=true enable_camera_dof=true >> "$voxel_test_dir/client.conf"
fi
if [ "${LUANTI_TEST_CLOUD_GI:-false}" = true ]; then
 printf '%s\n' enable_volumetric_clouds=true enable_cloud_shadows=true volumetric_cloud_density=1 voxel_test_cloud_gi=true >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_FOG_DENOISING:-}" ]; then
 printf '%s\n' enable_atmosphere=true enable_volumetric_fog=true "enable_fog_denoising=$LUANTI_TEST_FOG_DENOISING" \
  "voxel_test_fog_denoising=$LUANTI_TEST_FOG_DENOISING" >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_SSAO:-}" ]; then
 printf 'enable_ssao = %s\n' "$LUANTI_TEST_SSAO" >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_EMISSION_MASK:-}" ]; then
 printf '%s\n' enable_ssao=true "enable_ssao_emission_mask=$LUANTI_TEST_EMISSION_MASK" \
  "voxel_test_emission_mask=$LUANTI_TEST_EMISSION_MASK" >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_MATERIAL_SHADING:-}" ]; then
 printf 'enable_material_shading = %s\n' "$LUANTI_TEST_MATERIAL_SHADING" >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_DYNAMIC_LIGHTING:-}" ]; then
 printf '%s\n' "enable_voxel_dynamic_lighting=$LUANTI_TEST_DYNAMIC_LIGHTING" \
  voxel_test_dynamic_lighting=true >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_TRANSMISSION:-}" ]; then
 printf '%s\n' "enable_voxel_transmission=$LUANTI_TEST_TRANSMISSION" \
  voxel_test_transmission=true >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_DYNAMIC_DIRECT:-}" ]; then
 printf 'enable_voxel_dynamic_direct=%s\n' "$LUANTI_TEST_DYNAMIC_DIRECT" >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_WATER_LIGHTING:-}" ]; then
 printf '%s\n' enable_water_volume=true "enable_voxel_water_lighting=$LUANTI_TEST_WATER_LIGHTING" >> "$voxel_test_dir/client.conf"
 printf 'voxel_test_water_lighting=%s\n' "$LUANTI_TEST_WATER_LIGHTING" >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_VOXEL_FOG:-}" ]; then
 printf '%s\n' enable_atmosphere=true enable_volumetric_fog=true \
  "enable_voxel_fog_lighting=$LUANTI_TEST_VOXEL_FOG" voxel_test_fog_denoising=true >> "$voxel_test_dir/client.conf"
fi
if [ -n "${LUANTI_TEST_FOG_ANISOTROPY:-}" ]; then
 printf 'voxel_fog_anisotropy=%s\n' "$LUANTI_TEST_FOG_ANISOTROPY" >> "$voxel_test_dir/client.conf"
fi
if [ "${LUANTI_TEST_GEOMETRY:-false}" = true ]; then
 printf '%s\n' voxel_test_geometry=true >> "$voxel_test_dir/client.conf"
fi
if [ "${LUANTI_TEST_NATIVE_EMISSION:-false}" = true ]; then
 printf '%s\n' voxel_test_native_emission=true voxel_test_emission_mask=true \
  enable_material_shading=false enable_ssao=false enable_ssao_emission_mask=false \
  enable_cloud_shadows=false >> "$voxel_test_dir/client.conf"
fi
# Allow cold compilation of combined material/fog/water/stereo and MRT variants.
timeout --kill-after=5 "${LUANTI_TEST_TIMEOUT:-180}" "$voxel_root/bin/luanti" --config "$voxel_test_dir/client.conf" --go \
 --world "$voxel_test_dir/world" --gameid devtest --name VoxelTest --info > "$voxel_test_dir/run.log" 2>&1 || voxel_status=$?
cat "$voxel_test_dir/run.log"
if [ "$voxel_status" -ne 0 ]; then exit "$voxel_status"; fi
if [ "${LUANTI_TEST_NATIVE_EMISSION:-false}" = true ]; then
 rg -q 'nodes_shader .*MATERIAL_EMISSIVE=1' "$voxel_test_dir/run.log"
 rg -q 'object_shader .*MATERIAL_EMISSIVE=1' "$voxel_test_dir/run.log"
 for phase in glowing ordinary unshaded; do
  rg -q "Emission mask integration: object $phase" "$voxel_test_dir/run.log"
  rg -q "Native emission integration: sprite $phase" "$voxel_test_dir/run.log"
 done
 for phase in 'black emitter' 'ordinary replacement' 'restored emitter' removed; do
  rg -q "Native emission integration: $phase" "$voxel_test_dir/run.log"
 done
 if rg -q 'SSAO: emission mask bound|Cloud shadows: receiver bound|Material maps: normal=' "$voxel_test_dir/run.log"; then exit 1; fi
fi
if [ "${LUANTI_TEST_GEOMETRY:-false}" = true ]; then
 python3 - "$voxel_test_dir/run.log" <<'PY'
from pathlib import Path
import re
import sys
log=Path(sys.argv[1]).read_text()
for kind in ('basenodes:stone','voxel_lighting_test:filter_green','voxel_lighting_test:filter_blue','air'):
    assert 'Geometry integration: '+kind in log,kind
stage=0
pending=False
for line in log.splitlines():
    if 'Geometry integration:' in line: stage=max(stage,1)
    if not stage: continue
    match=re.search(r'Voxel geometry: revision=(\d+) changed=(\d+) blocked=(\d+) filters=(\d+) transmission=([\d.e+-]+),([\d.e+-]+),([\d.e+-]+) solve_pending=(\d)',line)
    if not match: continue
    _,changed,blocked,filters=map(int,match.groups()[:4])
    rgb=tuple(map(float,match.groups()[4:7]))
    pending |= match[8]=='1' and changed>0
    if stage==1 and filters==0: stage=2
    if stage==2 and filters==9 and abs(rgb[1]-1)<1e-5 and rgb[0]<0.51: stage=3
    if stage==3 and filters==9 and abs(rgb[2]-1)<1e-5 and rgb[1]<0.51: stage=4
    if stage==4 and filters==0: stage=5
assert stage==5,'Expected live solid/green/blue/clear optics uploads'
assert pending,'An actual optics edit must upload while the immutable solve is pending'
assert 'Voxel geometry snapshots:' in log,'Expected geometry scan/upload cost evidence'
print('Live voxel geometry integration: PASS')
PY
fi
if [ "${LUANTI_TEST_VOXEL_FOG:-}" = true ]; then
 rg -q 'Voxel fog: atlas bound at texture4' "$voxel_test_dir/run.log"
 rg -q 'Voxel fog: phase bound=' "$voxel_test_dir/run.log"
 rg -q 'Voxel fog: hidden-sky transport active' "$voxel_test_dir/run.log"
 if [ "${LUANTI_TEST_DYNAMIC_DIRECT:-false}" = true ] && [ "${LUANTI_TEST_DYNAMIC_LIGHTING:-false}" = true ]; then
  rg -q 'Voxel fog: moving sources bound' "$voxel_test_dir/run.log"
 fi
elif [ "${LUANTI_TEST_VOXEL_FOG:-}" = false ]; then
 if rg -q 'Voxel fog:' "$voxel_test_dir/run.log"; then exit 1; fi
fi
rg -q 'Voxel GI: sources=3 emission=2,2,2' "$voxel_test_dir/run.log"
if [ "${LUANTI_TEST_WATER_LIGHTING:-}" = true ]; then
 rg -q 'Voxel water: atlas bound at texture4' "$voxel_test_dir/run.log"
 if [ "${LUANTI_TEST_DYNAMIC_DIRECT:-false}" = true ] && [ "${LUANTI_TEST_DYNAMIC_LIGHTING:-false}" = true ]; then
  rg -q 'Voxel water: moving sources bound' "$voxel_test_dir/run.log"
 fi
 if [ "${LUANTI_TEST_DYNAMIC_LIGHTING:-false}" = true ]; then
  rg -q 'Water lighting integration: held underwater' "$voxel_test_dir/run.log"
  rg -q 'Water lighting integration: above after held' "$voxel_test_dir/run.log"
  python3 - "$voxel_test_dir/run.log" <<'PY'
from pathlib import Path
import sys
wet=False
held=False
red=False
green=False
for line in Path(sys.argv[1]).read_text().splitlines():
    if 'Water volume: underwater medium active' in line: wet=True
    if 'Water volume: underwater medium inactive' in line: wet=False
    if 'Water lighting integration: held underwater' in line: held=True
    if 'Water lighting integration: above after held' in line: held=False
    if wet and held and 'dynamic sources=1 held=1 emission=2,0,0' in line: red=True
    if wet and held and 'dynamic sources=1 held=1 emission=0,2,0' in line: green=True
assert red and green, 'Both held colors must reach a completed lighting solve while underwater'
PY
 fi
elif [ "${LUANTI_TEST_WATER_LIGHTING:-}" = false ]; then
 if rg -q 'Voxel water:' "$voxel_test_dir/run.log"; then exit 1; fi
fi
rg -q 'Voxel GI: sources=2 emission=2,2,0' "$voxel_test_dir/run.log"
awk '
 /Voxel GI: sources=3 emission=2,2,2/ { seen_three=1 }
 seen_three && /Voxel GI: sources=2 emission=2,2,0/ { seen_two=1 }
 seen_two && /Voxel GI: sources=0 emission=0,0,0/ { finished=1 }
 END { exit finished ? 0 : 1 }
' "$voxel_test_dir/run.log"
if rg -q 'ERROR\[|failed to generate shaders|GL_INVALID' "$voxel_test_dir/run.log"; then exit 1; fi
if [ "${LUANTI_TEST_QUALITY:-false}" = true ]; then
 rg -q 'Water refraction: bound opaque scene' "$voxel_test_dir/run.log"
 if [ "${LUANTI_TEST_SSAO:-true}" = true ]; then
  rg -q 'SSAO: surface guide bound' "$voxel_test_dir/run.log"
 fi
fi
if [ "${LUANTI_TEST_CAMERA_EFFECTS:-false}" = true ]; then
 rg -q 'camera_motion/opengl_fragment.glsl' "$voxel_test_dir/run.log"
 rg -q 'camera_dof/opengl_fragment.glsl' "$voxel_test_dir/run.log"
fi
if [ "${LUANTI_TEST_CLOUD_GI:-false}" = true ]; then
 rg -q 'nodes_shader .*MATERIAL_EMISSIVE=1' "$voxel_test_dir/run.log"
 awk '
  /Voxel GI: cloud attenuation active=1/ { if (cleared) restored=1; covered=1 }
  covered && /Voxel GI: cloud attenuation active=0/ { cleared=1 }
  END { exit restored ? 0 : 1 }
 ' "$voxel_test_dir/run.log"
fi
if [ "${LUANTI_TEST_FOG_DENOISING:-false}" = true ]; then
 awk '
  /Fog integration: hidden lights/ { hidden=1 }
  hidden && /Fog denoising: history reset/ { reset=1 }
  /Fog integration: restored lights/ { restored=1 }
  restored && /Fog denoising: history active/ { resumed=1 }
  END { exit reset && resumed ? 0 : 1 }
 ' "$voxel_test_dir/run.log"
 rg -q 'Fog integration: submerged' "$voxel_test_dir/run.log"
 rg -q 'Fog integration: above water' "$voxel_test_dir/run.log"
fi
if [ "${LUANTI_TEST_EMISSION_MASK:-false}" = true ]; then
 rg -q 'SSAO: emission mask bound' "$voxel_test_dir/run.log"
 rg -q 'nodes_shader .*MATERIAL_EMISSIVE=1' "$voxel_test_dir/run.log"
 rg -q 'object_shader .*MATERIAL_EMISSIVE=1' "$voxel_test_dir/run.log"
 for phase in glowing ordinary unshaded; do
  rg -q "Emission mask integration: object $phase" "$voxel_test_dir/run.log"
 done
elif [ "${LUANTI_TEST_EMISSION_MASK:-}" = false ]; then
 if rg -q 'SSAO: emission mask bound' "$voxel_test_dir/run.log"; then exit 1; fi
fi
if [ -n "${LUANTI_TEST_DYNAMIC_LIGHTING:-}" ]; then
 for phase in 'held red' 'held green' 'item blue' 'legacy item blue' 'moved node red' hidden restored removed 'explicit black'; do
  rg -q "Dynamic lighting integration: $phase" "$voxel_test_dir/run.log"
 done
 if [ "$LUANTI_TEST_DYNAMIC_LIGHTING" = true ]; then
  awk '
   /Voxel GI: dynamic sources=1 held=1 emission=2,0,0/ { red=1 }
   red && /Voxel GI: dynamic sources=1 held=1 emission=0,2,0/ { green=1 }
   green && /Voxel GI: dynamic sources=1 held=0 emission=0,0,2 centroid=-3.25,2,-8/ { blue=1 }
   blue && /Voxel GI: dynamic sources=1 held=0 emission=2,0,0 centroid=4.25,2,4/ { moved=1 }
   moved && /Voxel GI: dynamic sources=0 held=0 emission=0,0,0/ { hidden=1 }
   hidden && /Voxel GI: dynamic sources=1 held=0 emission=2,0,0/ { restored=1 }
   restored && /Voxel GI: dynamic sources=0 held=0 emission=0,0,0/ { cleared=1 }
   /Dynamic lighting integration: explicit black/ { black=1 }
   black && /Voxel GI: dynamic sources=[1-9]/ { bad_black=1 }
   END { exit cleared && !bad_black ? 0 : 1 }
  ' "$voxel_test_dir/run.log"
 else
  if rg -q 'Voxel GI: dynamic sources=[1-9]' "$voxel_test_dir/run.log"; then exit 1; fi
 fi
fi
if [ "${LUANTI_TEST_DYNAMIC_DIRECT:-}" = true ]; then
 rg -q 'atlas columns=14' "$voxel_test_dir/run.log"
 if [ "${LUANTI_TEST_DYNAMIC_LIGHTING:-false}" = true ]; then
  rg -q 'Voxel dynamic direct: shader bound' "$voxel_test_dir/run.log"
  awk '
   /Voxel dynamic direct: sources=1 held=1 emission=2,0,0/ { red=1 }
   red && /Voxel dynamic direct: sources=1 held=1 emission=0,2,0/ { green=1 }
   green && /Voxel dynamic direct: sources=1 held=0 emission=0,0,2/ { blue=1 }
   blue && /Voxel dynamic direct: sources=1 held=0 emission=2,0,0/ { moved=1 }
   moved && /Voxel dynamic direct: sources=0 held=0 emission=0,0,0/ { removed=1 }
   END { exit removed ? 0 : 1 }
  ' "$voxel_test_dir/run.log"
 fi
elif [ "${LUANTI_TEST_DYNAMIC_DIRECT:-}" = false ]; then
 rg -q 'atlas columns=13' "$voxel_test_dir/run.log"
 if rg -q 'Voxel dynamic direct:' "$voxel_test_dir/run.log"; then exit 1; fi
fi
if [ -n "${LUANTI_TEST_TRANSMISSION:-}" ]; then
 if [ -n "${LUANTI_TEST_DYNAMIC_LIGHTING:-}" ]; then
  rg -q 'Transmission integration: moving light filter' "$voxel_test_dir/run.log"
 fi
 python3 - "$voxel_test_dir/run.log" "$LUANTI_TEST_TRANSMISSION" <<'PY'
from pathlib import Path
import re
import sys
log=Path(sys.argv[1]).read_text()
for phase in ('green','blue','inferred','removed'):
    assert 'Transmission integration: '+phase in log,phase
stage=0
seen=False
for line in log.splitlines():
    match=re.search(r'Voxel GI: filters=(\d+) transmission=([\d.e+-]+),([\d.e+-]+),([\d.e+-]+)',line)
    if not match: continue
    seen=True
    count=int(match[1])
    rgb=tuple(map(float,match.groups()[1:]))
    if sys.argv[2]=='false':
        assert count==0,'Opt-out must retain clear transport'
        continue
    green=all(abs(a-b)<0.00001 for a,b in zip(rgb,(128/255,1,128/255)))
    blue=all(abs(a-b)<0.00001 for a,b in zip(rgb,(128/255,128/255,1)))
    if count==3 and green: stage=max(stage,1)
    if stage==1 and count==3 and blue: stage=2
    if stage==2 and count==3 and rgb[0]>0.95 and 0<rgb[1]<0.3 and 0<rgb[2]<0.3: stage=3
    if stage==3 and count==0: stage=4
assert seen,'Expected completed worker transmission metadata'
assert sys.argv[2]=='false' or stage==4,'Expected authored green/blue, inferred red and cleared worker snapshots'
PY
fi
printf 'Voxel lighting integration: PASS\n'
