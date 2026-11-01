// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "fog_denoise.h"
#include "client/client.h"
#include "client/camera.h"
#include "client/renderingengine.h"
#include "water_volume.h"
#include "settings.h"
#include "log.h"
#include <ICameraSceneNode.h>

bool useFogDenoising()
{
	return useVolumetricFog() && supportsSceneSurface() && g_settings->getBool("enable_fog_denoising") &&
		RenderingEngine::get_video_driver()->getLimits().MaxMaterialTextures >=
			(temporalAAEnabled() && useVolumetricClouds() ? 6 : 5);
}

void FogDenoiseState::prepare(PipelineContext &context, bool shader_ready)
{
	auto *node = context.client->getCamera()->getCameraNode();
	TemporalHistory::CameraFrame frame;
	const v2f jitter = temporal ? temporal->getJitter() : v2f();
	frame.projection = node->getProjectionMatrix();
	frame.projection[8] -= jitter.X * 2.0f;
	frame.projection[9] -= jitter.Y * 2.0f;
	frame.view = node->getViewMatrix();
	frame.offset = intToFloat(context.client->getCamera()->getOffset(), BS);
	frame.position = node->getAbsolutePosition() + frame.offset;
	frame.direction = (node->getTarget() - node->getAbsolutePosition()).normalize();
	frame.size = v2u32(context.target_size.X * scale.X, context.target_size.Y * scale.Y);
	frame.time = context.device->getTimer()->getTime();
	frame.camera_mode = static_cast<int>(context.client->getCamera()->getCameraMode());
	auto *core = RenderingEngine::get_rendering_core();
	auto *water = core ? core->get_water_volume() : nullptr;
	frame.medium = water && water->containsWater(frame.position) ? 1 : 0;
	auto parameters = core ? core->get_fog_frame() : FogRenderParameters{};
	parameters.ready &= shader_ready;
	history.begin(frame, parameters, jitter);
	const int active = history.valid;
	if (active != reported) {
		infostream << "Fog denoising: history " << (active ? "active" : "reset") << std::endl;
		reported = active;
	}
}

void FogDenoiseState::onSetUniforms(video::IMaterialRendererServices *services)
{
	inverse_projection.set(history.inverse_projection, services);
	inverse_view.set(history.inverse_view, services);
	reprojection.set(history.reprojection, services);
	previous_camera.set(history.previous_camera, services);
	const float data[] = {history.valid ? 1.0f : 0.0f,
		std::pow(g_settings->getFloat("fog_history_weight", 0.0f, 0.95f), history.camera.frame_ratio)};
	params.set(data, services);
}

void PrepareFogDenoiseStep::run(PipelineContext &context)
{
	const auto &shader = context.client->getShaderSource()->getShaderInfo(shader_id);
	state->prepare(context, shader.material != shader.base_material);
}

void FogCompositeState::onSetMaterial(const video::SMaterial &material)
{
	const auto *texture = material.getTexture(1);
	const auto dimensions = texture ? texture->getSize() : core::dimension2du(1, 1);
	size = v2f(dimensions.Width, dimensions.Height);
}
