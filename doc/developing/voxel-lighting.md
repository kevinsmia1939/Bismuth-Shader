# Voxel radiosity and colored lighting

`enable_voxel_fog_lighting` can also scatter this field and current moving lights
through volumetric atmosphere, using the same atlas and visibility data. It is
enabled by the quality preset; see [volumetric fog](volumetric-fog.md) for controls,
history behavior, six-lobe phase limits and measured GPU costs.

`enable_voxel_lighting` enables camera-independent local light transport on desktop
OpenGL. The quality preset enables it and disables the older screen-space bounce
pass to avoid stacking both estimates. The native scalar map-light data and all
gameplay light tests remain unchanged. Disable the option and restart to restore
native rendering without a worker or atlas.

## What is computed

The main thread snapshots loaded nodes into a camera-local, node-resolution grid.
Opaque and unknown nodes block rays. Surface reflectance comes from average node
textures, overlays, node color and palette tint. Animated base/overlay textures
use their first frame as a stable representative: averaging a tall strip on a
small sampling grid can repeatedly hit neutral texels and lose a lamp's hue.
This also feeds the existing minimap color without changing texture animation.
Emissive nodes contribute RGB
sources; map and moving sources share a budget of the brightest nearby 64 exposed
sources. Direct irradiance
uses inverse-square attenuation with a smooth 16-node cutoff and exact voxel-grid
visibility traversal. This is independent of which sources appear on screen.

Each exposed opaque voxel face receives direct light from those sources and the
current directional light. Sun, moon, visibility overrides and the game's custom
shadow direction are respected. Escaping directional rays require a boundary
cell with baked sky access so sunlight is not injected into underground volumes.
When cloud shadows are enabled, directional injection uses the shared procedural
cloud transmission at each visible reflecting face. This attenuates all resulting
sun-driven bounces while preserving direct and reflected emissive light. See
[cloud shadows](cloud-shadows.md) for the shared field and interpolation details.

Fourteen fixed directions gather incident radiance from visible voxel faces.
The visibility graph is cached within a solve. Jacobi updates reflect that light
with the surfaces' diffuse albedo over 1–4 bounces; the default is two. Albedo is
bounded below one to limit energy growth. This transports reflected sun/moon and
emissive light, including color transfer from hidden/off-screen surfaces, rather
than using already-rendered scene pixels. Direct emission is separate from the
reflected field, avoiding an extra direct-emission contribution in the GI term.

This is local, diffuse voxel radiosity, not path tracing. A single finite volume
cannot represent an infinite world, fine mesh geometry, specular transport, or
all angular radiance detail. Six receiver lobes approximate directionality.
Glass and authored light-propagating materials filter rays as described below.
Partial opaque nodes are conservatively represented as full cells. Diffuse
reflectance uses one average node color, not a per-face texture integral.

## Worker and GPU integration

One `std::async` worker owns a complete immutable map snapshot. It never accesses
Client, map storage, the driver or GPU textures. The main thread polls its future
without waiting, uploads completed data, then schedules another snapshot at most
once per 250 ms. Slow solves reduce update frequency instead of blocking drawing.
Shutdown joins the outstanding job. Static-source edits and reflected lighting
propagate on the next completed solve. With per-frame direct lighting enabled,
current moving lamps and map occupancy/transmission update independently before
drawing, including while that solve is pending. Dynamic entities still do not
occlude the volume.
Cloud changes likewise propagate through the next completed immutable field
snapshot. A worker-local sparse cache evaluates needed cloud-map texels without
GPU readback, driver access or an extra atlas.

A single RGBA32F atlas uses 13 columns of N×N slices, stacked across Z, or 14 with
per-frame moving direct lights. Six columns
store direct irradiance, six store reflected irradiance, and the thirteenth column
stores receiver tint and emissive markers. The optional fourteenth column stores
RGB transmission and air/solid validity for GPU visibility traversal. Alpha in
the irradiance bands marks valid air probes. The
shader interpolates adjacent Z slices and uses 2D filtering within each slice;
invalid/solid samples are excluded and boundary blending restores native light
near the grid edge. No mipmaps are generated for the atlas.

