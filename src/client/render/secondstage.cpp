// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (C) 2010-2013 celeron55, Perttu Ahola <celeron55@gmail.com>
// Copyright (C) 2017 numzero, Lobachevskiy Vitaliy <numzer0@yandex.ru>
// Copyright (C) 2020 appgurueu, Lars Mueller <appgurulars@gmx.de>

#include "secondstage.h"
#include "client/client.h"
#include "client/shader.h"
#include "settings.h"
#include "plain.h"
#include "taa.h"
#include "camera_effects.h"
#include "water_volume.h"
#include "client/shadows/dynamicshadowsrender.h"
#include "volumetric_clouds.h"
#include "cloud_shadows.h"
#include "cloud_denoise.h"
#include "fog_denoise.h"
#include "voxel_lighting.h"
#include "scene_statistics.h"
#include "client/renderingengine.h"
#include <ISceneManager.h>

PostProcessingStep::PostProcessingStep(u32 _shader_id, const std::vector<u8> &_texture_map) :
	shader_id(_shader_id), texture_map(_texture_map)
{
	assert(texture_map.size() <= video::MATERIAL_MAX_TEXTURES);
	configureMaterial();
}

void PostProcessingStep::configureMaterial()
{
	material.UseMipMaps = false;
	material.ZBuffer = video::ECFN_LESSEQUAL;
	material.ZWriteEnable = video::EZW_ON;
	for (u32 k = 0; k < texture_map.size(); ++k) {
		material.TextureLayers[k].AnisotropicFilter = 0;
		material.TextureLayers[k].MinFilter = video::ETMINF_NEAREST_MIPMAP_NEAREST;
		material.TextureLayers[k].MagFilter = video::ETMAGF_NEAREST;
		material.TextureLayers[k].TextureWrapU = video::ETC_CLAMP_TO_EDGE;
		material.TextureLayers[k].TextureWrapV = video::ETC_CLAMP_TO_EDGE;
	}
}

void PostProcessingStep::setRenderSource(RenderSource *_source)
{
	source = _source;
}

void PostProcessingStep::setRenderTarget(RenderTarget *_target)
{
	target = _target;
}

void PostProcessingStep::reset(PipelineContext &context)
{
}

void PostProcessingStep::run(PipelineContext &context)
{
	if (target)
		target->activate(context);

	// attach the shader
	material.MaterialType = context.client->getShaderSource()->getShaderInfo(shader_id).material;

	auto driver = context.device->getVideoDriver();

	for (u32 i = 0; i < texture_map.size(); i++)
		material.TextureLayers[i].Texture = source->getTexture(texture_map[i]);
	if (cloud_noise) {
		auto *core = RenderingEngine::get_rendering_core();
		auto *noise = core ? core->get_cloud_noise() : nullptr;
		material.setTexture(2, noise ? noise->getTexture() : nullptr);
		setBilinearFilter(2, true);
		material.TextureLayers[2].TextureWrapU = video::ETC_CLAMP_TO_EDGE;
		material.TextureLayers[2].TextureWrapV = video::ETC_CLAMP_TO_EDGE;
		material.TextureLayers[2].AnisotropicFilter = 0;
	}
	if (cloud_shadows) {
		auto *core = RenderingEngine::get_rendering_core();
		auto *shadows = core ? core->get_cloud_shadows() : nullptr;
		material.setTexture(7, shadows ? shadows->getTexture() : nullptr);
		setBilinearFilter(7, true);
		material.TextureLayers[7].TextureWrapU = video::ETC_CLAMP_TO_EDGE;
		material.TextureLayers[7].TextureWrapV = video::ETC_CLAMP_TO_EDGE;
		material.TextureLayers[7].AnisotropicFilter = 0;
	}
	if (shadow_map) {
		assert(texture_map.size() <= ShadowRenderer::TEXTURE_LAYER_SHADOW);
		auto *shadow = context.shadow_renderer;
		material.setTexture(ShadowRenderer::TEXTURE_LAYER_SHADOW,
			shadow && shadow->is_active() ? shadow->get_texture() : nullptr);
	}
	if (water_volume) {
		auto *core = RenderingEngine::get_rendering_core();
		auto *volume = core ? core->get_water_volume() : nullptr;
		material.setTexture(6, volume ? volume->getTexture() : nullptr);
		auto &layer = material.TextureLayers[6];
		layer.MinFilter = video::ETMINF_NEAREST_MIPMAP_NEAREST;
		layer.MagFilter = video::ETMAGF_NEAREST;
		layer.TextureWrapU = video::ETC_CLAMP_TO_EDGE;
		layer.TextureWrapV = video::ETC_CLAMP_TO_EDGE;
		layer.AnisotropicFilter = 0;
	}
	if (voxel_lighting) {
		auto *volume = RenderingEngine::get_voxel_lighting();
		material.setTexture(4, volume ? volume->getTexture() : nullptr);
		auto &layer = material.TextureLayers[4];
		// X/Y probe interpolation uses the atlas sampler; Z blends in GLSL.
		layer.MinFilter = video::ETMINF_LINEAR_MIPMAP_NEAREST;
		layer.MagFilter = video::ETMAGF_LINEAR;
		layer.TextureWrapU = video::ETC_CLAMP_TO_EDGE;
		layer.TextureWrapV = video::ETC_CLAMP_TO_EDGE;
		layer.AnisotropicFilter = 0;
	}

	static const video::SColor color = video::SColor(0, 0, 0, 255);
	static const video::S3DVertex vertices[4] = {
			video::S3DVertex(1.0, -1.0, 0.0, 0.0, 0.0, -1.0,
					color, 1.0, 0.0),
			video::S3DVertex(-1.0, -1.0, 0.0, 0.0, 0.0, -1.0,
					color, 0.0, 0.0),
			video::S3DVertex(-1.0, 1.0, 0.0, 0.0, 0.0, -1.0,
					color, 0.0, 1.0),
			video::S3DVertex(1.0, 1.0, 0.0, 0.0, 0.0, -1.0,
					color, 1.0, 1.0),
	};
	static const u16 indices[6] = {0, 1, 2, 2, 3, 0};
	driver->setMaterial(material);
	driver->drawVertexPrimitiveList(&vertices, 4, &indices, 2);
	if (cloud_shadows) material.setTexture(7, nullptr);
	if (water_volume) {
		auto *core = RenderingEngine::get_rendering_core();
		const bool active = core && core->is_water_medium_applied();
		// Each eye owns this step, even when both eyes share a shader program.
		if (!water_medium_reported || active != water_medium_last) {
			infostream << "Water volume: underwater medium " << (active ? "active" : "inactive") << std::endl;
			water_medium_last = active;
			water_medium_reported = true;
		}
	}
}

