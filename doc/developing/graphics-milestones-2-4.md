# Semi-realistic graphics: milestones 2–4

This is the implementation scope supplied by the user. Preserve the voxel art
style and existing texture packs. Numeric GPU tests and scripted world fixtures
replace screenshots and input-device automation.

## 2. Finish sunlight and atmosphere

Tune soft shadows, daylight color, sunset transitions, distance fog and restrained
light shafts. Volumetric clouds remain optional.

Acceptance: shadows remain stable during movement; interiors stay darker than
outdoors; fog preserves nearby terrain detail; transitions do not produce abrupt
brightness changes.

## 3. Finish water appearance

Tune waves, Fresnel reflections, screen-space reflections, sky fallback,
refraction and underwater absorption. Expensive caustics remain optional.

Acceptance: rivers reflect their surroundings convincingly; missing reflection
samples blend into the fallback; shorelines and water entry/exit have no obvious
seams or flashes.

## 4. Finish colored lighting and affordable indirect light

Placed glowing blocks and held lamps illuminate nearby terrain with consistent
colors. Local approximate diffuse bounce softens otherwise black areas.

Acceptance: lamps update when moved or removed; ordinary walls block direct
light; caves retain darkness away from sources; indirect light adds subtle color
without washing out the scene.

## Verification and boundaries

Use the fixed forest, sunset river, cave and underwater scenes from
[Milestone 1](graphics-milestone-1.md), supplemented by controlled wall, lamp and
interface fixtures. Preserve raw numeric evidence and test the actual production
shader composition, including fallback paths. Runtime checks must exercise
source changes, movement and water transitions after shaders are ready.

The suggested hardware budget remains 1080p/60 FPS on the available GTX 1650 Ti,
subject to profiling. Material response, combined-image stabilization and final
preset delivery are milestones 5, 6 and 7, respectively. They are not substituted
for the three milestones above. Existing material/TAA paths still need regression
coverage when these changes affect them.

Completion is unproven until each acceptance criterion has current implementation
and numeric/runtime evidence. See the [measured baseline](graphics-baseline/README.md)
for the initial performance and its limitations.

## Current verification

Milestones 2–4 are implemented and verified in the controlled native scenes and
tested desktop OpenGL paths. The [validation and lighting-cost report](graphics-milestones-2-4-results/README.md)
contains raw evidence, settings, source hashes and reproduction details.

The resumed Release build and complete
C++ suite passed (353 legacy tests and 53 default Catch cases). Numeric water
checks, including the final continuous TIR correction, passed on NVIDIA GLSL
120/330 and Mesa llvmpipe GLSL 330. Atmosphere, shadow and colored-light checks
also passed on the tested paths.

The eleven-phase native VoxeLibre replay passed with the final TIR gain
correction and opt-in scalar scene statistics. Cave darkness, warm lamp
brightening/removal and water transitions were checked against actual composed
scene values. Two repeats per timing condition used a balanced/control/control/
balanced order, identical 1080p/FOV/view-distance settings and the same frozen
world. The complete local-light path adds 3.1–4.9 ms per frame in these scenes,
including the worker, direct lighting and bounce. This is not an isolated
diffuse-GI or GPU-pass measurement. Partial/interrupted runs are excluded.

Balanced averages were 41.8 FPS in the forest, 40.5 FPS at the river, 65.9 FPS in
the cave and 51.0 FPS underwater. Only the cave meets the proposed 60 FPS/p95
budget. The control also misses 60 FPS in the forest and river; further complete
renderer optimization and the final preset remain milestone 7.

## Acceptance audit

| Requirement | Current evidence |
| --- | --- |
| Stable soft shadows during movement | Transported shadow-camera basis and fixed light-space PCSS kernel; C++ noon/custom-source basis checks, numeric PCSS warp/receiver tests, and native camera rotation beyond the frustum recapture threshold. |
| Darker interiors and nearby fog detail | Native cave mean luminance 0.000006 versus forest 0.089346. Production haze matches independent height quadrature and preserves one-node RGB within 0.002 in the numeric fixture. |
| Smooth daylight and restrained shafts; optional clouds | Shared linear source, horizon fade and natural sunset warmth; C++ radiance-continuity checks and native sunset sweep (largest sampled mean-luminance step 0.008390). The replay uses eight fog steps, half resolution and game strength 0.15; volumetric clouds remain optional. |
| Waves, reflections and fallback | Shared source/flow geometry and interface-normal tests; production SSR tests recover actual donor radiance, match an analytic edge-confidence curve and reject foreground/water hits. Native river motion passed. |
| Refraction, absorption, shorelines and entry/exit | Numeric Snell/TIR, wavelength-dependent absorption, thin-water transmission, edge-radiance fading and full scene-pass checks. Native entry/exit largest sampled luminance steps were 0.004590/0.006712. |
| Consistent colored placed/held lamps | Numeric CPU/GPU color/visibility/composition tests plus native warm RGB source packets and actual warm RGB brightening of the cave. Underwater torch transport passed. |
| Lamps clear when removed | Native scene returned to its original darkness for three consecutive samples within 289.2 ms for glowstone and 185.6 ms for the held torch. Moving-lamp position changes are checked by production GLSL and exercised in the native replay. |
| Ordinary walls block direct light | CPU opaque-wall/closed-room tests and GPU occupancy/transmission tests, including live blocker edits while the baked field remains stale. |
| Subtle, affordable local bounce | Closed-room darkness and colored corner-bounce tests, actual native darkness after source removal, bounded 32-node/one-bounce/0.35-gain preset and the matched lighting-cost comparison above. |

