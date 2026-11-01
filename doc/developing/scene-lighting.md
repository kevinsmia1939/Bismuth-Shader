# Optional scene lighting

The quality preset in `misc/graphics-quality.conf` now also selects TAA and optional
camera vignette (see `temporal-antialiasing.md`). It enables ray-marched clouds,
shadowed volumetric fog,
water screen-space reflections/refraction, material detail and voxel radiosity,
in addition to the engine's existing shadows and post processing. All new effects default to
disabled. The quality preset uses the voxel-lighting solver instead of screen-space
bounce (see `voxel-lighting.md`) and replaces screen-space bloom god rays with
integrated fog (see `volumetric-fog.md`). Toggle effects in Settings and restart the
client to rebuild the pipeline. Density, reflection strength, bounce strength,
and bounce radius can be adjusted live; material controls require restart.
The preset also enables contact-hardening sunlight shadows; see `soft-shadows.md`
for the blocker search, light angle and compatibility behavior.
Optional depth of field and camera motion blur are described in `camera-effects.md`.
Surface SSAO runs before cloud/fog/underwater compositing, so these volume source
terms do not acquire surface occlusion. Valid water surface metadata protects
already-refracted water color; see `ambient-occlusion.md` for the fallback and
native-lighting decomposition limits.

For a repeatable scene, run `util/preview_lighting.sh baseline`, then
`util/preview_lighting.sh atmosphere`, then `util/preview_lighting.sh full`.
These launch DevTest in the generated `worlds/lighting-preview` world, with a
fixed camera and time of day. The middle stage enables haze and water reflections;
the final stage also enables material detail and diffuse color bounce. The scene
sets game lighting through `player:set_lighting`; games retain control over shadow
intensity and volumetric light strength. The script copies the preset to a
temporary config rather than modifying it.

## Atmosphere

`enable_atmosphere` adds height-dependent exponential haze, wavelength-dependent
extinction, and a forward sunlight glow. `atmosphere_density` is optical density
per node, default 0.003. Scattering takes its color from the game's fog, daylight,
and sun direction. This preserves sky overrides, and atmospheric haze is bypassed
when the camera is inside a liquid or a non-light-propagating node. Geometry is
processed before exposure, bloom, FXAA, and tone mapping. Sky pixels are preserved.
This is analytic distance haze. `enable_volumetric_fog` replaces it with the
ray-integrated fog described in `volumetric-fog.md`. The independent
`enable_volumetric_clouds` option integrates a wind-driven density layer; see
`volumetric-clouds.md` for its controls and limitations.

Analytic haze integrates the clamped exponential height density along the ray,
including sea-level crossings, rather than estimating it at the midpoint.
Short height intervals use a cancellation-safe limit. Surface reflections,
analytic haze, volumetric sunlight, water lighting and diffuse bounce now share
one linear directional-source packet: game daylight, restrained natural sunset
warmth, a smooth horizon fade, weaker moonlight and visibility/custom-direction
controls. Authored directions keep their supplied daylight tint. Native baked
diffuse lighting remains game controlled. This source packet is independent of
shadow-map enablement and coverage.

## Surface attachment and reflections

Reflections and indirect lighting require desktop OpenGL with floating-point MRTs.
The renderer allocates an RGBA16F attachment alongside scene color. Node shaders
write an octahedral view-space normal in RG, signed linear view depth in B
(positive for water-like liquid materials, negative for other nodes), and validity
in A. A value of one in A also prevents alpha blending from corrupting water
normals. Other engine shader outputs invalidate the auxiliary data. Surface
positions are relative to the camera; reconstruction uses the actual projection.
The attachment is omitted entirely if neither reflections nor bounce is enabled.
SSAO emissive protection uses its own R8 coverage attachment, rather than changing
this validity channel. It is available with or without the normal/depth attachment
when the device has enough outputs; see `ambient-occlusion.md`.

`enable_screen_space_reflections` traces the view ray reflected around the water
normal, with 40 quadratic-distance steps over at most 64 nodes and eight refinement
steps at a possible hit. Depth discontinuities, sky hits, and water hits are
rejected. Confidence fades near viewport edges and at maximum range. Missing
hits use the game's sky/fog color. A Schlick air/water Fresnel factor determines
the reflection weight; `water_reflection_strength` scales it (default 0.8).
Wave normals follow the water settings. The existing sun glint is retained while
the old approximate sky reflection is suppressed when SSR is active.

The final segment is clipped to the screen boundary before checking for a hit,
so a coarse march step cannot discard a donor just inside the screen and abruptly
skip its confidence fade. The first foreground crossing is authoritative: an
ambiguous silhouette returns the fallback rather than searching through it for
unrelated background terrain. `util/test_water_reflections.py` checks actual
terrain hits, the edge-confidence curve against an analytic plane intersection,
offscreen fallback and foreground/water rejection using numeric GPU output.

