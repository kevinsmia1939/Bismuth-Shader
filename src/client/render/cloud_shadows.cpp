// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "cloud_shadows.h"
#include "secondstage.h"
#include "client/client.h"
#include "client/camera.h"
#include "client/shader.h"
#include "client/renderingengine.h"
#include "settings.h"
#include "log.h"
#include <ISceneManager.h>
#include <ISceneNode.h>
#include <cmath>

bool useCloudShadows()
{
	return useVolumetricClouds() && g_settings->getBool("enable_cloud_shadows") &&
		RenderingEngine::get_video_driver()->getLimits().MaxMaterialTextures >= 8;
}

CloudShadows::CloudShadows(Client *client) : client(client),
	resolution(core::clamp(g_settings->getS32("cloud_shadow_resolution"), 128, 1024)),
	shader_id(client->getShaderSource()->getShaderRaw("cloud_shadows")),
	buffer(std::make_unique<TextureBuffer>()),
	target(std::make_unique<TextureBufferOutput>(buffer.get(), 0)),
	step(std::make_unique<PostProcessingStep>(shader_id, std::vector<u8>{}))
{
	buffer->setTexture(0, core::dimension2du(resolution, resolution), "cloud_light_transmission", video::ECF_A16B16G16R16F);
	step->setCloudNoise(true);
}

CloudShadows::~CloudShadows()
{
	// Entity materials can outlive a rendering-core rebuild.
	const auto *texture = getTexture();
	// Game destroys Client before finalizing RenderingCore; only the device and
	// scene manager remain valid here.
	std::vector<scene::ISceneNode *> nodes{RenderingEngine::get_raw_device()->getSceneManager()->getRootSceneNode()};
	while (!nodes.empty()) {
		auto *node = nodes.back(); nodes.pop_back();
		for (u32 i = 0; i < node->getMaterialCount(); ++i)
			if (node->getMaterial(i).getTexture(7) == texture) node->getMaterial(i).setTexture(7, nullptr);
		for (auto *child : node->getChildren()) nodes.push_back(child);
	}
}

video::ITexture *CloudShadows::getTexture() const { return buffer->getTexture(0); }

void CloudShadows::prepare(const cloud_field::Density &density, v3f direction, bool enabled)
{
	this->density = density;
	frame.prepare(client->getCamera()->getPosition(), density.bottom, density.thickness, direction,
		g_settings->getFloat("cloud_shadow_distance", 16.0f, 1024.0f)*BS, resolution);
	frame.enabled &= enabled;
}

cloud_field::ShadowField CloudShadows::snapshot() const
{
	return {frame, density, resolution,
		g_settings->getFloat("cloud_shadow_strength", 0.0f, 1.0f), ready()};
}

void CloudShadows::render(PipelineContext &context)
{
	auto *driver = context.device->getVideoDriver();
	const auto screen_size = driver->getScreenSize();
	const auto viewport = driver->getViewPort();
	rendered = false;
	frame.enabled = false;
	const auto &shader = client->getShaderSource()->getShaderInfo(shader_id);
	if (shader.material != shader.base_material && g_settings->getFloat("cloud_shadow_strength", 0.0f, 1.0f) > 0.0f) {
		buffer->reset(context);
		if (getTexture()) {
			target->reset(context);
			if (target->getIrrRenderTarget(context)) {
				step->run(context);
				rendered = true;
			}
		}
	}
	// TextureBufferOutput uses OnResize for its offscreen viewport. This pass
	// runs before the main pipeline snapshots screen dimensions, so restore
	// them now rather than letting the 256px cloud map become the scene size.
	// RenderingCore invokes this standalone prepass from the window target.
	driver->setRenderTargetEx(nullptr,video::ECBF_NONE);
	driver->OnResize(screen_size);
	driver->setViewPort(viewport);
	const bool active = ready();
	if (!reported || active != last_active) {
		infostream << "Cloud shadows: " << (active ? "active" : "inactive") << " resolution=" << resolution << std::endl;
		last_active = active;
		reported = true;
	}
}
