# Semi-realistic graphics: milestone 6

Status: implementation and correctness validation complete. Smooth falloff,
foliage transmission, sand/snow grain shading and image-stability fixes pass
45 numeric suite/driver checks, the C++ suite, the 18-stage native audit and
three compatibility runs. Matched frame-time measurements are recorded in the
[results report](graphics-milestone-6-results/README.md). Keep the semi-realistic
style, readable pixel textures and existing texture-pack compatibility. Minetest Game is the
primary integration target.

Complete stages 6A–6C before the final stability audit, so the new shading is
included in that audit. The earlier milestone 4 lighting and milestone 5 material
reports describe their original verification checkpoints. They do not establish
completion of these additions.

## Completion checkpoint

| Stage | Result | Verification |
| --- | --- | --- |
| 6A | Soft attenuation and receiving-face correction for low lamps | Worker solves, dense floor strips, full node/exposure/tone composition and native lamp removal |
| 6B | Two-sided, colored foliage transmission with smooth grazing response | Full node cutouts/shadows, static/waving classification and native foliage replay |
| 6C | Separate filtered sand/snow grain responses | World anchoring, distance/view sweeps, daylight/local lamps, dark controls and temporal feedback |
| 6D | Chroma-reactive TAA, HDR preservation, black-preserving bloom and independent exposure meter | GPU feedback, 18 native stages, resize, stereo/MSAA and renderer fallbacks |

Balanced/quality presets enable the additions. For comparisons, restart after
setting `voxel_light_soft_falloff = false`, `enable_translucent_foliage = false`
or `enable_material_sparkle = false`. The basic preset provides the native
renderer fallback. These controls do not alter game node definitions or textures.

## 6A. Smooth torch and glowing-block light falloff

Correct the visible ground-lighting problem: the block beside a torch or glowing
block is excessively bright, followed by an abrupt brightness drop on the next
blocks. Cover placed torches, mese lamps, glowstone where the game provides it,
other node emitters and held lamps. Use native emission properties across games.

Trace the contribution from native baked light, voxel-field interpolation,
dynamic direct light, indirect light and exposure before tuning the attenuation.
Resolve block-boundary steps, overbright near-source response and any hard range
cutoff in the paths that cause them. Preserve emitter brightness, source colors,
occlusion and prompt updates when lights move or are removed.

Acceptance:

- A flat floor receives a smooth brightness gradient away from a fixed light,
  without conspicuous one-block rings, seams or a clipped patch beside the source.
- Moving a held light or shifting a placed light across a node boundary does not
  snap the illuminated ground between brightness levels.
- Overlapping lights blend smoothly; ordinary walls still block direct light.
- Source removal restores darkness. The daylight cave regression remains black
  where no light reaches the visible surfaces.

Verify controlled floor strips with dense numeric samples across node boundaries
and the light's range boundary. Compare individual lighting contributions and
the final image, at fixed exposure as well as automatic exposure. Exercise both
dynamic lighting and its supported fallback, then replay the native cave scenes.

## 6B. Translucent grass and leaves

Add a restrained thin-surface transmission response to grass and leaves. Sunlight
behind the foliage should produce softly lit blades and leaf surfaces. Account
for both face directions and distinguish foliage from ordinary opaque surfaces.
Provide sensible defaults for ordinary game textures; optional material controls
can refine the response without becoming a requirement for existing packs.

Acceptance:

- Backlit grass and leaves gain a soft, material-colored transmission response
  that changes continuously with light and viewing direction.
- Texture cutouts, silhouettes and shadows remain correct, including both sides
  of grass blades and supported leaf draw styles.
- Front-lit foliage remains readable, and animated foliage has no lighting pops
  or persistent temporal trails.
- Transmission follows incident light and visibility. Unlit foliage stays dark,
  and solid walls do not acquire the foliage response.

Check front/back illumination, shadowed foliage, moving grass/leaves and camera
movement through the forest. Test ordinary textures, optional material controls
and the effect-disabled fallback.

## 6C. Subtle sand and snow sparkle

