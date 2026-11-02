# Foliage transmission and grain highlights

These are the material additions for [milestone 6](graphics-milestone-6.md).
They preserve the existing color textures and cutout alpha. Minetest Game's
ordinary node groups supply defaults, with no authored maps required.

## Grass and leaves

`enable_translucent_foliage` enables bounded, colored thin-surface transmission.
The response uses the independent directional-light packet, local native sky
access and the shadow map's visibility before opaque-face self shadowing.
Cloud transmission attenuates it with the other explicit sunlight contributions.
Disabling shadows changes visibility availability, rather than removing the light
source. A covered, unlit surface cannot acquire light from the global sky tint.

The leaf sheet responds from either viewing side. Its orientation blends smoothly
near grazing incidence, avoiding a lighting pop when animated foliage or the
camera crosses the sheet's plane. The forward-scattering lobe and base-color tint
remain restrained. Transmission is composed in linear light after native-light
replacement, so artificial-light replacement does not erase this explicit sun
term. Alpha and texture cutouts remain controlled by the original node material.

Nodes in `leaves` receive transmission 0.35. Grass-like plant/mesh/nodebox nodes
receive 0.5; existing waving plant/leaf hints supply compatible defaults.
Classification does not depend on enabling waving animation or the selected
leaf draw style. Rooted plants apply transmission to the plant special tile,
while the base retains its own surface response.

A game can override the defaults with the existing synchronized node group
`shader_translucency`: zero disables the response, and 1–100 specifies its
percentage strength. This is an appearance hint, separate from node transparency
and gameplay light propagation.

## Sand and snow

`enable_material_sparkle` enables sparse, bounded grain highlights. Balanced and
quality presets enable it; the basic preset disables it. `sand` selects the sand
response; `snowy` selects snow. The latter is masked to pale upward-facing snow,
so snow-covered dirt keeps its brown side and bottom artwork. A rooted plant's
sand base can sparkle without assigning sand glints to its plant special tile.

Sand and snow have different grain densities, highlight widths, tints and bounded
strengths. The response follows incident directional light and local lamps. It
adds no self emission. Moving lights use their exact current incident direction;
placed lights and the worker fallback use a dominant receiving direction from
the existing six direct-light lobes. Back-facing lobes are excluded, and grain
energy is bounded by the receiving surface's direct irradiance. Mixed and
surface-adjusted probes remain an approximation. This introduces no extra atlas
or per-source static-light array. The material-shading master switch also
controls grain shading.

Grains are anchored in node coordinates. Cell hashing wraps with the camera
offset's period so origin rebasing preserves the pattern. Pixel derivatives
filter small grain disks and attenuate unresolved detail before it aliases.
Sampling happens before cutout discard and divergent visibility traversal;
local-light loops reuse that sample without taking derivatives inside the loop.

The optional group `shader_sparkle` overrides inference: zero disables sparkle,
one selects sand and two selects snow. No shader applies this response to ordinary
stone just because it is bright or rough.

## Verification

`python3 util/test_surface_materials.py` compiles the production helpers and full
node fragment composition. Positive and negative controls cover both foliage
faces, shadow enablement/strength, solid occlusion, local sky access, a grazing
camera sweep, distinct sparse grain responses, rebasing, distance filtering,
snow-covered dirt, directional/held lighting, alpha and darkness.

The C++ `[surface-material]` case checks synchronized group inference, overrides,
ordinary-node defaults and distinct shader cache identities. Scripted native
fixtures supplement numeric tests with real grass, leaves, sand and snow, and
placed/held lamp insertion and removal. See the milestone for the current
verification and performance checkpoint.
