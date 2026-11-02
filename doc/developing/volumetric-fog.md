# Shadowed volumetric fog

`enable_volumetric_fog` replaces analytic atmospheric haze with view-ray integration
on desktop OpenGL. It requires `enable_post_processing` and `enable_atmosphere`.
Other drivers retain analytic haze. The quality preset enables this fog and
disables the older screen-space bloom god rays to avoid stacking both estimates.
New effects remain off in default settings.

The shader reconstructs the world ray from the current projection/view matrices
and integrates to the nearest visible surface, water surface, or a configurable
maximum distance. Sky rays receive fog up to that distance. Quadratically spaced
segments concentrate samples near the camera; screen-space stratification
reduces bands, with temporal variation on the filtered path. Each segment
evaluates exponential height density and optional
world-space value noise, then analytically integrates its constant-density
extinction/scattering. RGB transmission accumulates front to back. The result
composites in linear color after surface SSAO and before TAA, exposure, bloom and tone mapping.

Directional single scattering uses a Henyey–Greenstein phase with g = 0.55 and the
existing directional shadow texture. It uses the same camera-centered perspective
warp as the shadow caster. Terrain and shadow-casting objects occlude the light;
the colored-shadow format supplies transparent RGB transmission. A small depth
bias reduces quantization artifacts. Direct scattering fades at the shadow-map
border and is suppressed outside its known coverage. If shadows are disabled,
fog uses local native skylight as its visibility fallback. A binding guard
prevents reads from a missing shadow texture. Both ambient and directional sky
scattering require local skylight, so an outdoor camera/sky tint cannot reveal
the shape of a zero-light cave; see [dark caves](dark-caves.md).

Sun/moon visibility, custom shadow direction and the game's
`player:set_lighting({volumetric_light = {strength = ...}})` control the light.
The game API defaults that strength to zero; increasing fog density alone does
not override that choice. Moon scattering is reduced relative to sunlight.
The source direction, linear color and smooth horizon fade are shared with
surface and water lighting and indirect-light injection. Natural low sun adds
a restrained warm tint; custom directions retain native daylight color.
Ambient in-scattering takes the game's fog tint weighted by local skylight.
The pass is bypassed while the
camera is inside a liquid or an opaque node and when both sky lights are hidden
without a custom light direction or active local voxel-fog lighting, preserving
game-defined underwater/solid fog.

## Colored local illumination

`enable_voxel_fog_lighting` adds local colored in-scattering from the existing
voxel lighting field. It requires voxel lighting, volumetric fog and five material
texture units. It is off by default and enabled by the quality preset.
`voxel_fog_strength` scales this contribution from 0–2 (default 0.5), updating live;
zero retains ambient/directional fog. Direct/bounce gains also follow
`voxel_light_strength` and `voxel_gi_strength`. Local light does not use the game's
sun/moon volumetric strength and does not change extinction or scene alpha.

Each integration sample gathers the six directional direct and indirect probes
with phase-weighted angular quadrature. Weights are computed once per view ray,
outside the integration loop, and normalized so a constant isotropic probe field
does not change with view direction or anisotropy. Empty-cell direct probes contain map emission,
not direct sunlight, so the sun's direct scattering is not added twice. Reflected
sunlight can contribute through indirect probes. A volume-specific moving-light
loop evaluates the actual sample-to-lamp direction with a Henyey–Greenstein
phase, loaded-map visibility and RGB path transmission. At zero anisotropy, its
point-light intensity is rotation invariant rather than using the previous sum
of six axis cosines. The ordinary axial isotropic scale is retained; diagonal directions
no longer receive an artificial brightness increase. Near the source, phase
blends to isotropic across a one-node finite core, with bounded inverse-square
intensity, avoiding an undefined direction or a coincident-light spike.
That contribution is excluded from baked direct probes in
the fast path; the 13-column asynchronous fallback instead uses baked direct light.
Opaque/unknown sample cells are rejected before radiance interpolation, and
the local contribution fades at the lighting grid boundary.

The fog material borrows the existing atlas at texture unit 4, preserving scene,
depth, surface, shadow and cloud bindings. It reuses the existing eight-light
packet format, with no new atlas or render pass. Inline fog and the separate
reduced-resolution transport
use the same helper. The feature can retain atmospheric transport when sky
lights are hidden, provided its atlas and nonzero strengths are ready. Water
and opaque-camera bypasses remain intact; underwater lamp scattering is separate
work.

`voxel_fog_anisotropy` controls phase from -0.85 to 0.85. Zero is isotropic;
positive values favor viewing toward a lamp, and negative values favor
backscattering. Its default is zero; the quality preset selects 0.35. It updates
live and resets fog history. This parameter does not change density, extinction,
scene alpha, source visibility or the separate sun/moon phase.

