# Milestone 5: measured material response

Minetest Game is the primary integration target. These runs use fresh native
terrain with seed 13371337 and the optional Bismuth ORM companions. Earlier
VoxeLibre timings describe different terrain and are not a direct comparison.

The Release build, 353 legacy tests, 54 default Catch cases, actual GL 3/legacy
mip uploads, 24 numeric suite/driver combinations and four runtime configurations
passed. Every runtime material state has at least two completed-client frame
checkpoints. The eleven-stage native replay passed source, medium, brightness
and removal checks. No screenshots or input-device events were generated.

| Native scene | Materials enabled FPS | Disabled FPS | Added whole-frame mean ms |
| --- | ---: | ---: | ---: |
| forest | 43.4 | 43.0 | -0.24 |
| sunset_river | 41.0 | 44.8 | +2.08 |
| glowing_cave | 33.9 | 38.3 | +3.41 |
| underwater | 44.4 | 48.0 | +1.70 |

Two runs per condition in enabled/disabled/disabled/enabled order. Each scene
has 12 seconds of settling and 12 seconds of measurement at 1920×1080, FOV 70
and view distance 96. The control changes only material shading; both use the
same frozen terrain, balanced effects and texture-pack setting. Scalar scene
readback is disabled during timings. The NVIDIA shader disk cache is enabled
for all timing conditions; compilation/settling are outside measured windows.

These are whole-client frame-delivery measurements, including submission and
waiting, rather than isolated GPU pass timers. Two repeats still have system
and worker variation. The small negative forest difference is within that
variation. Enabled cave repeats measured 36.1 and 31.7 FPS.
Run endpoint GPU temperatures ranged from 56 to 83 C;
clocks were not held constant. Treat the added
times as approximate configuration costs. The final preset/performance budget
remains milestone 7. None of these enabled scene averages meets 60 FPS.

Raw CSV/log bytes are gzip-compressed. Launch settings and settings saved at
shutdown are preserved separately. Source/binary/game/pack hashes and actual
driver names identify the tested state. The native scalar probes do not inspect
every pixel; controlled GLSL patterns cover normal/roughness minification.

See [scope and reproduction](../graphics-milestone-5.md) for acceptance criteria
and commands. The stopped input world remains local; terrain-source.json records
its fingerprint and the Minetest Game checkout revision.
