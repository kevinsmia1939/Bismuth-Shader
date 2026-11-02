# Graphics goal and remaining work

The active follow-up is the [five-stage renderer lighting replacement](renderer-lighting-migration.md).
Native visual lighting removal comes first; no brightness adapter is planned.
The torch approach regression must be fixed before final preset delivery.

[Milestone 8: Vulkan renderer](vulkan-renderer.md) follows the lighting migration
and preset delivery. It covers backend bring-up, shared shader compilation,
rendering-feature parity, validation and measured performance. It is planned, not
part of the current stages 1–5 implementation scope.

The current target is a semi-realistic preset. The feature inventory later in
this document preserves the earlier open-ended graphics goal.
[Milestones 2–4](graphics-milestones-2-4.md) are implemented and checked in the
reference scenes, following the [Milestone 1 baseline](graphics-baseline/README.md).
Material response is implemented and checked in
[Milestone 5](graphics-milestone-5.md).

[Milestone 6](graphics-milestone-6.md) covers the following implemented stages, in
implementation order, followed by the combined-image stability audit:

| Stage | Concrete scope | Acceptance |
| --- | --- | --- |
| 6A. Smooth local-light falloff | Correct the abrupt ground-brightness drop around torches, mese lamps, glowstone and other emitters; check placed and held lights | Smooth distance falloff across block boundaries, restrained brightness beside the source, preserved wall occlusion and cave darkness |
| 6B. Translucent foliage | Thin-surface light transmission for grass and leaves, with ordinary textures and optional authored control | Soft backlighting, preserved cutout silhouettes, stable moving foliage and no glow without incident light |
| 6C. Sand and snow sparkle | Sparse, restrained grain highlights driven by incident light and view direction | Distinct sand/snow response, stable world-space detail, filtered distant glints and no sparkle in unlit areas |
| 6D. Combined-image stability | Tune TAA, exposure, tone mapping and mild bloom; check movement, animation, resizing and water transitions | No persistent trails, exposure flashes or history smearing; previous lighting, water and darkness checks still pass |

All four stages pass the C++, numeric GPU, native scene and compatibility checks.
The [milestone 6 report](graphics-milestone-6-results/README.md) records their
combined audit and matched frame costs. Earlier milestone reports retain their
original scope and evidence. Final preset delivery and the complete performance
budget remain milestone 7. Items in the historical remaining-work
column below are not additional requirements for the completed bounded milestones.

Minetest Game is now the primary integration target. The earlier baseline and
milestones 2–4 reports describe historical VoxeLibre terrain. Milestone 5 uses
fresh Minetest Game scenes; existing VoxeLibre worlds are kept separately.

The requested goal covers soft sunlight shadows, global illumination, advanced
water, volumetric atmosphere, material shading, colored lighting, temporal
antialiasing, and camera effects. Existing effects and the initial screen-space
passes do not establish completion of that entire goal.

| Requirement | Current evidence | Remaining work |
| --- | --- | --- |
| Soft sunlight shadows | Blocker search with world-distance penumbra, exact XY-warp sampling, receiver-plane correction and colored filtering; analytic GPU and combined-renderer tests | Broader sun-angle, thin-caster, bias and performance audit; finite sampling and shadow-map coverage remain limits |
| Global illumination | Local voxel radiosity with map occlusion, RGB path transmission, cloud-attenuated directional injection, emissive light and multiple bounces; CPU/GPU/live update tests | Larger/cascaded coverage, finer geometry, dynamic occluders and transport-quality audit |
| Advanced water | Wave/Fresnel SSR, sun/moon glints independent of shadow enablement/coverage/intensity, two-way Snell refraction/TIR, loaded liquid-path RGB absorption, native and phase-weighted colored voxel/bounce/held-lamp underwater scattering, source/flow wave caustics with projected photon density, connected-face root continuation and solved-ray visibility; displaced source/flow triangles, shared flow geometry and interface normals; CPU/GPU and live transition tests | Wider geometry coverage, caustic crease filtering/multiple roots, mixed liquid boundaries, nested transparency, directional volume shafts, baked-source bulk liquid extinction, local-lamp interface bending and performance/appearance audit |
| Volumetric atmosphere | Shadowed heterogeneous fog, phase-weighted voxel emission/bounce and source-specific HG scattering for moving lamps, ray-marched clouds, separate spatial/temporal cloud and fog denoising, depth-aware composites, surface AO before volume source terms, volume-reactive TAA and shared cloud transmission on terrain/objects/direct fog/GI injection; CPU/GPU/control-transition tests | Higher angular resolution for baked-light phase, interleaved mixed-media transport, distributed-volume reprojection and wider performance audit |
| Material shading | Authored normal/ORM tiles, dielectric/conductor GGX for directional and moving local lights, independent directional radiance, shared local visibility/RGB transmission, normal-variance and roughness-moment mip chains, pixel-footprint filtering, preserved native emission, R8 emissive SSAO coverage and synchronized animation; numeric/runtime/Minetest Game checks and measured material cost | Wider assets and hardware; calibrated diffuse/specular and separate emission, finite-area light filtering and mixed-pixel integration remain extensions beyond milestone 5 |
| Colored lighting | Explicit/inferred RGB node emission transported through loaded voxels; per-frame GPU direct light from held/moving node items with current map occupancy/RGB transmission independent of pending solves, plus asynchronous diffuse bounce; glass/authored RGB transmission with thickness and slanted paths on direct, sun-injection and bounce rays; mesh/sprite receivers; CPU/GPU and source/filter-update integration tests | General mesh/sprite emission, partial/moving transparent geometry and automatic liquid coefficients; wider game compatibility/performance audit |
| Temporal antialiasing | Jitter, camera reprojection, depth rejection, reactive water, per-eye histories, CPU/GPU tests | Runtime movement/stereo/resize checks passed; object motion vectors remain for further ghost reduction |
| Camera effects | Bloom/exposure/filmic mapping, vignette, manual depth of field and camera-motion blur; GPU and combined-renderer tests | Broader motion/occlusion/performance audit; autofocus, foreground scatter and object motion vectors remain extensions |

The screen-space passes are useful intermediate implementations, not substitutes
for the remaining lighting and volume requirements. Track each requirement
against implementation, rendering evidence and tests before marking the overall
goal achieved.