Fog history rejects atlas readiness/gain/phase changes, changed map-source count/color
revisions, and moving-source insertion/removal, recoloring or movement of at
least 0.1 node between frames. Smaller movement uses the filter's radiance
clipping and change response. Source positions are stored in absolute node
coordinates so camera-origin shifts do not invalidate otherwise compatible light.
With per-frame direct lighting, current map occupancy/transmission changes also
advance that revision. Fog rejects newly occupied sample cells and traces moving
lamps through the current optics column before the next radiosity solve finishes.
Small source changes still rely on current neighborhood clipping; the baked
emission/bounce field and coverage retain their asynchronous update latency.

Moving lights use source-specific phase; baked emission/bounce retain a
six-direction angular approximation. That coarse field cannot resolve narrow
off-axis phase lobes or recover individual source directions, particularly at
high anisotropy. Normalization preserves an isotropic field but is not a full
spherical radiance representation or an energy-calibrated native lighting model.
Spotlights, entity occluders and multiple volume scattering remain unimplemented.
Coverage and material/geometry limits follow voxel
lighting. Cost grows with fog resolution, integration samples and active moving
lights: each sample can gather twelve probe directions and trace up to eight
light paths. Zero direct/bounce gains skip their respective reads/traversals;
both zero bypass local sampling. Correctness tests are not a frame-rate guarantee.

## Settings

- `atmosphere_density`: extinction density per node, shared with analytic haze.
- `volumetric_fog_distance`: maximum integration range in nodes; default 128.
- `volumetric_fog_height`: exponential falloff above sea level in nodes; default 64.
- `volumetric_fog_variation`: world-space density variation; default 0.35, zero for smooth fog.
- `volumetric_fog_steps`: segments per pixel, 8–64; default 24.
- `enable_fog_denoising`: separate spatial/temporal fog filtering; default false, restart.
- `fog_resolution`: transport resolution relative to scene, 0.25–1, default 0.5; restart.
- `fog_history_weight`: history contribution at 60 FPS, 0–0.95, default 0.9; live.
  Zero retains spatial filtering without temporal accumulation.
- `enable_voxel_fog_lighting`: scatter local voxel lights; default false, restart.
- `voxel_fog_strength`: local in-scattering strength, 0–2, default 0.5; live.
- `voxel_fog_anisotropy`: local scattering direction, -0.85–0.85, default 0; live.

The enable flags require a restart. Numeric controls update live. This pass does
not require a floating-point surface attachment or bloom; water metadata, when
available, supplies the water endpoint. Native far-distance map fog remains in
place to hide the loaded-world boundary.

## Separate fog transport and denoising

The quality preset enables fog denoising on desktop OpenGL with float MRTs and
five texture units (six when combined with volumetric clouds and TAA). Other
configurations retain the existing inline integration. The surface-lighting pass
skips inline fog when the separate path is active, so it is applied once.

The separate pass integrates RGB scattering and RGB transmission into two
RGBA16F targets, at half scene resolution by default. Their alpha channels store
extinction-weighted mean ray distance and the geometric endpoint; zero endpoint
marks sky and negative endpoint marks a bypassed volume. Existing water/node
surface metadata supplies the same endpoint as inline fog, with nearer objects
rejecting stale surface metadata. Temporal ray stratification varies between
frames independently of the final AA mode.

A 3×3 filter smooths only the volume payloads, guided by endpoint and mean depth,
transmission and scattering similarity. Strong shaft/shadow boundaries are
excluded from neighborhood history bounds. Temporal accumulation projects a
finite fog anchor into the previous eye camera. Each of four history taps is
checked against geometry, sky classification and mean depth before bilinear
filtering. Current-neighborhood clipping, radiance-change response and motion
reduce stale lighting history. Metadata remains current and is never averaged.

Each eye owns its state and histories. Camera cuts, resize, FOV/mode changes,
represented-water transitions and pauses reset history. Density/range/height/
variation/step changes, visibility, ambient/direct lighting, shadow binding and
cloud-shadow transport changes also reject incompatible history. Origin rebasing
and current/previous TAA jitter are accounted for. Filter states retain secondary
references to the eye's AA state through shutdown and pipeline rebuilds.

The full-resolution composite depth-weights four neighboring fog samples and
applies `scene_linear * transmission_rgb + scattering_rgb`, preserving scene
alpha. Scene textures, reflections and terrain color are not spatially filtered.
If no sample matches a thin foreground object, its scene color is preserved.
Disabling atmosphere/entering a liquid bypasses the composite before fog reads.
Final TAA reduces its history contribution in opaque fog to avoid stacking long
volume and scene histories. All history swaps follow their consumers.

