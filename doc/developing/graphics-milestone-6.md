# Semi-realistic graphics: milestone 6

Status: planned. The new appearance requirements and the combined-image audit
are pending. Keep the semi-realistic style, readable pixel textures and existing
texture-pack compatibility. Minetest Game is the primary integration target.

Complete stages 6A–6C before the final stability audit, so the new shading is
included in that audit. The earlier milestone 4 lighting and milestone 5 material
reports describe their original verification checkpoints. They do not establish
completion of these additions.

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
