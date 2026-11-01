// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/voxel_radiance.h"
#include "client/render/cloud_field.h"
#include <cmath>
#include <limits>

namespace {
voxel_light::Grid room(int size = 11)
{
	voxel_light::Grid grid(size);
	for (int z = 1; z < size-1; ++z) for (int y = 1; y < size-1; ++y) for (int x = 1; x < size-1; ++x)
		grid.cells[grid.index(x,y,z)].solid = false;
	return grid;
}
float energy(const std::array<v3f, 6> &directions)
{
	float sum = 0;
	for (const auto &v : directions) sum += v.X + v.Y + v.Z;
	return sum;
}
}

TEST_CASE("Voxel lighting transports colored emission and respects opaque walls", "[client][render][voxel]")
{
	auto grid = room();
	auto &emitter = grid.cells[grid.index(2,3,4)];
	emitter.solid = true;
	emitter.emission = v3f(2,0,0);
	for (int z = 1; z < 10; ++z) for (int y = 1; y < 10; ++y)
		grid.cells[grid.index(5,y,z)].solid = true;
	auto solution = voxel_light::solve(grid, 2);
	const auto &near = solution.fields[grid.index(3,3,4)];
	CHECK(near.direct[1].X > 0.1f);
	CHECK(near.direct[1].Y == 0.0f);
	CHECK(near.direct[1].Z == 0.0f);
	const auto &blocked = solution.fields[grid.index(7,3,4)];
	CHECK(energy(blocked.direct) == 0.0f);
	CHECK(energy(blocked.indirect) == 0.0f);
}

TEST_CASE("Voxel radiosity inherits material color and supports multiple bounces", "[client][render][voxel]")
{
	auto grid = room();
	for (auto &cell : grid.cells) cell.albedo = v3f(0.8f, 0.02f, 0.02f);
	auto &emitter = grid.cells[grid.index(3,3,3)];
	emitter.solid = true;
	emitter.emission = v3f(2.0f);
	emitter.albedo = v3f();
	const int receiver = grid.index(7,4,5);
	auto one = voxel_light::solve(grid, 1);
	auto two = voxel_light::solve(grid, 2);
	CHECK(energy(two.fields[receiver].indirect) > energy(one.fields[receiver].indirect));
	float red = 0, blue = 0;
	for (const auto &v : two.fields[receiver].indirect) { red += v.X; blue += v.Z; }
	CHECK(red > 0.001f);
	CHECK(red > blue * 5.0f);
	for (const auto &field : two.fields)
		for (const auto &v : field.indirect) {
			REQUIRE(std::isfinite(v.X));
			REQUIRE(v.X >= 0.0f);
		}
}

TEST_CASE("Voxel sunlight bounces from surfaces and is blocked by a roof", "[client][render][voxel]")
{
	voxel_light::Grid grid(9);
	for (auto &cell : grid.cells) { cell.solid = false; cell.sky = true; }
	for (int z = 0; z < 9; ++z) for (int x = 0; x < 9; ++x) {
		auto &floor = grid.cells[grid.index(x,2,z)];
		floor.solid = true; floor.albedo = v3f(0.8f,0.01f,0.01f);
	}
	grid.sun_direction = v3f(0,1,0);
	grid.sun_irradiance = v3f(1.0f);
	const int receiver = grid.index(4,4,4);
	auto open = voxel_light::solve(grid, 2);
	CHECK(energy(open.fields[receiver].direct) == 0.0f);
	CHECK(open.fields[receiver].indirect[3].X > 0.05f);
	CHECK(open.fields[receiver].indirect[3].X > open.fields[receiver].indirect[3].Z * 5);
	for (int z = 0; z < 9; ++z) for (int x = 0; x < 9; ++x)
		grid.cells[grid.index(x,6,z)].solid = true;
	auto roof = voxel_light::solve(grid, 2);
	CHECK(energy(roof.fields[receiver].indirect) == 0.0f);
}