Add sparse grain highlights to sand and snow. Tie the glints to stable surface
positions, incident illumination and view direction. Tune sand and snow
separately, with modest intensity and coverage that preserve the base textures.
Filter small or distant glints to control aliasing and retain restrained sparkle
under TAA. Expose an inexpensive disabled fallback.

Acceptance:

- Lit sand and snow show occasional small glints as the camera or light moves;
  the two materials have distinct, restrained responses.
- Grain positions remain attached to the surface, including across adjacent
  blocks. A stationary camera and light produce a stable result.
- Distant surfaces avoid widespread flicker, moire and excessive highlight
  shimmer; TAA does not leave persistent trails behind glints.
- Unlit sand and snow do not sparkle. Bloom and exposure do not turn glints into
  large glowing patches or wash out the terrain.

Extend the repeatable scenes with sand and snow patches under daylight, grazing
sunlight and a local lamp. Include dark controls, camera motion and several view
distances. Record temporal variation numerically alongside positive controls
that confirm the effect remains visible under illumination.

## 6D. Stabilize the combined image

Tune TAA, exposure, tone mapping and mild bloom with all three additions enabled.
Check camera movement, foliage, animated textures, resizing and underwater
transitions. Motion blur and depth of field remain optional.

Acceptance: no persistent trails, flashing exposure, obvious history smearing or
shader errors in the sunny forest, sunset river, dark cave and underwater scenes,
plus the foliage, falloff and sand/snow fixtures. Entering a cave must preserve
darkness without abruptly changing exposure; lamps must retain useful local
contrast. Water entry/exit must not flash or reuse stale reflection history.

## Validation and performance boundaries

Implementation notes: [smooth local light](local-light-falloff.md) and
[foliage/grain material response](surface-materials.md).

The combined pipeline now preserves HDR highlight separation until tone mapping.
Bloom reduction/reconstruction and output dithering preserve exact black; the
reduction kernel's four inner taps are symmetric. TAA compares chroma as well as
brightness, rejecting stale color from animated textures even when geometry and
brightness remain unchanged.
Exposure meters a linear input independently of bloom gain. Zero bloom gain and
disabled bloom retain metering data instead of introducing a zero denominator
or measuring an unexposed gamma-encoded image.
Client adaptation-rate limits (`auto_exposure_speed_dark_bright`, default 3/s;
`auto_exposure_speed_bright_dark`, default 1/s) prevent the game's fast default
rates from forcing immediate exposure changes. Slower authored rates remain in
effect. Games retain control of their metering range, including fixed exposure.
The adaptive native fixture explicitly authors a range to exercise these limits.

`benchmark_final_scene_log` adds optional scalar probes after TAA, exposure,
bloom and tone mapping. Its diagnostic output target, reduction/readback and
copy pass exist only when the option is set. No images are saved. The ordinary
`benchmark_scene_log` remains before those camera passes, allowing both stages
to be audited against the same runtime intervals.

The expanded native replay is invoked with:

```sh
python3 util/test_graphics_milestones.py /path/to/prepared-world \
  --output /tmp/graphics-milestone-6 \
  --texture-pack textures/bismuth-minetest-game \
  --daylight-cave --surface-materials --resize
```

The resize option builds a small SDL2/Linux test hook in the output directory
and loads it only into the disposable client. It calls SDL's window-size API on
that client's render thread, including under Wayland. It sends no keyboard,
pointer or focus events. Client acknowledgments and frame logs must show
all three requested sizes, including recovery to the original size. The surface
fixture also preserves a stopped `surface-prepared-world` for matched profiling;
`benchmark_graphics.py run --scenes surface_materials` selects that added scene.

Use fixed settings and repeatable fixtures. Preserve numeric GPU tests and
scripted runtime evidence, with screenshots and input-device automation excluded.
Re-run the existing darkness, lighting, material and water regressions affected
by each implementation change. Keep the user's playable world separate from
disposable test worlds.

Measure each addition's frame-time cost at the baseline resolution and view
distance on the GTX 1650 Ti. Include enabled/disabled comparisons and settings
for an affordable fallback. The complete 1080p/60 FPS target, final optimization,
preset settings and delivery remain milestone 7; this plan does not establish
that budget as achieved.
