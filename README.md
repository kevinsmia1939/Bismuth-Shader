# Bismuth Shader

Bismuth Shader is a Luanti renderer fork aiming for a semi-realistic look inspired
by Minecraft shader packs. The focus is richer sunlight, atmosphere, water and
colored lighting while keeping the block shapes and pixel textures readable.

The work spans GLSL shaders, the client rendering pipeline and the bundled
Irrlicht renderer. [Minetest Game](https://github.com/luanti-org/minetest_game) is
the main integration target. Ordinary game
textures should work well, with optional material maps providing more control.

Rendering features already in the tree include:

- Soft sunlight shadows, smooth daylight transitions, distance haze and shadowed
  volumetric fog. Volumetric clouds are optional.
- Waving water with Fresnel reflections, screen-space reflections and sky
  fallback, refraction and underwater absorption. Caustics are optional.
- Colored light from placed glowing blocks and held lamps, with voxel visibility
  and local approximate diffuse bounce.
- Optional normal and roughness/metallic maps, rough defaults for unmapped
  textures, preserved emission and normal/roughness mip filtering.
- TAA, SSAO, exposure, tone mapping and bloom. Motion blur and depth of field
  remain optional.

This is work in progress. The implementations need further combined-image tuning,
compatibility checks and profiling before a finished preset can be delivered.

The project follows these milestones:

| Milestone | Intended result | Current status |
| --- | --- | --- |
| 1. Baseline and budget | Repeatable forest, sunset river, glowing cave and underwater scenes | Baseline recorded |
| 2. Sunlight and atmosphere | Stable soft shadows, darker interiors, smooth daylight and restrained fog/light shafts | Implemented and checked in the reference scenes |
| 3. Water appearance | Reflections that blend into fallback, convincing refraction and smooth shorelines/entry/exit | Implemented and checked in the reference scenes |
| 4. Colored lighting and indirect light | Responsive lamps, wall occlusion and subtle local color bounce | Implemented; smoother ground-light falloff is a milestone 6 follow-up |
| 5. Material response | Matte ordinary surfaces, optional authored maps, restrained highlights and stable distant textures | Implemented and checked in Minetest Game; material cost measured |
| 6. Lighting, foliage and image stability | Smooth lamp falloff, translucent grass/leaves, restrained sand/snow sparkle and stable TAA/exposure/bloom | New appearance work and combined audit pending |
| 7. Usable preset | A measured balance of appearance, performance and a straightforward fallback | Candidate presets available; final budget pending |

[Milestone 6](doc/developing/graphics-milestone-6.md) starts with smoother ground
lighting around torches, mese lamps, glowstone and other emitters. It then adds
light transmission through grass and leaves, subtle sand/snow sparkle, and the
combined-image audit. Unlit caves must remain dark throughout these changes.

The performance target is **1080p at 60 FPS on a GTX 1650 Ti**, subject to
profiling. The historical VoxeLibre Milestone 1 balanced baseline achieved about 41 FPS in
the forest and river, 67 FPS in the cave and 47 FPS underwater. Those measurements
precede the latest changes; the current renderer has not been re-benchmarked
completely. See the [baseline report](doc/developing/graphics-baseline/README.md)
for hardware, settings, frame times and raw data.

The historical VoxeLibre [milestones 2–4 results](doc/developing/graphics-milestones-2-4-results/README.md)
include the native replay, brightness/lamp-response checks and repeated 1080p
timings. Balanced averages were about 42 FPS in the forest, 41 FPS at the river,
66 FPS in the cave and 51 FPS underwater. The measured local-light path costs
3.1–4.9 ms per frame; the complete-renderer performance target remains open for
milestone 7. The
[milestone notes](doc/developing/graphics-milestones-2-4.md) record the changes,
acceptance criteria and verification checkpoint.

[Milestone 5](doc/developing/graphics-milestone-5.md) finishes material mip
filtering and adds an optional
[Minetest Game material pack](textures/bismuth-minetest-game/README.md) that keeps
the existing color artwork. Its [results](doc/developing/graphics-milestone-5-results/README.md)
include actual mip uploads, numeric shimmer checks, native terrain replay and
repeated 1080p timings. Enabled averages are about 43 FPS in the forest, 41 FPS
at the river, 34 FPS in the cave and 44 FPS underwater. These Minetest Game
scenes differ from the historical VoxeLibre scenes. The 60 FPS preset target
remains open for milestone 7.

To try the renderer, install the dependencies from the existing
[build documentation](doc/compiling/README.md), then build this checkout:

```sh
cmake -S . -B build -DRUN_IN_PLACE=TRUE -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
./bin/luanti --config misc/graphics-balanced.conf
```

Install Minetest Game separately through the content browser or your usual game
installation method. The advanced pipeline targets desktop OpenGL; OpenGL 3 is
the primary tested renderer. Games retain control of shadow and volumetric-light
intensity through their lighting settings.

Three configurations are available:

- [Balanced](misc/graphics-balanced.conf): the working semi-realistic candidate,
  with local lighting, soft shadows, reflective/refractive water and restrained
  post-processing.
- [Quality](misc/graphics-quality.conf): a more expensive configuration for
  exercising optional effects, including volumetric clouds and caustics.
- [Basic](misc/graphics-basic.conf): native rendering with the optional effects
  disabled, for comparison and fallback.

Use the chosen file with `--config`, or merge its settings into your own
configuration. Restart the client after changing pipeline effects.

Validation uses C++ tests, numeric GPU checks and scripted native terrain
replays. Start with `./bin/luanti --run-unittests`; reproduction commands and
renderer details are in the [milestone notes](doc/developing/graphics-milestones-2-4.md),
[baseline procedure](doc/developing/graphics-milestone-1.md) and
[graphics documentation](doc/developing/scene-lighting.md).

Bismuth builds on [Luanti](https://github.com/luanti-org/luanti). Luanti's source
license remains LGPL-2.1-or-later; media and third-party components retain their
respective licenses. See [LICENSE.txt](LICENSE.txt) and source file notices.

Copyright (C) 2010-2026 Perttu Ahola <celeron55@gmail.com>
and contributors (see source file comments and the version control log).
