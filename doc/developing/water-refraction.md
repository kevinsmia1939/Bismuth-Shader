# Water refraction and absorption

Screen-edge refraction fades crossfade straight and refracted **linear radiance**,
not their texture coordinates. Interpolating UVs could sample unrelated terrain
between two valid endpoints and introduce a shoreline streak. Numeric regression
checks include an intervening colored texture strip and valid endpoint samples.
The last march segment is clipped to the usable screen area before rejection,
and confidence tends to zero at that boundary. Genuine positive shallow-water
thickness retains transmission down to depth precision, approaching the clear
background continuously instead of switching to native tint at a fixed tolerance.

`enable_water_refraction` adds transmission through transparent liquid surfaces.
It requires post processing and desktop OpenGL 3 with the floating-point surface
capabilities. The quality preset enables it. Default settings leave it disabled.
Opaque/alpha-clipped liquids retain native rendering. The liquid material type,
including flowing-liquid special tiles, determines eligibility rather than node
names. Games keep control of liquid texture color, opacity, waving and lighting.

## Opaque scene capture

The Irrlicht scene manager accepts an optional callback after sky/opaque drawing
and before any transparent/effect/GUI nodes. Draw3D uses that callback to copy
scene color and depth into two separate textures. With MSAA, the copy resolves
both into single-sample textures. It restores the scene framebuffer/viewport before
transparent rendering continues. No second geometry render is required.

Each eye owns its capture textures. Captures use the current projection jitter,
render scale and dimensions, and resize with the pipeline buffers. Published
capture pointers are cleared before and after each scene draw. They are only
published after the current opaque copy, preventing previous-frame/other-eye input.
The capture is disabled inside an opaque node. Liquid cameras retain native
rendering unless valid loaded-water geometry enables the underwater interfaces
described in `water-volume.md`.

During transparent liquid drawing, slot 1 holds opaque color and slot 2 opaque
depth. Slot 0 keeps the animated liquid texture and slot 3 the directional shadow
map. A material-binding guard allows refraction only when both captured textures
are bound. Crack overlays and voxel-atlas sampling are bypassed for that water
material; other world materials, entities, inventory and wield rendering keep
their existing bindings. Temporary bindings are removed from map mesh materials.
Water continues to receive native map/directional lighting; colored objects and
terrain behind it are included through the opaque color capture.

## Shader transport

The node shader bends the incident view ray with Snell refraction at an air/water
index ratio of 1/1.333. Wave normals use absolute world coordinates so a floating
camera-origin change does not shift their phase. Thirty-two quadratically
spaced steps trace against opaque depth, followed by five bisection steps at a
possible intersection. Foreground hits, depth discontinuities and off-screen
samples are rejected. Edge confidence fades back to straight transmission. Missing
hits retain the original opaque background and a capped depth estimate.

Water path length controls Beer–Lambert transmission in linear RGB. The default
extinction ratios absorb red most strongly and blue least strongly. Liquid texture
alpha scales turbidity, while the game's lit liquid texture supplies the limiting
in-scattering color. As depth increases, the background approaches that color.
Native sun highlights remain a separate surface contribution. Reflection/Fresnel,
atmospheric fog, SSAO, TAA, exposure and bloom remain downstream.

Surface sun/moon glints consume the same independent directional source as
material highlights. Disabling shadows or fading outside the shadow map no
longer removes the glint. Valid geometry shadows and cloud transmission still
attenuate it, including RGB shadow tint. Sky visibility, horizon fade, custom
direction and the native natural/artificial light ratio control the source.
The legacy sky-reflection fallback only reduces the natural-lit portion of
water color, preserving artificial illumination. Zero-length views skip the
view-dependent contribution. This retains the existing artistic glint profile;
it is not a calibrated water BRDF.

A successful transmission sample outputs alpha one because it already contains
the opaque background; ordinary alpha blending would count that background twice.
Rejected or unbound samples retain native color and alpha. The fixed far-distance
map fog still applies to hide the loaded-world boundary.

## Controls and limitations

- `enable_water_refraction`: restart to change the capture/shader pipeline.
- `water_refraction_strength`: 0–1, default 1; zero straightens the ray.
- `water_absorption_strength`: 0–4, default 1; zero removes absorption/scatter.
- `water_refraction_distance`: 1–64 nodes, default 32; caps trace/path length.

Numeric controls update live. The feature allocates one scene-size color texture
and one scene-size depth texture. Each water fragment can issue 37 depth lookups;
non-water fragments do not trace. Cost grows with visible water area and render
scale. No frame-rate guarantee follows from correct rendering/compilation.

This captures opaque geometry and sky. Transparent entities, particles, clouds,
other translucent nodes and nested liquid layers are not represented behind the
water. Without loaded-water geometry, the path estimate assumes the space between
the front surface and opaque receiver is liquid; thin waterfalls, rear liquid
exits and partially filled volumes can over-attenuate. `enable_water_volume`
counts actual represented liquid segments and supplies underwater absorption and
wave-refracted caustics; see `water-volume.md`. Missing screen-space geometry cannot be reconstructed.
This is a single-interface approximation without multiple internal reflections.
Underwater views retain native liquid fog when loaded-water transport is disabled
or unavailable. Source/flow corner triangles and wave displacement are now shared
with the optical volume; see `water-volume.md`. Wider coverage, mixed liquid boundaries and multiple
transparent layers remain limitations of the advanced-water implementation.

## Verification

`python3 util/test_water_refraction.py` compiles the actual shared GLSL in a hidden
SDL/OpenGL context. It compares float pixel values with analytic Beer–Lambert
transmission, tests RGB attenuation, opacity/turbidity, scattered color, zero
absorption, capped/deep paths, foreground rejection, unbound-material guards,
straight rays, analytic Snell intersections, foreground silhouettes and two-sided
normal orientation. It sends no input
events and captures no images. The test prints its actual renderer; see
`material-shading.md` for the verified Mesa offscreen environment on this desktop.
`util/test_surface_directional.py` additionally compiles the full node fragment
for water with and without shadow support, checking glints, shadow fades and
native artificial-light preservation. `LUANTI_TEST_SHADOWS=false` selects the
shadow-free runtime path in `util/test_water_volume.sh`.

A C++ scene-manager test verifies opaque/capture/transparent pass ordering and that
a callback does not leak into a later draw. The runtime quality integration test
creates a water basin, checks that an actual liquid material binds the current
capture, exercises FOV changes and underwater transitions, and verifies colored
lamp updates alongside the other effects. Run
`LUANTI_TEST_QUALITY=true util/test_voxel_lighting.sh`; add
`LUANTI_TEST_DRIVER=opengl LUANTI_TEST_AA=fsaa` for legacy OpenGL with 4x MSAA.

The Release build, full C++ suite (352 individual tests and 19 Catch cases), and
numeric water tests on NVIDIA and Mesa software rendering passed in this workspace.
The combined OpenGL 3/TAA integration scene confirmed real liquid bindings and
preserved ordered RGB lamp removal. Legacy OpenGL with 4x MSAA, OpenGL 3 with
side-by-side stereo/4x MSAA, anaglyph stereo/TAA and standalone refraction with
SSAA also passed. Use `LUANTI_TEST_STEREO=sidebyside` or `anaglyph` to repeat stereo
checks. These checks establish transport and pipeline
behavior, not a visual-quality or frame-rate guarantee on other hardware.
