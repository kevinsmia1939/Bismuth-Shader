// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (C) 2010-2013 celeron55, Perttu Ahola <celeron55@gmail.com>
// Copyright (C) 2017 numzero, Lobachevskiy Vitaliy <numzer0@yandex.ru>

#pragma once

#include "irr_v2d.h"
#include "irr_v3d.h"
#include "cloud_field.h"
#include "fog_history.h"
#include <SColor.h>
#include <memory>

class IrrlichtDevice;

class ShadowRenderer;
class Client;
class Hud;
class RenderPipeline;
class VoxelLighting;
class CloudNoise;
class CloudShadows;
class WaterVolume;
namespace video { class ITexture; }

class RenderingCore
{
protected:
	IrrlichtDevice *device;
	Client *client;
	Hud *hud;
	std::unique_ptr<ShadowRenderer> shadow_renderer;

	std::unique_ptr<RenderPipeline> pipeline;
	std::unique_ptr<VoxelLighting> voxel_lighting;
	std::unique_ptr<CloudNoise> cloud_noise;
	std::unique_ptr<CloudShadows> cloud_shadows;
	std::unique_ptr<WaterVolume> water_volume;

	v2f virtual_size_scale;
	v2u32 virtual_size { 0, 0 };
	video::ITexture *water_color = nullptr;
	video::ITexture *water_depth = nullptr;
	bool water_medium_applied = false;
	bool water_medium_handled = false;
	cloud_field::RenderParameters cloud_frame;
	FogRenderParameters fog_frame;

public:
	RenderingCore(IrrlichtDevice *device, Client *client, Hud *hud,
			std::unique_ptr<ShadowRenderer> shadow_renderer,
			std::unique_ptr<RenderPipeline> pipeline,
			v2f virtual_size_scale);
	RenderingCore(const RenderingCore &) = delete;
	RenderingCore(RenderingCore &&) = delete;
	virtual ~RenderingCore();

	RenderingCore &operator=(const RenderingCore &) = delete;
	RenderingCore &operator=(RenderingCore &&) = delete;

	void draw(video::SColor _skycolor, bool _show_hud,
			bool _draw_wield_tool, bool _draw_crosshair, v3f sun_direction, v3f sunlight);

	v2u32 getVirtualSize() const;

	VoxelLighting *get_voxel_lighting() { return voxel_lighting.get(); }
	CloudNoise *get_cloud_noise() { return cloud_noise.get(); }
	CloudShadows *get_cloud_shadows() { return cloud_shadows.get(); }
	void set_cloud_frame(const cloud_field::RenderParameters &value) { cloud_frame = value; }
	const cloud_field::RenderParameters &get_cloud_frame() const { return cloud_frame; }
	void set_fog_frame(const FogRenderParameters &value) { fog_frame = value; }
	const FogRenderParameters &get_fog_frame() const { return fog_frame; }
	WaterVolume *get_water_volume() { return water_volume.get(); }
	void set_water_medium_applied(bool value) { water_medium_applied = value; }
	bool is_water_medium_applied() const { return water_medium_applied; }
	void set_water_medium_handled(bool value) { water_medium_handled = value; }
	bool is_water_medium_handled() const { return water_medium_handled; }
	void set_water_scene(video::ITexture *color, video::ITexture *depth)
	{
		water_color = color;
		water_depth = depth;
	}
	video::ITexture *get_water_color() { return water_color; }
	video::ITexture *get_water_depth() { return water_depth; }

	ShadowRenderer *get_shadow_renderer() { return shadow_renderer.get(); };
};
