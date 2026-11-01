// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (C) 2021 Liso <anlismon@gmail.com>

#include "client/shadows/shadowsshadercallbacks.h"
#include "client/renderingengine.h"
#include "settings.h"
#include <algorithm>
#include <cmath>
#include <SMaterial.h>

ShadowUniformSetter::ShadowUniformSetter(bool supports_contact_hardening) :
	m_contact_hardening(supports_contact_hardening &&
		g_settings->getBool("enable_contact_hardening_shadows"))
{}

void ShadowUniformSetter::onSetMaterial(const video::SMaterial &material)
{
	m_bound_shadow_map = material.getTexture(ShadowRenderer::TEXTURE_LAYER_SHADOW);
}

void ShadowUniformSetter::onSetUniforms(video::IMaterialRendererServices *services)
{
	auto *shadow = RenderingEngine::get_shadow_renderer();
	if (!shadow) {
		const f32 disabled = 0.0f;
		m_shadow_strength.set(&disabled, services);
		return;
	}

	const auto &light = shadow->getDirectionalLight();

	core::matrix4 shadowViewProj = light.getProjectionMatrix();
	shadowViewProj *= light.getViewMatrix();
	m_shadow_view_proj.set(shadowViewProj.pointer(), services);

	m_light_direction.set(light.getDirection(), services);

	f32 TextureResolution = light.getMapResolution();
	m_texture_res.set(&TextureResolution, services);

	// Unbound preview/wield materials and unavailable maps retain unshadowed
	// illumination instead of sampling another texture or a stale binding.
	f32 ShadowStrength = shadow->get_texture() && m_bound_shadow_map == shadow->get_texture() ?
		shadow->getShadowStrength() : 0.0f;
	m_shadow_strength.set(&ShadowStrength, services);
	if (ShadowStrength > 0 && !m_reported_bound_map &&
			services->getPixelShaderConstantID("f_shadow_strength") >= 0) {
		infostream << "Surface shadow visibility: map bound" << std::endl;
		m_reported_bound_map = true;
	}

	video::SColor ShadowTint = shadow->getShadowTint();
	m_shadow_tint.set(ShadowTint, services);

	f32 timeOfDay = shadow->getTimeOfDay();
	m_time_of_day.set(&timeOfDay, services);

	f32 shadowFar = shadow->getMaxShadowFar();
	m_shadowfar.set(&shadowFar, services);

	f32 cam_pos[4];
	shadowViewProj.transformVect(cam_pos, light.getPlayerPos());
	m_camera_pos.set(cam_pos, services);

	s32 TextureLayerID = ShadowRenderer::TEXTURE_LAYER_SHADOW;
	m_shadow_texture.set(&TextureLayerID, services);

	f32 bias0 = shadow->getPerspectiveBiasXY();
	m_perspective_bias0_vertex.set(&bias0, services);
	m_perspective_bias0_pixel.set(&bias0, services);
	f32 bias1 = 1.0f - bias0 + 1e-5f;
	m_perspective_bias1_vertex.set(&bias1, services);
	m_perspective_bias1_pixel.set(&bias1, services);
	f32 zbias = shadow->getPerspectiveBiasZ();
	m_perspective_zbias_vertex.set(&zbias, services);
	m_perspective_zbias_pixel.set(&zbias, services);
	if (m_contact_hardening) {
		// Ortho clip Z spans two units. Texture Z additionally scales by zbias/2.
		const auto &projection = light.getProjectionMatrix();
		const f32 pcss_scale[] = {
			2.0f / std::max(std::abs(projection[10] * zbias), 0.000001f),
			2.0f / std::max(std::abs(projection[0]), 0.000001f)
		};
		m_pcss_scale.set(pcss_scale, services);
		const f32 pcss_params[] = {
			std::tan(g_settings->getFloat("shadow_light_angle", 0.0f, 10.0f) * core::DEGTORAD * 0.5f),
			g_settings->getFloat("shadow_blocker_search_distance", 1.0f, 256.0f) * BS
		};
		m_pcss_params.set(pcss_params, services);
	}
}

void ShadowDepthUniformSetter::onSetUniforms(video::IMaterialRendererServices *services)
{
	auto *driver = services->getVideoDriver();

	core::matrix4 lightMVP = driver->getTransform(video::ETS_PROJECTION);
	lightMVP *= driver->getTransform(video::ETS_VIEW);

	f32 cam_pos[4];
	lightMVP.transformVect(cam_pos, CameraPos);

	lightMVP *= driver->getTransform(video::ETS_WORLD);

	m_light_mvp_setting.set(lightMVP, services);
	m_map_resolution_setting.set(&MapRes, services);
	m_max_far_setting.set(&MaxFar, services);
	s32 TextureId = 0;
	m_color_map_sampler_setting.set(&TextureId, services);
	f32 bias0 = PerspectiveBiasXY;
	m_perspective_bias0.set(&bias0, services);
	f32 bias1 = 1.0f - bias0 + 1e-5f;
	m_perspective_bias1.set(&bias1, services);
	f32 zbias = PerspectiveBiasZ;
	m_perspective_zbias.set(&zbias, services);

	m_cam_pos_setting.set(cam_pos, services);
}
