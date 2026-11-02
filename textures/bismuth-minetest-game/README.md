# Optional Minetest Game materials

This small pack supplies only constant ORM data maps. It keeps the active game's
or texture pack's color artwork, with matte stone/cobble, moderately rough steel,
gold and copper, and dielectric glowing blocks. Other tiles retain the renderer's
rough dielectric defaults. These are material hints, not automatic recognition
of arbitrary texture names, ores, oxidized metals or texture-pack contents.

Select this pack in the client or set `texture_path` to this directory's absolute
path in your configuration. Enable `enable_material_shading`. For another color
pack, place these companions in that pack, adjusting roughness/metallic as needed.
Games' explicit material names take priority over automatic companions.

R is 255 (unoccluded); G is perceptual roughness; B is the metallic fraction.
The exact G/B bytes are:

| Texture | Roughness | Metallic |
| --- | ---: | ---: |
| default_stone | 230 | 0 |
| default_cobble | 240 | 0 |
| default_steel_block | 107 | 255 |
| default_gold_block | 87 | 255 |
| default_copper_block | 122 | 255 |
| default_meselamp | 217 | 0 |
| default_mese_block | 204 | 0 |

Divide by 255 for shader values. These original data maps are licensed under
LGPL-2.1-or-later. Reproduce their exact bytes with
`python3 util/generate_minetest_materials.py` from the repository.
