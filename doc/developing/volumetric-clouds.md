# Volumetric clouds

Clouds can cast a shared light-transmission map onto terrain, entities and direct
fog scattering. See `cloud-shadows.md` for controls, transport, limits and tests.

`enable_volumetric_clouds` replaces the game's cloud mesh with a ray-marched
cloud layer on supported desktop OpenGL. It requires post processing, floating
render targets, five material texture units and a 1088-pixel texture dimension.
It does not require atmospheric haze, bloom, SSAO, surface MRTs or shadow maps.
The quality preset enables it; default settings keep it off. Unsupported devices,
noise-allocation failure and zero-thickness layers retain the native cloud mesh.
Menu clouds remain unchanged.

## Density and light transport

A 32³ periodic scalar noise field is uploaded once per rendering core as padded
2D slices. XY border texels wrap within each slice, while the shader interpolates
adjacent Z slices explicitly. Two ordinary bilinear samples reconstruct trilinear
noise, including across slice/period boundaries. The atlas takes about 145 KiB
in RGBA8 and has no mipmaps. Its creation restores the driver's previous mipmap
creation flag. Both eyes share this immutable noise texture.

The cloud density combines large billows, smaller erosion and a smooth vertical
profile. Game coverage zero clears the layer; one produces overcast coverage.
Density stays inside the game's height/thickness slab. The existing cloud wind
origin advects the field in world space, with the existing cloud seed controlling
phase. Moving the camera origin does not shift the field.

View rays are intersected with that slab, clipped by visible scene depth and a
maximum range, then integrated front to back. Segment transmission follows
Beer–Lambert extinction. In-scattered light uses the game's cloud bright, ambient
and shadow colors, plus a forward Henyey–Greenstein phase. Three light-ray samples
estimate self-shadowing through the density toward the sun/moon or custom light
direction. Custom light directions below the layer are supported. Cloud color
alpha scales extinction. This light transport is independent of the older
screen-space bloom god rays and the game's god-ray strength.

Game `set_clouds` controls remain live: coverage, height, thickness, colors and wind.
Sky cloud visibility disables the pass. Flat layers fall back to native planes.
While volume rendering is active, the old mesh-based inside-cloud sky-color/fog
replacement is bypassed; the integrated density handles below/inside/above views.
The mesh still supplies those legacy behaviors in fallback mode.

## Pipeline and temporal behavior

Cloud scattering and scalar transmittance are rendered at half scene resolution
by default. A full-resolution composite combines them with scene color in linear
RGB. Four neighboring cloud samples are weighted by bilinear position and scene
depth to avoid pulling sky clouds through foreground silhouettes. If no sample
matches a thin foreground object, the composite preserves its original color.
Scene alpha is preserved. Each eye owns its intermediate textures, resized with
the pipeline; the current jittered inverse projection/view reconstruct its rays.

The pass runs after MSAA resolve and surface SSAO, before surface lighting/haze, TAA,
bloom, exposure and tone mapping. Wield/HUD rendering remains downstream.
`enable_cloud_denoising` adds a cloud-specific spatial/temporal filter on desktop
OpenGL with float MRTs, independently of the selected AA mode. The quality preset
enables it. Unsupported devices retain the unfiltered cloud transport.

The raw cloud pass records the extinction-weighted mean ray distance and spread,
geometric endpoint and opacity in a second half-resolution attachment. An online
weighted variance update avoids subtracting large squared distances for thin,
distant clouds. A 3×3 spatial filter rejects different cloud depths and terrain
endpoints, and weights neighbors by opacity similarity. Empty current rays remain
empty, preserving newly exposed foreground geometry and clear sky.

Temporal accumulation projects a finite cloud anchor into the previous camera,
subtracting the frame's world-space wind displacement first. This preserves cloud
advection instead of treating clouds as an infinite static sky. Current/previous
camera-origin offsets and TAA projection jitter are included. Four history taps
are checked independently against cloud depth and geometric endpoints before
bilinear filtering. History is clamped to the accepted current neighborhood;
motion and opacity changes reduce its weight. Scattering and transmission are
filtered separately from scene color in linear light.

Each eye owns its filter state and history textures. First use, resize, camera
cuts/mode changes, pauses, FOV changes and represented water-medium transitions
reset history. Changed density, layer geometry, seed, sample count, range,
visibility or large light/color/wind changes also invalidate it. Clearing and
restoring a layer cannot resurrect pre-clear history. History weight is adjusted
for elapsed frame time. Temporal ray stratification runs with the denoiser even
when final-image TAA is disabled. Without either, stratification stays spatially
stable. Final-image TAA still lowers history weight over clouds to avoid a second
long accumulation trail.

## Controls and cost

- `enable_volumetric_clouds`: restart to change the pipeline.
- `enable_cloud_denoising`: restart; requires float MRTs, default false.
- `cloud_history_weight`: history contribution at 60 FPS, 0–0.95, default 0.9; live.
  Zero retains spatial filtering without temporal accumulation.
