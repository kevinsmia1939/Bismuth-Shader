# Daylight cave darkness regression

The unlit Minetest Game cave measured **RGB (0, 0, 0)** at noon while an explicit
bright outdoor sky/fog override remained active. The same held after removing
placed and held light sources. Mese lamps and torches still illuminated terrain;
the native replay passed all eleven stages and source/removal/color checks.

The production-shader reproduction previously returned about
`(0.093, 0.124, 0.155)` for an unlit mapped stone fixture, and the full bright
fog tint at the fog limit. Both now return zero RGB. `reproduction.json`
preserves exact numeric values and before/after node-shader hashes.

Validation passed:

- Release build; 353 legacy tests and 54 default Catch cases.
- Actual OpenGL 3 and legacy draws to color, geometry and emission targets:
  110 assertions verify independent metadata blending and state restoration.
- 33 numeric suite/driver combinations on NVIDIA GLSL 330/120 and Mesa GLSL 330.
- Native Minetest Game replay with noon, bright sky/fog and local zero-light gates.
- Legacy OpenGL with 4x MSAA/stereo, and a separate emission-mask configuration
  without a surface buffer. Every runtime phase waited for completed client frames.

The source fingerprints and native environment identify the tested executable,
shader sources, game adapter, settings and material pack. Raw CSV/log bytes and
the engine-formatted scene manifest are gzip-compressed without rewriting them.
`native/scene.csv.gz` contains only scalar scene probes, not captured images.

See [implementation and reproduction](../dark-caves.md). These checks address
unlit-surface sky leakage and the affected render paths; they do not mark the
remaining combined-image or performance milestones complete.
