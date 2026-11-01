// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "irr_v3d.h"
#include <cmath>
#include <array>

// CPU counterpart of common/water_waves.glsl. Keep the lattice/hash arithmetic
// in float, like the vertex shader, including at negative world coordinates.
namespace WaterWaves {
inline float noise(v3f p)
{
	const auto mod = [](float x) { return x - std::floor(x / 289.0f) * 289.0f; };
	const auto perm = [&](float x) { return mod(((x * 34.0f) + 1.0f) * x); };
	const auto mix = [](float a, float b, float t) { return a * (1.0f - t) + b * t; };
	v3f a, d;
	for (int i = 0; i < 3; ++i) {
		const float cell = std::floor(p[i]);
		a[i] = mod(cell);
		d[i] = p[i] - cell;
		d[i] = d[i] * d[i] * (3.0f - 2.0f * d[i]);
	}
	float z[2];
	for (int k = 0; k < 2; ++k) {
		float y[2];
		for (int j = 0; j < 2; ++j) {
			float x[2];
			for (int i = 0; i < 2; ++i) {
				const float value = perm(perm(perm(a.X + i) + a.Y + j) + a.Z + k) * (1.0f / 41.0f);
				x[i] = value - std::floor(value);
			}
			y[j] = mix(x[0], x[1], d.X);
		}
		z[k] = mix(y[0], y[1], d.Y);
	}
	return mix(z[0], z[1], d.Z);
}

inline float height(v3f absolute, v3f waves)
{
	if (waves.X <= 0.0f) return 0.0f;
	for (int axis : {0, 2}) {
		const float period = std::floor(std::fmax(waves.Y, 0.1f) *
			(axis == 0 ? 867.0f : 578.0f) * 32.0f + 0.5f) / 32.0f;
		absolute[axis] = (absolute[axis] - std::floor(absolute[axis] / period) * period) * (289.0f / period);
	}
	absolute.Y *= 1.0f / 64.0f;
	absolute.Z += waves.Z;
	return (noise(absolute) - 1.0f) * waves.X * 5.0f;
}

// Height of the actual two mesh triangles, not a new noise sample at the
// interpolated fragment. min is the absolute lower X/Z corner and rest Y.
// Optional corner heights are in node units above min.Y, before displacement.
inline float surface(v3f min, float x, float z, v3f waves, const std::array<float, 4> &rest)
{
	const float b = rest[1]*10.0f + height(min + v3f(10, rest[1]*10.0f, 0), waves);
	const float c = rest[2]*10.0f + height(min + v3f(0, rest[2]*10.0f, 10), waves);
	if (x + z <= 1.0f) {
		const float a = rest[0]*10.0f + height(min + v3f(0, rest[0]*10.0f, 0), waves);
		return min.Y + a + (b - a) * x + (c - a) * z;
	}
	const float d = rest[3]*10.0f + height(min + v3f(10, rest[3]*10.0f, 10), waves);
	return min.Y + b + c - d + (d - c) * x + (d - b) * z;
}

inline float surface(v3f min, float x, float z, v3f waves)
{
	return surface(min, x, z, waves, {0, 0, 0, 0});
}
}