TEST_CASE("Voxel bounce lights around a corner without direct light leakage", "[client][render][voxel]")
{
	auto grid = room(13);
	auto &emitter = grid.cells[grid.index(3,3,3)];
	emitter.solid = true;
	emitter.emission = v3f(2,0,0);
	emitter.albedo = v3f();
	for (int y = 1; y < 12; ++y) for (int z = 1; z <= 5; ++z)
		grid.cells[grid.index(6,y,z)].solid = true;
	const int receiver = grid.index(9,3,3);
	auto reflected = voxel_light::solve(grid, 2);
	CHECK(energy(reflected.fields[receiver].direct) == 0.0f);
	CHECK(energy(reflected.fields[receiver].indirect) > 0.000001f);
	// Removing surface reflectance removes the indirect path, not its occluder.
	for (auto &cell : grid.cells) cell.albedo = v3f();
	auto absorbed = voxel_light::solve(grid, 2);
	CHECK(energy(absorbed.fields[receiver].direct) == 0.0f);
	CHECK(energy(absorbed.fields[receiver].indirect) == 0.0f);
}

TEST_CASE("Clouds attenuate sunlight injection and its bounces without dimming lamps", "[client][render][voxel][cloud]")
{
	voxel_light::Grid grid(9);
	for (auto &cell : grid.cells) { cell.solid = false; cell.sky = true; }
	for (int z = 0; z < 9; ++z) for (int x = 0; x < 9; ++x) {
		auto &floor = grid.cells[grid.index(x, 1, z)];
		floor.solid = true;
		floor.albedo = v3f(0.65f, 0.2f, 0.1f);
	}
	grid.sun_direction = v3f(0, 1, 0);
	grid.sun_irradiance = v3f(1.0f);
	const int receiver = grid.index(4, 3, 4);
	const auto open = voxel_light::solve(grid, 3);
	unsigned int calls = 0;
	const auto dim = voxel_light::solve(grid, 3, 64, [&](v3f position) {
		CHECK(position.Y == Catch::Approx(1.501f));
		++calls;
		return 0.25f;
	});
	CHECK(calls == dim.sunlight_faces);
	CHECK(calls == 81);
	CHECK(energy(open.fields[receiver].indirect) > 0.01f);
	CHECK(energy(dim.fields[receiver].indirect) == Catch::Approx(energy(open.fields[receiver].indirect) * 0.25f));

	// The actual procedural field feeds the solver at the reflecting surface.
	cloud_field::ShadowField clouds;
	clouds.ready = true;
	clouds.strength = 1.0f;
	clouds.resolution = 128;
	clouds.density.bottom = 100;
	clouds.density.thickness = 80;
	clouds.density.coverage = 1;
	clouds.density.extinction = 0.1f;
	clouds.frame.prepare(v3f(40, 30, 40), 100, 80, v3f(0, 1, 0), 640, 128);
	cloud_field::ShadowSampler sampler(clouds);
	auto sample = [&](v3f p) { return sampler.transmission(p * 10.0f); };
	const auto overcast = voxel_light::solve(grid, 3, 64, sample);
	CHECK(energy(overcast.fields[receiver].indirect) < energy(open.fields[receiver].indirect) * 0.003f);
	CHECK(overcast.min_sun_transmission < 0.003f);
	CHECK(overcast.max_sun_transmission < 0.003f);

	// Only red emission remains under a fully blocked directional source.
	grid.cells[grid.index(2, 3, 3)].emission = v3f(2, 0, 0);
	const auto mixed = voxel_light::solve(grid, 3, 64, [](v3f) { return 0.0f; });
	grid.sun_irradiance = v3f(0);
	const auto lamp = voxel_light::solve(grid, 3);
	CHECK(energy(lamp.fields[receiver].direct) > 0.01f);
	CHECK(energy(lamp.fields[receiver].indirect) > 0.001f);
	for (size_t i = 0; i < lamp.fields.size(); ++i) for (int d = 0; d < 6; ++d) {
		CHECK(mixed.fields[i].direct[d] == lamp.fields[i].direct[d]);
		CHECK(mixed.fields[i].indirect[d] == lamp.fields[i].indirect[d]);
	}
}

