# Loaded-water lighting and transport

`enable_water_volume` adds camera-local liquid geometry, underwater RGB absorption
and sunlight caustics. It requires post processing, translucent liquids, desktop
OpenGL, seven material texture units, RGBA32F textures and a 4096-pixel maximum texture dimension.
The quality preset enables it; default settings keep it off. It works independently
of bloom, atmosphere, surface MRTs and voxel lighting. Unsupported devices or
atlas allocation/upload failure retain native liquid effects.

## Geometry and bindings

A shared 48³ geometry cube follows the camera. A synchronous snapshot of loaded
client nodes refreshes at most four times per second, with immediate recentering
when the camera leaves its inner coverage. Snapshot/upload timing appears in the
profiler as `Water geometry snapshot [ms]`; shutdown logs its measured mean/max.
The loaded-node snapshot includes a one-node halo for flowing-liquid neighbors;
it visits the map once rather than issuing repeated lookups for every flow cell.
No world generation, texture readback, input events or image capture is required.

The RGBA32F atlas lays Z slices vertically, with two groups of N columns. The first
group stores cell metadata: R identifies unknown, air, opaque and eligible liquid
cells, distinguishing waving sources from waving flow; G stores the nominal liquid
level, B raw skylight and A the game's post-effect turbidity. The second group stores
the four actual mesh corner heights as floats relative to the node bottom.
Eligible liquids
are nonemissive, blended liquid/flowing-liquid draw types. Opaque, clipped and
emissive liquids keep native behavior. This uses definitions rather than node
names. Flow corner averaging, source connections, shore lowering and upper-liquid
connections use `client/liquid_geometry.h`, shared with mesh generation. Falling
flow follows the mesh's actual corners rather than assuming a full cell. Wave noise
samples each original corner's Y, including slopes. Its vertical noise scale is
1/64 world unit: with amplitude clamped to 4 and cubic-noise derivative bounded by
1.5, the displacement derivative is at most 20*1.5/64 = 0.46875 in magnitude.
Thus vertical deformation preserves ordering and thin shoreline sheets cannot
turn inside out. This also keeps shared source/flow boundaries connected when
they use the same waving definition. Both source and flowing water
use the animated boundary triangles. Unknown cells
stop traversal rather than becoming unoccluded space.

Node materials borrow texture unit 6 during scene drawing, then release that
borrowed binding. Normal/ORM maps retain units 4/5, shadow maps unit 3, and opaque
refraction or voxel lighting retain their previous bindings. The underwater post
pass binds the same atlas at unit 6. Both eyes share geometry but own their scene
targets and use their actual camera positions and projections.

Voxel-boundary traversal counts only the portions of each segment inside
liquid. It splits at the mesh diagonal, including static flow, and clips against
displaced top/bottom planes, including water displaced into cells below its source.
Intervals are unioned to avoid counting overlapping water twice. Solid/unknown
geometry takes precedence. Waving source top/bottom and flowing bottom faces use
the same fixed X/Z diagonal as the flowing top. Both smooth and flat lighting
preserve this split so lighting changes cannot change occupancy.
The traversal advances tied axes together at edges/corners. Air gaps,
rear exits, solid occluders, unknown geometry and the local grid boundary terminate
or limit the appropriate path. Water refraction uses this liquid length instead
of assuming the entire path to opaque background is water, whenever its starting
cell is known. Uncovered refraction retains the older capped path estimate.

Completely wet source cells with matching turbidity now accumulate their full
segment directly. They retain the existing eligibility check against the bounded
downward wave displacement and overlying source cells, and skip the interval
array, triangle split and union sort. Boundary, sloping, partially filled and
mixed-turbidity cells retain actual mesh clipping. Shared-plane roundoff is
excluded from exit/sky classification using a node-distance tolerance of
`0.000001 * max(1, ray_distance)`, bounded by 0.00064 world unit at the maximum
64-node path cap. Wet and turbidity-weighted lengths are still accumulated without
filling gaps; loaded solid/unknown clipping is unchanged.

## Underwater view and interfaces

While the camera is inside represented water, a scene pass integrates
Beer–Lambert RGB transmission along the water portions of the view ray. It uses
the same red/green/blue extinction ratios as surface refraction, weighted by the
game's liquid turbidity. In-scattering approaches the game's post-effect RGB;
`post_effect_color_shaded` uses the current native camera-light color.

