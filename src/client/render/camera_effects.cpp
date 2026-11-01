// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "camera_effects.h"
#include "taa.h"
#include "client/camera.h"
#include "client/client.h"
#include "client/renderingengine.h"
#include "settings.h"
#include <ICameraSceneNode.h>

bool cameraEffectsEnabled()
{
	const auto type = RenderingEngine::get_video_driver()->getDriverType();
	return (type == video::EDT_OPENGL || type == video::EDT_OPENGL3) &&
		g_settings->getBool("enable_post_processing") &&
		(g_settings->getBool("enable_camera_motion_blur") ||
		 g_settings->getBool("enable_camera_dof"));
}

CameraEffectsState::CameraEffectsState(v2f render_scale, v2f output_scale,
		irr_ptr<TemporalAAState> temporal) :
	m_render_scale(render_scale), m_pixel_scale(render_scale / output_scale), m_temporal(std::move(temporal))
{}

void CameraEffectsState::prepare(PipelineContext &context)
{
	auto *camera = context.client->getCamera()->getCameraNode();
	// Capture before TAA changes the projection; both matrices describe an unjittered grid.
	camera->updateAbsolutePosition();
	camera->updateMatrices();
	TemporalHistory::CameraFrame frame;
	frame.projection = camera->getProjectionMatrix();
	frame.view = camera->getViewMatrix();
	frame.offset = intToFloat(context.client->getCamera()->getOffset(), BS);
	frame.position = camera->getAbsolutePosition() + frame.offset;
	frame.direction = (camera->getTarget() - camera->getAbsolutePosition()).normalize();
	frame.size = v2u32(context.target_size.X * m_render_scale.X,
		context.target_size.Y * m_render_scale.Y);
	frame.time = context.device->getTimer()->getTime();
	frame.camera_mode = static_cast<int>(context.client->getCamera()->getCameraMode());
	m_history.begin(frame, false);
}

void CameraEffectsState::onSetUniforms(video::IMaterialRendererServices *services)
{
	m_reprojection.set(m_history.reprojection, services);
	m_sky_reprojection.set(m_history.sky_reprojection, services);
	m_inverse_projection.set(m_history.inverse_projection, services);
	m_depth_jitter.set(m_temporal ? m_temporal->getJitter() : v2f(), services);
	m_pixels.set(m_pixel_scale, services);
	const float motion[] = {
		m_history.history_valid ? 1.0f : 0.0f,
		g_settings->getFloat("camera_motion_blur_strength", 0.0f, 2.0f) / m_history.frame_ratio,
		g_settings->getFloat("camera_motion_blur_max", 0.0f, 64.0f),
		float(core::clamp(g_settings->getS32("camera_motion_blur_samples"), 4, 24))
	};
	m_motion_params.set(motion, services);
	const float dof[] = {
		g_settings->getFloat("camera_dof_focus_distance", 0.1f, 1000.0f) * BS,
		g_settings->getFloat("camera_dof_focus_range", 0.0f, 100.0f) * BS,
		g_settings->getFloat("camera_dof_blur", 0.0f, 16.0f)
	};
	m_dof_params.set(dof, services);
}