Surface shading returns native color before atlas access when the receiver is
outside the local field or both lighting gains are zero. Inactive direct/bounce
lobes skip their reads. This keeps distant terrain from paying for local probe
gathers that would be multiplied by zero, and preserves native fallbacks without
introducing a global ambient floor. Numeric tests poison unavailable probes to
check these guards. The balanced preset retains a 32-node grid, one diffuse
bounce and GI gain 0.35; additional coverage/bounces remain optional costs.

The atlas occupies material texture slot 2; crack overlays remain in slot 1 and
shadow maps in slot 3. A shared GLSL helper serves node and object shaders.
A material-binding guard enables sampling only when that material actually owns
the live atlas. This protects inventory/wield materials and other render passes
from accidentally sampling an unrelated texture. Mesh/sprite entities receive the
field; explicitly glowing/full-bright entities retain their authored lighting.
Wield/item scene nodes that do not expose those materials retain native lighting.

Native artificial light is replaced proportionally inside the valid volume,
while directional/baked lighting is retained. RGB direct light and diffuse bounce
are applied to linear receiver albedo. Node/palette tint is preserved; entities
use their own textures, independent of the map cell they occupy. Emissive node
surfaces keep their existing self illumination. Existing SSAO, reflections, fog,
TAA, exposure and bloom remain downstream consumers.

Native-light replacement uses the current draw's `MATERIAL_EMISSIVE` variant,
independent of the asynchronous atlas emission marker. This protects newly
placed glowing nodes, native mesh/sprite `glow`, and unshaded object variants
before a solve completes. It also protects a node whose explicitly black RGB
scene emission leaves the atlas marker zero: scene-light emission and the native
surface's authored brightness are separate decisions. Replacing an emitter
with an ordinary material immediately restores ordinary light replacement,
without inheriting stale self-illumination protection.

Node base/overlay/special tiles acquire this variant when voxel lighting is
enabled, including when material maps, the SSAO emission mask and cloud shadows
are all disabled. No extra shader uniform, atlas column or render pass is added.
The tint/marker atlas layout is retained; its emission alpha no longer decides
the visible material's classification. Static RGB emission, tint and bounced
radiance still follow solve latency. Native self illumination and baked diffuse
remain a combined authored term rather than separately calibrated energy lobes.

## Held and moving lamps

`enable_voxel_dynamic_lighting` defaults to true when voxel lighting is in use.
The selected inventory node emits at the local player's eye position minus
0.35 nodes, independently of the third-person camera and HUD visibility. This
approximates the carried lamp location rather than following the animated hand.
Changing the selected stack or its metadata changes the current frame's direct
sources on supported configurations; indirect light changes with the next solve.
Stack count does not multiply light intensity. Empty hands and non-emissive
items add no source.

Visible `node`, `item` and `wielditem` entity visuals also contribute at their
current world position, including fractional node coordinates and attached
objects. Modern serialized item stacks and legacy item texture names are
supported. Local-player `wielditem` display attachments are excluded to avoid
duplicating the carried inventory source. Visibility changes and removals remove
the direct source in the current frame and its bounce on the next completed
solve. Sources do not require screen visibility.

Emission uses the represented node's existing `light_source` and optional
`light_source_color`, with the same intensity normalization as map lamps.
Unspecified colors use average node texture color and the node palette/param2 or
itemstack color/palette metadata, with the same representative-frame handling
for animated tiles. Explicit black emits nothing. `glow` remains
self illumination; a bright mesh or sprite does not imply a new scene light.
There is no new network property or gameplay-light change.

