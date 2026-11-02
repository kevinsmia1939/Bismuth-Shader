// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (C) 2010-2013 celeron55, Perttu Ahola <celeron55@gmail.com>
// Copyright (C) 2017 numzero, Lobachevskiy Vitaliy <numzer0@yandex.ru>

#pragma once
#include "core.h"
#include "pipeline.h"

/**
 * Implements a pipeline step that renders the 3D scene
 */
class Draw3D : public RenderStep
{
public:
	virtual void setRenderSource(RenderSource *) override {}
	virtual void setRenderTarget(RenderTarget *target) override { m_target = target; }

	virtual void reset(PipelineContext &context) override {}
	virtual void run(PipelineContext &context) override;
	void setAuxiliaryClearTarget(RenderTarget *target) { m_auxiliary_clear = target; }
	void setWaterCapture(TextureBufferOutput *target, TextureBuffer *buffer,
			u8 color, u8 depth)
	{
		m_water_target = target;
		m_water_buffer = buffer;
		m_water_color = color;
		m_water_depth = depth;
	}

private:
	RenderTarget *m_target {nullptr};
	RenderTarget *m_auxiliary_clear = nullptr;
	TextureBufferOutput *m_water_target = nullptr;
	TextureBuffer *m_water_buffer = nullptr;
	u8 m_water_color = 0;
	u8 m_water_depth = 0;
};

class DrawWield : public RenderStep
{
public:
	virtual void setRenderSource(RenderSource *) override {}
	virtual void setRenderTarget(RenderTarget *target) override { m_target = target; }

	virtual void reset(PipelineContext &context) override {}
	virtual void run(PipelineContext &context) override;

private:
	RenderTarget *m_target {nullptr};
};

/**
 * Implements a pipeline step that renders the game HUD
 */
class DrawHUD : public RenderStep
{
public:
	virtual void setRenderSource(RenderSource *) override {}
	virtual void setRenderTarget(RenderTarget *) override {}

	virtual void reset(PipelineContext &context) override {}
	virtual void run(PipelineContext &context) override;
};

class MapPostFxStep : public TrivialRenderStep
{
public:
	virtual void setRenderTarget(RenderTarget *) override;
	virtual void run(PipelineContext &context) override;
private:
	RenderTarget *target;
};

class RenderShadowMapStep : public TrivialRenderStep
{
public:
	virtual void run(PipelineContext &context) override;
};

/**
 * UpscaleStep step performs rescaling of the image
 * in the source texture 0 to the size of the target.
 */
class UpscaleStep : public RenderStep
{
public:

	virtual void setRenderSource(RenderSource *source) override { m_source = source; }
	virtual void setRenderTarget(RenderTarget *target) override { m_target = target; }
	virtual void reset(PipelineContext &context) override {};
	virtual void run(PipelineContext &context) override;
private:
	RenderSource *m_source;
	RenderTarget *m_target;
};

std::unique_ptr<RenderStep> create3DStage(Client *client, v2f scale, v2f output_scale = v2f(1.0f));
RenderStep* addUpscaling(RenderPipeline *pipeline, RenderStep *previousStep, v2f downscale_factor, Client *client);

void populatePlainPipeline(RenderPipeline *pipeline, Client *client);

video::ECOLOR_FORMAT selectColorFormat(video::IVideoDriver *driver);
video::ECOLOR_FORMAT selectDepthFormat(video::IVideoDriver *driver);
