# Authored material shading

`enable_material_shading` now supports authored normal and packed material maps on
solid/alpha node surfaces. Desktop OpenGL with at least six material texture units
is required. The engine exposes eight slots; existing albedo, crack, voxel and
shadow bindings remain in slots 0–3, with normal/ORM in slots 4/5. Liquids and
waving foliage retain their existing shading. Unsupported drivers and unmapped
assets keep the existing albedo-derived detail/dielectric fallback.

## Authoring

A Lua tile table may provide `normal_texture` and `material_texture`, including on
base, overlay and special tiles. For example:

```lua
tiles = {{
    name = "stone.png",
    normal_texture = "stone_normal.png",
    material_texture = "stone_orm.png",
}}
```

Normal RGB encodes tangent-space XYZ from [-1,1] to [0,1]. +X follows tile U, +Y
follows V, and +Z points out of the surface. Neutral is approximately (128,128,255).
The normal strength is `material_map_normal_strength`, default 1, updated live.
The packed map is linear data: R = occlusion, G = perceptual roughness, B = metallic
fraction. White R means unoccluded; black B means dielectric, white B metallic.
Roughness is bounded to [0.045,1] to avoid singular highlights. Authored alpha in
both maps is ignored, and they bypass mesh color/transparent-pixel cleanup. They are not gamma-decoded.
The renderer may increase effective roughness where the shading normal varies
over the pixel footprint, reducing sharp highlight shimmer.

Without explicit names, a simple albedo filename may acquire `_normal` and `_orm`
companions before its extension from local texture packs. Games declare their
maps explicitly because server media may use `_normal` for ordinary color variants.
Local texture packs may supply these companions
without changing the game. Explicit names take priority; packs can override those
files by their existing names. Composite/modifier texture strings require explicit
map names. Map pixels must be authored for any image-space transforms in those
strings; arbitrary color modifiers are not a normal-vector transformation.

Maps share albedo UVs, face orientation, tile scale and wrap settings. The shader
builds a cotangent frame from world-position/UV derivatives, including mirrored or
rotated UVs. Degenerate derivatives return the geometric normal. A map can have
one static frame or match the albedo animation's frame count/layout. Each albedo
frame carries its corresponding normal/ORM textures; all three bindings update
together. A mismatched map warns and stays on its first frame.

## Lighting

Authored material highlights use GGX, height-correlated Smith visibility and
Schlick Fresnel in linear color. Dielectrics use F0 = 0.04. Metals interpolate F0
toward linear base texture color and remove diffuse response. Per-source GGX
peaks are bounded to 32 before bloom/exposure for stability. Directional
highlights use a world-space sun/moon source independent of shadow enablement,
shadow intensity and shadow-map coverage. Natural sources follow sky visibility
and fade at the horizon; moon radiance is halved. An authored
`shadows.direction` overrides the natural direction, including when sky lights
are hidden. `shadows.intensity` controls occlusion rather than reflected radiance.
Native daylight color is converted to linear color. RGB shadow visibility,
including colored-glass transmission, attenuates reflected light per channel;
unavailable, faded or unbound shadow maps retain unoccluded illumination.
Cloud transmission also attenuates reflected sunlight on emissive materials
without darkening their native self illumination. Preview/wield cameras do not
consume the world-space directional packet.

Mapped and unmapped surfaces add directional highlights in linear color. With
material-map support, both use the shared GGX helper; an unmapped surface is a
rough dielectric. The lower-capability fallback also adds its dielectric
highlight in linear color. Native artificial-light dominance suppresses the
directional contribution using the existing baked light-bank ratio. This remains
an approximation rather than separately calibrated diffuse/direct illumination;
limited shadow-map coverage still permits light leaking.

With voxel lighting and per-frame moving direct lights enabled, eligible node
surfaces also receive GGX highlights from held/moving lamps. The same bounded
eight-source loop traces occupancy and RGB transmission once for both diffuse
and specular response. Light distance, 16-node range/fade, current source color,
voxel coverage and direct-light strength apply to both. Direct specular is added
after metallic diffuse removal, so conductors can reflect lamps in dark scenes.
ORM occlusion affects bounce/environment, not direct lamp highlights. Emissive
variants retain their native lighting alongside reflected lamp light.