Moving sources are point samples, independent of map occupancy and material
emission markers. They use the same visibility traversal, range, surface
reflection and multi-bounce solve as map sources. A point in an opaque/unknown
cell or outside the volume is rejected, rather than opening a path through that
cell. The asynchronous bounce solve shares distance/brightness priority and a
64-source cap with map lamps. The per-frame direct path separately reserves a
held light and chooses nearby bright actors, up to eight moving sources. There
is no new GPU texture, render pass or material slot; the atlas gains one column.

The main thread copies positions, colors and source kind into the immutable
worker snapshot. The worker keeps no player, item, entity or driver references.
The 250 ms scheduling interval plus solve latency applies to bounced light and
map geometry. Disabling the dynamic option clears per-frame sources immediately
and their bounce in the next snapshot, while retaining map lighting. Unsupported
or disabled per-frame configurations retain the previous asynchronous direct
path too. Dynamic actors still do not occlude light. General mesh/sprite
emission, animated hand transforms, cascaded volumes and higher spatial/angular
resolution remain extensions.

## Per-frame moving direct light

`enable_voxel_dynamic_direct` defaults to true with voxel lighting on desktop
OpenGL 3 or newer (including the legacy driver on a modern context). Restart to
change it. Older contexts and the explicit opt-out keep the 13-column atlas and
worker-driven direct light. `enable_voxel_dynamic_lighting` still controls whether
held/actor sources exist, and can be changed for the next frame/snapshot.

The main thread collects current interpolated source positions and colors before
polling the worker, including while a solve is pending and between scheduled
snapshots. The held source has priority, then brightness/distance select actors.
At most eight sources reach the shader and the next bounce snapshot. The bounce
solver still applies its shared 64-source cap. Crowded scenes may omit a source
from bounced lighting even when it has a current direct light.

Node/object shaders receive bounded position/color uniform arrays in atlas-node
coordinates. Both eyes share these world-space sources, independent of projection
jitter and camera-origin rebasing. Sampling requires the material's actual live
atlas binding. The legacy Irrlicht uniform lookup accepts array base names as
well as its historical `[0]` spelling, matching OpenGL 3 array handling.

For each contributing source, the fragment shader traces the latest uploaded
occupancy/transmission grid with exact DDA segments and RGB Beer-Lambert
attenuation. It retains the existing 16-node inverse-square/fade cutoff. Unknown,
solid and outside-volume source/path cells fail closed. Node receivers may ignore
only their own coarse cell, preventing full-cell self blockage on partial node
geometry; an object inside a solid cell cannot do so. The 48-step bound covers a
16-node ray; exhaustion returns no light. Clear cells avoid power evaluations.

Direct irradiance uses the current fragment position and shading normal. Sprite
normals use the existing six-lobe isotropic convention. Source movement, recolor,
visibility and removal do not need an atlas upload. The worker excludes moving
sources from its direct-probe bands, while retaining their incident light on
reflecting surfaces and all bounces, so direct lighting is not counted twice.
Static map lamps and sky injection keep their existing asynchronous path.

The additional atlas column costs about 0.5 MiB at 32³ or 1.69 MiB at 48³.
Uniforms add two arrays of eight vec4 values and a count. No per-frame GPU
texture or material allocations are needed. Source collection is profiled as
`Voxel dynamic sources [ms]`; per-fragment cost grows with visible contributing
lights and traversed cells. Zero-source/zero-strength guards avoid those rays.
Eligible node materials also evaluate local GGX specular in the same source loop
and reuse the visibility result; see [material shading](material-shading.md).

The main thread walks the published atlas's loaded map cells every frame and
compares their occupancy/RGB transmission with its last published optics. A
changed grid uploads only the fourteenth atlas column using Irrlicht's optional
`ITexture::updateRegion`; unchanged grids avoid GPU uploads. That upload does not
read back or replace radiance. A completed worker may contain older geometry,
so its optics column is refreshed again before drawing. Both stereo eyes share
the same published origin and optics.

