# Milestone 8: Vulkan renderer

Status: planned. Add a Vulkan backend after the renderer lighting replacement
and the first usable semi-realistic preset. Adding this milestone does not claim
that Vulkan is implemented or that changing APIs alone will improve frame times.
The current active implementation goal remains the lighting migration's stages
1–5. New lighting code should keep transport and material calculations separate
from graphics API resource management so this backend can reuse them.

| Stage | Concrete scope | Acceptance criteria |
| --- | --- | --- |
| 8A. Backend foundation | Add Vulkan device/surface selection, swapchain, command submission, synchronization, GPU resource allocation and capability reporting behind the renderer interface | A native window presents correctly; resizing, minimize/restore and shutdown work; unsupported capabilities produce a clear fallback |
| 8B. Geometry and shaders | Render voxel terrain, entities, cutouts, translucent surfaces, animated textures and UI; compile shared shader calculations to SPIR-V; define explicit buffer, texture and descriptor layouts | Ordinary Minetest Game textures and optional material maps work; pipeline variants compile; geometry, palette colors, depth, blending and emission match the intended lighting model |
| 8C. Lighting and effect parity | Port renderer-owned sunlight/skylight, colored direct light, world lighting data, GI, shadows, water, atmosphere, foliage transmission and grain highlights; port TAA, exposure, tone mapping and bloom | Native brightness adapters stay absent; torch approach/retreat, dark caves, source removal, water transitions, camera motion and resize/history checks pass |
| 8D. Validation, profiling and delivery | Exercise validation layers, resource lifetimes, uploads and barriers; compare fixed-scene CPU/GPU times, memory and frame pacing against OpenGL on the available GTX 1650 Ti; document builds and configuration | No outstanding validation errors in the test scenes; repeatable timings and known limitations are published; Vulkan can be selected explicitly and the supported fallback remains usable |

Choose the required Vulkan version and optional feature set from an actual
capability audit when implementation starts. Record toolchain and shader compiler
requirements, and report missing build packages before relying on them. Keep the
backend optional during development and avoid forcing Vulkan dependencies onto
the existing OpenGL build.

Use numeric probes and disposable native-world replays. Screenshots and input-
device automation remain excluded unless the user changes that preference.
Performance success requires measurements; backend availability and visual
correctness are separate acceptance gates from the 1080p/60 FPS target.
