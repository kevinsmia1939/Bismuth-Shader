# Milestone 1: stable baseline and performance budget

The target is one semi-realistic VoxeLibre preset that keeps the block art style.
This milestone establishes a repeatable baseline and a measured settings choice;
it does not add further realism features or require screenshots.

The repeated 1080p measurements are in the
[baseline report](graphics-baseline/README.md), including exact settings and
compressed raw frame logs. Balanced results are 40–41 FPS in the forest,
41 FPS at the river, 66–67 FPS in the cave and 46–48 FPS underwater on the GTX
1650 Ti. Only the cave meets the proposed 60 FPS budget. These measurements
precede [Milestones 2–4](graphics-milestones-2-4.md).

## Required deliverables

1. Finish validation of the paused normal-map mip filtering change: CPU moment
   preservation, actual OpenGL mip uploads, shader roughness/highlight integration,
   raw/missing-map fallbacks, animation and a complete build/test run.
2. Prepare four fixed scenes in an isolated copy of a stopped VoxeLibre world:
   a sunny forest, a sunset river, an underground glowing-block chamber and an
   underwater river view. Store coordinates, view angles, environment and node
   evidence in a scene manifest. Never modify the source world.
3. Measure the complete client at 1920×1080 with fixed FOV/view distance, VSync
   disabled and equal focused/unfocused limits. Compare basic rendering, the
   existing combined quality preset and a candidate balanced preset. Exclude
   startup, shader compilation and scene-settling periods. Preserve raw frame
   samples, logs and exact settings. Repeat runs to expose variability.
4. Report aggregate FPS, median/p95/p99 frame times, sample counts and actual
   dimensions for every scene/profile. Record hardware, driver, engine/game
   revisions and source/settings hashes. Distinguish wall-clock frame delivery
   from CPU draw submission and isolated shader timing.
5. Deliver a fixed balanced settings file and a performance table explaining
   which effects remain optional. The proposed target is 60 FPS at 1080p on the
   available GTX 1650 Ti. Report misses honestly; a measured budget and settings
   choice are required, a speculative FPS claim is not sufficient.

## Scope boundary

Keep existing implementations and fallbacks. No path tracing, cascaded GI,
physically exact caustics, entity material overhaul or new cinematic effects.
Further feature work belongs to subsequent milestones. This milestone is complete
when the five deliverables above exist and their current-state evidence has been
checked.

## Reproduction commands

```sh
cmake --build build -j2
bin/luanti --run-unittests
bin/luanti --run-tests '[normal-mips]'
python3 util/test_normal_mipmaps.py
python3 util/test_graphics_benchmark.py
LUANTI_TEST_DYNAMIC_DIRECT=true LUANTI_TEST_DIRECTIONAL=true LUANTI_TEST_TIMEOUT=600 util/test_material_shading.sh

python3 util/benchmark_graphics.py prepare /path/to/stopped/voxelibre/world --output /path/to/benchmark
python3 util/benchmark_graphics.py run --output /path/to/benchmark --label baseline --repeats 2
python3 util/benchmark_graphics.py report --output /path/to/benchmark --label baseline --destination /path/to/report
```

The runner copies the supplied world, removes its camera worldmods, generates
native forest/river/cave coverage and stores `graphics-scenes.json`. It adds one
native glowstone block inside the disposable cave copy. It removes persistent
actors from run copies and disables new mobs/weather. V7 rivers use ordinary
water; preparation checks the v7 channel noise and banks rather than assuming
the valleys mapgen's river-water node. Sunset uses time 0.78.

Each run waits for an opt-in client frame-log readiness marker after a completed
frame, then settles each pose for 20 seconds and samples for 20 seconds. The
second repeat reverses profile order. Neither shader compilation nor pose-settling
frames enter the table. Static camera corrections during measurement invalidate
the run; nonmatching render dimensions and incomplete sample windows also fail.

`benchmark_frame_log` is a developer-only optional config path. The client buffers
frame timestamps, elapsed/busy/sleep times, CPU draw submission time, actual
dimensions and drawcall counts, then writes CSV on clean shutdown. No texture
readback, screenshots, GPU finish calls or input-device events are used. The
clock matches server `core.get_us_time()` for window alignment. This measures
whole-client frame delivery including the local server and presentation, rather
than isolated GPU pass time. `util/test_graphics_benchmark.py` independently checks
boundary/warmup exclusion, duration-weighted FPS and percentile calculations.

Normal-map validation passed the Release build, complete C++ suite (353 legacy
individual tests and 52 default Catch cases after the render-target regression was added), the opt-in OpenGL/legacy mip upload
test (138 assertions), and normal-mip/specular/material/emission shader suites on
NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330. The gated full-quality material
fixture passed authored/companion maps, both animation frames, mip uniform binding,
held light insertion/removal and directional-light transitions with clean teardown.

## Baseline validation findings

The resolution gate rejected an initial quality run: its cloud-shadow prepass
left the driver's screen dimensions at the 256×256 shadow-map size. The main
pipeline then allocated scene buffers at that size. The prepass now restores the
window target, dimensions and viewport; screen output also takes its dimensions
from the immutable frame context. A C++ regression covers both initial output and
subsequent resizing. The corrected runtime reports a 1920×1080 opaque scene.
All final comparisons use the corrected binary; the rejected run is excluded.

The balanced preset retains contact-hardening shadows, SSAO, immediate colored
moving lights, local diffuse bounce, material shading, TAA, water reflections,
refraction/absorption and restrained bloom/exposure. Volumetric fog/clouds, cloud
shadows, caustics and camera blur are optional quality costs. Trials found the
fixed-filter shadow fallback slower in the forest, while worker-only moving light
gave little forest benefit and adds update latency. The preset therefore keeps
contact hardening and per-frame direct lighting. The 60 FPS outdoor budget remains
unmet in the initial trials; the repeated final table determines the measured
baseline, without adding further rendering features to this milestone.

Game-provided lighting still controls shadow/volume intensity. The fixture uses
shadow intensity 0.65 and volumetric strength 0.15 consistently across profiles.
CPU draw submission time includes any driver blocking; it is not isolated GPU
execution time.