Direct diffuse and GGX use current geometry even when an old radiosity probe
still marks the receiver as solid. Baked diffuse/bounce interpolation and native
light replacement retain their own validity weight. Local fog rejects newly
occupied cells using current optics and uses those optics on moving-light rays.
Successful geometry changes advance the lighting revision so fog history resets
rather than retaining obsolete occlusion.

Two persistent CPU optics buffers cost 1 MiB at 32³ or 3.375 MiB at 48³.
An edited optics column transfers 0.5 MiB or 1.69 MiB respectively; a worker
upload can require another optics refresh even without a new edit. Scanning cost
is profiled as `Voxel direct geometry [ms]`; shutdown logs the mean/maximum cost,
scan count and upload count. This cost includes any driver upload wait, not only
CPU map traversal. No additional GPU texture, sampler or render pass is added.

Coverage/origin movement, first-atlas readiness, static-source direct light and
indirect bounce still follow snapshot/solve latency. This is node-resolution map
occupancy, without partial geometry or dynamic-object shadowing. Thin/partial
transparent geometry and hand animation retain the previously described limits.
TAA can still retain lighting history; this change does not add motion vectors
or a separate lighting-reactivity mask. Older contexts and the explicit
frame-direct opt-out retain asynchronous geometry with the 13-column atlas.

## Colored transmission

`enable_voxel_transmission` defaults to true with voxel lighting. Loaded
light-propagating map cells can carry a linear RGB transmittance for one node
of path length. Exact grid traversal integrates each segment as `T^length`:
thicker layers compound, slanted paths attenuate more, and starts/ends within a
material use only the traversed fraction. Zero channels fully absorb; clear
channels preserve energy. Opaque and unknown cells still stop rays regardless
of the authored transmission.

The same traversal filters map/held/moving lamps, directional-light injection
onto reflecting faces and reflected radiance gathered between surfaces and
probes. Bounce visibility caches retain RGB transmission across Jacobi updates.
Cloud attenuation multiplies the transmitted directional irradiance; it does
not recolor local lamps. Removing/recoloring a filter replaces the next complete
snapshot and its cached paths. This does not change scalar gameplay lighting.

Glass drawtypes infer a filter from average texture/palette hue in linear color,
normalized by the brightest channel, with a 0.96 neutral one-node transmission.
Neutral gray glass therefore stays neutral rather than acquiring strong bulk
absorption from its border texture. Ordinary plants, air and unconfigured liquids
remain clear. Other light-propagating materials can opt in, and glass can override
inference, using this optional node property:

```lua
core.register_node("example:green_glass", {
    drawtype = "glasslike",
    tiles = {"example_glass.png"},
    paramtype = "light",
    sunlight_propagates = true,
    light_transmission_color = "#80ff80",
})
```

RGB bytes divided by 255 are **linear transmission**, not gamma-decoded albedo;
alpha is ignored. White explicitly requests clear transport; black absorbs all
channels. The optional versioned tail follows the material-map extension inside
the length-wrapped nodedef payload. A transmission-only definition writes the
empty material extension first. Older material-aware readers retain their
existing maps and ignore the tail; new readers reset reused fields for older
payloads. Definitions without an authored value add no new suffix.

This is full-cell absorption along straight rays. It does not refract light,
resolve thin panes, alpha cutouts, flowing-liquid heights, nested media or moving
glass geometry. Transparent cells do not become reflective radiosity surfaces.
Only the voxel field is affected: primary native sunlight still uses the existing
colored shadow-map path. Automatic liquid optical coefficients and finer
transparent geometry remain work. Authored liquid filters use the full cell,
independently of the more detailed camera water-volume optics.

The atlas and shader texture slots are unchanged. Worker cells add 12 bytes each;
filtered solves optionally cache 14 RGB vectors per cell (about 5.25 MiB at 32³,
17.7 MiB at 48³), alongside the existing visibility indices. Clear solves avoid
that cache. Filtering adds per-segment power evaluations and can increase worker
latency in dense glass/media scenes. The existing scheduling/solve delay applies.
Disabling the option restores clear transport in the next snapshot.

