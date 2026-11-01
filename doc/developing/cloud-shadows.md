# Cloud shadows

`enable_cloud_shadows` makes the volumetric cloud field attenuate direct light on
terrain, non-glowing entities and volumetric fog. The graphics quality preset
enables it. Default settings leave it off. It requires volumetric clouds, float
render targets and eight material texture units on desktop OpenGL.

## Shared field and projection

One RGBA16F map is generated per frame, before the scene pipeline and either
stereo eye. It uses `common/volumetric_clouds.glsl`, sharing cloud density,
coverage, height, thickness, wind, seed offsets, detail and opacity with the
visible volume. Sky/cloud visibility and the selected sun, moon or custom light
direction also come from the same uniform path. Disabled, empty, transparent,
flat or hidden cloud layers produce no terrain attenuation.

Each map texel traces 24 midpoint samples along the light direction through the
layer. Four channels store transmission from normalized layer heights 0, 1/3,
2/3 and 1 toward the light. Receivers below the layer use its full transmission;
receivers inside interpolate in optical depth; receivers beyond the light-facing
boundary stay unattenuated. Downward custom lighting uses the upper boundary as
the entry plane and reverses the normalized height. This also handles objects
and terrain at different elevations.

Spatial filtering averages transmission, preserving light across cloud edges.
The generator uses physical framebuffer texel coordinates so X/Z orientation
agrees with receiver texture coordinates. A camera-centered light projection is
snapped to world texels; movement within a texel preserves sampling positions.
Both eyes share the same map. Receivers use camera-relative coordinates, so
camera-origin rebasing preserves the field. The edge of finite map coverage fades
to unattenuated light rather than clamping distant receivers to border shadows.

Nearly horizontal rays fade out between absolute light Y components 0.02 and
0.08. This bounds the otherwise singular light-plane projection. The optical
integration retains the actual slanted path length above that cutoff.

## Lighting and bindings

Terrain borrows texture unit 7 while drawing. Entity materials attach the map
only for shaded objects with `glow == 0`; glowing/unshaded entities retain
authored lighting.
The direct-fog pass uses the same map. Map allocation, shader readiness and
actual material bindings gate sampling; missing maps preserve native lighting.
Scene materials release borrowed bindings, and core destruction clears entity
references while the renderer's device remains alive.

Native baked day lighting combines direct sunlight and diffuse skylight. A
0.65 directional share, weighted by face orientation, day/night ratio and existing
colored geometry-shadow visibility, estimates how much cloud attenuation to
apply. Artificial light, ambient share and already occluded sunlight are
protected. Explicit water glints, foliage backlighting and material sun terms are
attenuated separately, avoiding a second diffuse estimate on those terms.
Emissive node materials retain their native lighting. Their classification is
enabled for cloud shadows independently of authored material maps or the SSAO
emission mask, including base, overlay and special tiles.
The standalone cloud-GI fixture passed with material shading and the SSAO mask
explicitly disabled, requiring emissive node shader variants and overcast/clear/
restored worker uploads alongside RGB map-source removals.

Cloud attenuation also gates source-water caustics and direct volumetric fog
scattering. Fog ambient scattering is preserved. Voxel GI attenuates directional
irradiance at each visible reflecting face before transporting any bounces;
direct emission and reflected lamp light stay unchanged. The worker captures the
field that generated the current map, including projection, wind, density, seed,
detail, coverage, strength and readiness. It evaluates only needed map texels and
caches them within a solve, using the same 24 samples, transmission filtering,
height interpolation, coverage fade and horizon fade. There is no GPU readback
or additional GPU texture. CPU interpolation and GPU hardware filtering/half-float
storage have small rounding differences; numeric comparisons bound these.

The screen-space bounce option gathers donor pixels that already include cloud
attenuation; applying transmission a second time would double-count it. Native
baked direct/ambient calibration and emissive-surface specular separation remain
work. The feature does not provide a full physical decomposition of native
lighting. Worker-driven GI inherits the existing snapshot interval and solve
latency, so rapidly changing clouds can precede their updated bounced light.

