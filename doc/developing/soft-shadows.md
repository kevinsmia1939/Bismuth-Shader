# Contact-hardening sunlight shadows

`enable_contact_hardening_shadows` adds blocker search and distance-dependent
filtering to node and mesh-object shadows. It requires dynamic shadows and a
nonzero `shadow_filters` setting. The quality preset enables it; default settings
retain the existing shadow filter. Changing the enable flag requires a restart.

The shader searches nearby shadow-map texels for casters in front of the receiver.
Their average separation in world units sets the penumbra radius:

`radius = blocker_receiver_separation * tan(light_angular_diameter / 2)`

Separation is reconstructed from the actual committed orthographic projection and
Z warp, rather than assuming the configured shadow draw distance equals the
light-frustum depth. Increasing the light angle widens the penumbra. Contact
shadows retain a half-texel antialiasing floor; zero light angle or zero filter
quality selects hard comparisons.

Luanti concentrates shadow-map resolution around the camera with a nonlinear XY
warp. The shader inverts that warp at the receiver, places search/filter disks in
the original light plane, then warps every sample back into the texture. This
keeps the footprint tied to world distance as the camera moves or the map
resolution changes. Receiver-plane depth gradients reduce false self-shadowing
on inclined surfaces; the existing caster/normal bias remains in use. Samples
outside the map contribute unoccluded light instead of repeating edge texels.

Opaque and colored transparent casters use the existing shadow-map format.
Transparent blocker weights account for their transmitted luminance; fully clear
texels do not hide opaque blockers behind them. Filtering keeps tint conditional
on actual shadow coverage, so a colored penumbra does not multiply its coverage
twice. The existing translucent-foliage depth smoothing is retained. This feature
adds no shadow render or render target and also works without post processing.

## Controls and cost

- `enable_contact_hardening_shadows`: optional blocker search; restart to change.
- `shadow_light_angle`: directional-light angular diameter in degrees, default
  0.53, range 0–10. Updates live.
- `shadow_blocker_search_distance`: maximum blocker/receiver separation in nodes,
  default 64, range 1–256. Updates live.

With this mode enabled, `shadow_light_angle` replaces the older
`shadow_soft_radius` control. `shadow_filters=1` uses 8 blocker and 16 filter
samples; quality 2 uses 16 and 32. A center tap helps preserve thin blockers;
remaining samples use a fixed Vogel disk in light space. The existing
`shadow_poisson_filter` choice continues to control the legacy filter when
contact hardening is disabled. No blockers skips the wider filter. Hard-shadow
mode skips both loops.

Finite search samples can miss small casters, especially with large search ranges.
The configured search distance also caps penumbra width for more distant casters.
Only the first opaque/transparent shadow layers are available; this is an
approximation of multiple colored sheets. Fixed disk sampling, shadow resolution,
map update intervals and the existing bias/interpolation can still produce
aliasing, transitions or separation artifacts. There are no ray-traced contact
shadows or cascades. GPU cost needs measurement on target scenes and hardware.

The light camera transports its previous up vector onto the new light plane.
This avoids the world-up singularity and basis flip as the sun crosses the zenith,
including the exact noon frame. A perpendicular fallback handles large custom
direction changes. The existing committed-frustum/map synchronization and fixed
light-space disk kernel remain in use; a camera turn does not randomize samples.

## Verification

`python3 util/test_soft_shadows.py` compiles the actual shared GLSL in a hidden GL
context and checks opaque/colored occlusion, penumbra growth with separation and
angle, world-scale invariance, warped-map footprints/inversion, finite search,
map borders, sloped receiver-plane correction, conditional tint, translucent
foliage smoothing and hard-shadow bypass. It runs all three filter
qualities with colored shadows on and off. `LUANTI_TEST_GLSL=120` selects legacy
GLSL instead of the default 330 core. No image capture or input events are used.
See `material-shading.md` for the verified Mesa llvmpipe environment.

`LUANTI_TEST_QUALITY=true util/test_voxel_lighting.sh` runs the combined renderer
with node/object receivers, water, RGB source removal and night/low-sun/noon/custom
lighting transitions. Optional `LUANTI_TEST_DRIVER=opengl`,
`LUANTI_TEST_AA=fsaa`, `LUANTI_TEST_STEREO=sidebyside`,
`LUANTI_TEST_SHADOW_COLOR=false` and `LUANTI_TEST_SHADOW_POISSON=false` select
compatibility paths. These checks establish shader/runtime correctness rather
than a visual-quality or frame-rate target.

In this workspace the Release build and complete C++ suite passed (352 individual
tests and 22 Catch cases). Numeric tests passed on NVIDIA with GLSL 120 and 330
core, and on Mesa llvmpipe with GLSL 330 core. Combined-renderer checks passed on
OpenGL 3/TAA and legacy OpenGL/4x MSAA, including colored shadows disabled and the
legacy grid-filter branch selected.