Moving-light diffuse and GGX visibility use the current map optics column,
updated independently of pending radiosity solves. Newly opened receivers retain
local highlights even if the old baked probe is still marked solid. Wall and
glass edits affect that shared direct-light path before the next bounce update;
see [voxel lighting](voxel-lighting.md) for coverage, costs and remaining latency.

Authored maps supply the shading normal, roughness and metallic F0. Unmapped
eligible surfaces use a rough dielectric fallback. Lights behind the geometric
face are rejected even if a normal map tilts toward them. Water, waving foliage and
general object materials keep their current separate shading paths. This path
requires the existing desktop OpenGL 3 per-frame-light support and material-map
capability; disabling either feature retains its existing rendering fallback.
It is independent of directional shadow strength, sun visibility and post
processing. No additional texture, uniform array, render target or pass is added.

The point-light loop and visibility traversal use bounded dynamic loop limits to
avoid large compile-time expansion on desktop drivers. GGX adds ALU work to
contributing lights, with no second visibility traversal. Zero-view, absent-atlas,
zero-strength and no-source cases return zero specular.

For surfaces with material-map support, derivatives of the geometric normal and
the decoded tangent-space normal estimate pixel footprint variance. A bounded
variance is added to GGX alpha-squared
(`roughness^4`), with the resulting roughness shared by directional highlights,
local highlights and environment approximation. Flat normals retain authored
roughness. The dielectric fallback uses the same filtered value. Normal/roughness
derivatives are evaluated before cutout discard; cutout testing still uses the
original base alpha, independent of crack overlays. GGX uses a cross-product
form of its normal/halfway denominator to avoid cancellation near smooth normal
incidence on drivers that reassociate floating-point expressions.

Normal maps now use a separate data-texture cache and CPU-built mip chains.
Each source normal is normalized after the existing positive-Z clamp. Successive
levels average those unit vectors without renormalizing the intermediate means;
RGB stores the mean and alpha stores the quantized square root of
`1 - dot(mean,mean)`. Equal-area filtering includes odd dimensions, single-pixel
axes and driver size reductions. Each animation frame has its own chain, so
neighboring frames cannot contaminate coarse levels. Raw source images and
ordinary color textures remain unchanged. The variance-bearing texture is forced
to RGBA8 with the driver's previous format flags restored afterward.

A separate binding flag enables variance decoding only on successfully prepared
normal textures. Unsupported image formats or upload failures retain the existing
normal path and continue ignoring asset alpha. Mips are rebuilt on reload; a flat
replacement clears the old variance. With mipmapping disabled, the prepared base
level has zero variance unless the driver reduced the source dimensions.

The shader adds half the decoded variance, scaled by live normal strength squared,
to the existing fragment-quad estimate before the shared 0.25 variance cap. The
result feeds directional/local GGX and environment roughness together. This is a
bounded small-angle approximation, with RGBA8 quantization and approximate
standard-deviation interpolation between mip levels. It does not retain an
anisotropic covariance matrix, exactly filter the nonlinear BRDF, or filter small
light sources and moving visibility boundaries. It omits variance from the cotangent
frame and the albedo-derived detail fallback to avoid undefined higher-order
derivatives ([GLSL specification](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.4.00.pdf)).
Motion vectors and finite-area lamps remain quality work. No additional sampler
or render pass is used. A source used as both a color texture and a normal map
has separate GPU copies; normal preparation does not reinterpret its color alpha.

A coarse sky/fog-tinted environment approximation gives metals a reflection even
without a resolved directional highlight. Roughness broadens that approximation;
it is not a prefiltered cubemap or an off-screen reflection render. The ORM
occlusion channel attenuates added voxel diffuse bounce and environment reflection;
it does not darken direct local light. Existing geometry SSAO remains downstream.
The voxel solver reduces donor diffuse reflectance by average metallic fraction,
using the primary material map. It still transports diffuse light, not specular
multiple-bounce paths. Map/palette tint remains in native diffuse lighting; metal
F0 currently comes from the base texture rather than a separate unlit tinted
albedo attachment.

Native baked diffuse lighting remains with bounded normal-detail modulation.
This does not replace the engine with a fully energy-calibrated material pipeline.
Emissive node variants preserve their native lighting term through metallic
diffuse attenuation, keeping glowing blocks lit. The current material variant
also protects native brightness during replacement of artificial light by the
voxel helper, including zero-RGB scene emitters and newly inserted lights.
The full-fragment checks in `util/test_native_emission.py` cover this classification
with and without frame-direct lighting; the local-GGX fixture checks metallic
emission in the artificial-light setting. There is no separate
emissive-map/lobe decomposition, parallax/displacement,
anisotropic BRDF, specular voxel transport, local reflection probes or authored
maps for general entity materials. Self illumination and baked diffuse remain
combined on emissive nodes rather than independently energy calibrated.
These limits remain part of the material/lighting quality audit.

