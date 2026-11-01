// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "irr_v3d.h"
#include <SColor.h>
#include <algorithm>
#include <cmath>

namespace surface_light {
enum class Source { NONE, SUN, MOON, CUSTOM };
struct Light {
	v3f direction{0, 1, 0}; // Toward the source, in world coordinates.
	v3f color; // Linear native daylight color.
	float strength = 0;
	Source source = Source::NONE;
};

// Illumination is independent of shadow enable/intensity/map coverage. The
// shadow map only supplies visibility in the receiving shader.
inline Light select(v3f sun, v3f moon, bool sun_visible, bool moon_visible,
		v3f custom, video::SColorf daylight)
{
	Light result;
	const bool authored = custom.X != 0 || custom.Y != 0 || custom.Z != 0;
	const bool day = sun.Y >= moon.Y;
	if (!authored && !(day ? sun_visible : moon_visible)) return result;
	v3f direction = authored ? custom : day ? sun : moon;
	if (!std::isfinite(direction.X) || !std::isfinite(direction.Y) || !std::isfinite(direction.Z)) return result;
	const float peak = std::max({std::abs(direction.X), std::abs(direction.Y), std::abs(direction.Z)});
	if (peak == 0 || !std::isfinite(daylight.r) || !std::isfinite(daylight.g) || !std::isfinite(daylight.b)) return result;
	// Scale before normalization, preserving both very small and large API vectors.
	direction /= peak;
	direction.normalize();
	const float elevation = core::clamp(direction.Y * 8.0f, 0.0f, 1.0f);
	result.strength = authored ? 1.0f : elevation * elevation * (3.0f - 2.0f * elevation) * (day ? 1.0f : 0.5f);
	result.direction = direction;
	result.color = v3f(std::pow(std::max(daylight.r, 0.0f), 2.2f),
		std::pow(std::max(daylight.g, 0.0f), 2.2f), std::pow(std::max(daylight.b, 0.0f), 2.2f));
	if (!authored && day) {
		// Restrained sunset warmth for reflected/scattered sunlight. Native baked
		// diffuse remains game controlled. Custom API lights retain their color.
		const float high = core::clamp((direction.Y - 0.02f) / 0.33f, 0.0f, 1.0f);
		const float blend = high * high * (3.0f - 2.0f * high);
		result.color *= v3f(1.0f, 0.7f + 0.3f * blend, 0.45f + 0.55f * blend);
	}
	result.source = authored ? Source::CUSTOM : day ? Source::SUN : Source::MOON;
	return result;
}
} // namespace surface_light