That pass replaces the fixed fullscreen liquid-color overlay only when its atlas
and camera geometry are valid. A dry wave trough inside a static source node
therefore has no liquid overlay. Displaced water entering an air node retains the
source liquid's scatter color. Native fog remains the fallback, and opaque-node
blackout remains intact. The far-distance map fog still hides unloaded terrain.
The pass runs after surface SSAO and before TAA and camera effects; HUD/wield rendering follows.
Its scattering is added after surface occlusion rather than inheriting it.
Scene alpha is preserved. Zero absorption removes both absorption and scattering.

With surface refraction enabled, valid underwater cameras can capture opaque scene
color/depth too. Their interface rays use a water/air index ratio of 1.333, while
air/water rays use its reciprocal. No transmitted sample is returned beyond the
critical angle. The reflection pass uses exact dielectric Fresnel for underwater
views and full total internal reflection when reflections are enabled. Missing
underwater reflection hits use the game's shaded liquid color rather than air sky.
Setting reflection strength to zero disables that reflection path.

TAA resets at represented water entry/exit and reduces underwater history weight
for independently moving caustics. Above water, the existing water-surface reactive
mask covers caustics seen through a liquid interface. No motion vectors or
separate caustic history are introduced.

## Colored underwater scattering

`enable_voxel_water_lighting` adds colored local in-scattering to the underwater
pass when loaded water and voxel lighting are both enabled. The quality preset
enables it. It works independently of atmosphere, air fog, bloom and material
maps. The pass borrows the existing voxel atlas at texture unit 4 alongside water
geometry at unit 6; it adds no target, atlas, snapshot or render pass.

The view ray is divided into 4–32 distance strata (eight by default). Each stratum
uses the actual displaced liquid intervals and turbidity for analytical RGB
Beer–Lambert transmission. Its lighting sample stays inside actual water and the
traversed interval: a dry midpoint moves to the first wet interval, and a solid or
unknown cell prevents sampling another pool behind it. Homogeneous incident light
integrates independently of the stratum count, including air gaps and thin flow.
Spatially varying light uses one representative sample per stratum; multiple wet
patches in one stratum still share that sample. Increasing the count improves this
quadrature at extra GPU cost. This is single scattering, without a separate
denoising history.

Direct map emission and bounced light come from the existing six-lobe field.
Normalized Henyey–Greenstein lobe weights approximate directional scattering
without changing the energy of a uniform field. Current held/moving lamps use
their actual source direction, bounded near-source phase, current voxel occupancy
and RGB filters. A second geometry traversal integrates water-only extinction on
each lamp-to-sample segment and rejects solid, unknown or truncated source paths.
These source rays are straight through mixed air/water: they do not solve Snell
refraction or local-lamp caustics at the interface. Baked map emission and bounce
retain the voxel solver's existing coarse transmission; automatic bulk liquid
extinction on those source-to-probe paths remains unimplemented.

Local light adds to the native liquid-color in-scattering in linear RGB. Its
neutral scattering coefficient is bounded by the blue extinction coefficient;
the greater red/green extinction remains absorption rather than being scattered
back into view. Water turbidity and the existing absorption gain scale both
extinction and this scattering. A zero local gain, unavailable lighting atlas or
zero direct/bounce gains retain the original water integration. Dry cameras,
missing water geometry and zero absorption retain the original scene. Alpha is
preserved.

## Wave focusing

The liquid mesh and caustic solver share `common/water_waves.glsl`, including the
existing absolute-coordinate noise displacement and animation phase. Mesh,
reflection and caustic waves use the same live numeric height/wavelength/speed
packet. Camera medium checks evaluate the same mesh triangles on the CPU every
frame, independently of the four-Hz geometry refresh. Wave periods are rounded
to 1/32 world unit before coordinate reduction, avoiding far-origin phase drift
from CPU/GPU division and multiply-add differences. The lattice is reduced before
polynomial hashing too. Refraction, reflections and the surface buffer share the
actual triangle normal on desktop GL and GLES 3, including nonwaving slopes; GLES 2 keeps its
existing mesh-normal fallback without requiring derivative extensions.

Caustics apply to submerged node receivers under a waving source or flowing face.
An upward refracted
ray locates a water exit. A bounded three-iteration Newton solve then inverts the
wave-refracted photon map locally. The solver recovers the actual source/flow
triangle's rest height and slopes. Each correction walks the represented rest
surface, splitting at X/Z cell edges and triangle diagonals. Shared-edge heights
must agree within 0.002 node; a connected destination supplies its own slope and
height. This supports flow diagonals, neighboring flow cells and source/flow
joins without extending the old plane through another face. Missing, unknown,
solid, nonwaving or discontinuous faces fail closed, including invalid intermediate
faces even when the endpoint is valid. Covered internal tops are rejected.
Each correction is bounded to one node on each horizontal axis and eight faces.

