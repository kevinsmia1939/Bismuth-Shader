// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "voxel_radiance.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <numeric>

namespace voxel_light {
namespace {
constexpr float PI = 3.14159265359f;
struct Hit { int face = -1; bool sky = false; v3f transmission{1.0f, 1.0f, 1.0f}; };

// Exact traversal of the node-size occupancy grid; never steps through a solid.
Hit trace(const Grid &g, v3f start, v3f direction, float distance, int ignore = -1)
{
	int cell[3];
	int step[3];
	float next[3];
	float increment[3];
	const float p[] = { start.X, start.Y, start.Z };
	const float d[] = { direction.X, direction.Y, direction.Z };
	for (int axis = 0; axis < 3; ++axis) {
		cell[axis] = int(std::floor(p[axis] + 0.5f));
		step[axis] = d[axis] >= 0 ? 1 : -1;
		increment[axis] = std::abs(d[axis]) > 1e-7f ? 1.0f / std::abs(d[axis]) : 1e30f;
		next[axis] = std::abs(d[axis]) > 1e-7f ?
			(cell[axis] + step[axis] * 0.5f - p[axis]) / d[axis] : 1e30f;
	}
	if (!g.inside(cell[0], cell[1], cell[2]))
		return {};
	int current = g.index(cell[0], cell[1], cell[2]);
	if (g.cells[current].solid && current != ignore)
		return {current * 6, false};
	v3f transmission(1.0f);
	float traveled = 0;
	for (int iteration = 0; iteration < g.size * 3 + 3; ++iteration) {
		int axis = next[0] < next[1] ? 0 : 1;
		if (next[2] < next[axis]) axis = 2;
		const float end = std::min(next[axis], distance);
		const float length = std::max(end - traveled, 0.0f);
		const auto filter = g.cells[current].transmission;
		if (current != ignore && length > 0 && filter != v3f(1.0f)) {
			transmission.X *= std::pow(filter.X, length);
			transmission.Y *= std::pow(filter.Y, length);
			transmission.Z *= std::pow(filter.Z, length);
		}
		if (next[axis] > distance) return {-1, false, transmission};
		traveled = end;
		cell[axis] += step[axis];
		next[axis] += increment[axis];
		if (!g.inside(cell[0], cell[1], cell[2]))
			return {-1, g.cells[current].sky, transmission};
		current = g.index(cell[0], cell[1], cell[2]);
		if (g.cells[current].solid && current != ignore)
			return {current * 6 + axis * 2 + (step[axis] > 0 ? 1 : 0), false, transmission};
	}
	return {};
}
struct Source {
	int index;
	v3f position;
	v3f emission;
	float priority;
	bool dynamic = false;
	bool held = false;
};
struct Surface { int face; int adjacent; v3f normal; v3f direct; };

v3f irradiance(const Grid &grid, const std::vector<Source> &sources, v3f p, v3f normal, int self = -1)
{
	v3f sum;
	for (const auto &source : sources) {
		if (self >= 0 && source.index == self) continue;
		v3f delta = source.position - p;
		float distance = delta.getLength();
		if (distance > 16.0f) continue;
		if (distance < 0.01f) { sum += source.emission; continue; }
		const float cosine = normal.dotProduct(delta / distance);
		if (cosine <= 0.0f) continue;
		const auto path = trace(grid, p, delta / distance, distance, source.index);
		if (path.face >= 0) continue;
		float fade = std::max(0.0f, 1.0f - distance / 16.0f);
		sum += source.emission * path.transmission *
			(cosine * fade * fade / std::max(distance * distance, 1.0f));
	}
	return sum;
}

std::array<v3f, 6> probeIrradiance(const Grid &grid, const std::vector<Source> &sources, v3f p)
{
	std::array<v3f, 6> result;
	for (const auto &source : sources) {
		if (source.dynamic && !grid.bake_dynamic_direct) continue;
		v3f delta = source.position - p;
		const float squaredDistance = delta.getLengthSQ();
		if (squaredDistance > 256.0f) continue;
		if (squaredDistance < 0.0001f) {
			for (auto &value : result) value += source.emission;
			continue;
		}
		const float distance = std::sqrt(squaredDistance);
		const v3f direction = delta / distance;
		const auto path = trace(grid, p, direction, distance, source.index);
		if (path.face >= 0) continue;
		const float fade = std::max(0.0f, 1.0f - distance / 16.0f);
		const v3f incident = source.emission * path.transmission *
			(fade * fade / std::max(squaredDistance, 1.0f));
		for (int d = 0; d < 6; ++d)
			result[d] += incident * std::max(normals[d].dotProduct(direction), 0.0f);
	}
	return result;
}
} // namespace

std::vector<DynamicSource> selectDynamicSources(std::vector<DynamicSource> sources,
		v3f center, unsigned int limit)
{
	sources.erase(std::remove_if(sources.begin(), sources.end(), [](const auto &source) {
		const auto p = source.position;
		const auto e = source.emission;
		return !std::isfinite(p.X) || !std::isfinite(p.Y) || !std::isfinite(p.Z) ||
			!std::isfinite(e.getLengthSQ()) || e.getLengthSQ() <= 0 || e.X < 0 || e.Y < 0 || e.Z < 0;
	}), sources.end());
	std::stable_sort(sources.begin(), sources.end(), [&](const auto &a, const auto &b) {
		if (a.held != b.held) return a.held;
		return a.emission.getLengthSQ() / (1 + a.position.getDistanceFromSQ(center)) >
			b.emission.getLengthSQ() / (1 + b.position.getDistanceFromSQ(center));
	});
	if (sources.size() > limit) sources.resize(limit);
	return sources;
}

Solution solve(Grid grid, unsigned int bounces, unsigned int max_sources,
		const std::function<float(v3f)> &sun_transmission)
{
	const auto began = std::chrono::steady_clock::now();
	const int count = int(grid.cells.size());
	Solution result;
	result.size = grid.size;
	result.fields.resize(count);
	std::vector<Source> sources;
	const v3f middle((grid.size - 1) * 0.5f);
	for (int i = 0; i < count; ++i) {
		auto &cell = grid.cells[i];
		cell.albedo.X = core::clamp(cell.albedo.X, 0.0f, 0.85f);
		cell.albedo.Y = core::clamp(cell.albedo.Y, 0.0f, 0.85f);
		cell.albedo.Z = core::clamp(cell.albedo.Z, 0.0f, 0.85f);
		for (int axis = 0; axis < 3; ++axis)
			cell.transmission[axis] = std::isfinite(cell.transmission[axis]) ?
				core::clamp(cell.transmission[axis], 0.0f, 1.0f) : 0.0f;
		if (!cell.solid && cell.transmission != v3f(1.0f)) {
			++result.filter_count;
			for (int axis = 0; axis < 3; ++axis)
				result.min_transmission[axis] = std::min(result.min_transmission[axis], cell.transmission[axis]);
		}
		if (cell.emission.getLengthSQ() > 0.0f) {
			v3f p = grid.position(i);
			bool exposed = !cell.solid;
			for (const auto &normal : normals) {
				const auto neighbor = p + normal;
				if (grid.inside(neighbor.X, neighbor.Y, neighbor.Z) &&
						!grid.cells[grid.index(neighbor.X, neighbor.Y, neighbor.Z)].solid)
					exposed = true;
			}
			if (!exposed) continue;
			sources.push_back({i, p, cell.emission,
				cell.emission.getLengthSQ() / (1.0f + p.getDistanceFromSQ(middle))});
		}
	}
	for (const auto &source : grid.dynamic_sources) {
		const auto p = source.position;
		const auto e = source.emission;
		// Reject unknown/solid locations instead of ignoring the occupied cell:
		// a moving lamp inside a wall must not open a path through that wall.
		if (!std::isfinite(p.X) || !std::isfinite(p.Y) || !std::isfinite(p.Z) ||
				p.X < -0.5f || p.Y < -0.5f || p.Z < -0.5f ||
				p.X >= grid.size - 0.5f || p.Y >= grid.size - 0.5f || p.Z >= grid.size - 0.5f ||
				!std::isfinite(e.X) || !std::isfinite(e.Y) || !std::isfinite(e.Z) ||
				e.X < 0 || e.Y < 0 || e.Z < 0 ||
				!std::isfinite(e.getLengthSQ()) || e.getLengthSQ() <= 0)
			continue;
		const int cell = grid.index(int(std::floor(p.X + 0.5f)),
			int(std::floor(p.Y + 0.5f)), int(std::floor(p.Z + 0.5f)));
		if (grid.cells[cell].solid) continue;
		sources.push_back({-1, p, e, e.getLengthSQ() / (1.0f + p.getDistanceFromSQ(middle)),
			true, source.held});
	}
	std::stable_sort(sources.begin(), sources.end(), [](const Source &a, const Source &b) {
		return a.priority > b.priority;
	});
	if (sources.size() > max_sources) sources.resize(max_sources);
	result.source_count = sources.size();
	for (const auto &source : sources) {
		result.emission_sum += source.emission;
		if (source.dynamic) {
			++result.dynamic_source_count;
			result.held_source_count += source.held;
			result.dynamic_emission_sum += source.emission;
			result.dynamic_position_sum += source.position;
		}
	}
	std::vector<Surface> surfaces;
	std::vector<v3f> radiance(count * 6);
	for (int i = 0; i < count; ++i) {
		const v3f p = grid.position(i);
		if (!grid.cells[i].solid) {
			result.fields[i].direct = probeIrradiance(grid, sources, p);
			continue;
		}
		for (int d = 0; d < 6; ++d) {
			v3f neighbor = p + normals[d];
			if (!grid.inside(neighbor.X, neighbor.Y, neighbor.Z)) continue;
			const int adjacent = grid.index(neighbor.X, neighbor.Y, neighbor.Z);
			if (grid.cells[adjacent].solid) continue;
			const v3f origin = p + normals[d] * 0.501f;
			v3f direct = irradiance(grid, sources, origin, normals[d], i);
			float cosine = std::max(normals[d].dotProduct(grid.sun_direction), 0.0f);
			const auto sunlight = cosine > 0 ? trace(grid, origin, grid.sun_direction, grid.size * 2.0f) : Hit{};
			if (cosine > 0 && sunlight.sky) {
				const float transmission = sun_transmission ? core::clamp(sun_transmission(origin), 0.0f, 1.0f) : 1.0f;
				direct += grid.sun_irradiance * sunlight.transmission * (cosine * transmission);
				++result.sunlight_faces;
				result.min_sun_transmission = std::min(result.min_sun_transmission, transmission);
				result.max_sun_transmission = std::max(result.max_sun_transmission, transmission);
			}
			direct = direct * grid.cells[i].albedo / PI;
			radiance[i * 6 + d] = direct;
			surfaces.push_back({i * 6 + d, adjacent, normals[d], direct});
		}
	}

	std::array<v3f, 14> rays;
	std::copy(normals.begin(), normals.end(), rays.begin());
	int ray_count = 6;
	for (int z : {-1, 1}) for (int y : {-1, 1}) for (int x : {-1, 1})
		rays[ray_count++] = v3f(x, y, z).normalize();
	// Cache geometric visibility once, then transport multiple bounces over it.
	std::vector<std::array<int, 14>> visibility(count);
	std::vector<std::array<v3f, 14>> path_transmission;
	if (result.filter_count) path_transmission.resize(count);
	for (int i = 0; i < count; ++i) {
		visibility[i].fill(-1);
		if (grid.cells[i].solid) continue;
		for (int r = 0; r < 14; ++r) {
			const auto path = trace(grid, grid.position(i), rays[r], grid.size * 2.0f);
			visibility[i][r] = path.face;
			if (!path_transmission.empty()) path_transmission[i][r] = path.transmission;
		}
	}
	for (unsigned int bounce = 0; bounce < std::min(bounces, 4u); ++bounce) {
		for (int i = 0; i < count; ++i) {
			if (grid.cells[i].solid) continue;
			auto &field = result.fields[i].indirect;
			field.fill(v3f());
			for (int r = 0; r < 14; ++r) {
				const int face = visibility[i][r];
				if (face < 0) continue;
				const auto transmission = path_transmission.empty() ? v3f(1.0f) : path_transmission[i][r];
				for (int d = 0; d < 6; ++d)
					field[d] += radiance[face] * transmission *
						(std::max(normals[d].dotProduct(rays[r]), 0.0f) * (4.0f * PI / 14.0f));
			}
		}
		// Jacobi iteration: all air probes above read the previous surface field.
		for (const auto &surface : surfaces) {
			const int d = surface.face % 6;
			radiance[surface.face] = surface.direct +
				grid.cells[surface.face / 6].albedo * result.fields[surface.adjacent].indirect[d] / PI;
		}
	}
	result.cells = std::move(grid.cells);
	result.solve_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - began).count();
	return result;
}
} // namespace voxel_light