## Transport and lifetime

Optional map names are appended as a versioned suffix to the length-wrapped
ContentFeatures payload, after the existing optional emission-color suffix.
Definitions without maps do not add this extension. Old readers ignore the tail;
new readers accept older payloads and clear reused map fields. TileDef's existing
inline serialization layout is unchanged. The Lua read/push paths preserve both
fields.

Tile material equality/hash includes the map identities so two nodes sharing an
albedo but using different maps cannot merge into one material. Textures remain
owned by TextureSource. AnimationInfo borrows the existing frame vector and clears
map bindings when a frame has none. No per-frame GPU material allocations are
required. Extra maps cost their texture/mipmap storage and extra per-pixel samples;
there is no extra render target or full-screen material pass.

## Verification

Run `python3 util/test_material_maps.py` with SDL2/desktop OpenGL available. The
actual shared GLSL is tested numerically for high texture units, tangent normal
orientation, mirrored/rotated UVs, degenerate derivatives, zero strength, linear
ORM channels, missing-map guards, dielectric/conductor GGX response, roughness,
BRDF reciprocity, bounded highlights, occluded environment reflection and
preservation of native emission on metallic lamps.
The tests print the actual renderer; `LUANTI_TEST_GLSL=120` selects legacy GLSL
instead of the default 330 core. On this NVIDIA desktop, Mesa llvmpipe is selected
with `SDL_VIDEODRIVER=offscreen`,
`__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json` and
`LIBGL_ALWAYS_SOFTWARE=true`. They send no input or image capture.

The C++ suite verifies extension round-trip/legacy prefixes/reset, material
identity/grouping and synchronized animation/clearing. The runtime test
`util/test_material_shading.sh` loads explicit game maps, local texture-pack
companions, an emissive metallic node and animated maps, then replaces a material with an unmapped node.
It checks actual shader bindings and clean shutdown with the quality preset.
Optional `LUANTI_TEST_DRIVER=opengl`, `LUANTI_TEST_AA=fsaa` and
`LUANTI_TEST_STEREO=sidebyside` select other rendering paths.
`LUANTI_TEST_POST_PROCESSING=false` checks the direct forward-rendering path.
`LUANTI_TEST_DYNAMIC_DIRECT=true` adds/removes a held lamp while mapped receivers
and animation remain active; `false` checks the asynchronous direct-light fallback.
`LUANTI_TEST_SHADOWS=false` checks compilation and binding without shadow maps.
`LUANTI_TEST_DIRECTIONAL=true` exercises zero shadow intensity, hidden sky lights,
sun, moon and a restored custom direction, requiring the actual world shader
bindings to report each source state.

`python3 util/test_surface_directional.py` compiles the full production node
fragment and reads numeric floating-point pixels. It checks mapped conductors,
unmapped and lower-capability dielectric fallbacks, disabled/zero/faded shadows,
RGB transmission, hidden sources, moon strength, native-light ratios, degenerate
views, geometric-face guards and emissive/cloud composition. The water variants
check sun glints independently of shadows and preservation of artificial light
in the legacy sky fallback. No screenshots or input events are generated.

These full-fragment checks passed on NVIDIA GLSL 120/330 and Mesa llvmpipe
GLSL 330. The Release build and full C++ suite passed again (353 individual
tests and 50 Catch cases), including source selection, visibility, horizon fade,
linear daylight conversion and custom-direction normalization. Live source-control
tests passed on OpenGL 3/TAA with shadows enabled and disabled, on legacy
OpenGL/4x MSAA/stereo, and with post processing disabled. The shadow-enabled
fixture requires an actual bound shadow map as well as sun/moon/custom source
transitions. The full-quality water basin passed with shadows disabled, requiring
the directional packet to bind on a real refractive liquid material alongside
source/flow geometry and medium transitions. The water-reflection shader flag
and its settings dependency no longer require shadow maps.
The native VoxeLibre terrain-copy run also passed with the final source packet,
real water binding, held-torch RGB insertion/removal, colored voxel lighting,
cloud/fog denoising and underwater transitions enabled together. These numeric
and runtime checks do not establish visual parity or frame-rate targets.

