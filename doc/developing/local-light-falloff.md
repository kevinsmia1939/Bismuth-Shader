# Smooth local-light falloff

Milestone 6A addresses the excessively bright patch beside a torch followed by a
steep brightness drop across the next ground blocks. The old local-light curve
used `max(distance², 1)` and a fade starting immediately at the source. Its
derivative changed abruptly at one node, and the early fade compressed useful
illumination into the nearest blocks.

Placed floor lamps and the worker fallback also had a geometry error. Their
upward-facing light lobe was evaluated at an air-probe center above the floor.
A low torch can be at or below that center, leaving the floor unlit beyond its
coincident probe even where light should reach it.

`voxel_light_soft_falloff` defaults to true. The new attenuation is
`max(0, 1 - (distance / 16)^4)^2 / (distance² + 4)`, with distance in nodes.
A two-node soft core reduces the near-source hotspot, the middle range retains
more light, and the finite 16-node window reaches zero with a zero derivative.
This is an appearance-oriented approximation; the core is broader than a torch's
visible flame. Native source intensity/color and visible emitter self illumination
retain their existing definitions.

The worker anchors a probe's adjacent exposed-face lobe to that face's
already-computed irradiance. It reuses the existing atlas and adds no visibility
rays, textures or rendering pass. Sunlight and GPU frame-direct lamps are
excluded from this baked term; reflected light still uses complete incident
light. Volume and object sampling remain coarse near surfaces.

The worker uses the same curve for placed sources, fallback moving lights and
incident light feeding diffuse bounce. The GPU uses it for per-frame moving
direct light, local material highlights and participating air/water lighting.
RGB transmission, wall occlusion and source-removal behavior stay independent
of the attenuation change. The native game light banks are unchanged.

Disable `voxel_light_soft_falloff` and restart to compare against the previous
curve and air-center sampling. This switch changes both worker and GPU transport.
Disabling voxel lighting
still provides the ordinary native rendering fallback.

## Numeric reproduction

The production shader, for a light 0.6 nodes above a flat floor with RGB emission
`(2, 1, 0.5)`, previously returned red irradiance about 1.85 directly below the
source and 0.10 two nodes away. Soft falloff reduces the near value to about 0.46,
with about 0.069 at two nodes. The ratio improves from 18.6:1 to 6.7:1. These are
linear irradiance samples before albedo and camera post-processing.

`python3 util/test_light_falloff.py` measures dense floor strips across node
boundaries and tests the actual old/new GPU curves, movement, overlapping lights,
source removal, occlusion and smooth finite-range behavior. It also checks the
production static/fallback atlas sampler with a known continuous input field.
The C++ `[falloff]` case separately inspects actual worker solves for both placed
and moving sources, their colors, bounded peak, finite range and legacy control.

`python3 util/test_floor_shading.py` exercises complete node fragments with a low
lamp, deliberately discontinuous native light banks, actual probe offsets,
direct/bounced light, removal, and fixed/adaptive exposure followed by production
tone mapping. Its old air-center control reproduces zero floor light two nodes
away; corrected static and frame-direct cases retain smooth gradients.

`test_dynamic_lighting.py`, `test_point_materials.py`, `test_native_emission.py`,
`test_voxel_fog.py` and `test_water_lighting.py` cover the affected production
transport/composition paths. The native cave replay includes noon with a bright
outdoor fog override, plus lamp insertion/removal controls. See
[milestone 6](graphics-milestone-6.md) for the current combined audit.
