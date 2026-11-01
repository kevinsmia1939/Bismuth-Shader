// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include "irr_v2d.h"
#include "irr_v3d.h"
#include <matrix4.h>

// Camera-only temporal reprojection. History is stored on an unjittered grid.
// Independent of the driver so camera-offset and reset rules can be unit tested.
class TemporalHistory
{
public:
	struct CameraFrame {
		core::matrix4 projection;
		core::matrix4 view;
		v3f offset;
		v3f position;
		v3f direction;
		v2u32 size;
		u32 time = 0;
		int camera_mode = 0;
		int medium = 0;
	};

	static float radicalInverse(u32 index, u32 base)
	{
		float result = 0.0f;
		float fraction = 1.0f;
		while (index) {
			fraction /= base;
			result += fraction * (index % base);
			index /= base;
		}
		return result;
	}

	void begin(const CameraFrame &frame, bool enable_jitter = true)
	{
		m_current = frame;
		const u32 elapsed = frame.time - m_previous.time;
		history_valid = m_available && frame.size == m_previous.size &&
			frame.projection.equals(m_previous.projection, 0.00001f) &&
			frame.position.getDistanceFromSQ(m_previous.position) < 6400.0f &&
			frame.direction.dotProduct(m_previous.direction) > 0.5f &&
			frame.camera_mode == m_previous.camera_mode && elapsed < 250;
		history_valid = history_valid && frame.medium == m_previous.medium;
		if (!history_valid)
			m_sequence = 0;
		const u32 sample = m_sequence % 8 + 1;
		jitter = v2f(radicalInverse(sample, 2) - 0.5f,
			radicalInverse(sample, 3) - 0.5f);
		jitter.X /= core::max_(frame.size.X, 1u);
		jitter.Y /= core::max_(frame.size.Y, 1u);
		if (!enable_jitter)
			jitter = v2f();
		projection = frame.projection;
		projection[8] += jitter.X * 2.0f;
		projection[9] += jitter.Y * 2.0f;
		core::matrix4 inverse_current;
		m_invertible = projection.getInverse(inverse_projection) &&
			(projection * frame.view).getInverse(inverse_current);
		if (!m_invertible)
			history_valid = false;
		core::matrix4 offset_change;
		offset_change.setTranslation(frame.offset - m_previous.offset);
		reprojection = m_previous.projection * m_previous.view * offset_change * inverse_current;

		// Infinite sky follows camera rotation but has no translation/parallax.
		core::matrix4 previous_rotation = m_previous.view;
		core::matrix4 current_rotation = frame.view;
		previous_rotation.setTranslation(v3f());
		current_rotation.setTranslation(v3f());
		core::matrix4 inverse_rotation;
		current_rotation.getInverse(inverse_rotation);
		sky_reprojection = m_previous.projection * previous_rotation *
			inverse_rotation * inverse_projection;
		frame_ratio = core::clamp(elapsed / (1000.0f / 60.0f), 0.25f, 8.0f);
	}

	void commit()
	{
		m_previous = m_current;
		m_available = m_invertible;
		++m_sequence;
	}

	bool history_valid = false;
	float frame_ratio = 1.0f;
	v2f jitter;
	core::matrix4 projection;
	core::matrix4 inverse_projection;
	core::matrix4 reprojection;
	core::matrix4 sky_reprojection;

private:
	CameraFrame m_current;
	CameraFrame m_previous;
	bool m_available = false;
	bool m_invertible = false;
	u32 m_sequence = 0;
};