TEST_CASE("Moving colored voxel sources retain fractional positions and bounce", "[client][render][voxel]")
{
	auto grid = room();
	grid.dynamic_sources.push_back({v3f(3.25f, 4, 4), v3f(2, 0.5f, 0), true});
	const int receiver = grid.index(5, 4, 4);
	const auto first = voxel_light::solve(grid, 2);
	REQUIRE(first.source_count == 1);
	CHECK(first.dynamic_source_count == 1);
	CHECK(first.held_source_count == 1);
	CHECK(first.dynamic_emission_sum == v3f(2, 0.5f, 0));
	CHECK(first.dynamic_position_sum == v3f(3.25f, 4, 4));
	const float distance = 1.75f;
	const float expected = 2 * std::pow(1 - distance / 16, 2) / (distance * distance);
	CHECK(first.fields[receiver].direct[1].X == Catch::Approx(expected));
	CHECK(first.fields[receiver].direct[1].Y == Catch::Approx(expected * 0.25f));
	CHECK(first.fields[receiver].direct[1].Z == 0);
	CHECK(energy(first.fields[receiver].indirect) > 0.001f);
	grid.dynamic_sources[0].position.X += 0.25f;
	const auto moved = voxel_light::solve(grid, 2);
	CHECK(moved.fields[receiver].direct[1].X > first.fields[receiver].direct[1].X);
	// Point sources neither voxelize an object nor turn its air cell into an
	// emissive material: that would suppress native shading on other receivers.
	for (size_t i = 0; i < grid.cells.size(); ++i) {
		CHECK(first.cells[i].solid == grid.cells[i].solid);
		CHECK(first.cells[i].emission == v3f());
	}
}

TEST_CASE("Moving voxel lamps respect walls and cannot tunnel from solid cells", "[client][render][voxel]")
{
	auto grid = room();
	for (int z = 1; z < 10; ++z) for (int y = 1; y < 10; ++y)
		grid.cells[grid.index(5, y, z)].solid = true;
	grid.dynamic_sources.push_back({v3f(3.25f, 4, 4), v3f(0, 0, 2)});
	auto lit = voxel_light::solve(grid, 2);
	CHECK(energy(lit.fields[grid.index(4, 4, 4)].direct) > 0.1f);
	CHECK(energy(lit.fields[grid.index(7, 4, 4)].direct) == 0);
	CHECK(energy(lit.fields[grid.index(7, 4, 4)].indirect) == 0);
	grid.dynamic_sources[0].position.X = 5.1f;
	const auto buried = voxel_light::solve(grid, 2);
	CHECK(buried.source_count == 0);
	for (const auto &field : buried.fields) {
		CHECK(energy(field.direct) == 0);
		CHECK(energy(field.indirect) == 0);
	}
}

TEST_CASE("Dynamic voxel source changes and removal replace complete snapshots", "[client][render][voxel]")
{
	auto grid = room();
	grid.dynamic_sources.push_back({v3f(3, 4.25f, 4), v3f(2, 0, 0)});
	const int receiver = grid.index(5, 4, 4);
	const auto red = voxel_light::solve(grid, 2);
	grid.dynamic_sources[0].emission = v3f(0, 2, 0);
	const auto green = voxel_light::solve(grid, 2);
	CHECK(red.fields[receiver].direct[1].X > 0.1f);
	CHECK(green.fields[receiver].direct[1].X == 0);
	CHECK(green.fields[receiver].direct[1].Y > 0.1f);
	grid.dynamic_sources.clear();
	const auto removed = voxel_light::solve(grid, 2);
	CHECK(removed.dynamic_source_count == 0);
	CHECK(removed.held_source_count == 0);
	CHECK(removed.dynamic_emission_sum == v3f());
	for (const auto &field : removed.fields) {
		CHECK(energy(field.direct) == 0);
		CHECK(energy(field.indirect) == 0);
	}
}

