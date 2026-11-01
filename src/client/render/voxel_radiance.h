// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "irr_v3d.h"
#include <array>
#include <functional>
#include <vector>

namespace voxel_light {
inline const std::array<v3f, 6> normals = {
	v3f(1,0,0), v3f(-1,0,0), v3f(0,1,0), v3f(0,-1,0), v3f(0,0,1), v3f(0,0,-1)
};
struct Cell {
	v3f albedo{0.5f, 0.5f, 0.5f};
	v3f tint{1.0f, 1.0f, 1.0f};
	v3f emission;
	// Linear RGB transmittance through one node of material (Beer-Lambert).
	v3f transmission{1.0f, 1.0f, 1.0f};
	bool solid = true;
	bool sky = false;
};
struct Field {
	// Irradiance incident on each of six axis-aligned receiver normals.
	std::array<v3f, 6> direct;
	std::array<v3f, 6> indirect;
};
struct DynamicSource {
	// Fractional grid-node coordinates. These sources never change occupancy.
	v3f position;
	v3f emission;
	bool held = false;
};
// Frame-direct lights reserve the held source, then prefer nearby bright actors.
std::vector<DynamicSource> selectDynamicSources(std::vector<DynamicSource> sources,
	v3f center, unsigned int limit);
struct Grid {
	explicit Grid(int dimension) : size(dimension), cells(dimension * dimension * dimension) {}
	int index(int x, int y, int z) const { return x + size * (y + size * z); }
	bool inside(int x, int y, int z) const {
		return x >= 0 && y >= 0 && z >= 0 && x < size && y < size && z < size;
	}
	v3f position(int i) const { return v3f(i % size, (i / size) % size, i / (size * size)); }
	int size;
	std::vector<Cell> cells;
	std::vector<DynamicSource> dynamic_sources;
	bool bake_dynamic_direct = true;
	v3f sun_direction;
	v3f sun_irradiance;
};
struct Solution {
	int size = 0;
	std::vector<Field> fields;
	std::vector<Cell> cells;
	double solve_ms = 0;
	unsigned int source_count = 0;
	v3f emission_sum;
	unsigned int dynamic_source_count = 0;
	unsigned int held_source_count = 0;
	v3f dynamic_emission_sum;
	v3f dynamic_position_sum;
	unsigned int sunlight_faces = 0;
	float min_sun_transmission = 1.0f;
	float max_sun_transmission = 0.0f;
	unsigned int filter_count = 0;
	v3f min_transmission{1.0f, 1.0f, 1.0f};
};
// Bounded, diffuse voxel radiosity. Geometry and radiance are independent of the camera.
// Optional directional attenuation is evaluated at a visible surface in grid-node
// coordinates, before reflection; it never attenuates direct or reflected emission.
Solution solve(Grid grid, unsigned int bounces, unsigned int max_sources = 64,
	const std::function<float(v3f)> &sun_transmission = {});
} // namespace voxel_light
