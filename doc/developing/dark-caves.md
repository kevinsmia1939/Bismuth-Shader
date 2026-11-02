# Unlit caves remain dark

The renderer used the camera's outdoor fog color as unoccluded environment light.
Mapped cave walls could therefore reflect a bright sky even when their native
skylight was zero. Legacy fog, analytic haze and volumetric ambient fog could
also add that tint with distance, exposing the cave's shape. Testing only a
nighttime cave did not exercise this daylight failure.

Material environment reflection and legacy node/object fog now follow local
native skylight rather than the global sky alone. The existing RGBA16F surface
attachment carries the local skylight estimate alongside normal and signed
depth. Analytic and volumetric sky scattering use that estimate; directional fog
also retains shadow-map occlusion. Water's sky fallback follows the same local
access. Real screen-space reflection hits, lamps, emission and diffuse bounce
remain independent. Tone mapping preserves zero instead of lifting black through
a rounded constant.

This is a conservative native-light-bank estimate, not a hemispherical sky probe
at every air sample. In particular, a dark endpoint does not acquire sunlight
fog solely because an incomplete/unavailable shadow map says it is unoccluded.
Local voxel-lit fog still evaluates actual lamp visibility independently.

## Surface metadata and blending

Auxiliary alpha stores `1 + skylight / SCENE_SKY_DIVISOR` on covered surfaces;
zero marks empty pixels. The divisor is one without MSAA, and twice the configured
sample count with MSAA. This keeps partially covered resolved samples below the
validity tag of one. FP16 quantizes skylight more coarsely with higher sample
counts. Ordinary per-surface lighting retains its unquantized native value.

The scene surface and emission buffers clear separately to zero, rather than
inheriting the sky-colored scene clear. A material's auxiliary blend mask disables
blending on the surface attachment only. Color and emission coverage continue
blending normally, including configurations with an emission buffer but no surface
buffer. OpenGL 3 exposes its indexed blend-enable capability; the legacy driver
uses the existing extension. Drivers lacking this capability retain the forward
fog/conservative post-processing fallback. No new texture or render pass is added.

## Verification

`python3 util/test_dark_caves.py` tests production shader paths numerically:

- Mapped/unmapped black walls and objects against a bright outdoor sky/fog.
- Actual node MRT output and MSAA coverage tags, including transparent geometry.
- Analytic, inline volumetric and separated/filtered fog with and without shadows.
- Blocked and incomplete shadow-map cases, continuous partial skylight, water
  fallback and exact final black through tone mapping.
- Positive controls for real skylight, artificial illumination and outdoor water.

`bin/luanti --run-tests '[surface-blend]'` exercises actual OpenGL 3 and legacy
driver draws to three floating-point targets. It checks normal/depth/skylight
preservation, color/emission coverage and restoring ordinary blend behavior.
The full C++ suite and existing material, fog, cloud-shadow, water and emission
regressions supplement these checks.

The native Minetest Game replay uses an explicit bright sky/fog override, noon,
zero-light cave receivers, placed mese lamps and held torches:

```sh
python3 util/test_graphics_milestones.py /path/to/prepared-world \
  --output /tmp/daylight-cave \
  --texture-pack textures/bismuth-minetest-game --daylight-cave
```

The extra gate requires all three unlit/removal stages to have mean RGB below
`1e-7`, while retaining the normal lamp-brightening/color/removal checks. Numeric
readbacks and scripted fixtures are used without screenshots or input-device
automation. See the [recorded results](dark-caves-results/README.md).