## Configuration and node API

- `enable_voxel_lighting`: default false; restart to change.
- `enable_voxel_dynamic_lighting`: default true; next frame for direct light,
  next snapshot for bounce (or for direct light in the fallback).
- `enable_voxel_dynamic_direct`: default true; requires desktop OpenGL 3; restart.
- `enable_voxel_transmission`: default true; applies to the next snapshot.
- `voxel_lighting_size`: 16, 24, 32 or 48 nodes per side; default 32; restart to change.
- `voxel_gi_bounces`: default 2, range 1–4.
- `voxel_light_strength`: default 1.0. Zero retains native artificial lighting.
- `voxel_gi_strength`: default 0.5. Zero disables added reflected light.

An optional node `light_source_color` ColorSpec controls the hue of emitted light.
`light_source` continues to determine scalar intensity/range; alpha is ignored.
When unspecified, hue is inferred from average texture/palette color. Explicit
black emits no RGB radiance. For example:

```lua
core.register_node("example:blue_lamp", {
    tiles = {"example_lamp.png"},
    light_source = core.LIGHT_MAX,
    light_source_color = "#3070ff",
})
```

The color and its presence flag are appended to the existing length-wrapped node
definition payload. Old readers ignore the suffix. New readers accept payloads
without it and reset reused definitions to the unspecified/white defaults. This
preserves scalar map lighting and the older-client fallback.

## Performance and verification

A 32³ atlas occupies approximately 6.5 MiB of GPU memory, or 7 MiB with per-frame
direct lighting. Worker-side geometry, visibility and irradiance arrays require
additional CPU memory. Larger grids cost cubically more work. Profiling separates
`Voxel GI snapshot [ms]`, `Voxel GI solve [ms]` and `Voxel dynamic sources [ms]`.
Current map visibility adds `Voxel direct geometry [ms]` separately from solving.
The checks below establish correctness, not frame-rate claims on other hardware.

The Release build and full C++ suite passed with 353 individual tests and 48
Catch cases. Solver tests cover RGB emission, sealed-wall/roof occlusion,
reflectance color, multiple bounces, hidden indirect paths, cloud-modulated sun,
fractional moving sources, recolor/removal, source budgets, RGB path length,
slanted/partial segments and filtered reflected paths. Nodedef cases cover
emission/transmission/maps, optional tails, legacy prefixes and reset on reused
definitions. Frame-direct tests require that only dynamic direct-probe light is
removed while its diffuse bounce remains identical, and that source selection
reserves the held light, rejects invalid data and obeys its bound.

`python3 util/test_dynamic_lighting.py` compiles the actual shared voxel GLSL.
It checks movement/recolor/removal using only uniform changes, all eight array
entries, isotropic/coincident sources, opaque/unknown/outside guards, the node
receiver exception, colored thickness/slanted/partial paths, zero channels,
static/direct/bounce/palette bands in the 14-column atlas, origin rebasing,
strength/readiness/no-source guards and the original 13-column fallback.
Optics-only subregion checks additionally change a wall to glass and back to air
without replacing solved radiance. A stale solid probe must not suppress current
direct lighting; the local material test checks the same invariant for GGX.
Numeric tests passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330. Set
`LUANTI_TEST_GLSL=120` for legacy GLSL. Mesa selection in this workspace uses
`SDL_VIDEODRIVER=offscreen`,
`__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json` and
`LIBGL_ALWAYS_SOFTWARE=true`. Tests report the actual renderer and use no image
capture or input events.

The current live-optics build passed the full C++ suite (353 individual tests
and 50 default Catch cases). Dynamic-light, local-GGX and fog numeric tests
passed on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330, including newly occupied
fog samples with stale valid radiance and newly opened material receivers with
stale solid probes.

