# Graphics goal and remaining work

This is the historical feature inventory from the earlier open-ended graphics
goal. The current target is a semi-realistic preset.
[Milestones 2–4](graphics-milestones-2-4.md) are implemented and checked in the
reference scenes, following the [Milestone 1 baseline](graphics-baseline/README.md).
Material response is implemented and checked in
[Milestone 5](graphics-milestone-5.md). Combined-image stability and final preset
delivery remain milestones 6–7. Items in the remaining-work column below are not additional
requirements for the completed bounded milestones.

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
