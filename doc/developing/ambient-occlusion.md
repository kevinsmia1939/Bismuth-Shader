# Screen-space ambient occlusion

Enable `enable_ssao` under Settings > Graphics > Post Processing and restart the
client. Post processing must be enabled. The default remains disabled to preserve
performance on low-end hardware. `misc/graphics-quality.conf` combines this pass
with the engine's shadows, bloom, volumetric lighting, water reflections, and
filmic tone mapping for an optional quality preset. Games must also enable shadow
intensity and volumetric light strength via `player:set_lighting`; the preset
respects the game's lighting settings.

`ssao_radius` controls the sampling distance in nodes (default 0.75).
`ssao_strength` controls darkening (default 1.0; zero leaves colors unchanged).
Both numeric controls can be changed without rebuilding the pipeline.
`enable_ssao_emission_mask` defaults to true and requires a restart to change.
It allocates resources only while SSAO and its hardware requirements are enabled.

The renderer resolves multisampling first, then runs the `ssao` shader against
surface color and the unfiltered depth attachment, before cloud compositing,
surface reflections/screen-space bounce, fog and underwater-volume scattering.
The cloud composite receives the AO-shaded color rather than the original scene
texture. Thus cloud/fog/water source terms do not inherit surface creases, and
reflection donors include the surface's occlusion. Both inline and separately
filtered fog follow this ordering. It reconstructs view-space
positions using the current camera's inverse projection, so field of view,
aspect ratio, camera offset, and near/far plane changes are accounted for.
Normals use the closest depth neighbor on each screen axis to reduce dark halos
at silhouettes. Sixteen fixed spiral samples estimate nearby occlusion with a
world-space falloff and an angular bias to avoid shading coplanar surfaces.
Attenuation is applied in linear light; alpha and sky pixels are preserved.

When the optional surface MRT is available, a bound-guide guard identifies
positive water depth with valid alpha, including interfaces near the camera.
Their already-refracted/scattered surface color is preserved instead of shading
it as the opaque floor behind it. A nearer depth-writing object rejects a stale
water marker and still receives SSAO. Missing guides retain the depth-only path;
sky and zero-strength bypasses precede any surface-guide sampling. The pass does
not allocate a surface MRT just for SSAO.

## Emissive coverage

On desktop OpenGL 3+, SSAO can use a separate R8 coverage attachment. It needs
two color outputs and three texture units without surface metadata, or three
outputs and four texture units with it. Irrlicht reports the usable output count
as the minimum of color-attachment and draw-buffer limits. R8/float-target support
is checked too. Unsupported configurations and the disabled option retain ordinary
SSAO without allocating or sampling a mask.

Emissive map nodes and glowing/unshaded objects using `object_shader` write the
mask alongside scene color, independently of enabling authored material maps.
Transparent fragments use their scene alpha, so a
glass/ordinary layer does not erase a glowing surface behind it. Opaque ordinary
fragments overwrite protection. MSAA resolves the mask independently from scene
color and normal/depth metadata; partial coverage blends AO visibility toward one.
Fully covered emissive faces bypass the depth neighborhood. Receiver alpha is
preserved, and a binding guard prevents absent-mask sampling.

Each eye clears the mask to zero every frame through a temporary mask-only target
activation, then restores the scene target without another clear. This avoids
using sky color as emission and prevents source-removal trails, including when
the sky is hidden. It adds no full-screen shading pass. The existing normal/depth
guide keeps alpha one; its blending is unchanged. Glow zero/nonzero transitions
refresh object shader classification, while glow intensity updates within the
same class keep their existing light-update path. Explicitly unshaded objects
also retain their authored lighting instead of acquiring cloud/voxel illumination.

Logical mask storage is about 2 MiB per eye at 1920×1080 before driver padding.
MSAA adds sample-count-scaled storage for its unresolved mask. Ordinary shaded
receivers cost one extra small texture lookup; full emissive faces skip the
occlusion neighborhood. Arbitrary node/item entity visuals and custom shaders
without the mask output are not automatically classified as emissive. Coverage
is categorical/fractional, not an exact split of mixed-pixel emitted and reflected
radiance. Bloom and optical attenuation still apply to light-source faces.

The shaded scene feeds bloom extraction, exposure metering, FXAA, and final tone
mapping. Disabling SSAO avoids its draw call and additional color target entirely.
It uses existing Irrlicht depth textures, optional surface metadata and render
targets without adding a normal buffer or changing the material/texture-pack format.