Wave-normal differences follow the current affine face's rest Y as X/Z vary.
Converged roots skip further Newton work below 0.0001 world unit of horizontal
residual; the final density is still evaluated. Mesh entry/exit locations are
displaced only once, and solved positions project back onto the animated mesh.
The incident projected photon density divided by the absolute outgoing Jacobian
determinant estimates focusing/divergence, clamped to four times the unfocused
horizontal-light flux. The incident factor accounts for oblique sunlight on a
sloped or curved interface.

Sun/moon visibility, light angle, receiver orientation, liquid-path RGB absorption,
loaded solid/unknown geometry, raw skylight and existing directional-shadow
visibility limit the modulation. The air-side ray follows the actual light
direction. Visibility, receiver orientation and RGB absorption follow the solved
mesh-interface-to-receiver segment, separately from the initial search ray.
Solid/unknown cells, premature liquid exits and dry gaps reject that segment.
An air-side ray crossing additional water is also rejected: that path would
require another refractive interface. Solved roots outside represented water
are rejected. Grid-edge fading
avoids a hard local-coverage boundary. Artificial-light-dominated receivers are
protected by the native day/night ratio.

This is a local photon-density estimate, not a decorative projected pattern or
a global photon map. It locally modulates the native natural-light contribution;
the native baked ambient/direct split is approximate. Multiple caustic roots,
photon-map folds, exact flux conservation and refracted shadow-map rendering are not
solved. The bounded face walk follows connected slopes, but sharp normal creases
still need flux filtering and multiple-root treatment. Failed or nonconvergent
paths retain native lighting. Photon focusing uses the smooth shared wave field rather than the
piecewise-planar mesh normal, so very short wavelengths remain an approximation.
Shader cost can be substantial on visible submerged surfaces. A contributing
receiver traces the search, solved-water and air-side paths and performs bounded
face lookups; the extra solved visibility traversal prevents leakage at extra GPU
cost. There are no additional atlases, allocations or render passes.

## Controls, cost and limits

- `enable_water_volume`: restart to change the geometry/post pipeline.
- `water_volume_size`: 32–64 nodes per cube edge, default 48; restart.
- `water_caustics_strength`: 0–2, default 0.7; live. Zero disables focusing only.
- `enable_voxel_water_lighting`: requires water volume and voxel lighting; restart.
- `voxel_water_strength`: 0–2, default 0.5; live local-scattering gain. Also uses
  `voxel_light_strength` for direct and `voxel_gi_strength` for bounced light.
- `voxel_water_anisotropy`: −0.85–0.85, default 0.5; live HG phase. Positive favors
  looking toward a light; zero is isotropic.
- `voxel_water_steps`: 4–32, default 8; live view-ray quadrature count.
- `water_absorption_strength`: existing 0–4 absorption/scatter control; live.
- `water_refraction_distance`: existing 1–64 node path cap; live.
- Wave height (clamped to the existing 0–4 range), wavelength and speed follow the existing water controls.

At 48³ the atlas occupies 3.375 MiB on the GPU (8 MiB at 64³). Persistent CPU
metadata/corner arrays occupy about 2.1 MiB at 48³; a transient snapshot and loaded
node halo add about 2.6 MiB during refresh, excluding driver staging buffers.
Float corners preserve sloped mesh/wave phase precision at a higher memory and
upload cost than the former height-slab atlas. The underwater pass adds one scene-size
color target per eye. Rays use at most 325 boundary/diagonal iterations. Full source
columns skip boundary-noise evaluation when their whole segment is known wet. Snapshot cost grows
cubically; GPU cost grows with represented path length and visible submerged
receivers. Correctness tests do not establish frame-rate or appearance targets.

Coverage is finite and refreshed periodically. Nodeboxes and foliage/glass filtering
remain approximate. Nonwaving flow keeps its native caustic behavior; waving flow
uses its sloped, displaced interface. Connected flow triangles support root
continuation; discontinuous heights and unsupported interfaces still reject it.
Custom adjacent liquids with different waving definitions can leave gaps or
interpenetrate; interval union prevents double absorption, but does not reconstruct
missing internal faces. Wavelengths smaller than the one-node mesh are undersampled.
Dynamic entities do not
occlude the geometry atlas, and entities do not receive this caustic modulation.
Multiple transparent sheets, secondary refraction interfaces, directional-sun
volume shafts and multiple scattering remain extensions. Beyond
known geometry, only the locally observed water path can be integrated.

