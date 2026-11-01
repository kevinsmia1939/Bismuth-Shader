// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "irr_v3d.h"
#include "voxel_radiance.h"
#include "cloud_field.h"
#include <future>
#include <SColor.h>
#include <unordered_map>

class Client;
namespace video { class IVideoDriver; class ITexture; }

bool voxelLightingEnabled();
bool voxelDynamicDirectEnabled();

class VoxelLighting
{
public:
	static constexpr unsigned int MAX_DYNAMIC_LIGHTS = 8;
	explicit VoxelLighting(video::IVideoDriver *driver) : m_driver(driver),
		m_dynamic_direct(voxelDynamicDirectEnabled()) {}
	~VoxelLighting();
	void update(Client *client, v3f sun_direction, v3f sunlight, u32 time,
		cloud_field::ShadowField clouds = {});
	video::ITexture *getTexture() const { return m_texture; }
	v3s32 getOrigin() const { return m_origin; }
	int getSize() const { return m_size; }
	bool usesDynamicDirect() const { return m_dynamic_direct; }
	const std::vector<voxel_light::DynamicSource> &getDynamicSources() const { return m_frame_sources; }
	double getSolveTime() const { return m_solve_ms; }
	u32 getLightRevision() const { return m_light_revision; }
private:
	struct JobResult { voxel_light::Solution solution; v3s32 origin; };
	void upload(const JobResult &result);
	void refreshGeometry(Client *client);
	std::vector<voxel_light::DynamicSource> collectDynamicSources(Client *client, v3s32 origin, int n);
	video::IVideoDriver *m_driver;
	const bool m_dynamic_direct;
	std::vector<voxel_light::DynamicSource> m_frame_sources;
	int m_frame_count = -1;
	int m_frame_held = -1;
	v3f m_frame_emission;
	video::ITexture *m_texture = nullptr;
	v3s32 m_origin;
	int m_size = 0;
	u32 m_last_update = 0;
	bool m_started = false;
	std::future<JobResult> m_job;
	double m_solve_ms = 0;
	u32 m_light_revision = 0;
	u32 m_geometry_revision = 0;
	bool m_geometry_dirty = true;
	std::vector<std::array<float, 4>> m_optics;
	std::vector<std::array<float, 4>> m_next_optics;
	u32 m_geometry_scans = 0, m_geometry_uploads = 0;
	double m_geometry_total_ms = 0, m_geometry_max_ms = 0;
	int m_source_count = -1;
	v3f m_emission_sum;
	int m_dynamic_source_count = -1;
	int m_held_source_count = -1;
	v3f m_dynamic_emission_sum;
	int m_cloud_active = -1;
	int m_filter_count = -1;
	v3f m_min_transmission{1.0f, 1.0f, 1.0f};
};
