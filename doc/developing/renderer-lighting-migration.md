# Renderer lighting replacement

Active goal: complete stages 1–5. The torch approach regression reopened the
lighting architecture work after milestone 6's bounded tests. Those earlier
reports remain historical evidence; they do not prove distance consistency.

Native visual lighting removal is the first milestone. Do not build or retain a
native-to-renderer brightness adapter, and do not blend native brightness back
at the edges of a local field. The advanced path must compose renderer-owned
lighting from the start. Server light data is a separate compatibility decision;
its removal has not been authorized unambiguously yet.

| Stage | Required implementation | Completion evidence |
| --- | --- | --- |
| 1. Remove native visual lighting | Separate palette/texture color from baked vertex brightness; explicit linear sunlight, skylight, local light, indirect light and self emission; remove native brightness adapters and edge fallbacks | Production node/object shaders ignore poisoned native brightness; palette, cutouts, emission, UI previews and gameplay behavior remain correct |
| 2. Cover visible terrain | World-anchored direct lighting and visibility across visible lit terrain, including distant placed lights; updates for placed and held sources | Fixed-exposure approach/retreat and camera-rotation replay over the same ground patches, crossing old field boundaries; wall and colored-transmission controls; no native fallback |
| 3. Improve global illumination | Stable, wider diffuse bounce from sunlight and colored emitters, with bounded cost and predictable invalidation | Hidden/off-screen source bounce, color transfer, blocked transport, lamp removal and camera movement; no ambient floor in unlit caves |
| 4. Finish removal and integration audit | Eliminate remaining native illumination dependencies in the advanced surface/volume/material paths; stabilize combined water, atmosphere and camera effects | Source inspection plus runtime/GPU tests for surfaces, objects, foliage, water, fog, emission, TAA, exposure, stereo and resizing |
| 5. Optimize and deliver | Profile full renderer, tune useful quality levels, document one usable semi-realistic preset and fallback behavior | Repeated fixed-setting 1080p timings on GTX 1650 Ti, measured memory/update costs, actual preset checks, committed/pushed code and evidence |

The 60 FPS target must be assessed against the actual final renderer. It is not
established by isolated tests or by disabling required lighting coverage. Record
measured shortfalls and continue useful optimization instead of claiming the
budget was achieved without evidence.

## Initial evidence

A controlled production node-fragment test held surface position, irradiance and
exposure fixed while translating the old camera-local field. Its red output fell
from 0.4000 outside the field to 0.14958 inside it. This demonstrates a native/voxel
composition mismatch without auto exposure. It is a controlled reproduction of
the mechanism, not a measurement of the user's exact world patch.

The replacement should use world-anchored transport data. A larger moving local
cube alone merely moves the native/voxel mismatch farther away and is not a fix.
Use immutable map snapshots, bounded asynchronous work and dirty-region updates;
never let camera position alter the irradiance of an unchanged receiving surface.
Geometry and source edits must invalidate affected direct and indirect results.
Unknown geometry blocks transport rather than being treated as open sky.

The initial separation introduces linear light packets and unlit mesh colors.
The native-brightness replacement adapter has been removed rather than retained
as a migration layer; missing renderer transport contributes zero radiance.
This is work in progress: direct-light coverage, GI refinement, object/volume
integration and final performance remain unproven. No screenshots or input-device
automation are part of validation. Use disposable test worlds, preserving the
user's playable terrain and preferences.

[Milestone 8: Vulkan renderer](vulkan-renderer.md) follows these five stages.
Keep lighting transport and material composition independent of API-specific
resource management so the Vulkan backend can reuse the finished lighting model.