## Verification

`python3 util/test_water_columns.py` compares the interior shortcut with explicit
production triangle clipping in the same program. Its 2,464 paired controls cover
static/max-height waves, source/flow interfaces, varying turbidity, air gaps,
opaque/unknown cells, axis/corner/oblique rays, first-exit truncation, sky and wet
sample intervals. Additional controls exercise 64-node geometry and a genuine
0.002-world-unit air gap in both directions. A continuous oblique column formerly
reported an exit at 115.71 world units in the clipping path despite its entire
119.156-unit ray being wet; it now retains the complete path and no-exit marker.
The column controls and existing colored-water, water-volume, flow-caustic and
connected-face suites passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330.
The optimized helper also passed the full-quality native VoxeLibre run on
OpenGL 3/TAA, including underwater torch binding/removal and medium transitions.
The full-quality legacy OpenGL/4x MSAA/side-by-side basin passed source/flow,
wave-gap, roof and drain/refill transitions. Both shut down cleanly without
shader/GL errors, screenshots or input automation.

`python3 util/test_water_lighting.py` compiles the complete underwater pass with
13-column worker and 14-column current-optics atlases. Analytic pixel checks cover
RGB emission/bounce, phase normalization, step-count independence for uniform
fields, gapped and thin sloped water, alpha and invalid/disabled inputs. A wall
test puts another lit pool beyond the stratum midpoint and requires sampling the
front pool. Moving-lamp controls cover forward/backward HG phase, incoming and
view-path extinction, an air-side source, current recolor/removal and independent
occlusion in the voxel and liquid grids. Numeric tests send no input and capture
no images.

`python3 util/benchmark_water_lighting.py` times the complete underwater pass with
native scattering, the field alone, one moving lamp and eight moving lamps in the
same shader/context. Analytic RGB controls must pass before timing. After warming
all branches, twelve GPU queries alternate and reverse their order. A GTX 1650 Ti
run before the interior traversal optimization measured these medians for eight
strata, g=0.5, a six-node uniform pool and a
16³ voxel grid:

| Draw size | Native (ms) | Field (ms) | One lamp (ms) | Eight lamps (ms) |
| --- | --- | --- | --- | --- |
| 64×64 | 0.006 | 0.055 | 0.121 | 0.591 |
| 128×128 | 0.016 | 0.171 | 0.373 | 1.869 |
| 256×256 | 0.061 | 0.601 | 1.397 | 7.150 |

The benchmark also accepts `--baseline /path/to/saved/helpers`, containing the
previous `water_volume.glsl` and `water_lighting.glsl`. Both complete old/current
passes share the same shader, uniforms, context and atlas. RGB/alpha controls must
match, both branches are warmed, and twelve paired GPU queries reverse their
order on successive repetitions. For baseline SHA256 `7b841dd376e3d0a3` and current
`9ddf06540ca474c2`, the interior source-pool medians were:

| Draw size | Native before/current (ms) | Field before/current (ms) | One lamp before/current (ms) | Eight lamps before/current (ms) |
| --- | --- | --- | --- | --- |
| 64×64 | 0.006 / 0.004 | 0.057 / 0.049 | 0.125 / 0.096 | 0.596 / 0.407 |
| 128×128 | 0.016 / 0.009 | 0.172 / 0.149 | 0.379 / 0.309 | 1.883 / 1.261 |
| 256×256 | 0.063 / 0.033 | 0.622 / 0.580 | 1.441 / 1.173 | 7.303 / 4.773 |

This is about 35% less draw time for the 256×256 eight-lamp case. It changes no
sample count, source limit, phase model or solid/unknown visibility check. Cost still grows
with view-ray samples, source count and path complexity.

`--flow` selects a shallow sloping flow layer. Its view rays still use triangle
clipping; lamp rays also enter the full source cells below it. The paired
eight-lamp medians were 0.834 / 0.642 ms at 64×64, 2.688 / 2.040 ms at 128×128 and
10.425 / 7.786 ms at 256×256 (before/current). The last case improved about 25%,
while field-only draw time changed from 0.825 to 0.798 ms. Thus the gain depends
on how much of each ray crosses proven interior water.

