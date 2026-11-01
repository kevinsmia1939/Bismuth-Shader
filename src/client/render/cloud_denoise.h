// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "cloud_history.h"
#include "taa.h"

bool useCloudDenoising();

class CloudDenoiseState : public IShaderUniformSetterRC
{
public:
	// The AA state is borrowed from the eye pipeline; retain a secondary reference.
	CloudDenoiseState(v2f scale, TemporalAAState *temporal) :
		scale(scale), temporal(::grab(temporal)) {}
	void prepare(PipelineContext &context, bool shader_ready);
	void finish() { history.commit(); }
	void onSetUniforms(video::IMaterialRendererServices *services) override;
private:
	v2f scale;
	irr_ptr<TemporalAAState> temporal;
	CloudHistory history;
	int reported = -1;
	CachedPixelShaderSetting<float, 16> inverse_projection{"cloudInverseProjection"};
	CachedPixelShaderSetting<float, 16> inverse_view{"cloudInverseView"};
	CachedPixelShaderSetting<float, 16> reprojection{"cloudReprojection"};
	CachedPixelShaderSetting<float, 3> previous_camera{"cloudPreviousCamera"};
	CachedPixelShaderSetting<float, 2> wind_delta{"cloudWindDelta"};
	CachedPixelShaderSetting<float, 2> params{"cloudHistoryParams"};
};

class PrepareCloudDenoiseStep : public TrivialRenderStep
{
public:
	PrepareCloudDenoiseStep(irr_ptr<CloudDenoiseState> state, u32 shader_id) :
		state(std::move(state)), shader_id(shader_id) {}
	void run(PipelineContext &context) override;
private:
	irr_ptr<CloudDenoiseState> state;
	u32 shader_id;
};

class FinishCloudDenoiseStep : public TrivialRenderStep
{
public:
	explicit FinishCloudDenoiseStep(irr_ptr<CloudDenoiseState> state) : state(std::move(state)) {}
	void run(PipelineContext &) override { state->finish(); }
private:
	irr_ptr<CloudDenoiseState> state;
};
