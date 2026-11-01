// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/fog_history.h"

namespace {
TemporalHistory::CameraFrame fogCamera()
{
	TemporalHistory::CameraFrame frame;
	frame.projection.buildProjectionMatrixPerspectiveFovLH(1.2f, 16.0f / 9.0f, 1, 4000, false);
	frame.view.buildCameraLookAtMatrixLH(v3f(0, 10, -20), v3f(0, 10, 0), v3f(0, 1, 0));
	frame.position = v3f(0, 10, -20); frame.direction = v3f(0, 0, 1);
	frame.size = v2u32(640, 360); frame.time = 1000;
	return frame;
}
FogRenderParameters fogParameters()
{
	FogRenderParameters p;
	p.ready = true; p.density = 0.0003f; p.distance = 1280; p.height = 640;
	p.variation = 0.35f; p.steps = 24; p.ambient = v3f(0.4f); p.light = v3f(0.8f);
	return p;
}
}

TEST_CASE("Fog history keeps finite world anchors across jitter and origin changes", "[client][render][fog]")
{
	auto frame = fogCamera(); auto params = fogParameters();
	FogHistory history;
	const v2f jitter(0.0002f, -0.0003f);
	history.begin(frame, params, jitter);
	CHECK_FALSE(history.valid); history.commit();
	frame.time += 16; frame.offset = v3f(1000, 0, 0); frame.position.X = 2;
	frame.view.buildCameraLookAtMatrixLH(v3f(-998, 10, -20), v3f(-998, 10, 0), v3f(0, 1, 0));
	history.begin(frame, params, v2f(-0.0003f, 0.0001f));
	REQUIRE(history.valid);
	CHECK(history.previous_camera == v3f(-1000, 10, -20));
	float current[] = {-990, 40, 100, 1}; history.reprojection.multiplyWith1x4Matrix(current);
	auto first = fogCamera(); first.projection[8] += jitter.X * 2; first.projection[9] += jitter.Y * 2;
	float old[] = {10, 40, 100, 1}; (first.projection * first.view).multiplyWith1x4Matrix(old);
	for (int i = 0; i < 4; ++i) CHECK(current[i] == Catch::Approx(old[i]).margin(0.0002));
}

TEST_CASE("Fog history invalidates changed media and light without reviving bypassed history", "[client][render][fog]")
{
	auto frame = fogCamera(); auto params = fogParameters();
	FogHistory history; history.begin(frame, params, {}); history.commit(); frame.time += 16;
	history.begin(frame, params, {}); REQUIRE(history.valid);
	for (int i = 0; i < 10; ++i) {
		auto changed = params;
		switch (i) {
		case 0: changed.ready = false; break;
		case 1: changed.density = 0; break;
		case 2: changed.distance /= 2; break;
		case 3: changed.height /= 2; break;
		case 4: changed.variation = 0; break;
		case 5: changed.steps /= 2; break;
		case 6: changed.light = v3f(0); break;
		case 7: changed.direction = v3f(0, -1, 0); break;
		case 8: changed.shadow_ready = true; break;
		case 9: changed.clouds.ready = true; break;
		}
		history.begin(frame, changed, {}); CHECK_FALSE(history.valid);
	}
	auto disabled = params; disabled.ready = false;
	history.begin(frame, disabled, {}); history.commit(); frame.time += 16;
	history.begin(frame, params, {}); CHECK_FALSE(history.valid);
	history.commit(); frame.time += 16; history.begin(frame, params, {}); CHECK(history.valid);
	frame.medium = 1; history.begin(frame, params, {}); CHECK_FALSE(history.valid);
	frame.medium = 0; frame.size.X += 1; history.begin(frame, params, {}); CHECK_FALSE(history.valid);
}

TEST_CASE("Fog history rejects changed voxel and moving lamp lighting", "[client][render][fog]")
{
	auto frame = fogCamera(); auto params = fogParameters();
	params.voxel_ready = true;
	params.voxel_strength = v3f(0.5f, 1, 0.5f);
	params.voxel_light_revision = 1;
	params.local_count = 1;
	params.local_sources[0] = {v3f(2, 3, 4), v3f(1, 0.5f, 0.2f), true};
	FogHistory history;
	history.begin(frame, params, {}); history.commit(); frame.time += 16;
	history.begin(frame, params, {}); REQUIRE(history.valid);
	for (int i = 0; i < 7; ++i) {
		auto changed = params;
		switch (i) {
		case 0: changed.voxel_ready = false; break;
		case 1: changed.voxel_strength.X = 0; break;
		case 2: ++changed.voxel_light_revision; break;
		case 3: changed.local_count = 0; break;
		case 4: changed.local_sources[0].position.X += 0.5f; break;
		case 5: changed.local_sources[0].emission = v3f(0, 1, 0); break;
		case 6: changed.voxel_anisotropy = 0.5f; break;
		}
		history.begin(frame, changed, {}); CHECK_FALSE(history.valid);
	}
	auto invalid = params; invalid.local_count = invalid.local_sources.size() + 1;
	CHECK_FALSE(FogHistory::compatible(invalid, invalid));
	// Small motion uses the shader's radiance clipping/response instead of
	// resetting volume history on every fractional source movement.
	auto small = params; small.local_sources[0].position.X += 0.01f;
	history.begin(frame, small, {}); CHECK(history.valid);
	// Source positions are absolute node coordinates, independent of origin rebasing.
	frame.offset = v3f(1000, 0, 0);
	history.begin(frame, params, {}); CHECK(history.valid);
}