The fixed rays all traverse water and sample all active sources. These are GPU
draw times, excluding the rest of the renderer and CPU work; full-resolution,
deep-water and many-lamp costs can be substantial. They do not establish full-game
FPS or appearance parity with another renderer. Disable colored water lighting,
reduce its steps, or disable per-frame direct lighting to trade cost for quality.
The 13-column worker fallback retains colored field scattering without per-source
incoming water extinction.

The colored-water checks and existing water-volume, flow-caustic and connected-face
regressions passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330. The air-fog
suite also passed on all three paths after sharing the phase/coverage helpers.
The Release build and full C++ suite passed (353 individual tests and 50 default
Catch cases). A native VoxeLibre terrain copy passed the full OpenGL 3/TAA quality
preset, with the underwater voxel atlas and current warm torch source bound during
submersion, source removal, medium transitions and clean teardown. The supplied
world was untouched. The 13-column worker fallback passed on legacy OpenGL with
4x MSAA and side-by-side stereo, without atmosphere or material maps. Both red and
green held sources reached completed field uploads while the camera was underwater.
The full-quality OpenGL 3/TAA basin also passed with colored water lighting
explicitly disabled: no voxel-water bindings were reported, and source/flow,
wave-gap, drain/refill and medium transitions retained their native transport.

`python3 util/test_water_faces.py` runs actual caustic composition for analytic
Snell roots across a flow diagonal and a neighboring cell edge. The old affine
solve returned native color instead of the expected focused value at the first
control. The tests also cover camera-origin rebasing, forward/reverse surface
walks, source/flow joins, simultaneous corner crossings, an invalid intermediate
face with a valid endpoint, internal covered tops, discontinuous heights,
nonwaving/unknown/solid cells, coverage exits and correction bounds.
These checks and the existing flow/water-volume regressions passed on NVIDIA
GLSL 120/330 and Mesa llvmpipe GLSL 330 with the final convergence cutoff.

`python3 util/benchmark_water_faces.py /path/to/saved/water_volume.glsl` compares
a saved baseline with the current implementation. Both branches share the same
program, context, atlas and controls; a numeric pixel control must agree. After
warming both branches, twelve GPU queries alternate and reverse their order.
On the GTX 1650 Ti, the recorded medians were:

| Draw size | Source before/current (ms) | Sloping flow before/current (ms) |
| --- | --- | --- |
| 64×64 | 0.211 / 0.225 | 0.289 / 0.351 |
| 128×128 | 0.904 / 1.049 | 1.611 / 1.873 |
| 256×256 | 4.431 / 4.583 | 7.148 / 7.536 |

This is shader draw time for the fixed pool, light, absorption and wave phase,
with height/wavelength 1/20. It includes the existing solved-water/air visibility
rays and the new face walk, but excludes the rest of the renderer. The flow
control has a continuous global rest plane so both methods can be compared for
the same result. It is not a frame-rate or cross-game performance guarantee.
Caustic cost still grows with visible submerged area and represented depth.

The final implementation passed the full-quality basin fixture on OpenGL 3/TAA
and legacy OpenGL/4x MSAA/side-by-side stereo, including source/flow medium
transitions and clean teardown. A native VoxeLibre terrain copy passed with the
full preset, held-torch insertion/removal, underwater transitions and live voxel
lighting enabled together. These runtime checks establish integration; numeric
fragment controls establish the cross-face focusing behavior. The Release build
and full C++ suite passed again (353 individual tests and 50 default Catch cases).

`python3 util/test_water_volume.py` compiles the actual traversal, underwater and
reflection GLSL. It checks finite/separated pools, partial flow, corner ties,
unknown/solid occlusion, origin shifts, turbidity, exact homogeneous transport,
alpha/bypass guards, displaced top/bottom faces, both mesh triangles, diagonal
crossings, static/waving flow slopes and lower-cell coverage, thin-shoreline
ordering/occupancy at maximum amplitude/minimum wavelength, two-node displacement,
first-exit truncation, actual shared normals,
analytic curved-interface focusing/divergence, bounded folds,
shadows, artificial-light guards, dielectric Fresnel, critical angles, TIR and
underwater reflection fallback. `util/test_water_refraction.py` also checks both
interface directions, TIR and actual liquid lengths at rear exits. Numeric tests
capture no images and send no input. Use `LUANTI_TEST_GLSL=120` for legacy GLSL;
default is 330 core. A small temporary C++ reference program compiles the production
wave header and compares 144 animated CPU/GPU wave/triangle samples at negative
and far-world coordinates, including sloped corners, maximum amplitude and
noninteger wavelength.
It requires the same C++ compiler/headers as the engine build. See
`material-shading.md` for the verified Mesa environment.