- `volumetric_cloud_samples`: 8–64 view segments, default 32; live.
- `volumetric_cloud_distance`: 128–4096 nodes, default 1024; live.
- `volumetric_cloud_resolution`: 0.25–1.0 relative to scene, default 0.5; restart.
- `volumetric_cloud_density`: extinction per node, default 0.18; live.
- `volumetric_cloud_detail`: erosion strength, default 0.35; live.

Cloud transport/compositing uses two additional render targets. With 16-bit scene
color at 1920×1080 and half-resolution clouds they occupy about 20 MiB. Denoising
adds four half-resolution RGBA16F targets, about 16 MiB more, before stereo and
other effects. These hold current/previous guides and resolved/previous transport.
The current raw guide is swapped into history without an extra copy. History and
current resolved textures are swapped only after every consumer finishes.
Empty space skips light-ray sampling; negligible transmission ends the ray early.
Cost scales with resolution, visible clouds and view samples. No target-hardware
frame-rate claim follows from passing correctness tests.

This is a single finite cloud layer with approximate single scattering and ambient
fill. Shared cloud shadows on terrain, objects, fog and GI injection are described
in `cloud-shadows.md`. It does not compute multiple scattering, simulate fluid
weather, or scatter local colored lamps. Fog and clouds are composed
as separate media, without exact interleaved transport. The noise field is periodic;
very distant/repetitive structures and very thin density features can be limited.
Conservative depth upsampling can leave holes on thin geometry behind a cloud;
higher cloud resolution reduces that case. Temporal reprojection uses one mean
depth for a distributed volume; strong parallax through broad or overlapping
billows can reject history and expose more current-frame noise. Finite angular
samples, spatial blur and history lag remain tradeoffs. Separate fog denoising is
documented in `volumetric-fog.md`. Broader performance/appearance audits remain work.

## Verification

`python3 util/test_volumetric_clouds.py` compiles the actual transport/composite/TAA
GLSL and compares numeric float pixels. It checks homogeneous transmission and
scattering, sample/jitter invariance, geometry before the layer, above/inside/below
and parallel rays, range clipping, empty/unbound bypass, self-shadow direction,
periodic trilinear seams, wind translation, depth edges/thin foregrounds, alpha and
cloud-reactive TAA. Binary fractional atlas coordinates avoid conflating atlas
layout with hardware texture-filter rounding. It captures no images or input.
Use `LUANTI_TEST_GLSL=120` for legacy GLSL; the default is 330 core. Tests report
the actual renderer. See `material-shading.md` for the verified Mesa environment.

`python3 util/test_cloud_denoise.py` exercises the actual filter and moment
integration. It checks first-use NaN-history guards, noise reduction over 40
frames, wind direction, per-tap occlusion, partial history footprints, empty rays,
zero history weight and extinction-event mean/spread. In a controlled noisy-cloud
test, linear-radiance RMSE fell from 0.05506 to 0.00936; this is a numeric fixture,
not a measurement of general game appearance or GPU performance.

The C++ suite checks real atlas padding/periodicity and mipmap-state restoration,
plus cloud-history wind/origin/jitter reprojection and transport-change resets.
`util/test_volumetric_clouds.sh` exercises live coverage, flat-layer fallback, sky
visibility, FOV and below/inside/above camera transitions with the quality preset.
Optional `LUANTI_TEST_DRIVER=opengl`, `LUANTI_TEST_AA=fsaa`,
`LUANTI_TEST_STEREO=sidebyside` and `LUANTI_TEST_CLOUD_ONLY=true` select alternative
paths. Logs require allocated noise, active game layer parameters, all phases and
clean shutdown without shader/GL errors. With denoising, completed frames must
reset and resume history after coverage clears. `LUANTI_TEST_CLOUD_DENOISING=false`
checks the cloud path without the new filter.

In this workspace the Release build and full C++ suite passed (353 individual
tests and 34 Catch cases). Numeric tests passed on NVIDIA with
GLSL 120 and 330 core, and Mesa llvmpipe with GLSL 330 core. Runtime integration
passed with OpenGL 3/TAA (mono and side-by-side stereo), legacy OpenGL/4x MSAA
and clouds alone. These are
correctness checks; they do not establish appearance or performance targets.
The combined quality pipeline also completed a VoxeLibre compatibility run with
live game cloud-layer changes, water refraction and nine local RGB sources.

The denoising implementation passed the full-quality OpenGL 3/TAA integration,
side-by-side stereo and standalone clouds with legacy OpenGL/4x MSAA. An isolated
native VoxeLibre biome copy completed submerged, above-water and submerged-again
poses with active cloud history, resets at each transition and a clean shutdown.
The quality integration also passed with denoising disabled, with no cloud-history
state activated. Legacy GLSL 120, NVIDIA GLSL 330 and Mesa llvmpipe GLSL 330 passed
the filter/moment numeric tests, including wind reprojection and partial footprints.
These runs generated no screenshots or input events.
The cloud and fog filter constructors retain borrowed AA state with balanced
references. A shared-lifetime regression covers both filter teardown orders;
the standalone fog integration also checks clean shutdown without cloud ownership
masking AA-state lifetime errors.