This is a screen-space approximation: hidden/off-screen geometry cannot cast
ambient shading, and blended surfaces that do not write depth cannot contribute.
It still attenuates combined native surface lighting rather than separating
ambient and direct terms; native per-material fog and optical effects are not
fully decomposed. Emissive receivers are protected where the mask is available.
Without surface metadata it cannot identify water
receivers separately. It costs one full-resolution color target and a pass with
21 depth fetches per shaded opaque pixel plus one optional surface-guide lookup,
so measure on target hardware. Water receivers with a valid guide bypass the
depth neighborhood. Supersampling
increases this cost. There is no temporal accumulation or history buffer.

For validation, compare the same camera with SSAO off/on, then check sky and flat
surfaces, close corners, silhouettes, transparent water, different aspect ratios,
and combinations of MSAA, SSAA, FXAA, bloom, and auto exposure. The existing
`util/test_singleplayer.sh` shader smoke test includes SSAO.

## Validation

`python3 util/test_surface_ao.py` compiles the actual SSAO, cloud/fog composites
and loaded-water volume shaders. Numeric float-pixel tests check flat/sky/zero
bypasses, corner attenuation, alpha, water/nearer-object classification and absent
guide guards. Composed passes verify that only surface radiance inherits AO,
while cloud/fog/underwater scattering stays independent. A regression control
also evaluates the incorrect order that darkens the accumulated volume radiance.
The actual node output block is also checked through RGBA16F MRT alpha blending
for water, opaque and emissive variants: validity alpha remains one so blended
metadata does not corrupt normals/depth.
No images or input events are generated. `LUANTI_TEST_GLSL=120` selects legacy
GLSL; default is 330 core. The tests report the actual renderer.

The quality voxel integration requires an actual bound SSAO surface guide. Use
`LUANTI_TEST_SSAO=true/false` to override the quality preset, or enable it without
the preset to exercise the depth-only path. OpenGL ES and mobile hardware have
not been exercised.

The Release build and full C++ suite passed with 353 individual tests and 34 Catch
cases. Numeric tests passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330.
Combined quality integration passed with OpenGL 3/TAA and legacy OpenGL/4x MSAA/
side-by-side stereo, including actual surface-guide bindings, RGB source removals
and fog/water transitions. The depth-only OpenGL 3/TAA configuration also passed
without a surface guide. These are correctness checks, not GPU frame-rate claims.
The SSAO-disabled quality path also passed with no surface-guide activation.
An isolated native VoxeLibre biome copy completed underwater/above-water/
submerged-again poses with surface-guide binding, inline fog, and clean shutdown.

`python3 util/test_scene_emission.py` checks the actual node output/helper and
SSAO receiver in both attachment layouts. It validates R8 blending, transparent
pass-through, ordinary opaque overwrite, frame clearing without erasing scene
color, normal/depth preservation, full/partial emissive coverage, unavailable
bindings, and 4x MSAA resolves of color/guide/mask independently. Numeric tests
passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330. Add
`LUANTI_TEST_EMISSION_MASK=true` to the voxel integration test for live object
glow/non-glow/unshaded transitions and actual mask-binding assertions; `false`
checks the explicit opt-out. Cold shader compilation can require a longer harness
timeout (`LUANTI_TEST_TIMEOUT`), independently of warm-frame rendering performance.

With the emission mask enabled, combined quality integration passed on OpenGL 3
with TAA and legacy OpenGL with 4x MSAA/side-by-side stereo. Both runs exercised
live glowing/ordinary/unshaded object transitions, RGB source removal, fog/water
transitions and clean shutdown. Standalone SSAO with fog denoising also passed
with `LUANTI_TEST_MATERIAL_SHADING=false` and without the normal/depth attachment,
exercising the second mask layout. Its assertions require actual emissive map-node
and object shader variants, independently of material-map support. The
explicit mask-disabled quality run passed with the surface guide bound and no
emission-mask binding. Authored/companion normal and ORM maps, synchronized
animation and texture-pack overrides also passed material integration with both
the surface guide and emission mask bound.
An isolated native VoxeLibre biome copy completed generated-water submerged/
above/submerged-again transitions with both bindings and clean shutdown. This
fixture changes player poses and cloud controls without placing or removing
terrain.