`python3 util/test_flow_caustics.py` checks both source/flow rest triangles,
projection onto displaced flow, invalid and cross-face roots, analytic planar
Snell photon density with oblique light, sloped Newton steps and the wave Y
chain rule. Its actual caustic-composition checks include waving sloped flow,
camera-origin shifts and solved-length RGB attenuation. Wall/unknown/dry-gap
controls leave the initial search ray open but block the solved light ray;
another control rejects an extra air-side water layer. These numeric checks and
the existing water suite passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330.
The standalone basin integration also passed with the new flow caustics and
solved-path checks, preserving its ordered source/static-flow/waving-flow medium
transitions, roof changes and drain/refill sequence.
The full-quality basin passed on OpenGL 3/TAA and legacy OpenGL/4x MSAA/stereo.
The held-lamp authored-material fixture and a native VoxeLibre world copy also
passed with the new caustics, including torch insertion/removal, underwater
transitions and clean shutdown without shader/GL errors.

`python3 util/benchmark_water_caustics.py` times the production GLSL with GPU
elapsed-time queries, alternating disabled/enabled caustics after shader warmup.
It uses a seven-node-deep loaded pool, native wave noise, fixed light/phase and
one output draw; it excludes other node shading, full scene rendering and CPU
snapshot work. A GTX 1650 Ti run measured these medians of nine draws:

| Draw size | Caustics disabled | Caustics enabled | Difference |
| --- | --- | --- | --- |
| 64×64 | 0.012 ms | 1.845 ms | 1.833 ms |
| 128×128 | 0.018 ms | 4.014 ms | 3.996 ms |
| 256×256 | 0.010 ms | 5.911 ms | 5.901 ms |

These figures expose the kernel's cost on this workload. They are not full-frame
FPS, an old/new shader comparison, or a performance guarantee on other hardware.
Scene-wide GPU profiling and optimization remain open.

The C++ suite verifies node classification, light/turbidity encoding, source/flow
levels, shared flow corner/shore/upper-neighbor rules and native/unknown
exclusions, plus CPU wave triangles and shoreline ordering. The legacy mesh test
checks actual generated flow vertices and top/bottom diagonals with smooth and
flat lighting, including outward bottom normals. Temporal-history tests verify
medium-transition resets. `util/test_water_volume.sh` runs a basin with roof insertion/removal,
underwater/above-water views, draining/refilling and FOV changes. Logs require
ordered geometry and medium updates, a submerged/trough/submerged sequence within
the same native source node, held poses above/below static and waving flow, and
clean shutdown.
Liquid sinking is disabled separately from gravity so the held waterline poses
remain stationary. Optional
`LUANTI_TEST_QUALITY=true`, `LUANTI_TEST_DRIVER=opengl`, `LUANTI_TEST_AA=fsaa/taa`
and `LUANTI_TEST_STEREO=sidebyside` select integration paths.
`LUANTI_TEST_TIMEOUT` extends the 95-second default for cold combined shader
compilation without changing the scene's transition timing.

`util/voxelibre_water_test` is a read-only camera fixture for an isolated VoxeLibre
world copy. It scouts naturally generated water columns near the origin and in
successively wider regions, then visits submerged/above/submerged poses. Disable
other camera-control worldmods before using it. It never places or removes terrain.

In this workspace the Release build and complete C++ suite passed (353 individual
tests and 27 Catch cases). Numeric tests passed on NVIDIA with GLSL 120/330 core
and on Mesa llvmpipe with GLSL 330 core. Runtime checks passed for standalone water,
the complete OpenGL 3/TAA pipeline, legacy OpenGL/4x MSAA and side-by-side/TAA,
including one wet and one dry eye at a shoreline. RGB source removal and authored
material-map animation/emission checks also passed with water volume enabled.

VoxeLibre's naturally generated `mcl_core:water_source` completed underwater,
above-water and underwater-again checks without shader/GL errors. Its atlas also
included 31 native flowing-water cells; the camera poses checked source columns.
In the test
scenes, the former slab atlas averaged roughly 1.1–1.7 ms per 48³ refresh; the new
float corner atlas averaged about 3.1–3.4 ms in the standalone/stereo basins, with
a mean near 4.0 ms in the VoxeLibre run. Individual updates reached about 20 ms
in that run, which includes loading and shader compilation. These timings
measure main-thread snapshot/upload wall time. General GPU/frame-rate profiling
remains open.
No screenshots were captured.
