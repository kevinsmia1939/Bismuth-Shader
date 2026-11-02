# Milestones 2–4: validation and lighting cost

CPU: AMD Ryzen 5 4600H with Radeon Graphics. GPU/driver: NVIDIA GeForce GTX 1650 Ti, 580.196.07.
Native VoxeLibre replay: eleven phases at 640×360 and a 30 FPS cap, with scalar scene readback.
Timing comparison: 1920×1080, view distance 96, FOV 70°, VSync off, 1000 FPS cap; no readback or progress logging.
Both timing conditions use the same binary, shaders, preset and frozen terrain. The control overrides only `enable_voxel_lighting=false`.
Order: balanced, control, control, balanced. Each scene settles for 12 seconds and samples for 12 seconds.
Startup/compilation and incomplete/spanning frames are excluded. Whole-client timing includes the local server, driver and presentation.

| Scene | Balanced FPS (range) | Control FPS (range) | Added mean frame ms |
| --- | ---: | ---: | ---: |
| forest | 41.8 (41.17–42.50) | 52.2 (52.18–52.24) | +4.75 |
| sunset_river | 40.5 (39.96–41.05) | 48.1 (47.47–48.80) | +3.92 |
| glowing_cave | 65.9 (65.79–65.97) | 97.5 (95.77–99.25) | +4.92 |
| underwater | 51.0 (48.76–53.17) | 60.6 (58.94–62.27) | +3.12 |

FPS combines frame counts and sampled durations, not instantaneous FPS. The cost difference covers the entire local-light path (worker, direct lights and bounce), not diffuse GI alone or isolated GPU execution. Run-to-run variation remains visible in the ranges.

| Scene | Condition | Median ms range | p95 ms range | p99 ms range |
| --- | --- | ---: | ---: | ---: |
| forest | balanced | 23.03–23.58 | 27.26–27.84 | 29.42–29.98 |
| forest | control | 19.08–19.10 | 20.85–20.99 | 21.72–21.87 |
| sunset_river | balanced | 23.92–24.82 | 27.97–28.91 | 29.33–30.59 |
| sunset_river | control | 20.47–21.02 | 22.41–22.84 | 23.17–23.41 |
| glowing_cave | balanced | 14.65–14.74 | 18.48–18.58 | 20.57–20.77 |
| glowing_cave | control | 10.05–10.30 | 11.69–11.85 | 12.74–12.94 |
| underwater | balanced | 18.72–19.78 | 22.50–24.70 | 24.00–27.35 |
| underwater | control | 16.12–16.79 | 18.14–18.33 | 19.46–19.62 |

The proposed full-renderer budget is 60 FPS with p95 ≤22.2 ms. Its final preset/performance gate belongs to milestone 7.

- forest: misses the proposed budget.
- sunset_river: misses the proposed budget.
- glowing_cave: meets the proposed budget.
- underwater: misses the proposed budget.

## Native transition checks

Statistics sample a fixed 16×9 grid of the composed scene before TAA/exposure. Only mean linear RGB and sampled peak luminance leave the GPU. No images or input-device events are produced.
The replay requires real frame coverage, completed-client warmup, correct source/medium states, darker caves, warm lamp brightening/removal and no frame-to-frame sampled mean-luminance jump ≥0.1 linear white. Removed lamps must return the sampled scene to darkness for three consecutive frames within one second. These scalar probes detect broad brightness failures; per-pixel numeric shader tests cover reflection edges, shorelines and the TIR limit. They do not establish visual parity with another shader pack.

| Phase | Completed frames | Mean luminance | Largest adjacent-sample luminance change |
| --- | ---: | ---: | ---: |
| forest_movement | 170 | 0.089346 | 0.021147 |
| sunset_transition | 180 | 0.038212 | 0.008390 |
| river_reflections | 179 | 0.034138 | 0.002532 |
| water_entry | 179 | 0.018589 | 0.004590 |
| underwater_lamp | 179 | 0.039307 | 0.008265 |
| water_exit | 180 | 0.019743 | 0.006712 |
| cave_dark | 179 | 0.000006 | 0.000001 |
| cave_placed | 179 | 0.014729 | 0.000690 |
| cave_removed | 179 | 0.000005 | 0.000000 |
| held_movement | 179 | 0.007728 | 0.000720 |
| held_removed | 180 | 0.000005 | 0.000000 |

Placed-glowstone removal reached three consecutive dark samples in 289.2 ms; held-torch removal took 185.6 ms.

The controlled replay covers forest rotation past the shadow-frustum recapture threshold, sunset, river motion, entry/exit, underwater torch, placed glowstone and held-lamp removal.
The Release build and C++ suite passed. [Validation logs](validation) include production-shader numeric checks on NVIDIA GLSL 120/330 and Mesa llvmpipe GLSL 330.
Exact launch/saved configs, raw CSV/logs and per-run records are in [raw](raw). Hardware, binary/shader/source hashes and protocol are in [environment.json](environment.json).
The initial [Milestone 1 baseline](../graphics-baseline/README.md) predates these changes. Interrupted earlier runs are excluded.

Reproduce the replay with `util/test_graphics_milestones.py`; prepare/measure terrain with `util/benchmark_graphics.py`. Export this report with `util/report_graphics_milestones.py --replay ... --timings ... --validation-prefix ... --destination ...`.
