// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/temporal_history.h"
#include <cmath>

static TemporalHistory::CameraFrame testFrame()
{
	TemporalHistory::CameraFrame frame;
	frame.projection.buildProjectionMatrixPerspectiveFovLH(1.2f, 16.0f / 9.0f, 1.0f, 4000.0f, false);
	frame.view.buildCameraLookAtMatrixLH(v3f(0, 10, -20), v3f(0, 10, 0), v3f(0, 1, 0));
	frame.position = v3f(0, 10, -20);
	frame.direction = v3f(0, 0, 1);
	frame.size = v2u32(1280, 720);
	frame.time = 1000;
	return frame;
}

static void project(const core::matrix4 &matrix, float *point)
{
	matrix.multiplyWith1x4Matrix(point);
}

TEST_CASE("Temporal history resets on discontinuities", "[client][render]")
{
	TemporalHistory history;
	auto frame = testFrame();
	history.begin(frame);
	CHECK_FALSE(history.history_valid);
	history.commit();
	frame.time += 16;
	history.begin(frame);
	CHECK(history.history_valid);

	SECTION("resize") { frame.size.X *= 2; }
	SECTION("FOV change") { frame.projection[0] *= 1.1f; }
	SECTION("teleport") { frame.position.X += 100.0f; }
	SECTION("turn") { frame.direction = v3f(0, 0, -1); }
	SECTION("camera mode") { frame.camera_mode = 1; }
	SECTION("liquid interface") { frame.medium = 1; }
	SECTION("long frame gap") { frame.time += 500; }
	history.begin(frame);
	CHECK_FALSE(history.history_valid);
}

TEST_CASE("Temporal history stays aligned across jitter and origin shifts", "[client][render]")
{
	TemporalHistory history;
	auto frame = testFrame();
	// A large absolute coordinate must not leak into current clip-space positions.
	frame.position.X = 2010;
	frame.view.buildCameraLookAtMatrixLH(frame.position, frame.position + v3f(0, 0, 20), v3f(0, 1, 0));
	history.begin(frame);
	history.commit();
	frame.offset = v3f(2000, 0, 0);
	frame.view.buildCameraLookAtMatrixLH(frame.position - frame.offset,
		frame.position - frame.offset + v3f(0, 0, 20), v3f(0, 1, 0));

	for (u32 i = 0; i < 16; ++i) {
		frame.time += 16;
		history.begin(frame);
		CHECK(history.history_valid);
		CHECK(std::abs(history.jitter.X * frame.size.X) <= 0.5f);
		CHECK(std::abs(history.jitter.Y * frame.size.Y) <= 0.5f);
		float current[] = { 10, 10, 20, 1 };
		project(history.projection * frame.view, current);
		for (u32 j = 0; j < 3; ++j)
			current[j] /= current[3];
		current[3] = 1;
		project(history.reprojection, current);
		CHECK(std::abs(current[0] / current[3]) < 0.0001f);
		CHECK(std::abs(current[1] / current[3]) < 0.0001f);
		history.commit();
	}
}

TEST_CASE("Temporal sky rejects camera translation", "[client][render]")
{
	TemporalHistory history;
	auto frame = testFrame();
	history.begin(frame);
	history.commit();
	frame.position += v3f(10, 0, 0);
	frame.view.buildCameraLookAtMatrixLH(frame.position, frame.position + v3f(0, 0, 20), v3f(0, 1, 0));
	frame.time += 16;
	history.begin(frame);
	float direction[] = { history.jitter.X * 2, history.jitter.Y * 2, 1, 1 };
	project(history.sky_reprojection, direction);
	CHECK(std::abs(direction[0] / direction[3]) < 0.0001f);
	CHECK(std::abs(direction[1] / direction[3]) < 0.0001f);
}

TEST_CASE("Camera effects reproject without adding jitter", "[client][render]")
{
	TemporalHistory history;
	auto frame = testFrame();
	history.begin(frame, false);
	CHECK(history.jitter == v2f());
	CHECK(history.projection == frame.projection);
	CHECK_FALSE(history.history_valid);
	const auto previous = frame.projection * frame.view;
	history.commit();
	frame.time += 16;
	frame.position.X += 2;
	frame.view.buildCameraLookAtMatrixLH(frame.position, frame.position + v3f(0, 0, 20), v3f(0, 1, 0));
	history.begin(frame, false);
	REQUIRE(history.history_valid);
	CHECK(history.jitter == v2f());
	float current[] = {0, 10, 10, 1};
	float expected[] = {0, 10, 10, 1};
	project(history.projection * frame.view, current);
	project(previous, expected);
	project(history.reprojection, current);
	CHECK(current[0] / current[3] == Catch::Approx(expected[0] / expected[3]).margin(0.00001));
	CHECK(current[1] / current[3] == Catch::Approx(expected[1] / expected[3]).margin(0.00001));
}