`bin/luanti --run-tests '[texture-region]'` opts into an Irrlicht GPU test. It
creates desktop OpenGL 3 and legacy OpenGL devices and checks real RGBA32F region
uploads, untouched surrounding radiance, exact edge bounds, invalid/empty/null
regions, locked textures and refusal to stale retained CPU copies or mipmaps.
The ordinary C++ suite remains independent of a display. This GPU case passed
16,416 assertions on both NVIDIA and Mesa llvmpipe in this workspace.

`python3 util/test_native_emission.py` compiles the full production node and
object fragments with the actual voxel helper. Both 13/14-column paths check
emissive/ordinary variants against contradictory atlas markers, native brightness,
RGB direct/bounce additions, moving-lamp and sprite response, alpha and unbound/
disabled fallbacks. The pre-fix node case returned black instead of the expected
native RGB when its atlas marker was zero. The corrected full fragments pass on
NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330. The mapped local-GGX test also
checks native emission in the artificial-light setting.

`util/test_voxel_lighting.sh` creates a temporary devtest world and checks Lua
RGB transport, an off-screen source, ordered source removals, object receivers,
TAA/bloom and clean shutdown. Its optional environment flags combine features:

- `LUANTI_TEST_QUALITY=true`: quality preset, fog/water and day/custom-light poses.
- `LUANTI_TEST_DRIVER=opengl`, `LUANTI_TEST_AA=fsaa`,
  `LUANTI_TEST_STEREO=sidebyside`: alternate driver, 4x MSAA and stereo.
- `LUANTI_TEST_CLOUD_GI=true`: overcast/clear/restored directional injection.
- `LUANTI_TEST_DYNAMIC_LIGHTING=true`: held red/green metadata, fractional
  off-screen blue item, legacy item name, moved red node, hide/restore/removal
  and explicit-black control; requires completed worker uploads. `false` runs
  the same changes with moving-source injection disabled.
- `LUANTI_TEST_TRANSMISSION=true`: authored green/blue, inferred red and removed
  glass in completed worker snapshots; overlaps held lamps when enabled together.
  `false` requires clear transport through the same node edits. Solver tests
  separately establish irradiance attenuation; runtime checks establish data flow.
- `LUANTI_TEST_DYNAMIC_DIRECT=true`: 14-column atlas, actual uniform-array IDs,
  current-frame source changes and shader binding. `false` requires the
  13-column fallback and no frame-direct bindings.
- `LUANTI_TEST_GEOMETRY=true` with moving lighting enabled: rapid solid/green/
  blue/clear map edits, requiring current optics uploads while a real immutable
  solve is pending. Shutdown reports map scan and partial-upload costs.
  `LUANTI_TEST_VOXEL_SIZE=48 LUANTI_TEST_BOUNCES=4 LUANTI_TEST_FPS=120
  LUANTI_TEST_WIDTH=128 LUANTI_TEST_HEIGHT=128` stresses maximum coverage/bounces
  while allowing enough frames to observe solve overlap. The fixture sets both
  focused and unfocused frame limits, without sending input or changing focus.
- `LUANTI_TEST_NATIVE_EMISSION=true`: disables authored maps, SSAO/emission-mask
  and cloud-shadow dependencies, then requires emissive node/object variants,
  black-RGB emitter insertion/replacement/removal and cube/sprite glow/ordinary/
  unshaded transitions. This is a runtime binding/update check; numeric fragment
  tests establish brightness preservation without screenshots or input events.

The native-emission fixture passed on OpenGL 3/TAA with current-frame direct
lighting and on legacy OpenGL/4x MSAA/stereo with the 13-column worker fallback.
Both disabled material shading, SSAO/emission-mask and cloud-shadow dependencies
while exercising zero-RGB emitter changes and cube/sprite property updates.
The quality material fixture passed with authored/companion/animated maps,
metallic emission, held-light changes, directional source transitions and clean
shutdown. A native VoxeLibre terrain copy also passed with held-torch hue/removal,
water transitions and the full quality preset. The Release build and full C++
suite passed again (353 individual tests and 50 default Catch cases).

