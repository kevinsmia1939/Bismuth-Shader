// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (C) 2010-2013 celeron55, Perttu Ahola <celeron55@gmail.com>
// Copyright (C) 2017 numzero, Lobachevskiy Vitaliy <numzer0@yandex.ru>

#include "core.h"

#include "pipeline.h"
#include "voxel_lighting.h"
#include "volumetric_clouds.h"
#include "cloud_shadows.h"
#include "water_volume.h"
#include "client/shader.h"
#include "settings.h"
#include "log.h"
#include "client/shadows/dynamicshadowsrender.h"

RenderingCore::RenderingCore(IrrlichtDevice *_device, Client *_client, Hud *_hud,
		std::unique_ptr<ShadowRenderer> _shadow_renderer,
		std::unique_ptr<RenderPipeline> _pipeline,
		v2f _virtual_size_scale)
	: device(_device), client(_client), hud(_hud), shadow_renderer(std::move(_shadow_renderer)),
	pipeline(std::move(_pipeline)), virtual_size_scale(_virtual_size_scale)
{
	if (waterVolumeEnabled())
		water_volume = std::make_unique<WaterVolume>(device->getVideoDriver());
	else if (g_settings->getBool("enable_water_volume"))
		warningstream << "Water volume lighting requires post processing, translucent liquids, desktop OpenGL, "
			"seven texture units, float textures and 4096-pixel dimensions; retaining native liquid effects." << std::endl;
	if (useVolumetricClouds())
		cloud_noise = std::make_unique<CloudNoise>(device->getVideoDriver());
	else if (g_settings->getBool("enable_volumetric_clouds"))
		warningstream << "Volumetric clouds require desktop OpenGL, float targets and five textures; "
			"using native clouds." << std::endl;
	if (voxelLightingEnabled())
		voxel_lighting = std::make_unique<VoxelLighting>(device->getVideoDriver());
	else if (g_settings->getBool("enable_voxel_lighting"))
		warningstream << "Voxel lighting requires desktop OpenGL and RGBA32F textures; "
			"using native lighting." << std::endl;
	if (useCloudShadows())
		cloud_shadows = std::make_unique<CloudShadows>(client);
}

RenderingCore::~RenderingCore() = default;

void RenderingCore::draw(video::SColor _skycolor, bool _show_hud,
		bool _draw_wield_tool, bool _draw_crosshair, v3f sun_direction, v3f sunlight)
{
	if (water_volume)
		water_volume->update(client, device->getTimer()->getTime());
	water_medium_applied = false;
	water_medium_handled = false;
	v2u32 screensize = device->getVideoDriver()->getScreenSize();
	virtual_size = v2u32(screensize.X * virtual_size_scale.X, screensize.Y * virtual_size_scale.Y);

	PipelineContext context(device, client, hud, shadow_renderer.get(), _skycolor, screensize);
	context.draw_crosshair = _draw_crosshair;
	context.draw_wield_tool = _draw_wield_tool;
	context.show_hud = _show_hud;
	if (cloud_shadows)
		cloud_shadows->render(context);
	// The worker snapshots the same field that generated this frame's cloud map.
	if (voxel_lighting)
		voxel_lighting->update(client, sun_direction, sunlight, device->getTimer()->getTime(),
			cloud_shadows ? cloud_shadows->snapshot() : cloud_field::ShadowField{});

	pipeline->reset(context);
	pipeline->run(context);
}

v2u32 RenderingCore::getVirtualSize() const
{
	return virtual_size;
}
