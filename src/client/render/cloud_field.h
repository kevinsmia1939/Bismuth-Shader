// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "irr_v2d.h"
#include "irr_v3d.h"
#include <array>
#include <unordered_map>

struct CloudShadowFrame
{
	v3f origin; // absolute world coordinates, center of the entry plane
	v3f direction{0, 1, 0};
	float thickness = 0;
	float span = 1;
	float sign = 1;
	float reciprocalResolution = 1;
	bool enabled = false;
	void prepare(v3f camera, float bottom, float height, v3f light, float radius, int resolution);
};

namespace cloud_field {
constexpr int NOISE_SIZE = 32;
u8 noiseValue(int x, int y, int z);
float noise(v3f position);

// Immutable values shared with common/volumetric_clouds.glsl. World units.
struct Density
{
	float bottom = 0;
	float thickness = 0;
	float coverage = 0;
	float extinction = 0;
	float detail = 0;
	v2f wind;
	v2f seed;
	float at(v3f position) const;
};

struct ShadowField
{
	CloudShadowFrame frame;
	Density density;
	int resolution = 256;
	float strength = 0;
	bool ready = false;
};

// Current visible-volume uniforms, copied by the cloud pass for per-eye history.
struct RenderParameters
{
	Density density;
	v3f bright;
	v3f ambient;
	v3f shadow;
	v3f light_direction{0, 1, 0};
	float light_intensity = 0;
	float distance = 0;
	int samples = 0;
	bool ready = false;
};

// Worker-local sparse evaluation of the GPU transmission map, without readback.
// Generated texels are cached across all surface injections in one solve.
class ShadowSampler
{
public:
	explicit ShadowSampler(ShadowField field) : field(field) {}
	float transmission(v3f position);
private:
	std::array<float, 4> texel(int x, int z);
	ShadowField field;
	std::unordered_map<int, std::array<float, 4>> cache;
};
} // namespace cloud_field
