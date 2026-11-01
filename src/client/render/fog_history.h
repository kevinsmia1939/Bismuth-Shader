// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "cloud_field.h"
#include "temporal_history.h"
#include "voxel_lighting.h"

struct FogRenderParameters
{
	v3f ambient;
	v3f light;
	v3f direction{0, 1, 0};
	float density = 0;
	float distance = 0;
	float height = 0;
	float variation = 0;
	int steps = 0;
	bool ready = false;
	bool shadow_ready = false;
	bool voxel_ready = false;
	v3f voxel_strength;
	float voxel_anisotropy = 0;
	u32 voxel_light_revision = 0;
	unsigned int local_count = 0;
	std::array<voxel_light::DynamicSource, VoxelLighting::MAX_DYNAMIC_LIGHTS> local_sources{};
	cloud_field::ShadowField clouds;
};

class FogHistory
{
public:
	void begin(const TemporalHistory::CameraFrame &frame, const FogRenderParameters &parameters, v2f jitter)
	{
		camera.begin(frame, false);
		current = frame;
		current_parameters = parameters;
		auto projection = frame.projection;
		projection[8] += jitter.X * 2.0f;
		projection[9] += jitter.Y * 2.0f;
		const bool invertible = projection.getInverse(inverse_projection) && frame.view.getInverse(inverse_view);
		current_projection_view = projection * frame.view;
		core::matrix4 shift;
		shift.setTranslation(frame.offset - previous.offset);
		reprojection = previous_projection_view * shift;
		previous_camera = previous.position - frame.offset;
		valid = invertible && camera.history_valid && compatible(parameters, previous_parameters);
	}
	void commit()
	{
		previous = current;
		previous_parameters = current_parameters;
		previous_projection_view = current_projection_view;
		camera.commit();
	}
	static bool compatible(const FogRenderParameters &a, const FogRenderParameters &b)
	{
		if (!a.ready || !b.ready || a.density <= 0 || a.density != b.density ||
			a.distance != b.distance || a.height != b.height || a.variation != b.variation || a.steps != b.steps ||
			a.shadow_ready != b.shadow_ready || a.ambient.getDistanceFromSQ(b.ambient) >= 0.0004f ||
			a.light.getDistanceFromSQ(b.light) >= 0.0004f || a.direction.dotProduct(b.direction) <= 0.999f ||
			a.clouds.ready != b.clouds.ready)
			return false;
		if (a.voxel_ready != b.voxel_ready || (a.voxel_ready &&
			(a.voxel_strength != b.voxel_strength || a.voxel_anisotropy != b.voxel_anisotropy ||
			 a.voxel_light_revision != b.voxel_light_revision ||
			 a.local_count != b.local_count || a.local_count > a.local_sources.size()))) return false;
		if (a.voxel_ready) for (unsigned int i = 0; i < a.local_count; ++i) {
			if (a.local_sources[i].position.getDistanceFromSQ(b.local_sources[i].position) >= 0.01f ||
				a.local_sources[i].emission.getDistanceFromSQ(b.local_sources[i].emission) >= 0.0004f)
				return false;
		}
		if (!a.clouds.ready) return true;
		const auto &x = a.clouds.density;
		const auto &y = b.clouds.density;
		return a.clouds.strength == b.clouds.strength && x.bottom == y.bottom && x.thickness == y.thickness &&
			x.coverage == y.coverage && x.extinction == y.extinction && x.detail == y.detail && x.seed == y.seed &&
			x.wind.getDistanceFromSQ(y.wind) < 1024.0f;
	}
	TemporalHistory camera;
	bool valid = false;
	core::matrix4 inverse_projection;
	core::matrix4 inverse_view;
	core::matrix4 reprojection;
	v3f previous_camera;
private:
	TemporalHistory::CameraFrame current, previous;
	FogRenderParameters current_parameters, previous_parameters;
	core::matrix4 current_projection_view, previous_projection_view;
};
