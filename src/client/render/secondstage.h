// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (C) 2010-2013 celeron55, Perttu Ahola <celeron55@gmail.com>
// Copyright (C) 2017 numzero, Lobachevskiy Vitaliy <numzer0@yandex.ru>

#pragma once
#include "pipeline.h"

/**
 *  Step to apply post-processing filter to the rendered image
 */
class PostProcessingStep : public RenderStep
{
public:
	/**
	 * Construct a new PostProcessingStep object
	 *
	 * @param shader_id ID of the shader in IShaderSource
	 * @param texture_map Map of textures to be chosen from the render source
	 */
	PostProcessingStep(u32 shader_id, const std::vector<u8> &texture_map);


	void setRenderSource(RenderSource *source) override;
	void setRenderTarget(RenderTarget *target) override;
	void reset(PipelineContext &context) override;
	void run(PipelineContext &context) override;

	/**
	 * Configure bilinear filtering for a specific texture layer
	 *
	 * @param index Index of the texture layer
	 * @param value true to enable the bilinear filter, false to disable
	 */
	void setBilinearFilter(u8 index, bool value);
	void setShadowMap(bool value) { shadow_map = value; }
	void setCloudNoise(bool value) { cloud_noise = value; }
	void setCloudShadows(bool value) { cloud_shadows = value; }
	void setWaterVolume(bool value) { water_volume = value; }
	void setVoxelLighting(bool value) { voxel_lighting = value; }
private:
	u32 shader_id;
	std::vector<u8> texture_map;
	RenderSource *source { nullptr };
	RenderTarget *target { nullptr };
	video::SMaterial material;
	bool shadow_map = false;
	bool cloud_noise = false;
	bool cloud_shadows = false;
	bool water_volume = false;
	bool voxel_lighting = false;
	bool water_medium_reported = false;
	bool water_medium_last = false;

	void configureMaterial();
};


class ResolveMSAAStep : public TrivialRenderStep
{
public:
	ResolveMSAAStep(TextureBufferOutput *_msaa_fbo, TextureBufferOutput *_target_fbo) :
			msaa_fbo(_msaa_fbo), target_fbo(_target_fbo) {};
	void run(PipelineContext &context) override;

private:
	TextureBufferOutput *msaa_fbo;
	TextureBufferOutput *target_fbo;
};


class TemporalAAState;
class CameraEffectsState;

RenderStep *addPostProcessing(RenderPipeline *pipeline, RenderStep *previousStep, v2f scale, Client *client, TemporalAAState *temporal = nullptr, CameraEffectsState *camera_effects = nullptr);