## Controls and cost

- `enable_cloud_shadows`: pipeline/shader switch; restart.
- `cloud_shadow_strength`: 0–1, default 0.75; live. Zero skips map generation.
- `cloud_shadow_distance`: radius in nodes, 16–1024, default 256; live.
- `cloud_shadow_resolution`: 128–1024, default 256; restart.

The default map occupies 0.5 MiB, shared by both eyes. Generation cost grows with
resolution squared: 256² × 24 density samples, with additional noise lookups for
detail. Receivers use one filtered map lookup and optical-depth interpolation.
Distance changes spatial resolution at a fixed texture size. The three vertical
intervals approximate partial-layer transmission in heterogeneous clouds. Fine
structure below map texel size, low sun angles, volume denoising and broader
performance/appearance tuning remain limits. These settings control cloud
attenuation separately from geometric shadow-map strength/tint.

## Verification

`python3 util/test_cloud_shadows.py` compiles the actual generation and sampling
GLSL. It checks native density-profile integrals, oblique/downward rays, empty
and unavailable guards, receiver elevations, origin shifts, spatial energy
filtering, artificial-light preservation, explicit node sun terms and ambient fog
preservation. A generated float map is copied directly to the receiver sampler to
verify end-to-end transport and both texture axes. No images or input events are
generated. `LUANTI_TEST_GLSL=120` selects legacy GLSL; default is 330 core.

The C++ suite checks projected origins, texel snapping, downward lighting,
negative/far coordinates and degenerate layers/rays. The Release build and full
suite passed with 353 legacy tests and 29 Catch cases. Numeric tests passed on
NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330.

`python3 util/test_cloud_field.py` compiles the production CPU sampler and compares
it to actual GLSL using the RGBA8 noise atlas and generated RGBA16F map. It checks
negative/far coordinates, wind/seed offsets, partial layers, both light signs,
coverage/detail, horizon fade, strength and unavailable fields. Voxel transport
tests verify sun-driven bounce attenuation and unchanged direct/reflected lamp
emission. Add `LUANTI_TEST_CLOUD_GI=true` to the voxel integration test to require
overcast → clear → restored attenuation in completed worker results.
The CPU/GPU test passed 384 comparisons on NVIDIA GLSL 120/330 and Mesa llvmpipe
GLSL 330, using a 256² map. Maximum transmission differences were below 0.0032
(absolute transmission), including hardware interpolation and half-float storage.
Live overcast/clear/restored GI checks passed with the full quality preset on
OpenGL 3/TAA and legacy OpenGL/MSAA/side-by-side stereo.
The cloud-disabled voxel integration also passed, retaining unattenuated
directional injection and the existing RGB source-removal sequence.

`util/test_volumetric_clouds.sh` checks below/inside/above-cloud poses, density
clearing, zero-thickness fallback, hidden sky and restoration. It requires real
terrain and object bindings plus active/inactive/resumed map transitions. Use
`LUANTI_TEST_CLOUD_ONLY=true` for independent clouds/shadows, or
`LUANTI_TEST_DRIVER=opengl LUANTI_TEST_AA=fsaa` and
`LUANTI_TEST_STEREO=sidebyside` for renderer variants. These four configurations
passed, including full-quality rendering with fog. Colored-light source removal
(`LUANTI_TEST_QUALITY=true LUANTI_TEST_WATER_VOLUME=true
util/test_voxel_lighting.sh`) and authored/companion/animated material-map
integration (`util/test_material_shading.sh`) also passed with cloud shadows
enabled. The visible-cloud transport, composite and TAA numeric regressions passed.

A native VoxeLibre test on an isolated copy of a generated biome completed
underwater, above-water and submerged-again poses with active cloud shadows and
a clean shutdown. The cloud-aware GI rerun also uploaded attenuated directional
injection for 1,567 sunlit faces in native terrain. The optional
`native_water_test_clouds` setting on `util/voxelibre_water_test` supplies a
deterministic cloud layer without placing terrain. Runtime checks establish
pipeline behavior; they do not establish
general GPU frame-rate or visual-quality targets.
