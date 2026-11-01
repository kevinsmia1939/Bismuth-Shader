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

## Paused checkpoint

Implementation is paused at the user's request. The Release build and complete
C++ suite passed (353 legacy tests and 53 default Catch cases). Numeric water
checks, including the final continuous TIR correction, passed on NVIDIA GLSL
120/330 and Mesa llvmpipe GLSL 330. Atmosphere, shadow and colored-light checks
also passed on the tested paths.

The eleven-phase native VoxeLibre replay passed before the final TIR gain
correction. A replay of that final correction was interrupted by the pause and
must be completed. The 1080p comparison of balanced rendering with native-light
control is also unfinished; partial/interrupted runs do not establish the final
lighting cost or a 60 FPS result. Milestones 2–4 are not marked complete.

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

`benchmark_frame_progress=true` is a developer-only companion to
`benchmark_frame_log`; it emits one checkpoint per 30 buffered frames. It is off
for frame-time benchmarks to retain buffered-only sample I/O.

For restrained shafts with the existing balanced effects, the replay uses density
0.0015, eight fog steps, half-resolution denoising, 64-node range, variation 0.15
and game volumetric strength 0.15. Native clouds remain available while
volumetric clouds and caustics are optional. The final preset and agreed complete
renderer performance gate remain milestone 7.
