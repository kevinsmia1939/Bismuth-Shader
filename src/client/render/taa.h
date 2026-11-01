// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include "pipeline.h"
#include "client/shader.h"
#include "temporal_history.h"

bool temporalAAEnabled();

class TemporalAAState : public IShaderUniformSetterRC
{
public:
	explicit TemporalAAState(v2f scale) : m_scale(scale) {}
	void prepare(PipelineContext &context);
	void finish(PipelineContext &context);
	v2f getJitter() const { return m_history.jitter; }
	void onSetUniforms(video::IMaterialRendererServices *services) override;
private:
	TemporalHistory m_history;
	core::matrix4 m_original_projection;
	v2f m_scale;
	float m_medium_reactive = 0.0f;
	CachedPixelShaderSetting<float, 16> m_reprojection{"taaReprojection"};
	CachedPixelShaderSetting<float, 16> m_sky_reprojection{"taaSkyReprojection"};
	CachedPixelShaderSetting<float, 16> m_inverse_projection{"taaInverseProjection"};
	CachedPixelShaderSetting<float, 4> m_params{"taaParams"};
	CachedPixelShaderSetting<float> m_water_reactive{"taaWaterReactive"};
};

class PrepareTAAStep : public TrivialRenderStep
{
public:
	explicit PrepareTAAStep(irr_ptr<TemporalAAState> state) : m_state(std::move(state)) {}
	void run(PipelineContext &context) override { m_state->prepare(context); }
private:
	irr_ptr<TemporalAAState> m_state;
};

class FinishTAAStep : public TrivialRenderStep
{
public:
	explicit FinishTAAStep(irr_ptr<TemporalAAState> state) : m_state(std::move(state)) {}
	void run(PipelineContext &context) override { m_state->finish(context); }
private:
	irr_ptr<TemporalAAState> m_state;
};
