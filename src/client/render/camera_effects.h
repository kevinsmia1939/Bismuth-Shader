// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "pipeline.h"
#include "client/shader.h"
#include "temporal_history.h"
#include "taa.h"

bool cameraEffectsEnabled();

// One instance per eye; no texture readbacks or input-device control.
class CameraEffectsState : public IShaderUniformSetterRC
{
public:
	CameraEffectsState(v2f render_scale, v2f output_scale, irr_ptr<TemporalAAState> temporal);
	void prepare(PipelineContext &context);
	void finish() { m_history.commit(); }
	void onSetUniforms(video::IMaterialRendererServices *services) override;
private:
	TemporalHistory m_history;
	v2f m_render_scale;
	v2f m_pixel_scale;
	irr_ptr<TemporalAAState> m_temporal;
	CachedPixelShaderSetting<float, 16> m_reprojection{"cameraReprojection"};
	CachedPixelShaderSetting<float, 16> m_sky_reprojection{"cameraSkyReprojection"};
	CachedPixelShaderSetting<float, 16> m_inverse_projection{"cameraInverseProjection"};
	CachedPixelShaderSetting<float, 2> m_depth_jitter{"cameraDepthJitter"};
	CachedPixelShaderSetting<float, 2> m_pixels{"cameraPixelScale"};
	CachedPixelShaderSetting<float, 4> m_motion_params{"cameraMotionParams"};
	CachedPixelShaderSetting<float, 3> m_dof_params{"cameraDOFParams"};
};

class PrepareCameraEffectsStep : public TrivialRenderStep
{
public:
	explicit PrepareCameraEffectsStep(irr_ptr<CameraEffectsState> state) : m_state(std::move(state)) {}
	void run(PipelineContext &context) override { m_state->prepare(context); }
private:
	irr_ptr<CameraEffectsState> m_state;
};

class FinishCameraEffectsStep : public TrivialRenderStep
{
public:
	explicit FinishCameraEffectsStep(irr_ptr<CameraEffectsState> state) : m_state(std::move(state)) {}
	void run(PipelineContext &) override { m_state->finish(); }
private:
	irr_ptr<CameraEffectsState> m_state;
};