The live geometry fixture passed with 48³ coverage and four bounces on OpenGL
3/TAA and legacy OpenGL/4x MSAA/side-by-side stereo. Both required solid/green/
blue/clear uploads while a real solve was pending, alongside moving lamps,
source removal, local fog, water and clean teardown. At 128×128 with both frame
limits set to 120, the geometry-update function averaged 1.823 ms (4.965 ms
maximum, 4,433 scans/169 optics uploads) on the OpenGL 3 run and 1.812 ms
(7.283 ms maximum, 4,368 scans/164 uploads) on the legacy stereo run. These are
function wall times from this desktop, including upload waits, rather than
whole-frame FPS or isolated CPU traversal benchmarks. Initial low-frame-rate
runs verified edits but could not prove overlap because each solve had finished
before the next unfocused frame; the fixture now explicitly controls that cap.
The original 13-column worker fallback also passed with moving lamps and authored/
inferred filter edits, without live-geometry scans. A native VoxeLibre terrain
copy passed the full preset with live map optics, held-torch RGB insertion/removal,
underwater transitions, fog/cloud denoising and clean shutdown. The original
world was not modified.

The combined quality run passed on OpenGL 3/TAA and legacy OpenGL/4x MSAA/
side-by-side stereo with moving lights, colored filters, SSAO coverage, fog/water
transitions and clean shutdown. The explicit asynchronous fallback passed the
same held/moving/filter sequence with its original atlas layout. Cold shader
compilation may require `LUANTI_TEST_TIMEOUT` independently of warm-frame cost.

`LUANTI_TEST_DYNAMIC_DIRECT=true util/test_material_shading.sh` checks mapped
normal/ORM receivers, texture-pack companions and animated maps while a held
lamp is added and removed. This run passed with actual frame-direct bindings
and clean shutdown. Numeric `util/test_point_materials.py` separately verifies
the local specular response and the actual node composition.

`util/test_voxelibre_lighting.sh /path/to/stopped/voxelibre/world` copies an
existing SQLite world and installs only the native-water fixture in that copy.
It leaves the supplied world unchanged and removes temporary data afterward.
The fixture uses naturally generated water, cloud/fog denoising and a held native
torch. Assertions require valid frame-direct array bindings, a warm current-frame
source and completed worker source upload (red > green > blue > zero), then both
paths clearing after removal. The representative-frame color check rejects the
neutral hue caused by sparse sampling of the complete animated torch strip.
The native test passed with the quality preset, separate cloud/fog denoising,
both SSAO guides and clean shutdown. Its current-frame and completed worker
source colors were approximately `(2, 1.05425, 0.640482)`; direct and bounced
source lists both cleared after torch removal. The supplied world was untouched.

## Underwater light transport

`enable_voxel_water_lighting` shares the direct/bounced field and current moving
source list with the underwater pass. It requires loaded-water geometry and voxel
lighting, independently of atmosphere and air fog. The quality preset enables it.
Map/bounce probes use normalized six-lobe HG weights; moving lamps also trace
water-only RGB extinction from the source to each wet view sample, with current
voxel RGB filtering and solid/unknown checks in both grids. The 13-column worker
fallback uses the baked field without per-source incoming water extinction.
See `water-volume.md` for integration, sampling controls, transport approximations
and measured GPU cost. No new atlas or worker solve is introduced.

`LUANTI_TEST_WATER_LIGHTING=true/false` overrides the voxel integration harness to
check bindings or opt-out. The native VoxeLibre harness now requires the underwater
voxel atlas and moving-source arrays too; its torch is held during the initial
submerged pose. Numeric `util/test_water_lighting.py` verifies actual RGB transport
independently of runtime binding logs.