TEST_CASE("Map and moving voxel sources share a bounded priority budget", "[client][render][voxel]")
{
	auto grid = room(9);
	grid.cells[grid.index(1, 1, 1)].emission = v3f(2, 0, 0);
	grid.dynamic_sources.push_back({v3f(4.25f, 4, 4), v3f(0, 2, 0), true});
	grid.dynamic_sources.push_back({v3f(7, 7, 7), v3f(0, 0, 2)});
	const auto one = voxel_light::solve(grid, 1, 1);
	CHECK(one.source_count == 1);
	CHECK(one.dynamic_source_count == 1);
	CHECK(one.held_source_count == 1);
	CHECK(one.emission_sum == v3f(0, 2, 0));
	const auto two = voxel_light::solve(grid, 1, 2);
	CHECK(two.source_count == 2);
	CHECK(two.dynamic_source_count == 1);
	CHECK(two.emission_sum == v3f(2, 2, 0));
	const auto zero = voxel_light::solve(grid, 1, 0);
	CHECK(zero.source_count == 0);
	CHECK(zero.dynamic_source_count == 0);
}

TEST_CASE("Dynamic voxel sources reject invalid and outside positions or emission", "[client][render][voxel]")
{
	auto grid = room(7);
	const float nan = std::numeric_limits<float>::quiet_NaN();
	const float inf = std::numeric_limits<float>::infinity();
	for (const auto p : {v3f(nan, 3, 3), v3f(3, inf, 3), v3f(-1, 3, 3), v3f(7, 3, 3)})
		grid.dynamic_sources.push_back({p, v3f(2)});
	for (const auto e : {v3f(nan), v3f(inf), v3f(-1, 2, 0), v3f()})
		grid.dynamic_sources.push_back({v3f(3), e});
	const auto result = voxel_light::solve(grid, 1);
	CHECK(result.source_count == 0);
	CHECK(result.dynamic_source_count == 0);
	for (const auto &field : result.fields) CHECK(energy(field.direct) == 0);
}

TEST_CASE("Voxel transmission attenuates map and moving lamps by thickness", "[client][render][voxel]")
{
	for (const bool moving : {false, true}) {
		auto grid = room();
		if (moving) grid.dynamic_sources.push_back({v3f(2, 4, 4), v3f(2)});
		else grid.cells[grid.index(2, 4, 4)].emission = v3f(2);
		const int receiver = grid.index(8, 4, 4);
		const auto clear = voxel_light::solve(grid, 0);
		const v3f filter(0.8f, 0.5f, 0.25f);
		for (int x : {5, 6}) {
			for (int y = 1; y < 10; ++y) for (int z = 1; z < 10; ++z)
				grid.cells[grid.index(x, y, z)].transmission = filter;
			const auto shaded = voxel_light::solve(grid, 0);
			CHECK(shaded.filter_count == unsigned((x - 4) * 81));
			CHECK(shaded.min_transmission == filter);
			for (int c = 0; c < 3; ++c)
				CHECK(shaded.fields[receiver].direct[1][c] == Catch::Approx(
					clear.fields[receiver].direct[1][c] * std::pow(filter[c], x - 4)));
		}
	}
}

TEST_CASE("Voxel transmission integrates slanted paths and partial source cells", "[client][render][voxel]")
{
	auto grid = room();
	const v3f filter(0.8f, 0.5f, 0.25f);
	grid.dynamic_sources.push_back({v3f(2, 3, 3), v3f(2)});
	const int receiver = grid.index(8, 6, 3);
	const auto clear = voxel_light::solve(grid, 0);
	for (int y = 1; y < 10; ++y) for (int z = 1; z < 10; ++z)
		grid.cells[grid.index(5, y, z)].transmission = filter;
	const auto angled = voxel_light::solve(grid, 0);
	const float path_length = std::sqrt(45.0f) / 6.0f;
	for (int c = 0; c < 3; ++c)
		CHECK(angled.fields[receiver].direct[1][c] == Catch::Approx(
			clear.fields[receiver].direct[1][c] * std::pow(filter[c], path_length)));

	grid.dynamic_sources[0].position = v3f(5.25f, 4, 4);
	const auto partial = voxel_light::solve(grid, 0);
	for (auto &cell : grid.cells) cell.transmission = v3f(1);
	const auto partial_clear = voxel_light::solve(grid, 0);
	const int straight_receiver = grid.index(8, 4, 4);
	for (int c = 0; c < 3; ++c)
		CHECK(partial.fields[straight_receiver].direct[1][c] == Catch::Approx(
			partial_clear.fields[straight_receiver].direct[1][c] * std::pow(filter[c], 0.25f)));
}

