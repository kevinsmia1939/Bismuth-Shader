// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "taa.h"
#include "client/client.h"
#include "client/camera.h"
#include "client/renderingengine.h"
#include "water_volume.h"
#include "settings.h"
#include <ICameraSceneNode.h>
#include <cmath>

bool temporalAAEnabled()
{
	auto *driver = RenderingEngine::get_video_driver();
	const bool precision_available = driver->getDriverType() != video::EDT_OGLES2 ||
		driver->getLimits().GLVersion.X >= 3;
	return precision_available && g_settings->getBool("enable_post_processing") &&
		g_settings->get("antialiasing") == "taa" &&
		driver->queryFeature(video::EVDF_RENDER_TO_FLOAT_TEXTURE) &&
		driver->queryTextureFormat(video::ECF_A16B16G16R16F);
}

void TemporalAAState::prepare(PipelineContext &context)
{
	auto *camera = context.client->getCamera()->getCameraNode();
	// Stereo offsets change the node position immediately before this step.
	camera->updateAbsolutePosition();
	camera->updateMatrices();
	m_original_projection = camera->getProjectionMatrix();
	TemporalHistory::CameraFrame frame;
	frame.projection = m_original_projection;
	frame.view = camera->getViewMatrix();
	frame.offset = intToFloat(context.client->getCamera()->getOffset(), BS);
	frame.position = camera->getAbsolutePosition() + frame.offset;
	frame.direction = (camera->getTarget() - camera->getAbsolutePosition()).normalize();
	frame.size = v2u32(context.target_size.X * m_scale.X,
		context.target_size.Y * m_scale.Y);
	frame.time = context.device->getTimer()->getTime();
	frame.camera_mode = static_cast<int>(context.client->getCamera()->getCameraMode());
	auto *core = RenderingEngine::get_rendering_core();
	auto *water = core ? core->get_water_volume() : nullptr;
	frame.medium = water && water->containsWater(frame.position) ? 1 : 0;
	m_medium_reactive = float(frame.medium);
	m_history.begin(frame);
	camera->setProjectionMatrix(m_history.projection);
}

void TemporalAAState::finish(PipelineContext &context)
{
	auto *camera = context.client->getCamera()->getCameraNode();
	camera->setProjectionMatrix(m_original_projection);
	camera->updateMatrices();
	m_history.commit();
}

void TemporalAAState::onSetUniforms(video::IMaterialRendererServices *services)
{
	m_reprojection.set(m_history.reprojection, services);
	m_sky_reprojection.set(m_history.sky_reprojection, services);
	m_inverse_projection.set(m_history.inverse_projection, services);
	const float weight = g_settings->getFloat("taa_history_weight", 0.0f, 0.98f);
	const float params[] = { m_history.jitter.X, m_history.jitter.Y,
		m_history.history_valid ? 1.0f : 0.0f, std::pow(weight, m_history.frame_ratio) };
	m_params.set(params, services);
	m_water_reactive.set(&m_medium_reactive, services);
}
