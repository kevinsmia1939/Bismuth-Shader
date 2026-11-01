#!/bin/bash
# Standalone camera passes; reuses the lighting fixture for camera/FOV transitions.
# Optional DRIVER=opengl, AA=fsaa/ssaa/taa, STEREO=sidebyside (LUANTI_TEST_ prefix).
# LUANTI_TEST_MOTION=false or LUANTI_TEST_DOF=false tests either effect alone.
set -euo pipefail
camera_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
camera_test_dir=$(mktemp -d /tmp/luanti-camera-test.XXXXXX)
trap 'rm -rf "$camera_test_dir"' EXIT
mkdir -p "$camera_test_dir/world/worldmods"
ln -s "$camera_root/util/voxel_lighting_test" "$camera_test_dir/world/worldmods/voxel_lighting_test"
cat > "$camera_test_dir/client.conf" <<EOF_CONFIG
video_driver = ${LUANTI_TEST_DRIVER:-opengl3}
3d_mode = ${LUANTI_TEST_STEREO:-none}
antialiasing = ${LUANTI_TEST_AA:-none}
fsaa = 2
screen_w = 480
screen_h = 320
fps_max = 30
enable_sound = false
opengl_debug = true
mg_name = singlenode
time_speed = 0
enable_post_processing = true
post_processing_texture_bits = 8
enable_camera_motion_blur = ${LUANTI_TEST_MOTION:-true}
enable_camera_dof = ${LUANTI_TEST_DOF:-true}
EOF_CONFIG
camera_status=0
timeout --kill-after=5 40 "$camera_root/bin/luanti" --config "$camera_test_dir/client.conf" --go \
 --world "$camera_test_dir/world" --gameid devtest --name CameraTest --info > "$camera_test_dir/run.log" 2>&1 || camera_status=$?
cat "$camera_test_dir/run.log"
if [ "$camera_status" -ne 0 ]; then exit "$camera_status"; fi
if [ "${LUANTI_TEST_MOTION:-true}" = true ]; then
 rg -q 'camera_motion/opengl_fragment.glsl' "$camera_test_dir/run.log"
fi
if [ "${LUANTI_TEST_DOF:-true}" = true ]; then
 rg -q 'camera_dof/opengl_fragment.glsl' "$camera_test_dir/run.log"
fi
for phase in 'low sun' noon 'custom direction'; do
 rg -q "Lighting integration: $phase" "$camera_test_dir/run.log"
done
if rg -q 'ERROR\[|failed to generate shaders|GL_INVALID' "$camera_test_dir/run.log"; then exit 1; fi
printf 'Standalone camera integration: PASS\n'
