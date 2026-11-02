# Semi-realistic graphics: milestone 5

Scope: finish material response with optional normal and roughness/metallic maps,
sensible defaults for ordinary textures, restrained highlights and preserved
emission. Resolve mip filtering. Keep existing texture packs usable.

Acceptance: stone looks mostly matte, metals reflect more strongly, glowing
blocks stay bright, and distant textured surfaces avoid excessive highlight
shimmer. Verify the forest, sunset river, glowing cave and underwater scenes.
The overall 1080p/60 FPS preset budget remains milestone 7.

## Implementation

The existing node material pipeline handles explicit normal/ORM fields, local
texture-pack companions, tangent-space orientation, synchronized animation,
dielectric/conductor GGX and preserved native emission. Unmapped textures retain
the rough dielectric fallback. See [authoring and limits](material-shading.md).

Material textures now have distinct color/normal/ORM cache identities. Normal
mips retain mean directions and normal variance. ORM mips average perceptual
roughness to the fourth power before re-encoding, preserving GGX width rather
than averaging it as color. Occlusion/metallic channels remain linear. CPU
moments remain unquantized between levels, including odd-sized images and driver
reductions. Reloads rebuild every mip; each animation frame has its own chain.
No sampler or rendering pass is added. Original color textures stay intact.

The optional [Minetest Game pack](../../textures/bismuth-minetest-game/README.md) provides
matte stone/cobble and moderately rough metal hints while retaining the game's
color artwork. Mese lamps and mese blocks remain dielectric emitters. Other
textures use the existing fallback. Authored maps stay optional.

## Verification

Verification is complete in the tested desktop paths. The
[results and raw evidence](graphics-milestone-5-results/README.md) cover the
Release build, 353 legacy tests and 54 default Catch cases, real mip uploads on
OpenGL 3/legacy, 24 numeric suite/driver combinations, four runtime configurations,
eleven native Minetest Game phases and two 1080p runs per material condition.

The runtime material fixture waits for completed client frame checkpoints at
each stage. Shader compilation cannot silently skip sky-source, held-lamp,
removal or unmapped-replacement states. Screenshots and input-device automation
are excluded from this workflow.

| Requirement | Evidence |
| --- | --- |
| Optional normal/roughness/metallic maps | C++ serialization, identity and animation tests; production GLSL orientation/channel/GGX tests; explicit, companion and animated bindings in the real client |
| Matte stone and stronger restrained metals | Rough dielectric fallback, conservative stone/metal hints, actual shipped-map byte tests and finite GGX peaks; native ORM binding in Minetest Game |
| Glowing blocks retain emission | Full-fragment emission tests including metallic emitters and stale worker markers; native mese lamp brightening and removal, with measured color agreement |
| Stable distant textures | Unquantized normal/roughness moments, odd-size/reduction/reload tests, real driver mip uploads and production minification/GGX tests. Moving subpixel normal-pattern highlight variation fell from about 15 HDR units to zero in the controlled test |
| Existing textures remain usable | Independent data caches preserve source color/alpha, unmapped defaults and replacement, cutout/animated assets, legacy stereo/MSAA, forward/base-only and disabled-material paths |
| Four native scenes and measured cost | Coniferous forest, sunset river, stone cave and underwater replay; actual composed-scene probes and repeated enabled/disabled 1080p frame logs. None meets the final 60 FPS target yet |

The Minetest Game checkout used was `9e895af6e9feb98332fa1a778001442f5669bc20`.
Fresh v7 terrain uses seed `13371337`. The playable local copy is
`worlds/bismuth-minetest-game`; its real-client smoke check verifies native
inventory items, creative mode, forest spawn and normal movement. The existing
VoxeLibre world is preserved separately.

Core reproduction commands:

```sh
cmake --build build -j4
bin/luanti --run-unittests
bin/luanti --run-tests '[normal-mips],[material-mips]'
python3 util/test_material_maps.py
python3 util/test_specular_filter.py
python3 util/test_normal_mipmaps.py
python3 util/test_orm_mipmaps.py
python3 util/test_point_materials.py
python3 util/test_native_emission.py
python3 util/test_surface_directional.py
LUANTI_TEST_DYNAMIC_DIRECT=true LUANTI_TEST_DIRECTIONAL=true bash util/test_material_shading.sh
python3 util/test_graphics_milestones.py /path/to/prepared-world --output /tmp/material-native --texture-pack textures/bismuth-minetest-game
```

For numeric legacy GL set `LUANTI_TEST_GLSL=120`. For Mesa set
`SDL_VIDEODRIVER=offscreen`,
`__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json` and
`LIBGL_ALWAYS_SOFTWARE=true`. Runtime fixture switches support legacy OpenGL,
stereo/MSAA, forward rendering, disabled mipmaps/material shading and the
asynchronous direct-light fallback; see `util/test_material_shading.sh`.

## Approximation limits

This remains a semi-realistic forward material pipeline. Normal variance and
roughness moments approximate an isotropic pixel footprint; trilinear samples
interpolate encoded values. Small lights, mixed metallic/dielectric footprints
and visibility edges are not exactly integrated. The sky/fog environment is an
approximation rather than a prefiltered reflection probe. Native baked diffuse
and self emission are retained together on emissive nodes. General entity maps,
parallax and physically calibrated emission are outside this milestone.
