// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "cloud_field.h"
#include "temporal_history.h"
#include <cmath>

// Driver-independent, per-eye cloud history. Texture samples remain on the
// jittered ray grid; only discontinuity validation uses an unjittered projection.
class CloudHistory
{
public:
	void begin(const TemporalHistory::CameraFrame &frame,
		const cloud_field::RenderParameters &parameters, v2f jitter)
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
		wind_delta = parameters.density.wind - previous_parameters.density.wind;
		valid = invertible && camera.history_valid && compatible(parameters, previous_parameters);
	}

	void commit()
	{
		previous = current;
		previous_parameters = current_parameters;
		previous_projection_view = current_projection_view;
		camera.commit();
	}

	static bool compatible(const cloud_field::RenderParameters &a, const cloud_field::RenderParameters &b)
	{
		const auto &x = a.density;
		const auto &y = b.density;
		return a.ready && b.ready && x.coverage > 0 && x.extinction > 0 && x.thickness > 0 &&
			x.bottom == y.bottom && x.thickness == y.thickness && x.coverage == y.coverage &&
			x.extinction == y.extinction && x.detail == y.detail && x.seed == y.seed &&
			a.distance == b.distance && a.samples == b.samples &&
			a.bright.getDistanceFromSQ(b.bright) < 0.0004f &&
			a.ambient.getDistanceFromSQ(b.ambient) < 0.0004f &&
			a.shadow.getDistanceFromSQ(b.shadow) < 0.0004f &&
			a.light_direction.dotProduct(b.light_direction) > 0.999f &&
			std::abs(a.light_intensity - b.light_intensity) < 0.025f &&
			x.wind.getDistanceFromSQ(y.wind) < 1024.0f;
	}

	bool valid = false;
	TemporalHistory camera;
	core::matrix4 inverse_projection;
	core::matrix4 inverse_view;
	core::matrix4 reprojection; // current camera-relative world -> previous clip
	v3f previous_camera; // previous camera relative to the current origin offset
	v2f wind_delta;
private:
	TemporalHistory::CameraFrame current;
	TemporalHistory::CameraFrame previous;
	cloud_field::RenderParameters current_parameters;
	cloud_field::RenderParameters previous_parameters;
	core::matrix4 current_projection_view;
	core::matrix4 previous_projection_view;
};