TEST_CASE("Optical filters cannot open opaque walls or amplify light", "[client][render][voxel]")
{
	auto grid = room();
	grid.dynamic_sources.push_back({v3f(2, 4, 4), v3f(2)});
	const int receiver = grid.index(8, 4, 4);
	const auto clear = voxel_light::solve(grid, 0);
	for (int y = 1; y < 10; ++y) for (int z = 1; z < 10; ++z)
		grid.cells[grid.index(5, y, z)].transmission = v3f(0, 0.5f, 2.0f);
	const auto black_channel = voxel_light::solve(grid, 0);
	CHECK(black_channel.fields[receiver].direct[1].X == 0);
	CHECK(black_channel.fields[receiver].direct[1].Z == clear.fields[receiver].direct[1].Z);
	for (int y = 1; y < 10; ++y) for (int z = 1; z < 10; ++z) {
		auto &cell = grid.cells[grid.index(5, y, z)];
		cell.solid = true;
		cell.transmission = v3f(1);
	}
	const auto wall = voxel_light::solve(grid, 0);
	CHECK(energy(wall.fields[receiver].direct) == 0);
}

TEST_CASE("Reflected voxel light is filtered on both transport legs", "[client][render][voxel]")
{
	auto grid = room();
	for (auto &cell : grid.cells) cell.albedo = v3f();
	for (int y = 1; y < 10; ++y) for (int z = 1; z < 10; ++z) {
		auto &wall = grid.cells[grid.index(8, y, z)];
		wall.solid = true;
		wall.albedo = v3f(0.6f);
	}
	grid.dynamic_sources.push_back({v3f(2, 4, 4), v3f(2)});
	const int receiver = grid.index(3, 4, 4);
	const auto clear = voxel_light::solve(grid, 1);
	for (int y = 1; y < 10; ++y) for (int z = 1; z < 10; ++z)
		grid.cells[grid.index(5, y, z)].transmission = v3f(1, 0.5f, 0.25f);
	const auto filtered = voxel_light::solve(grid, 1);
	const auto bounced = filtered.fields[receiver].indirect[0];
	REQUIRE(bounced.X > 0.001f);
	CHECK(bounced.X == Catch::Approx(clear.fields[receiver].indirect[0].X));
	CHECK(bounced.Y <= bounced.X * 0.25001f);
	CHECK(bounced.Z <= bounced.X * 0.06251f);
	CHECK(filtered.fields[receiver].direct[1] == clear.fields[receiver].direct[1]);
}

TEST_CASE("Voxel sunlight injection combines colored transmission with cloud attenuation", "[client][render][voxel]")
{
	voxel_light::Grid grid(9);
	for (auto &cell : grid.cells) { cell.solid = false; cell.sky = true; }
	for (int x = 0; x < 9; ++x) for (int z = 0; z < 9; ++z)
		grid.cells[grid.index(x, 1, z)].solid = true;
	grid.sun_direction = v3f(0, 1, 0);
	grid.sun_irradiance = v3f(1);
	const int receiver = grid.index(4, 3, 4);
	const auto clear = voxel_light::solve(grid, 1);
	const v3f filter(0.8f, 0.4f, 0.2f);
	for (int x = 0; x < 9; ++x) for (int z = 0; z < 9; ++z)
		grid.cells[grid.index(x, 6, z)].transmission = filter;
	const auto filtered = voxel_light::solve(grid, 1, 64, [](v3f) { return 0.5f; });
	REQUIRE(energy(clear.fields[receiver].indirect) > 0.01f);
	for (int c = 0; c < 3; ++c)
		CHECK(filtered.fields[receiver].indirect[3][c] == Catch::Approx(
			clear.fields[receiver].indirect[3][c] * filter[c] * 0.5f));
	CHECK(filtered.sunlight_faces == clear.sunlight_faces);
}