These checks establish the requested behavior in the tested scenes. Screen-space
reflection coverage, finite shadow resolution/sampling, conservative partial-node
occlusion and asynchronous static/bounce updates remain approximation limits.
The scalar replay cannot inspect every pixel. Material/asset compatibility,
general combined-image stability and final preset delivery remain milestones
5–7, rather than additional realism work for these three milestones.

## Implemented changes and ongoing verification

- Shared linear daylight source for surfaces, fog, water and diffuse bounce;
  smooth horizon strength, weaker moonlight and bounded natural sunset warmth.
- A transported light-camera basis avoids the shadow-camera singularity at noon.
  The fixed light-space shadow kernel remains independent of camera jitter.
- Analytic haze integrates height density across the whole ray, including
  sea-level crossings. Volumetric fog retains shadowed light shafts and separate
  denoising; clouds remain optional.
- Water SSR clips its final screen-edge segment, refines valid hits, rejects the
  first ambiguous foreground crossing and fades valid hits into the fallback.
  Refraction blends linear sample radiance rather than UV coordinates.
  Shallow water approaches clear transmission continuously; subcritical
  underwater reflections approach full TIR without a gain discontinuity.
- Local-light shading skips inactive/out-of-coverage probe gathers. The existing
  bounded worker, direct-light visibility, colored transmission and one-bounce
  balanced settings remain in use.

`python3 util/test_atmosphere.py` compares production haze integration with an
independent quadrature and checks nearby detail, source transitions and dark
interior/medium guards. `python3 util/test_water_reflections.py` checks actual
reflected terrain radiance, analytic edge confidence and foreground rejection.
Existing refraction, water-volume, shadow, directional-light and colored-light
tests cover their production helpers and composition. These are numeric GPU
readbacks, not screenshots.

```sh
python3 util/test_graphics_milestones.py /path/to/prepared-world --output /tmp/graphics-acceptance
```

The native replay copies the stopped benchmark world, disables weather/mobs, and
uses eleven phases across the four environments: forest motion, sunset sweep,
river motion, water entry, submerged torch, water exit, cave darkness, placed
glowstone, its removal, held-torch movement and removal. Each phase waits for two
completed-client progress checkpoints before starting. The post-run audit also
requires real frame coverage in every exercise window, correct dimensions,
current lamp/medium state, bound effects and clean shutdown. It preserves raw
CSV/logs, exact config, scene manifest and source/binary hashes. This 640×360,
30-FPS-capped replay validates transitions; it is not a 1080p performance result.

The replay turns the camera past the shadow-frustum's 15-degree recapture
threshold. `benchmark_scene_log` installs a test-only reduction pass: a fixed
16×9 set of probes measures mean linear RGB and sampled peak luminance after
fog/water composition and before TAA/exposure. Only one RGBA32F texel is read per
frame; no image is stored. Its buffered CSV detects broad brightness failures,
checks that caves stay substantially darker than the forest, confirms warm lamp
color in the composed scene, and checks removal against the original darkness.
Three consecutive dark samples must arrive within one second of lamp removal.
Per-pixel numeric tests cover shoreline, reflection-edge and critical-angle
continuity. Fixed scalar probes cannot certify every pixel or visual parity with
a particular shader pack.

This diagnostic is used by the mono desktop-OpenGL replay and is disabled during
performance measurement. Without `benchmark_scene_log`, its pass, texture and
readback are absent. The runner preserves `launch.conf` separately from
`client.conf`, which the engine may rewrite on shutdown, and hashes both.

`benchmark_frame_progress=true` is a developer-only companion to
`benchmark_frame_log`; it emits one checkpoint per 30 buffered frames. It is off
for frame-time benchmarks to retain buffered-only sample I/O.

For restrained shafts with the existing balanced effects, the replay uses density
0.0015, eight fog steps, half-resolution denoising, 64-node range, variation 0.15
and game volumetric strength 0.15. Native clouds remain available while
volumetric clouds and caustics are optional. The final preset and agreed complete
renderer performance gate remain milestone 7.
