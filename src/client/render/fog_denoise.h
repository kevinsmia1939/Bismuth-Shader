// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "fog_history.h"
#include "taa.h"

bool useFogDenoising();

class FogDenoiseState : public IShaderUniformSetterRC
{
public:
	// The AA state is borrowed from the eye pipeline; retain a secondary reference.
	FogDenoiseState(v2f scale, TemporalAAState *temporal) :
		scale(scale), temporal(::grab(temporal)) {}
	void prepare(PipelineContext &context, bool shader_ready);
	void finish() { history.commit(); }
	void onSetUniforms(video::IMaterialRendererServices *services) override;
private:
	v2f scale;
	irr_ptr<TemporalAAState> temporal;
	FogHistory history;
	int reported = -1;
	CachedPixelShaderSetting<float, 16> inverse_projection{"fogInverseProjection"};
	CachedPixelShaderSetting<float, 16> inverse_view{"fogInverseView"};
	CachedPixelShaderSetting<float, 16> reprojection{"fogReprojection"};
	CachedPixelShaderSetting<float, 3> previous_camera{"fogPreviousCamera"};
	CachedPixelShaderSetting<float, 2> params{"fogHistoryParams"};
};

class PrepareFogDenoiseStep : public TrivialRenderStep
{
public:
	PrepareFogDenoiseStep(irr_ptr<FogDenoiseState> state, u32 shader_id) : state(std::move(state)), shader_id(shader_id) {}
	void run(PipelineContext &context) override;
private:
	irr_ptr<FogDenoiseState> state;
	u32 shader_id;
};
class FinishFogDenoiseStep : public TrivialRenderStep
{
public:
	explicit FinishFogDenoiseStep(irr_ptr<FogDenoiseState> state) : state(std::move(state)) {}
	void run(PipelineContext &) override { state->finish(); }
private:
	irr_ptr<FogDenoiseState> state;
};

class FogCompositeState : public IShaderUniformSetterRC
{
public:
	void onSetMaterial(const video::SMaterial &material) override;
	void onSetUniforms(video::IMaterialRendererServices *services) override { texture_size.set(size, services); }
private:
	v2f size;
	CachedPixelShaderSetting<float, 2> texture_size{"fogTextureSize"};
};
