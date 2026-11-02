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

ORM maps also have a separate data-texture cache and CPU-built RGBA8 mip chains.
Occlusion and metallic fraction use linear averages. Roughness is filtered in
GGX alpha-squared space: average `roughness^4`, then take its fourth root for
storage. This prevents mixtures of smooth and rough texels from acquiring the
overly narrow highlights of a color-averaged roughness value. Intermediate
moments stay unquantized; odd sizes, driver reductions, animation and reload use
the same path as normal maps. Source color textures and their alpha are unchanged.
Both maps retain ordinary texture sampling in the shader, without an extra
sampler, pass or live-frame CPU filtering. Hardware bilinear/trilinear sampling
still interpolates the encoded roughness between prepared texels/levels. This is
a bounded isotropic approximation, not exact filtering of the nonlinear BRDF.

The optional [Minetest Game material pack](../../textures/bismuth-minetest-game/README.md)
supplies restrained constant ORM companions for stone, cobble, steel, gold,
copper, mese lamps and mese blocks. It contains no replacement color artwork.
Ordinary unmapped textures remain rough dielectrics; the engine does not infer
metallicity from arbitrary albedo colors or filenames.

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

[Milestone 5](graphics-milestone-5.md) tracks the acceptance criteria and current
checks. The primary native target is Minetest Game. Earlier VoxeLibre results
remain in the historical milestones 2–4 report.

Numeric checks use production GLSL and floating-point pixel readbacks:

| Command in util/ | Coverage |
| --- | --- |
| `python3 test_material_maps.py` | Tangent normal orientation, mirrored/rotated UVs, derivative guards, linear ORM, absent maps, dielectric/conductor GGX, reciprocity, bounded highlights, environment occlusion and metallic emission |
| `python3 test_specular_filter.py` | Pixel-footprint variance, cutout participation, strength, directional/local composition and smooth-incidence precision |
| `python3 test_normal_mipmaps.py` | Actual coarse mip sampling, strength, shared roughness, directional/local GGX, raw-alpha guards and moving subpixel normal patterns |
| `python3 test_orm_mipmaps.py` | Roughness-aware minification, trilinear/subtexel stability, base data, production GGX and unmapped defaults |
| `python3 test_point_materials.py` | Local source response, all eight entries, visibility, colored transmission, source movement/removal and geometric-face guards |
| `python3 test_native_emission.py` | Full node-fragment preservation of native emission, including stale worker state and zero-RGB emitters |
| `python3 test_surface_directional.py` | Full-fragment mapped/unmapped and lower-capability fallbacks, sun/moon/custom sources, RGB shadow visibility and emissive/cloud composition |
| `python3 test_minetest_materials.py` | The shipped Minetest Game map bytes: matte stone, stronger bounded metal response and retained lamp emission |

Run these from the repository as `python3 util/<script>`. The default context
uses desktop GLSL 330. `LUANTI_TEST_GLSL=120` selects legacy GLSL. Mesa llvmpipe
is selected here with `SDL_VIDEODRIVER=offscreen`,
`__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json` and
`LIBGL_ALWAYS_SOFTWARE=true`. Tests print the actual renderer.

`bin/luanti --run-unittests` checks material serialization/legacy prefixes,
identity/grouping, animation and CPU mip moments. The opt-in command
`bin/luanti --run-tests '[normal-mips],[material-mips]'` checks actual OpenGL 3
and legacy texture uploads, every mip, reloads and format-flag restoration.

`bash util/test_material_shading.sh` creates a disposable devtest fixture with
explicit maps, local pack companions, animated maps, cutout and metallic-emissive
nodes, then replaces a mapped receiver with an ordinary node. Each state waits
for two completed-client frame checkpoints. `util/audit_material_runtime.py`
rejects missing frame coverage and incomplete shutdown. Optional switches:

- `LUANTI_TEST_DRIVER=opengl LUANTI_TEST_AA=fsaa LUANTI_TEST_STEREO=sidebyside`
  tests legacy GL with MSAA and both signed eye bindings.
- `LUANTI_TEST_DYNAMIC_DIRECT=true` inserts/removes a held lamp;
  `false` checks the asynchronous direct-light fallback.
- `LUANTI_TEST_DIRECTIONAL=true` tests zero shadow intensity, hidden sources,
  sunlight, moonlight and a restored custom direction.
- `LUANTI_TEST_POST_PROCESSING=false` tests forward rendering.
- `LUANTI_TEST_MIPMAPS=false` tests base-only data textures.
- `LUANTI_TEST_MATERIALS=false` tests the disabled-material fallback.
- `LUANTI_TEST_SHADOWS=false` tests compilation/binding without shadow maps.

The native runner `util/test_graphics_milestones.py` supports prepared Minetest
Game scenes and the legacy VoxeLibre inputs. `--texture-pack` accepts the supplied
ORM-only pack and requires actual native map binding. The eleven phases include
forest movement, sunset, river motion, water entry/exit, placed lamps and held
torch movement/removal, with scalar scene brightness and completed-frame gates.
The benchmark runner preserves game identity when copying worlds and stores
exact launch settings separately from settings saved on shutdown.

These tests do not capture images or send input-device events. Numeric patterns
and native scalar probes cover defined behavior; they cannot certify every
asset, every visible pixel or parity with a particular Minecraft shader pack.