## Limits and cost

This is single-scattering fog with a tinted ambient approximation. It does not
solve atmospheric multiple scattering. An independent cloud density pass is
available through `enable_volumetric_clouds`; see `volumetric-clouds.md`. Local RGB
illumination uses the optional phase-aware voxel estimate described above.
Density is static world-space noise;
there is no fog wind simulation. Temporal reprojection uses one representative
depth for an extended medium; strong parallax can reject history and reveal more
current noise. Thin foreground geometry without matching low-resolution samples
can omit fog; higher `fog_resolution` reduces that case. Hard shadow samples
and finite ray steps can miss very thin shafts. Large integration distances and
high sample counts increase GPU cost.

Without denoising, fog runs at scene resolution inside the existing lighting
pass without another target. Denoising uses six reduced-resolution RGBA16F
transport/history targets and one scene-resolution composite target. At 1920×1080,
half-resolution fog and 16-bit scene color, these add about 40 MiB per eye.
Resolution changes integration/filter cost quadratically. No additional shadow
render is needed. Each segment costs one shadow lookup when
directional scattering is nonzero; density noise is skipped at zero variation.
The ray stops early at negligible transmission. Benchmark on target hardware;
correct shader compilation does not establish a frame-rate claim.

## Verification

`python3 util/test_voxel_fog.py` compiles the shared voxel helper and actual inline
and MRT fog transport. It checks map emission/bounce, boundary coverage, solid/
unknown and missing-atlas guards, current moving-light position/color/removal,
RGB transmission and wall occlusion. Analytic homogeneous transport checks RGB
scattering/extinction, sample-count invariance, alpha and bypass identity with
both 13- and 14-column atlases. These tests passed on NVIDIA GLSL 120/330 and Mesa
llvmpipe GLSL 330. They read numeric pixels without input or image capture.

Phase checks compare forward, backward and intermediate angles with analytic HG,
rotate source/view together, cover the finite near-source core, all eight array
entries and strength/occupancy guards. Baked-probe tests verify angular response
and constant-field energy normalization for isotropic, forward and backward
scattering. Inline/MRT checks cover both atlas layouts and origin rebasing;
disabled direct/bounce channels are tested with invalid data in the unused lobe.
The phase extension passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330,
including colored path filtering and wall rejection with a nonzero phase.
The Release build and full C++ suite passed (353 unit tests and 49 Catch cases),
including history reset on live phase changes. Runtime checks passed for quality
OpenGL 3/TAA, legacy OpenGL/4x MSAA/stereo, negative-phase standalone inline fog,
the asynchronous field fallback, opt-out, authored materials and native VoxeLibre.
Active fog programs bound 0.35 in the quality/native runs and -0.35 in the inline
control; native torch removal and underwater transitions remained correct.

`LUANTI_TEST_VOXEL_FOG=true util/test_voxel_lighting.sh` requires the actual atlas
binding and hidden-sky transport. Combined with `LUANTI_TEST_DYNAMIC_DIRECT=true`
and `LUANTI_TEST_DYNAMIC_LIGHTING=true`, it also requires active moving-source
array bindings in a fog shader. `false` verifies the feature opt-out. Existing
quality, fog-denoising, driver and stereo switches select the other paths.

The Release build and full C++ suite passed with this feature (353 unit tests,
49 Catch cases), including local-light history rejection and origin handling.
Live runs passed on full-quality OpenGL 3/TAA and legacy OpenGL/4x MSAA/stereo,
standalone inline fog, asynchronous direct-light fallback and explicit opt-out.
Actual texture-4 and moving-source uniform bindings were observed. The authored
normal/ORM/held-lamp fixture and native VoxeLibre torch/underwater transitions
also passed without shader/GL errors.

`python3 util/benchmark_voxel_fog.py` times the production GLSL with GPU elapsed
queries after warmup, alternating local light off, baked field, one moving lamp
and eight moving lamps. `LUANTI_BENCH_FOG_ANISOTROPY` selects the phase (default
0.35); `0,0.35` pairs both values within one program/context and reverses their
order on alternating repetitions. It uses 24 samples over a six-node view ray in an open
16³ field, fixed light positions, no directional illumination and no shadow/cloud
work. Before the phase-aware extension, a GTX 1650 Ti run measured these medians
of nine draws for the former isotropic implementation:

| Draw size | Local off | Baked field | One moving lamp | Eight moving lamps |
| --- | --- | --- | --- | --- |
| 64×64 | 0.007 ms | 0.127 ms | 0.338 ms | 2.165 ms |
| 128×128 | 0.017 ms | 0.503 ms | 0.839 ms | 4.381 ms |
| 256×256 | 0.057 ms | 2.010 ms | 2.085 ms | 9.552 ms |

