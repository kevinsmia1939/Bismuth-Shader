#!/bin/bash
# Test cloud controls, layer transitions and the post-processing pipeline.
# Optional: LUANTI_TEST_DRIVER=opengl, LUANTI_TEST_AA=fsaa, LUANTI_TEST_STEREO=sidebyside.
# LUANTI_TEST_CLOUD_ONLY=true disables the other quality effects.
# LUANTI_TEST_CLOUD_DENOISING=false checks the original cloud path without history.
set -euo pipefail
cloud_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cloud_test_dir=$(mktemp -d /tmp/luanti-cloud-test.XXXXXX)
trap 'rm -rf "$cloud_test_dir"' EXIT
mkdir -p "$cloud_test_dir/world/worldmods"
ln -s "$cloud_root/util/volumetric_clouds_test" "$cloud_test_dir/world/worldmods/volumetric_clouds_test"
cp "$cloud_root/misc/graphics-quality.conf" "$cloud_test_dir/client.conf"
cat >> "$cloud_test_dir/client.conf" <<EOF_CONFIG
video_driver = ${LUANTI_TEST_DRIVER:-opengl3}
3d_mode = ${LUANTI_TEST_STEREO:-none}
antialiasing = ${LUANTI_TEST_AA:-taa}
fsaa = 4
screen_w = 480
screen_h = 320
fps_max = 30
enable_sound = false
opengl_debug = true
mg_name = singlenode
time_speed = 0
enable_cloud_denoising = ${LUANTI_TEST_CLOUD_DENOISING:-true}
EOF_CONFIG
if [ "${LUANTI_TEST_CLOUD_ONLY:-false}" = true ]; then
 printf '%s\n' enable_bloom=false enable_auto_exposure=false enable_dynamic_shadows=false \
  enable_volumetric_lighting=false enable_water_reflections=false enable_water_refraction=false \
  enable_ssao=false enable_atmosphere=false enable_screen_space_reflections=false \
  enable_material_shading=false enable_indirect_lighting=false enable_voxel_lighting=false \
  enable_camera_motion_blur=false enable_camera_dof=false enable_water_volume=false >> "$cloud_test_dir/client.conf"
fi
cloud_status=0
timeout --kill-after=5 75 "$cloud_root/bin/luanti" --config "$cloud_test_dir/client.conf" --go \
 --world "$cloud_test_dir/world" --gameid devtest --name CloudTest --info > "$cloud_test_dir/run.log" 2>&1 || cloud_status=$?
cat "$cloud_test_dir/run.log"
if [ "$cloud_status" -ne 0 ]; then exit "$cloud_status"; fi
rg -q 'Volumetric clouds: periodic noise atlas ready' "$cloud_test_dir/run.log"
rg -q 'Volumetric clouds: active height=8 thickness=8 coverage=0.7' "$cloud_test_dir/run.log"
for phase in 'below layer' clear 'flat fallback' 'hidden sky' 'inside layer' 'above layer'; do
 rg -q "Cloud integration: $phase" "$cloud_test_dir/run.log"
done
rg -q 'Cloud shadows: receiver bound nodes' "$cloud_test_dir/run.log"
rg -q 'Cloud shadows: receiver bound objects' "$cloud_test_dir/run.log"
awk '
 /Cloud shadows: active/ { if (!active) active=1; else if (inactive) resumed=1 }
 active && /Cloud shadows: inactive/ { inactive=1 }
 END { exit active && inactive && resumed ? 0 : 1 }
' "$cloud_test_dir/run.log"
if [ "${LUANTI_TEST_CLOUD_DENOISING:-true}" = true ]; then
 awk '
  /Cloud integration: clear/ { clear=1 }
  clear && /Cloud denoising: history reset/ { reset=1 }
  reset && /Cloud denoising: history active/ { resumed=1 }
  END { exit resumed ? 0 : 1 }
 ' "$cloud_test_dir/run.log"
fi
if rg -q 'ERROR\[|failed to generate shaders|GL_INVALID' "$cloud_test_dir/run.log"; then exit 1; fi
printf 'Volumetric cloud integration: PASS\n'
