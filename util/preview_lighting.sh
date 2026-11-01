#!/bin/bash
# Fixed visual comparison scene. Usage: util/preview_lighting.sh [baseline|atmosphere|full]
set -eu
preview_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
preview_mode=${1:-full}
case "$preview_mode" in baseline|atmosphere|full) ;; *) echo "Expected baseline, atmosphere, or full" >&2; exit 1 ;; esac
preview_world="$preview_root/worlds/lighting-preview"
mkdir -p "$preview_world/worldmods"
ln -sfn "$preview_root/util/lighting_preview" "$preview_world/worldmods/lighting_preview"
preview_config=$(mktemp /tmp/luanti-lighting-preview.XXXXXX.conf)
trap 'rm -f "$preview_config"' EXIT
cp "$preview_root/misc/graphics-quality.conf" "$preview_config"
cat >> "$preview_config" <<EOF_CONFIG
mg_name = singlenode
fixed_map_seed = 42
time_speed = 0
video_driver = ${LUANTI_PREVIEW_DRIVER:-opengl3}
antialiasing = ${LUANTI_PREVIEW_AA:-taa}
fsaa = 4
screen_w = 1280
screen_h = 720
fullscreen = false
fps_max = 30
viewing_range = 80
show_debug = false
lighting_preview_motion = ${LUANTI_PREVIEW_MOTION:-false}
mod_storage_backend = sqlite3
EOF_CONFIG
if [ "$preview_mode" != full ]; then
 cat >> "$preview_config" <<EOF_CONFIG
enable_material_shading = false
enable_indirect_lighting = false
EOF_CONFIG
fi
if [ "$preview_mode" = baseline ]; then
 cat >> "$preview_config" <<EOF_CONFIG
enable_atmosphere = false
enable_screen_space_reflections = false
EOF_CONFIG
fi
"$preview_root/bin/luanti" --config "$preview_config" --go --world "$preview_world" --gameid devtest --name LightingPreview
