# Milestone 6: smooth local light, foliage, grain and image stability

Stages 6A–6D are implemented and verified with Minetest Game. The work targets
restrained semi-realistic shading with the existing color textures. Final preset
optimization and the complete 1080p/60 FPS budget remain milestone 7.

The local-light change combines a two-node soft attenuation core with receiving
face samples for low lamps. Previously, a floor's air-center probe could sit above
a torch and reject its upward-facing contribution entirely. The corrected worker
reuses existing face evaluations and the existing atlas. The disabled control
restores both the old curve and air-center sampling.

Grass and leaves receive bounded thin-sheet sunlight transmission. Sand and snow
receive separately tuned, sparse, world-anchored grain highlights, filtered by
pixel footprint. Existing node groups infer the materials, with optional group
overrides. These effects require incident illumination; ordinary walls and unlit
surfaces do not gain self emission.

The combined audit also fixed premature HDR clipping, positive bloom RGB floors,
a repeated bloom tap and exposure metering coupled to bloom gain. TAA's chroma
rejection reduces the controlled equal-brightness animation's four-frame stale
color energy from 0.6561 to 0.03671. Client exposure-rate caps preserve slower
rates authored by games.

## Verification

- Release build; 353 legacy tests in 50 modules, 57 default Catch cases with
  224,215 assertions, and 110 assertions exercising actual GL3/legacy blending.
- 45 numeric suite/driver combinations: 15 suites on NVIDIA GLSL 330, NVIDIA
  GLSL 120 and Mesa software GLSL 330. They cover full floor composition, native
  emission, shadows, materials, temporal feedback, darkness and water/air light.
- An 18-stage native terrain replay with pre-camera and final-output scalar
  probes: forest movement, sunset, reflections, water entry/exit, cave lamps and
  native grass/leaves/sand/snow. All six unlit/removal stages return exact RGB
  zero after camera effects. Placed/held cave removal clears within 161/103 ms.
- Three acknowledged SDL window resizes (640×360 → 800×450 → 720×480 → 640×360),
  plus legacy OpenGL/4x MSAA/side-by-side stereo, simple and opaque leaf styles,
  worker direct-light fallback, exposure without bloom and no-postprocessing
  configurations. No shader/GL errors occurred in these runs.

The 51 final checks and their raw logs are in `validation/`. `native/` contains
launch/saved settings, stage results, frame and scalar CSVs, environment hashes
and resize acknowledgments. Logs/CSVs are gzip-compressed without timestamps.
No screenshots, keyboard events or pointer events were generated. The resize
hook calls SDL's own window-size API inside the disposable client only.

## Matched performance

| Effect | Scene | Enabled FPS | Control FPS | Added mean ms |
| --- | --- | ---: | ---: | ---: |
| falloff | glowing_cave | 39.0 | 38.7 | -0.222 |
| foliage | forest | 47.6 | 50.1 | +1.037 |
| grain | surface_materials | 70.4 | 88.2 | +2.856 |
| camera | forest | 43.7 | 44.7 | +0.509 |
| camera | sunset_river | 37.9 | 41.9 | +2.496 |
| camera | glowing_cave | 35.3 | 38.4 | +2.263 |
| camera | underwater | 41.2 | 47.7 | +3.338 |

The grain-enabled repeats ranged from 11.83 to 17.73 ms (84.5 to 56.4 FPS),
versus 11.12 to 11.57 ms disabled. This variation limits the precision of the
reported grain cost. Foliage-enabled repeats were 20.15 and 21.94 ms. The
small negative falloff delta is within variation, rather than evidence of a speedup.

Measurements use 1920×1080, view distance 96, FOV 70 and the balanced preset with
the optional Minetest Game ORM pack. Conditions run ON/OFF/OFF/ON, with two repeats
per condition, eight seconds of settling and twelve seconds of measurement per
scene. The new sand/snow/foliage fixture supplies the grain scene; the other four
scenes use the unchanged milestone 5 input terrain. Scalar diagnostic readback is
disabled during timings. Shader compilation occurs before settling/measurement.

These are whole-client delivered frame times, including submission and waiting,
not isolated GPU pass timers. Camera costs compare the entire TAA, exposure,
bloom, tone mapping and vignette path with that path disabled; they do not isolate
the arithmetic cost of the stability fixes. Small or negative deltas can be run
variation. GPU clocks and temperatures were not held constant; each run preserves
its endpoint GPU state. Raw frames, both configuration files and per-run metadata
are under `timings/`; repeat means and p95 ranges are in `timings/summary.json`.

## Reproduction and limits

See the [milestone scope](../graphics-milestone-6.md),
[falloff implementation](../local-light-falloff.md) and
[surface material controls](../surface-materials.md). The existing prepared-world
procedure is in [milestone 1](../graphics-milestone-1.md); use Minetest Game for
this checkpoint. The input world and added surface world remain local, identified
by `provenance.json`, the native environment file and timing plan. Worlds, player
authentication data, binaries and images are excluded from this archive.

```sh
# Actual native scenes, with disposable world copies and scalar readback only:
SDL_VIDEODRIVER=wayland python3 util/test_graphics_milestones.py /path/to/prepared-world \
  --output /tmp/bismuth-native --texture-pack textures/bismuth-minetest-game \
  --daylight-cave --surface-materials --resize
# Sequential matched timings, after other GPU jobs have stopped:
SDL_VIDEODRIVER=wayland python3 util/benchmark_milestone_6.py /path/to/prepared-world \
  /tmp/bismuth-native/surface-prepared-world --output /tmp/bismuth-costs
```

The archived validation orchestrator records the exact commands used on this
machine, including driver environment overrides. Its absolute scratch paths must
be adapted for another checkout. All tested source fingerprints are in
`source-sha256.json`; `sha256.json` covers the archived files. The tested binary
was built from the listed base commit plus this change, so its version string
precedes the final commit while its renderer/shader fingerprints identify the
verified implementation.

Limits remain: six-lobe voxel transport and static grain directions are local
approximations; camera TAA has no object motion vectors. Scalar scene probes
sample the scene and cannot establish every pixel's appearance. Controlled full
node shader tests cover localized falloff, cutouts, grazing transmission and
sparkle/temporal behavior. Desktop NVIDIA GL3/legacy and Mesa software GL were
exercised; this is not a hardware-wide or GLES verification claim. Minetest Game
supplies mese lamps and torches rather than a glowstone node; emission uses the
game's native node properties, and previous VoxeLibre reports remain historical.

Affordable controls are `enable_material_sparkle = false`,
`enable_translucent_foliage = false`, or the basic preset. Restart after changing
pipeline effects. The final 60 FPS preset and broader optimization remain open.
