# Scene camera effects

Optional camera motion blur and manual depth of field run on desktop OpenGL with
post processing enabled. Default settings leave both off. The quality preset uses
gentle motion blur; depth of field remains an optional cinematic control. The
existing bloom, exposure, tone mapping and vignette remain available separately.

Each eye captures an unjittered camera frame before TAA prepares its projection.
The same temporal-history rules reject camera cuts, projection/FOV changes,
resizes, camera-mode changes and frame gaps of 250 ms or more. Reprojection
accounts for camera-origin shifts. Sky motion uses rotation without translation.
These effects allocate no previous-color texture and never read camera data back
from the GPU. Motion blur does not require TAA.

## Motion blur

`enable_camera_motion_blur` adds camera motion estimated by reprojecting the current
depth into the preceding camera frame. TAA color is already on an unjittered grid;
depth lookups include the current TAA jitter. This avoids treating projection
jitter as camera motion. Shutter duration is normalized toward a 60 FPS reference
using the measured frame interval, with the history system's safety clamps for
very short/long intervals. The blur length is capped in output pixels, independently
of supersampling, undersampling and the eye's output size.

A centered line gather averages scene color in linear RGB. Samples outside the
viewport or across significant depth discontinuities are rejected; sky and
geometry do not gather each other. First frames/cuts, zero shutter/maximum blur,
subpixel movement and behind-camera reprojections preserve the source pixel.
Scene alpha is preserved. Moving objects have no separate velocity vectors, so
this feature represents camera motion rather than independent object animation.

- `camera_motion_blur_strength`: shutter duration in units of a 60 FPS frame,
  default 0.5, range 0–2. The quality preset uses 0.35.
- `camera_motion_blur_max`: maximum blur length in output pixels, default 24,
  range 0–64.
- `camera_motion_blur_samples`: 4–24 samples, default 12.

## Depth of field

`enable_camera_dof` adds a manually selected focus plane and sharp range in nodes.
The signed circle of confusion increases with relative distance from that range,
up to a configurable radius in output pixels. Near and far surfaces, including
sky, can defocus. Pixels inside the sharp range and subpixel/zero blur bypass the
gather. A fixed 24-sample disk averages linear scene color and preserves alpha.

Depth-aware weights limit background bleed through foreground silhouettes and
avoid spreading focused foreground donors onto distant surfaces. This is a
conservative screen-space gather: it cannot reveal hidden background behind a
defocused object or fully spread foreground bokeh outside a focused receiver.
There is no autofocus, physical lens simulation, polygonal aperture or separate
near-field scatter pass. Finite samples and single-layer scene depth can leave
edge, transparent-surface and thin-object artifacts.
Volumetric clouds/fog also do not supply a separate lens-depth or motion layer.

- `camera_dof_focus_distance`: focus distance in nodes, default 8, range 0.1–1000.
- `camera_dof_focus_range`: half-width of the sharp range in nodes, default 2,
  range 0–100.
- `camera_dof_blur`: maximum defocus radius in output pixels, default 6,
  range 0–16.

For example, enable depth of field and set focus distance 8/range 2 to retain a
sharp band from 6 to 10 nodes. Numeric controls update live; changing either
enable flag requires a restart to rebuild the pipeline.

## Pipeline and validation

Motion blur runs after TAA and before depth of field. Both precede bloom,
auto-exposure and final color grading, and neither feeds the TAA history. HUD and
wield rendering happen afterward with the restored camera projection. Each enabled
effect adds one full-resolution color target per eye. Camera effects do not
require bloom, voxel lighting, surface MRTs or floating-point targets.

`python3 util/test_camera_effects.py` compiles the actual GLSL in a hidden context.
It checks stationary/cut bypass, shutter normalization and bounds, sky rotation
versus translation, depth/viewport rejection, manual focus/range, near/far/sky
defocus, TAA depth coordinates, foreground protection, HDR color and preserved
alpha. Set `LUANTI_TEST_GLSL=120` for legacy GLSL; default is 330 core. No image
capture or input-device control is used. The C++ suite verifies unjittered
reprojection alongside existing reset/origin/sky rules.

`LUANTI_TEST_CAMERA_EFFECTS=true LUANTI_TEST_QUALITY=true util/test_voxel_lighting.sh`
exercises both shaders with the complete quality pipeline, camera translation/FOV
changes, underwater transitions and RGB source removal. The script supports
legacy OpenGL, MSAA and stereo variants documented in `voxel-lighting.md`.
Correctness checks do not establish a frame-rate or appearance target.

`util/test_camera_effects.sh` tests the camera effects with an 8-bit scene target,
without the quality preset or TAA. `LUANTI_TEST_MOTION=false` and
`LUANTI_TEST_DOF=false` select individual effects; driver/AA/stereo variables
select the same compatibility paths as the combined test. It reuses the lighting
fixture for camera translation, FOV and underwater transitions.

In this workspace the Release build and complete C++ suite passed (352 individual
tests and 23 Catch cases). Numeric tests passed on NVIDIA with GLSL 120/330 core
and on Mesa llvmpipe with GLSL 330 core. Runtime checks passed with the complete
quality pipeline on OpenGL 3/TAA (mono and side-by-side), legacy OpenGL/4x MSAA,
and standalone 8-bit/no-AA targets. DOF alone also passed with side-by-side stereo
and 2x supersampling.
VoxeLibre also completed a compatibility run with both camera effects, clouds,
water, authored-material support and voxel lighting enabled, without shader/GL
errors. Authored-map animation and native/emissive replacements passed their
separate combined-renderer integration test.
