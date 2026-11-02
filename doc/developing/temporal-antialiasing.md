# Temporal antialiasing and scene camera effects

Select `antialiasing = taa` with post processing enabled and restart the client.
The optional quality preset now selects TAA and disables FXAA to avoid stacking
spatial smoothing filters. `taa_history_weight` controls the history contribution
(default 0.9 at 60 FPS); a time-based exponent maintains a similar response across
frame rates. This setting can be adjusted live.

An eight-sample Halton sequence jitters the camera's projection by less than half
a rendered pixel. The resolve reconstructs the current frame onto an unjittered
output grid, then reprojects camera motion into an unjittered previous view.
World-origin offsets are included in the transform. Sky reprojection uses only
camera rotation so moving the camera does not introduce sky parallax.

Two RGBA16F textures hold alternating resolved frames. Alpha stores linear camera
depth, with zero reserved for sky. The resolve runs after surface lighting and
SSAO, before bloom/exposure metering and final tone mapping. History is swapped
only after all current-frame consumers have rendered. The camera projection is
then restored; wielded items and HUD elements are outside the temporal history.

New history is rejected on first use, resizing, projection/FOV changes, camera
mode changes, large position or orientation changes, and frame gaps over 250 ms.
The per-pixel depth test rejects disoccluded geometry. A 3x3 YCoCg variance and
neighborhood clamp bounds previous colors, with lower history weight for motion
and large luminance or normalized-chroma changes. Chroma rejection clears
stale hues in equal-brightness animated textures; the milestone 6 feedback test
reduces four-frame stale-color energy from 0.6561 to about 0.03671. Water receives a reactive cap to reduce trails from
animated reflections. Each stereo eye owns independent history and reprojection
state, including anaglyph and side-by-side modes.

This is camera-based TAA, without per-object motion vectors. Moving entities and
waving foliage can still ghost or soften. It does not provide temporal upscaling
or a general-purpose reflection/GI denoiser. Float render targets and fragment
high precision are required. Unsupported post-processing drivers fall back to
FXAA; ES2 is excluded because fragment high precision is optional. ES3 has not
been exercised in this workspace. TAA does not run with post processing disabled.

The additional history storage is 16 bytes per rendered pixel (two RGBA16F
textures), plus one full-screen resolve with neighborhood sampling. Sample counts
and memory scale with the actual per-eye, undersampled render resolution.

`enable_camera_vignette` adds optional lens-edge darkening in the final scene
pass after tone mapping and color grading, before dithering. Strength defaults to
0.2 and is bounded to 0.75. The option and strength require restart because they
are shader constants. Bloom, exposure adaptation and filmic tone mapping retain
their existing settings. HUD elements are not darkened.

## Reproduction

Run `LUANTI_PREVIEW_AA=taa util/preview_lighting.sh full` for the fixed scene.
Set `LUANTI_PREVIEW_MOTION=true` as well to move the camera on a repeatable path.
Compare against `LUANTI_PREVIEW_AA=none` and `LUANTI_PREVIEW_AA=fsaa`.

The client Catch tests in `src/test/client/test_temporal_history.cpp` verify reset
rules, subpixel bounds, reprojection through an origin shift, and sky translation
invariance. Direct GPU tests exercise first-frame history bypass, depth storage,
clipping of invalid old colors, accumulation, water reactivity, and disocclusion.
Runtime validation includes legacy OpenGL, OpenGL 3, stereo modes, resize, and a
moving camera. See `screenshots/temporal-validation.txt` for the recorded outcomes.