These are isolated shader draws, not whole-frame FPS or performance guarantees.
Multiple moving lights add measurable cost; wider scene profiling and local
volume-light optimization remain open.

After the phase extension, paired measurements at 256×256 produced the following
medians of nine draws in the same workload/context. Direct-only and bounce-only
cases disable the other lobe before its texture reads. Separate initial runs
showed a GPU clock ramp; pairing the phase values avoids treating that change as
a scattering-mode performance difference.

| Anisotropy | Local off | Baked field | Direct only | Bounce only | One lamp | Eight lamps |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.068 ms | 1.467 ms | 0.747 ms | 0.748 ms | 2.085 ms | 9.587 ms |
| 0.35 | 0.068 ms | 1.462 ms | 0.747 ms | 0.750 ms | 2.085 ms | 9.597 ms |

The phase values have effectively equal cost in this matched test. Disabling a
baked lobe roughly halves the field-only draw cost. These results do not compare
identical images against the former isotropic algorithm, whose orientation and
near-source response were corrected; they do not establish whole-game FPS.

Run `python3 util/test_volumetric_fog.py` with SDL2 and desktop OpenGL available.
It compiles the actual scene GLSL in a hidden context and compares numeric float
pixels with the exact homogeneous single-scattering solution. It checks opaque
occlusion, colored transparent transmission, zero density, absent shadow bindings,
underwater bypass, sky integration, distance limits, height falloff, sample-count
invariance and density stability across camera-origin changes. It does not send
input events, capture images or write screenshots.

`util/test_singleplayer.sh` enables fog with the other effects to catch shader
compilation and pipeline integration failures. The full C++ unit suite covers the
shared engine regressions; it does not measure atmospheric appearance.

In this workspace the Release build and full C++ suite passed (353 individual
tests and 34 Catch cases). Numeric fog tests passed on the NVIDIA driver and Mesa
software rendering. Runtime checks passed with OpenGL 3 plus TAA/all quality
effects, legacy OpenGL plus 4x MSAA/all quality effects, and a standalone fog
configuration with shadows, bloom, surface effects and voxel lighting disabled.
The quality integration scene exercises night, daylight and a custom light
direction while RGB lamps are removed; source updates remain correct. Run it with
`LUANTI_TEST_QUALITY=true util/test_voxel_lighting.sh`, optionally adding
`LUANTI_TEST_DRIVER=opengl LUANTI_TEST_AA=fsaa`.

The numeric test prints its actual renderer. See `material-shading.md` for the
verified offscreen Mesa environment on this NVIDIA desktop.

`python3 util/test_fog_denoise.py` compiles actual MRT transport, filtering,
compositing and fog-reactive TAA GLSL. It checks RGBA16F transport against analytic
RGB extinction/scattering, bypass identities, uninitialized history, geometry/sky
rejection, partial history footprints, shaft edges, water/node endpoints,
nearer-object occlusion, scene alpha and both TAA texture layouts (with/without
clouds). A 40-frame noisy-volume fixture reduced scattering RMSE from 0.02032 to
0.00437 and transmission RMSE from 0.01208 to 0.00209; these are controlled numeric
results, not general visual-quality or GPU frame-rate measurements.

Client C++ tests cover finite-anchor reprojection through jitter/origin changes,
transport/light resets, bypass/restoration, water/resize invalidation and shared
AA-state lifetime through independent cloud/fog teardown. Add
`LUANTI_TEST_FOG_DENOISING=true` to the voxel integration test for live hidden/
restored lights and submerged/above-water transitions. `false` selects inline fog.

The separate fog numeric tests passed on NVIDIA GLSL 120/330 and Mesa llvmpipe
GLSL 330. The standalone OpenGL 3/TAA run passed light/medium transitions, RGB
source removals and clean shutdown, without clouds or surface MRT data. The
combined quality pipeline also passed these transitions with water volumes,
cloud denoising and colored emission.
The final legacy OpenGL/MSAA/side-by-side run also passed after the AA-state
ownership correction. An isolated native VoxeLibre biome copy completed submerged,
above-water and submerged-again poses, activating fog history above water and
resetting it upon submersion, with a clean shutdown and no shader/GL errors.
The full-quality inline-fog fallback also passed source removals, medium/light
changes and clean shutdown, with no fog-history state activated.

The six-lobe phase weighting, field gather and coverage/occupancy guard are shared
with colored underwater scattering. Air fog keeps its own strength, anisotropy and
transport integration; `enable_voxel_water_lighting` does not require atmosphere or
fog. `water-volume.md` describes the underwater source/view extinction and controls.
The air-fog numeric suite is also run after changes to these shared helpers.