`python3 util/test_point_materials.py` tests the actual shared GGX/voxel helpers
and extracts the node material-composition block and directional GGX expression.
Numeric checks cover dielectric/conductor response, roughness, view dependence,
reciprocity, all eight source entries, colored transmission, occlusion, movement,
removal, finite peaks and missing-data/strength guards. Node checks cover mapped
normal response, rough unmapped fallback, metallic composition, preserved emission,
ORM occlusion, alpha, field-edge coverage and camera-origin conventions. The
directional control checks clear/opaque and colored/fractional shadow visibility.
No screenshots or input events are generated.

`python3 util/test_specular_filter.py` checks the actual node roughness-filter
expression and directional/local composition. It verifies flat roughness,
monotonic and bounded normal variance, smooth-incidence precision, metallic
lamp highlights, derivative participation at a cutout edge, sampled tangent
normals, map strength, geometric variance and absent-map guards. The runtime
material fixture also places an alpha-clipped block with authored normal/ORM
maps. Numeric filtering and existing material/local-light regressions passed
on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330.
The mapped cutout fixture with filtered roughness passed on OpenGL 3/TAA,
including held-light insertion/removal, animated companions and clean shutdown.
It also passed on legacy OpenGL/4x MSAA/stereo and OpenGL 3/TAA/stereo with
both signed eye bindings, with post processing disabled, and with asynchronous
direct lighting restored. The native VoxeLibre torch/water integration passed
again with the final filter and precision correction. These checks cover
shader execution and source/medium transitions; warm-frame performance and
visual comparisons across games remain separate audits.

The Release build and full C++ suite passed in this workspace (353 individual
tests and 48 Catch cases). Numeric material tests passed on the NVIDIA GTX 1650 Ti
with GLSL 120/330 core and on Mesa llvmpipe with GLSL 330 core. Runtime material
tests passed on OpenGL 3/TAA, legacy OpenGL/4x MSAA and side-by-side stereo/TAA.
The mapped-material fixture also passed with post processing disabled. A separate
side-by-side OpenGL 3/4x MSAA run preserved water capture and ordered RGB source
updates with the expanded material texture slots.
They verified local texture-pack loading, emissive variants and actual normal/ORM
bindings. These checks establish implemented behavior; they do not prove parity
with a particular Minecraft shader pack or performance on other hardware.

Local/directional specular numeric tests passed on NVIDIA GLSL 120/330 and Mesa
llvmpipe GLSL 330, alongside the existing diffuse/atlas regression on all three
configurations. The combined held-lamp material run passed on OpenGL 3/TAA and
legacy OpenGL/4x MSAA/side-by-side stereo, with authored/companion/animated maps,
source removal, fog/water quality effects and clean shutdown. The first prototype
hit the cold shader-compilation timeout before gameplay. Dynamic loop bounds and
compile-time omission of ineligible water/foliage GGX completed the subsequent
cold run; warm-frame performance remains hardware/scene dependent.
The explicit asynchronous-direct fallback also passed with mapped receivers
and held-lamp source updates, using the 13-column atlas without local GGX.
The held-lamp material fixture passed with post processing disabled as well,
exercising the same local-highlight path in forward rendering.

The combined voxel quality fixture also passed with frame-direct lighting,
dynamic sources, RGB transmission, emissive SSAO coverage, fog denoising and
water geometry enabled together. A native VoxeLibre world copy passed with the
full quality preset, native held-torch insertion/removal and underwater
transitions. Both current-frame and completed-worker light lists carried the
warm torch RGB and cleared after removal. These runs do not establish visual
parity with a Minecraft shader pack.

View-dependent material uniforms use the rendered camera node plus the map
origin, including each stereo eye displacement. Stereo offsets also update the
absolute camera transform immediately, so water capture and medium checks made
before scene traversal see the current eye. The stereo material fixture checks
that active material shaders receive both signed eye offsets.
After the camera correction, the Release build and full C++ suite passed again,
as did the held-lamp material fixture on legacy OpenGL/4x MSAA/stereo and
OpenGL 3/TAA/stereo, including both material-eye binding checks.
The native VoxeLibre torch/water integration passed again after that correction.

A copied VoxeLibre night world also ran with the full quality preset and shut
down cleanly. Its nine colored emissive sources remained active, and ordinary
server `_normal` color textures were not auto-bound as material maps.