TEST_CASE("Replacing optical cells restores unfiltered voxel light", "[client][render][voxel]")
{
	auto grid = room();
	grid.dynamic_sources.push_back({v3f(2, 4, 4), v3f(2)});
	const int receiver = grid.index(8, 4, 4);
	const auto clear = voxel_light::solve(grid, 2);
	for (int y = 1; y < 10; ++y) for (int z = 1; z < 10; ++z)
		grid.cells[grid.index(5, y, z)].transmission = v3f(0.8f, 0.1f, 0.1f);
	const auto filtered = voxel_light::solve(grid, 2);
	CHECK(filtered.fields[receiver].direct[1].Y < clear.fields[receiver].direct[1].Y);
	for (auto &cell : grid.cells) cell.transmission = v3f(1);
	const auto restored = voxel_light::solve(grid, 2);
	CHECK(restored.filter_count == 0);
	for (size_t i = 0; i < restored.fields.size(); ++i) {
		CHECK(restored.fields[i].direct == clear.fields[i].direct);
		CHECK(restored.fields[i].indirect == clear.fields[i].indirect);
	}
}

TEST_CASE("Frame-direct voxel lights retain their bounce without baking direct light twice", "[client][render][voxel]")
{
	auto grid = room();
	grid.dynamic_sources.push_back({v3f(2.25f, 4, 4), v3f(2, 0, 0), true});
	grid.cells[grid.index(7, 4, 4)].emission = v3f(0, 2, 0);
	const auto baked = voxel_light::solve(grid, 2);
	grid.bake_dynamic_direct = false;
	const auto frame_direct = voxel_light::solve(grid, 2);
	const int receiver = grid.index(4, 4, 4);
	CHECK(baked.fields[receiver].direct[1].X > 0.1f);
	CHECK(frame_direct.fields[receiver].direct[1].X == 0);
	CHECK(frame_direct.fields[receiver].direct[0].Y == baked.fields[receiver].direct[0].Y);
	CHECK(frame_direct.fields[receiver].direct[0].Y > 0.1f);
	CHECK(frame_direct.source_count == baked.source_count);
	CHECK(frame_direct.dynamic_source_count == baked.dynamic_source_count);
	CHECK(energy(frame_direct.fields[receiver].indirect) > 0.01f);
	for (size_t i = 0; i < baked.fields.size(); ++i)
		CHECK(frame_direct.fields[i].indirect == baked.fields[i].indirect);
}

TEST_CASE("Frame-direct source selection reserves held light and bounds actor cost", "[client][render][voxel]")
{
	using voxel_light::DynamicSource;
	std::vector<DynamicSource> candidates = {
		{v3f(7, 4, 4), v3f(2, 0, 0), true},
		{v3f(6, 4, 4), v3f(0, 2, 0)},
		{v3f(4.25f, 4, 4), v3f(0, 0, 2)},
		{v3f(4), v3f(-2)},
		{v3f(std::numeric_limits<float>::quiet_NaN()), v3f(2)},
		{v3f(4), v3f()}
	};
	const auto selected = voxel_light::selectDynamicSources(candidates, v3f(4), 2);
	REQUIRE(selected.size() == 2);
	CHECK(selected[0].held);
	CHECK(selected[1].position == v3f(4.25f, 4, 4));
	CHECK(voxel_light::selectDynamicSources(candidates, v3f(4), 0).empty());
	CHECK(voxel_light::selectDynamicSources(candidates, v3f(4), 8).size() == 3);
}