void PostProcessingStep::setBilinearFilter(u8 index, bool value)
{
	assert(index < video::MATERIAL_MAX_TEXTURES);
	material.TextureLayers[index].MinFilter = value ? video::ETMINF_LINEAR_MIPMAP_NEAREST : video::ETMINF_NEAREST_MIPMAP_NEAREST;
	material.TextureLayers[index].MagFilter = value ? video::ETMAGF_LINEAR : video::ETMAGF_NEAREST;
}

RenderStep *addPostProcessing(RenderPipeline *pipeline, RenderStep *previousStep, v2f scale, Client *client, TemporalAAState *temporal, CameraEffectsState *camera_effects)
{
	auto buffer = pipeline->createOwned<TextureBuffer>();
	auto driver = client->getSceneManager()->getVideoDriver();

	// configure texture formats
	video::ECOLOR_FORMAT color_format = selectColorFormat(driver);
	video::ECOLOR_FORMAT depth_format = selectDepthFormat(driver);

	verbosestream << "addPostProcessing(): color = "
		<< video::ColorFormatName(color_format) << ", depth = "
		<< video::ColorFormatName(depth_format) << std::endl;

	// init post-processing buffer
	static const u8 TEXTURE_COLOR = 0;
	static const u8 TEXTURE_DEPTH = 1;
	static const u8 TEXTURE_BLOOM = 2;
	static const u8 TEXTURE_EXPOSURE_1 = 3;
	static const u8 TEXTURE_EXPOSURE_2 = 4;
	static const u8 TEXTURE_FXAA = 5;
	static const u8 TEXTURE_VOLUME = 6;

	static const u8 TEXTURE_MSAA_COLOR = 7;
	static const u8 TEXTURE_MSAA_DEPTH = 8;
	static const u8 TEXTURE_SSAO = 9;

	static const u8 TEXTURE_SURFACE = 30;
	static const u8 TEXTURE_MSAA_SURFACE = 31;
	static const u8 TEXTURE_LIGHTING = 32;
	static const u8 TEXTURE_HISTORY = 33;
	static const u8 TEXTURE_HISTORY_OUTPUT = 34;
	static const u8 TEXTURE_WATER_COLOR = 35;
	static const u8 TEXTURE_WATER_DEPTH = 36;
	static const u8 TEXTURE_CLOUD_SCATTER = 37;
	static const u8 TEXTURE_CLOUD_COLOR = 38;
	static const u8 TEXTURE_CAMERA_MOTION = 39;
	static const u8 TEXTURE_CAMERA_DOF = 40;
	static const u8 TEXTURE_WATER_MEDIUM = 41;
	static const u8 TEXTURE_CLOUD_GUIDE = 42;
	static const u8 TEXTURE_CLOUD_HISTORY = 43;
	static const u8 TEXTURE_CLOUD_HISTORY_GUIDE = 44;
	static const u8 TEXTURE_CLOUD_FILTERED = 45;
	static const u8 TEXTURE_FOG_SCATTER = 46, TEXTURE_FOG_TRANSMIT = 47;
	static const u8 TEXTURE_FOG_HISTORY_SCATTER = 48, TEXTURE_FOG_HISTORY_TRANSMIT = 49;
	static const u8 TEXTURE_FOG_FILTERED_SCATTER = 50, TEXTURE_FOG_FILTERED_TRANSMIT = 51;
	static const u8 TEXTURE_FOG_COLOR = 52;
	static const u8 TEXTURE_EMISSION_MASK = 53;
	static const u8 TEXTURE_MSAA_EMISSION_MASK = 54;
	static const u8 TEXTURE_SCENE_STATISTICS = 55;
	static const u8 TEXTURE_FINAL_COLOR = 56, TEXTURE_FINAL_STATISTICS = 57;

	static const u8 TEXTURE_SCALE_DOWN = 10;
	static const u8 TEXTURE_SCALE_UP = 20;

	// because bloom_format is floating point
	const bool bloom_available = driver->queryFeature(video::EVDF_RENDER_TO_FLOAT_TEXTURE);
	const bool enable_bloom = g_settings->getBool("enable_bloom") && bloom_available;
	const bool enable_volumetric_light = g_settings->getBool("enable_volumetric_lighting") && enable_bloom;
	const bool enable_auto_exposure = g_settings->getBool("enable_auto_exposure") && bloom_available;
	if (g_settings->getBool("enable_bloom") && !bloom_available) {
		warningstream << "Ignoring configured bloom since it's not supported by "
			"the current video driver." << std::endl;
	}
	if (g_settings->getBool("enable_auto_exposure") && !bloom_available) {
		warningstream << "Ignoring configured auto exposure since it's not supported by "
			"the current video driver." << std::endl;
	}

	verbosestream << "addPostProcessing(): bloom = "
		<< enable_bloom << (enable_volumetric_light ? " + volumetric" : "")
		<< ", exposure = " << enable_auto_exposure << std::endl;

	const std::string antialiasing = g_settings->get("antialiasing");
	const u16 antialiasing_scale = MYMAX(2, g_settings->getU16("fsaa"));

	// This code only deals with MSAA in combination with post-processing. MSAA without
	// post-processing works via a flag at OpenGL context creation instead.
	// To make MSAA work with post-processing, we need multisample texture support,
	// which has higher OpenGL (ES) version requirements.
	// Note: This is not about renderbuffer objects, but about textures,
	// since that's what we use and what Irrlicht allows us to use.

	const bool msaa_available = driver->queryFeature(video::EVDF_TEXTURE_MULTISAMPLE);
	const bool enable_msaa = antialiasing == "fsaa" && msaa_available;
	if (antialiasing == "fsaa" && !msaa_available) {
		warningstream << "Ignoring configured FSAA since it's not supported in "
			"combination with post-processing by the current video driver." << std::endl;
	}

	const bool enable_ssaa = antialiasing == "ssaa";
	const bool taa_fallback = antialiasing == "taa" && !temporal;
	if (taa_fallback)
		warningstream << "TAA requires floating-point render targets and high-precision shaders; "
			"using FXAA instead." << std::endl;
	const bool enable_fxaa = g_settings->getBool("fxaa") || taa_fallback;

	verbosestream << "addPostProcessing(): AA = "
		<< (enable_msaa ? "msaa" : enable_ssaa ? "ssaa" : "none")
		<< " " << antialiasing_scale << "x" << (enable_fxaa ? " + fxaa" : "") << std::endl;

	// Super-sampling is simply rendering into a larger texture.
	// Downscaling is done by the final step when rendering to the screen.
	if (enable_ssaa) {
		scale *= antialiasing_scale;
	}

	if (enable_msaa) {
		buffer->setTexture(TEXTURE_MSAA_COLOR, scale, "3d_render_msaa", color_format, false, antialiasing_scale);
		buffer->setTexture(TEXTURE_MSAA_DEPTH, scale, "3d_depthmap_msaa", depth_format, false, antialiasing_scale);
	}

	buffer->setTexture(TEXTURE_COLOR, scale, "3d_render", color_format);
	buffer->setTexture(TEXTURE_EXPOSURE_1, core::dimension2du(1,1), "exposure_1", color_format, /*clear:*/ true);
	buffer->setTexture(TEXTURE_EXPOSURE_2, core::dimension2du(1,1), "exposure_2", color_format, /*clear:*/ true);
	buffer->setTexture(TEXTURE_DEPTH, scale, "3d_depthmap", depth_format);

	const bool surface_enabled = useSceneSurface();
	const bool emission_mask = useSceneEmissionMask();
	const bool water_refraction = useWaterRefraction();
	if (g_settings->getBool("enable_water_refraction") && !water_refraction)
		warningstream << "Water refraction requires desktop OpenGL 3 and floating-point MRTs."
			<< std::endl;
	if (water_refraction) {
		buffer->setTexture(TEXTURE_WATER_COLOR, scale, "water_opaque_color", color_format);
		buffer->setTexture(TEXTURE_WATER_DEPTH, scale, "water_opaque_depth", depth_format);
		auto *draw = dynamic_cast<Draw3D *>(previousStep);
		sanity_check(draw);
		draw->setWaterCapture(pipeline->createOwned<TextureBufferOutput>(buffer,
			std::vector<u8> { TEXTURE_WATER_COLOR }, TEXTURE_WATER_DEPTH),
			buffer, TEXTURE_WATER_COLOR, TEXTURE_WATER_DEPTH);
	}
	const bool lighting_enabled = surface_enabled || g_settings->getBool("enable_atmosphere");
	if (g_settings->getBool("enable_atmosphere") &&
			g_settings->getBool("enable_volumetric_fog") && !useVolumetricFog())
		warningstream << "Volumetric fog requires desktop OpenGL; using analytic haze."
			<< std::endl;
	if (!supportsSceneSurface() && (g_settings->getBool("enable_screen_space_reflections") ||
			g_settings->getBool("enable_indirect_lighting") ||
			g_settings->getBool("enable_material_shading")))
		warningstream << "Advanced surface lighting requires desktop OpenGL and floating-point MRTs."
			<< std::endl;

	std::vector<u8> scene_textures { TEXTURE_COLOR };
	std::vector<u8> msaa_textures { TEXTURE_MSAA_COLOR };
	if (surface_enabled) {
		buffer->setTexture(TEXTURE_SURFACE, scale, "scene_surface", video::ECF_A16B16G16R16F);
		scene_textures.push_back(TEXTURE_SURFACE);
		if (enable_msaa) {
			buffer->setTexture(TEXTURE_MSAA_SURFACE, scale, "scene_surface_msaa",
				video::ECF_A16B16G16R16F, false, antialiasing_scale);
			msaa_textures.push_back(TEXTURE_MSAA_SURFACE);
		}
	}
	if (emission_mask) {
		buffer->setTexture(TEXTURE_EMISSION_MASK, scale, "scene_emission", video::ECF_R8);
		scene_textures.push_back(TEXTURE_EMISSION_MASK);
		if (enable_msaa) {
			buffer->setTexture(TEXTURE_MSAA_EMISSION_MASK, scale, "scene_emission_msaa", video::ECF_R8, false, antialiasing_scale);
			msaa_textures.push_back(TEXTURE_MSAA_EMISSION_MASK);
		}
	}
	if (surface_enabled || emission_mask) {
		std::vector<u8> auxiliary_textures;
		if (surface_enabled)
			auxiliary_textures.push_back(enable_msaa ? TEXTURE_MSAA_SURFACE : TEXTURE_SURFACE);
		if (emission_mask)
			auxiliary_textures.push_back(enable_msaa ? TEXTURE_MSAA_EMISSION_MASK : TEXTURE_EMISSION_MASK);
		auto *draw = dynamic_cast<Draw3D *>(previousStep);
		sanity_check(draw);
		draw->setAuxiliaryClearTarget(pipeline->createOwned<TextureBufferOutput>(buffer, auxiliary_textures));
	}

	// attach buffer to the previous step
	if (enable_msaa) {
		TextureBufferOutput *msaa = pipeline->createOwned<TextureBufferOutput>(buffer, msaa_textures, TEXTURE_MSAA_DEPTH);
		previousStep->setRenderTarget(msaa);
		TextureBufferOutput *normal = pipeline->createOwned<TextureBufferOutput>(buffer, scene_textures, TEXTURE_DEPTH);
		pipeline->addStep<ResolveMSAAStep>(msaa, normal);
	} else {
		previousStep->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, scene_textures, TEXTURE_DEPTH));
	}

	// shared variables
	u32 shader_id;

	// Number of mipmap levels of the bloom downsampling texture
	// (this affects the bloom strength, so don't blindly change it)
	const u8 MIPMAP_LEVELS = 4;

	// color_format can be a normalized integer format, but bloom requires
	// values outside of [0,1] so this needs to be a different one.
	const auto bloom_format = video::ECF_A16B16G16R16F;

	// post-processing stage

	u8 scene_source = TEXTURE_COLOR;
	const bool clouds_enabled = useVolumetricClouds();
	const bool cloud_denoising = useCloudDenoising();
	const bool fog_denoising = useFogDenoising();
	// Occlude surface radiance before adding cloud/fog/water scattering or
	// screen-space lighting. Volume radiance must not inherit surface creases.
	if (g_settings->getBool("enable_ssao")) {
		buffer->setTexture(TEXTURE_SSAO, scale, "ssao", color_format);
		shader_id = client->getShaderSource()->getShaderRaw("ssao");
		std::vector<u8> inputs{scene_source, TEXTURE_DEPTH};
		if (surface_enabled)
			inputs.push_back(TEXTURE_SURFACE);
		if (emission_mask)
			inputs.push_back(TEXTURE_EMISSION_MASK);
		auto ao = pipeline->addStep<PostProcessingStep>(shader_id, inputs);
		ao->setRenderSource(buffer);
		ao->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_SSAO));
		scene_source = TEXTURE_SSAO;
	}
	if (clouds_enabled) {
		const float resolution = g_settings->getFloat("volumetric_cloud_resolution", 0.25f, 1.0f);
		buffer->setTexture(TEXTURE_CLOUD_SCATTER, scale * resolution, "cloud_scatter", bloom_format);
		buffer->setTexture(TEXTURE_CLOUD_COLOR, scale, "cloud_color", color_format);
		shader_id = client->getShaderSource()->getShaderRaw("volumetric_clouds");
		auto clouds = pipeline->addStep<PostProcessingStep>(shader_id,
			std::vector<u8> { scene_source, TEXTURE_DEPTH });
		clouds->setRenderSource(buffer);
		clouds->setCloudNoise(true);
		u8 cloud_source = TEXTURE_CLOUD_SCATTER;
		if (cloud_denoising) {
			buffer->setTexture(TEXTURE_CLOUD_GUIDE, scale * resolution, "cloud_guide", bloom_format);
			buffer->setTexture(TEXTURE_CLOUD_HISTORY, scale * resolution, "cloud_history", bloom_format);
			buffer->setTexture(TEXTURE_CLOUD_HISTORY_GUIDE, scale * resolution, "cloud_history_guide", bloom_format);
			buffer->setTexture(TEXTURE_CLOUD_FILTERED, scale * resolution, "cloud_filtered", bloom_format);
			clouds->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer,
				std::vector<u8>{TEXTURE_CLOUD_SCATTER, TEXTURE_CLOUD_GUIDE}));
			auto state = make_irr<CloudDenoiseState>(scale * resolution, temporal);
			pipeline->addStep<PrepareCloudDenoiseStep>(state, shader_id);
			const u32 filter_id = client->getShaderSource()->getShader("cloud_denoise", {}, video::EMT_SOLID, state.get());
			auto filter = pipeline->addStep<PostProcessingStep>(filter_id,
				std::vector<u8>{TEXTURE_CLOUD_SCATTER, TEXTURE_CLOUD_GUIDE, TEXTURE_CLOUD_HISTORY, TEXTURE_CLOUD_HISTORY_GUIDE});
			filter->setRenderSource(buffer);
			filter->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_CLOUD_FILTERED));
			pipeline->addStep<FinishCloudDenoiseStep>(state);
			cloud_source = TEXTURE_CLOUD_FILTERED;
		} else {
			clouds->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_CLOUD_SCATTER));
		}
		shader_id = client->getShaderSource()->getShaderRaw("cloud_composite");
		auto composite = pipeline->addStep<PostProcessingStep>(shader_id,
			std::vector<u8> { scene_source, TEXTURE_DEPTH, cloud_source });
		composite->setRenderSource(buffer);
		composite->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_CLOUD_COLOR));
		scene_source = TEXTURE_CLOUD_COLOR;
	}
	if (lighting_enabled) {
		buffer->setTexture(TEXTURE_LIGHTING, scale, "scene_lighting", color_format);
		shader_id = client->getShaderSource()->getShaderRaw("scene_lighting");
		auto lighting = pipeline->addStep<PostProcessingStep>(shader_id,
			std::vector<u8> { scene_source, TEXTURE_DEPTH, TEXTURE_SURFACE });
		lighting->setRenderSource(buffer);
		lighting->setBilinearFilter(0, true);
		lighting->setShadowMap(useVolumetricFog() && !fog_denoising);
		lighting->setCloudShadows(useCloudShadows() && !fog_denoising);
		lighting->setVoxelLighting(useVoxelFogLighting() && !fog_denoising);
		lighting->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_LIGHTING));
		scene_source = TEXTURE_LIGHTING;
	}
	if (fog_denoising) {
		const v2f fog_scale = scale * g_settings->getFloat("fog_resolution", 0.25f, 1.0f);
		for (const auto &definition : std::vector<std::pair<u8, const char *>>{
			{TEXTURE_FOG_SCATTER, "fog_scatter"}, {TEXTURE_FOG_TRANSMIT, "fog_transmit"},
			{TEXTURE_FOG_HISTORY_SCATTER, "fog_history_scatter"}, {TEXTURE_FOG_HISTORY_TRANSMIT, "fog_history_transmit"},
			{TEXTURE_FOG_FILTERED_SCATTER, "fog_filtered_scatter"}, {TEXTURE_FOG_FILTERED_TRANSMIT, "fog_filtered_transmit"}})
			buffer->setTexture(definition.first, fog_scale, definition.second, bloom_format);
		buffer->setTexture(TEXTURE_FOG_COLOR, scale, "fog_color", color_format);
		const u32 raw_id = client->getShaderSource()->getShader("scene_lighting", {{"FOG_TRANSPORT_PASS", 1}}, video::EMT_SOLID);
		auto fog = pipeline->addStep<PostProcessingStep>(raw_id, std::vector<u8>{scene_source, TEXTURE_DEPTH, TEXTURE_SURFACE});
		fog->setRenderSource(buffer);
		fog->setShadowMap(true); fog->setCloudShadows(useCloudShadows());
		fog->setVoxelLighting(useVoxelFogLighting());
		fog->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer,
			std::vector<u8>{TEXTURE_FOG_SCATTER, TEXTURE_FOG_TRANSMIT}));
		auto state = make_irr<FogDenoiseState>(fog_scale, temporal);
		pipeline->addStep<PrepareFogDenoiseStep>(state, raw_id);
		const u32 filter_id = client->getShaderSource()->getShader("fog_denoise", {}, video::EMT_SOLID, state.get());
		auto filter = pipeline->addStep<PostProcessingStep>(filter_id, std::vector<u8>{TEXTURE_FOG_SCATTER,
			TEXTURE_FOG_TRANSMIT, TEXTURE_FOG_HISTORY_SCATTER, TEXTURE_FOG_HISTORY_TRANSMIT});
		filter->setRenderSource(buffer);
		filter->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer,
			std::vector<u8>{TEXTURE_FOG_FILTERED_SCATTER, TEXTURE_FOG_FILTERED_TRANSMIT}));
		pipeline->addStep<FinishFogDenoiseStep>(state);
		auto composite_state = make_irr<FogCompositeState>();
		const u32 composite_id = client->getShaderSource()->getShader("fog_composite", {}, video::EMT_SOLID, composite_state.get());
		auto composite = pipeline->addStep<PostProcessingStep>(composite_id, std::vector<u8>{scene_source,
			TEXTURE_FOG_FILTERED_SCATTER, TEXTURE_FOG_FILTERED_TRANSMIT, TEXTURE_DEPTH, TEXTURE_SURFACE});
		composite->setRenderSource(buffer);
		composite->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_FOG_COLOR));
		scene_source = TEXTURE_FOG_COLOR;
	}
	if (waterVolumeEnabled()) {
		buffer->setTexture(TEXTURE_WATER_MEDIUM, scale, "water_medium", color_format);
		shader_id = client->getShaderSource()->getShaderRaw("water_volume");
		auto medium = pipeline->addStep<PostProcessingStep>(shader_id,
			std::vector<u8> { scene_source, TEXTURE_DEPTH });
		medium->setRenderSource(buffer);
		medium->setWaterVolume(true);
		medium->setVoxelLighting(useVoxelWaterLighting());
		medium->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_WATER_MEDIUM));
		scene_source = TEXTURE_WATER_MEDIUM;
	}
	std::string statistics_path;
	g_settings->getNoEx("benchmark_scene_log", statistics_path);
	if (!statistics_path.empty()) {
		if ((driver->getDriverType() == video::EDT_OPENGL || driver->getDriverType() == video::EDT_OPENGL3) &&
				driver->queryTextureFormat(video::ECF_A32B32G32R32F)) {
			buffer->setTexture(TEXTURE_SCENE_STATISTICS, core::dimension2du(1, 1),
				"scene_statistics", video::ECF_A32B32G32R32F);
			const auto statistics_id = client->getShaderSource()->getShaderRaw("scene_statistics");
			auto reduce = pipeline->addStep<PostProcessingStep>(statistics_id, std::vector<u8>{scene_source});
			reduce->setRenderSource(buffer);
			reduce->setBilinearFilter(0, true);
			reduce->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_SCENE_STATISTICS));
			pipeline->addStep<SceneStatisticsStep>(buffer, TEXTURE_SCENE_STATISTICS, statistics_path);
		} else {
			errorstream << "Scene statistics: desktop OpenGL and RGBA32F targets required" << std::endl;
		}
	}
	if (temporal) {
		buffer->setTexture(TEXTURE_HISTORY, scale, "taa_history", video::ECF_A16B16G16R16F);
		buffer->setTexture(TEXTURE_HISTORY_OUTPUT, scale, "taa_output", video::ECF_A16B16G16R16F);
		shader_id = client->getShaderSource()->getShader("taa", {}, video::EMT_SOLID, temporal);
		std::vector<u8> taa_textures { scene_source, TEXTURE_HISTORY, TEXTURE_DEPTH, TEXTURE_SURFACE };
		if (clouds_enabled)
			taa_textures.push_back(TEXTURE_CLOUD_SCATTER);
		if (fog_denoising)
			taa_textures.push_back(TEXTURE_FOG_FILTERED_TRANSMIT);
		auto taa = pipeline->addStep<PostProcessingStep>(shader_id, taa_textures);
		taa->setRenderSource(buffer);
		taa->setBilinearFilter(0, true);
		taa->setBilinearFilter(1, true);
		taa->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_HISTORY_OUTPUT));
		scene_source = TEXTURE_HISTORY_OUTPUT;
	}

	if (!camera_effects && (g_settings->getBool("enable_camera_motion_blur") ||
			g_settings->getBool("enable_camera_dof")))
		warningstream << "Scene camera effects require desktop OpenGL; skipping camera blur." << std::endl;
	if (camera_effects) {
		for (bool motion : {true, false}) {
			if (!g_settings->getBool(motion ? "enable_camera_motion_blur" : "enable_camera_dof"))
				continue;
			const u8 target = motion ? TEXTURE_CAMERA_MOTION : TEXTURE_CAMERA_DOF;
			const std::string name = motion ? "camera_motion" : "camera_dof";
			buffer->setTexture(target, scale, name, color_format);
			shader_id = client->getShaderSource()->getShader(name, {}, video::EMT_SOLID, camera_effects);
			auto effect = pipeline->addStep<PostProcessingStep>(shader_id,
				std::vector<u8> { scene_source, TEXTURE_DEPTH });
			effect->setRenderSource(buffer);
			effect->setBilinearFilter(0, true);
			effect->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, target));
			scene_source = target;
		}
	}

	u8 source = scene_source;

	// common downsampling step for bloom or autoexposure
	if (enable_bloom || enable_auto_exposure) {

		v2f downscale = scale * 0.5f;
		for (u8 i = 0; i < MIPMAP_LEVELS; i++) {
			buffer->setTexture(TEXTURE_SCALE_DOWN + i, downscale, std::string("downsample") + std::to_string(i), bloom_format);
			if (enable_bloom)
				buffer->setTexture(TEXTURE_SCALE_UP + i, downscale, std::string("upsample") + std::to_string(i), bloom_format);
			downscale *= 0.5f;
		}

		{
			buffer->setTexture(TEXTURE_BLOOM, scale, "bloom", bloom_format);

			// Linear exposed input for both bloom and exposure metering, including
			// the configuration with exposure enabled and bloom disabled.
			u32 shader_id = client->getShaderSource()->getShaderRaw("extract_bloom");
			RenderStep *extract_bloom = pipeline->addStep<PostProcessingStep>(shader_id, std::vector<u8> { source, TEXTURE_EXPOSURE_1 });
			extract_bloom->setRenderSource(buffer);
			extract_bloom->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_BLOOM));
			source = TEXTURE_BLOOM;
		}

		u8 downsample_start = 0;
		if (enable_volumetric_light) {
			// The volumetric pass is expensive (a raymarch per target pixel)
			// and its output only reaches the screen through the blur of the
			// bloom chain, whose first target is half resolution anyway. So
			// with performance_tradeoffs enabled, render it directly into the
			// first downsample target and skip the then-redundant first
			// bloom_downsample step.
			const bool half_res = g_settings->getFlag("performance_tradeoffs");

			shader_id = client->getShaderSource()->getShaderRaw("volumetric_light");
			auto volume = pipeline->addStep<PostProcessingStep>(shader_id, std::vector<u8> { source, TEXTURE_DEPTH });
			volume->setRenderSource(buffer);
			if (half_res) {
				// Only the color input is minified; depth stays unfiltered
				// because the shader does exact comparisons against 1.0.
				volume->setBilinearFilter(0, true);
				volume->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_SCALE_DOWN));
				source = TEXTURE_SCALE_DOWN;
				downsample_start = 1;
			} else {
				buffer->setTexture(TEXTURE_VOLUME, scale, "volume", bloom_format);
				volume->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_VOLUME));
				source = TEXTURE_VOLUME;
			}
		}

		// downsample
		shader_id = client->getShaderSource()->getShaderRaw("bloom_downsample");
		for (u8 i = downsample_start; i < MIPMAP_LEVELS; i++) {
			auto step = pipeline->addStep<PostProcessingStep>(shader_id, std::vector<u8> { source });
			step->setRenderSource(buffer);
			step->setBilinearFilter(0, true);
			step->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_SCALE_DOWN + i));
			source = TEXTURE_SCALE_DOWN + i;
		}
	}

	// Bloom pt 2
	if (enable_bloom) {
		// upsample
		shader_id = client->getShaderSource()->getShaderRaw("bloom_upsample");
		for (u8 i = MIPMAP_LEVELS - 1; i > 0; i--) {
			auto step = pipeline->addStep<PostProcessingStep>(shader_id, std::vector<u8> { u8(TEXTURE_SCALE_DOWN + i - 1), source });
			step->setRenderSource(buffer);
			step->setBilinearFilter(0, true);
			step->setBilinearFilter(1, true);
			step->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, u8(TEXTURE_SCALE_UP + i - 1)));
			source = TEXTURE_SCALE_UP + i - 1;
		}
	}

	// Dynamic Exposure pt2
	if (enable_auto_exposure) {
		shader_id = client->getShaderSource()->getShaderRaw("update_exposure");
		auto update_exposure = pipeline->addStep<PostProcessingStep>(shader_id, std::vector<u8> { TEXTURE_EXPOSURE_1, u8(TEXTURE_SCALE_DOWN + MIPMAP_LEVELS - 1) });
		update_exposure->setBilinearFilter(1, true);
		update_exposure->setRenderSource(buffer);
		update_exposure->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_EXPOSURE_2));
	}

	// FXAA
	u8 final_stage_source = scene_source;

	if (enable_fxaa) {
		final_stage_source = TEXTURE_FXAA;

		buffer->setTexture(TEXTURE_FXAA, scale, "fxaa", color_format);
		shader_id = client->getShaderSource()->getShaderRaw("fxaa");
		PostProcessingStep *effect = pipeline->createOwned<PostProcessingStep>(shader_id, std::vector<u8> { scene_source });
		pipeline->addStep(effect);
		effect->setBilinearFilter(0, true);
		effect->setRenderSource(buffer);
		effect->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_FXAA));
	}

	// final merge
	shader_id = client->getShaderSource()->getShaderRaw("second_stage");
	PostProcessingStep *effect = pipeline->createOwned<PostProcessingStep>(shader_id, std::vector<u8> { final_stage_source, TEXTURE_SCALE_UP, TEXTURE_EXPOSURE_2 });
	pipeline->addStep(effect);
	if (enable_ssaa)
		effect->setBilinearFilter(0, true);
	effect->setBilinearFilter(1, true);
	effect->setRenderSource(buffer);

	// Optional scalar probes of the actual final TAA/exposure/bloom/tone result.
	// Rendering into this diagnostic target never captures or saves an image;
	// the only readback is a reduced RGBA32F texel, as for scene statistics above.
	std::string final_statistics_path;
	g_settings->getNoEx("benchmark_final_scene_log", final_statistics_path);
	if (!final_statistics_path.empty() &&
			(driver->getDriverType() == video::EDT_OPENGL || driver->getDriverType() == video::EDT_OPENGL3) &&
			driver->queryTextureFormat(video::ECF_A32B32G32R32F)) {
		buffer->setTexture(TEXTURE_FINAL_COLOR, scale, "final_scene", video::ECF_A8R8G8B8);
		effect->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_FINAL_COLOR));
		buffer->setTexture(TEXTURE_FINAL_STATISTICS, core::dimension2du(1, 1),
			"final_scene_statistics", video::ECF_A32B32G32R32F);
		auto reduce = pipeline->addStep<PostProcessingStep>(client->getShaderSource()->getShaderRaw("scene_statistics"),
			std::vector<u8>{TEXTURE_FINAL_COLOR});
		reduce->setRenderSource(buffer);
		reduce->setBilinearFilter(0, true);
		reduce->setRenderTarget(pipeline->createOwned<TextureBufferOutput>(buffer, TEXTURE_FINAL_STATISTICS));
		pipeline->addStep<SceneStatisticsStep>(buffer, TEXTURE_FINAL_STATISTICS, final_statistics_path);
		effect = pipeline->addStep<PostProcessingStep>(client->getShaderSource()->getShaderRaw("scene_copy"),
			std::vector<u8>{TEXTURE_FINAL_COLOR});
		effect->setRenderSource(buffer);
	}

	if (enable_auto_exposure) {
		pipeline->addStep<SwapTexturesStep>(buffer, TEXTURE_EXPOSURE_1, TEXTURE_EXPOSURE_2);
	}

	// Keep this swap after every consumer of the current resolved frame.
	if (temporal)
		pipeline->addStep<SwapTexturesStep>(buffer, TEXTURE_HISTORY, TEXTURE_HISTORY_OUTPUT);
	if (cloud_denoising) {
		pipeline->addStep<SwapTexturesStep>(buffer, TEXTURE_CLOUD_HISTORY, TEXTURE_CLOUD_FILTERED);
		pipeline->addStep<SwapTexturesStep>(buffer, TEXTURE_CLOUD_HISTORY_GUIDE, TEXTURE_CLOUD_GUIDE);
	}
	if (fog_denoising) {
		pipeline->addStep<SwapTexturesStep>(buffer, TEXTURE_FOG_HISTORY_SCATTER, TEXTURE_FOG_FILTERED_SCATTER);
		pipeline->addStep<SwapTexturesStep>(buffer, TEXTURE_FOG_HISTORY_TRANSMIT, TEXTURE_FOG_FILTERED_TRANSMIT);
	}

	return effect;
}

void ResolveMSAAStep::run(PipelineContext &context)
{
	context.device->getVideoDriver()->blitRenderTarget(msaa_fbo->getIrrRenderTarget(context),
			target_fbo->getIrrRenderTarget(context));
}
