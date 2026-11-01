// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "cloud_field.h"
#include <algorithm>
#include <cmath>

void CloudShadowFrame::prepare(v3f camera, float bottom, float height, v3f light,
		float radius, int resolution)
{
	enabled = false;
	if (height <= 0.0f || radius <= 0.0f || resolution <= 0 || light.getLengthSQ() < 0.000001f)
		return;
	light.normalize();
	if (std::abs(light.Y) < 0.02f)
		return;
	direction = light;
	sign = light.Y > 0 ? 1.0f : -1.0f;
	thickness = height;
	span = radius * 2.0f;
	reciprocalResolution = 1.0f / resolution;
	origin.Y = sign > 0 ? bottom : bottom + height;
	const float t = (origin.Y - camera.Y) / light.Y;
	const float texel = span / resolution;
	origin.X = std::round((camera.X + light.X * t) / texel) * texel;
	origin.Z = std::round((camera.Z + light.Z * t) / texel) * texel;
	enabled = true;
}

namespace cloud_field {
namespace {
float mix(float a, float b, float t) { return a + (b - a) * t; }
float smooth(float a, float b, float x)
{
	const float t = core::clamp((x - a) / (b - a), 0.0f, 1.0f);
	return t * t * (3.0f - 2.0f * t);
}
}

u8 noiseValue(int x, int y, int z)
{
	u32 hash = u32(x & (NOISE_SIZE - 1)) * 0x9e3779b9u ^
		u32(y & (NOISE_SIZE - 1)) * 0x85ebca6bu ^ u32(z & (NOISE_SIZE - 1)) * 0xc2b2ae35u;
	hash ^= hash >> 16;
	hash *= 0x7feb352du;
	hash ^= hash >> 15;
	hash *= 0x846ca68bu;
	hash ^= hash >> 16;
	return hash & 255;
}

float noise(v3f p)
{
	const int x = int(std::floor(p.X)), y = int(std::floor(p.Y)), z = int(std::floor(p.Z));
	const float fx = p.X - x, fy = p.Y - y, fz = p.Z - z;
	auto slice = [&](int layer) {
		return mix(mix(noiseValue(x, y, layer), noiseValue(x + 1, y, layer), fx),
			mix(noiseValue(x, y + 1, layer), noiseValue(x + 1, y + 1, layer), fx), fy);
	};
	return mix(slice(z), slice(z + 1), fz) / 255.0f;
}

float Density::at(v3f position) const
{
	const float h = (position.Y - bottom) / std::max(thickness, 0.001f);
	if (h <= 0.0f || h >= 1.0f || coverage <= 0.0f)
		return 0.0f;
	const v3f p((position.X - wind.X) / 320.0f + seed.X,
		h * 2.0f, (position.Z - wind.Y) / 320.0f + seed.Y);
	const float threshold = mix(1.1f, -0.1f, coverage);
	const float shape = smooth(threshold - 0.1f, threshold + 0.1f, noise(p));
	if (shape <= 0.0f)
		return 0.0f;
	float erosion = 1.0f;
	if (detail > 0.0f)
		erosion = mix(1.0f, core::clamp(noise(p * 3.11f + v3f(17.0f)) * 1.5f + 0.1f, 0.0f, 1.0f), detail);
	return shape * erosion * smooth(0.0f, 0.18f, h) * (1.0f - smooth(0.72f, 1.0f, h));
}

std::array<float, 4> ShadowSampler::texel(int x, int z)
{
	x = core::clamp(x, 0, field.resolution - 1);
	z = core::clamp(z, 0, field.resolution - 1);
	const int key = x + z * field.resolution;
	if (const auto found = cache.find(key); found != cache.end())
		return found->second;
	const auto &frame = field.frame;
	const v3f start = frame.origin + v3f(((x + 0.5f) / field.resolution - 0.5f) * frame.span,
		0, ((z + 0.5f) / field.resolution - 0.5f) * frame.span);
	const float ds = field.density.thickness / std::abs(frame.direction.Y) / 24.0f;
	float tau[3] = {};
	for (int i = 0; i < 24; ++i)
		tau[i / 8] += field.density.at(start + frame.direction * ((i + 0.5f) * ds)) * field.density.extinction * ds;
	std::array<float, 4> result = {std::exp(-std::min(tau[0] + tau[1] + tau[2], 64.0f)),
		std::exp(-std::min(tau[1] + tau[2], 64.0f)), std::exp(-std::min(tau[2], 64.0f)), 1.0f};
	cache.emplace(key, result);
	return result;
}

float ShadowSampler::transmission(v3f position)
{
	const auto &frame = field.frame;
	if (!field.ready || !frame.enabled || field.strength <= 0.0f || field.resolution <= 0 ||
			field.density.coverage <= 0.0f || field.density.extinction <= 0.0f ||
			frame.thickness <= 0.0f || std::abs(frame.direction.Y) < 0.02f)
		return 1.0f;
	const float h = (position.Y - frame.origin.Y) * frame.sign / frame.thickness;
	if (h >= 1.0f)
		return 1.0f;
	const v3f entry = position + frame.direction * ((frame.origin.Y - position.Y) / frame.direction.Y);
	const float u = (entry.X - frame.origin.X) / frame.span + 0.5f;
	const float v = (entry.Z - frame.origin.Z) / frame.span + 0.5f;
	const float edge = std::min({u, v, 1.0f - u, 1.0f - v});
	if (edge <= 0.0f)
		return 1.0f;
	const float x = u * field.resolution - 0.5f, z = v * field.resolution - 0.5f;
	const int ix = int(std::floor(x)), iz = int(std::floor(z));
	const auto a = texel(ix, iz), b = texel(ix + 1, iz), c = texel(ix, iz + 1), d = texel(ix + 1, iz + 1);
	std::array<float, 4> depths;
	for (int i = 0; i < 4; ++i) {
		const float t = mix(mix(a[i], b[i], x - ix), mix(c[i], d[i], x - ix), z - iz);
		depths[i] = -std::log(std::max(t, 0.000001f));
	}
	const float layer = core::clamp(h, 0.0f, 1.0f) * 3.0f;
	const int i = std::min(int(layer), 2);
	const float tau = mix(depths[i], depths[i + 1], layer - i);
	const float strength = field.strength * smooth(0.02f, 0.08f, std::abs(frame.direction.Y)) * smooth(0.0f, 0.04f, edge);
	return mix(1.0f, std::exp(-std::max(tau, 0.0f)), strength);
}
} // namespace cloud_field