Underwater reflection gain approaches full reflection smoothly as dielectric
Fresnel approaches total internal reflection. Applying the configured gain to
all subcritical samples and switching abruptly to 100% at the critical angle
would create a brightness jump. Ordinary-angle gain and the zero-reflection
opt-out remain intact. The numeric tests cover the critical-angle limit and the
actual scene-pass Fresnel/TIR composition.

MSAA resolves each color attachment independently in Irrlicht, then resolves depth
(and stencil only if present). Broadcasting scene color into the auxiliary
attachment would corrupt normals and water identification. MSAA averages surface
metadata at geometry edges, so partial-coverage reflections can still be imperfect.

Only visible scene color/depth are available. Off-screen objects and geometry
hidden behind other objects cannot appear in reflections. Water-like materials
use the engine's existing liquid material classification, not node-name matching.
Blended object/water intersections can be imperfect because there is only one
surface sample per pixel. Nearer depth-writing objects invalidate background node
metadata before surface lighting.
Refraction and depth-dependent absorption are available through the optional
opaque-scene capture described in `water-refraction.md`. There is no planar
reflection camera or secondary geometry render. Desktop drivers without the required
MRT/float support skip surface effects and log a warning. OpenGL ES currently
skips surface effects and material detail; analytic haze can run independently.

## Material detail

`enable_material_shading` estimates bump detail from color-texture luminance using
surface gradients. `material_normal_strength` controls perturbation (default 0.2).
Existing baked lighting is retained with a bounded diffuse-detail modulation.
Dielectric sunlight highlights use a GGX distribution, Schlick Fresnel, and
roughness-controlled geometry attenuation. `material_roughness` defaults to 0.8.
Highlights follow dynamic shadow visibility and the game's direct-light settings.
Foliage and water are excluded from the generic solid-surface shading.

This is an optional artistic fallback for existing texture packs. Color is not a
physical height measurement. Authored normal and occlusion/roughness/metallic maps
are supported separately; see `material-shading.md`. There is no parallax mapping.

## Indirect lighting

`enable_indirect_lighting` gathers diffuse color from twelve nearby visible opaque
node surfaces. Receiver and donor normals, distance falloff, and a midpoint depth
visibility test limit light leaking. The original scene is always sampled, so
there is no multi-frame feedback or accumulating brightness. Default
`indirect_light_strength` is 0.35; `indirect_light_radius` is 3 nodes.

This is a bounded one-bounce color-bleeding approximation using already-lit scene
color, not path tracing or full global illumination. It cannot separate ambient,
direct, and emissive radiance. Occluded and off-screen surfaces cannot contribute;
a single visibility sample cannot eliminate every thin-wall leak. Diffuse receiver
reflectance is estimated from lit color because an unlit albedo buffer is not
available. There is no
history buffer, temporal denoiser, voxel scene representation, or RTX requirement.

## Cost and validation

Atmosphere adds one full-resolution color pass. Reflections and bounce share that
pass and add one full-resolution RGBA16F surface buffer; MSAA also needs its
multisample counterpart. Water pixels perform up to 45 depth tests; opaque bounce
pixels gather twelve donors plus visibility checks. These are optional quality
features: supersampling increases their cost and performance must be measured on
target hardware.

The existing `util/test_singleplayer.sh` all-effects smoke test enables these
features. Validate legacy OpenGL and OpenGL 3, MSAA and SSAA, pipeline effects off,
resize/aspect changes, underwater views, and grazing-angle water. Use the preview
scene for before/after captures and the full unit suite for C++ regressions.

## Validation in this workspace

The Release client built successfully, and the complete C++ suite passed with
352 individual unit tests and 155,998 Catch assertions. All-effects smoke tests
passed on legacy OpenGL with SSAA and OpenGL 3 with 4x MSAA. Separate smoke tests
passed with post processing disabled and with atmosphere alone (no surface buffer).
A direct GPU harness exercised the actual shader for coplanar bounce rejection,
red-wall color transfer, sky preservation, haze, zero reflection strength, and
Fresnel sky fallback. No visual-quality or performance claims are made for ES or
mobile hardware; the surface effects are currently disabled on ES.

Screenshots in `screenshots/04-lighting-baseline.png`,
`screenshots/05-atmosphere-water.png`, and
`screenshots/06-materials-indirect.png` record the stages at 1280x720 on a GTX 1650 Ti.
The final screenshot also uses 4x MSAA. For a matching run, use
`LUANTI_PREVIEW_AA=fsaa util/preview_lighting.sh full`.
