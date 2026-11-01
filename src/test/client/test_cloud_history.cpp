// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/cloud_history.h"

namespace {
TemporalHistory::CameraFrame cameraFrame()
{
	TemporalHistory::CameraFrame frame;
	frame.projection.buildProjectionMatrixPerspectiveFovLH(1.2f, 16.0f / 9.0f, 1.0f, 4000.0f, false);
	frame.view.buildCameraLookAtMatrixLH(v3f(0, 10, -20), v3f(0, 10, 0), v3f(0, 1, 0));
	frame.position = v3f(0, 10, -20);
	frame.direction = v3f(0, 0, 1);
	frame.size = v2u32(640, 360);
	frame.time = 1000;
	return frame;
}
cloud_field::RenderParameters cloudParameters()
{
	cloud_field::RenderParameters p;
	p.ready = true;
	p.density.bottom = 80;
	p.density.thickness = 80;
	p.density.coverage = 0.7f;
	p.density.extinction = 0.018f;
	p.density.detail = 0.35f;
	p.bright = v3f(0.8f);
	p.ambient = v3f(0.4f);
	p.light_intensity = 1;
	p.distance = 10240;
	p.samples = 32;
	return p;
}
}

TEST_CASE("Cloud history preserves wind motion, jitter and origin rebasing", "[client][render][cloud]")
{
	auto frame = cameraFrame();
	auto parameters = cloudParameters();
	CloudHistory history;
	const v2f first_jitter(0.0002f, -0.0003f);
	history.begin(frame, parameters, first_jitter);
	CHECK_FALSE(history.valid);
	history.commit();
	frame.time += 16;
	frame.offset = v3f(1000, 0, 0);
	frame.position.X = 2;
	frame.view.buildCameraLookAtMatrixLH(v3f(-998, 10, -20), v3f(-998, 10, 0), v3f(0, 1, 0));
	parameters.density.wind = v2f(4, 2);
	history.begin(frame, parameters, v2f(-0.0003f, 0.0001f));
	REQUIRE(history.valid);
	CHECK(history.wind_delta == v2f(4, 2));
	CHECK(history.previous_camera == v3f(-1000, 10, -20));
	// Current absolute anchor (14,100,102) advected from (10,100,100).
	float current[] = {-990, 100, 100, 1};
	history.reprojection.multiplyWith1x4Matrix(current);
	auto first = cameraFrame();
	first.projection[8] += first_jitter.X * 2;
	first.projection[9] += first_jitter.Y * 2;
	float old[] = {10, 100, 100, 1};
	(first.projection * first.view).multiplyWith1x4Matrix(old);
	for (int i = 0; i < 4; ++i)
		CHECK(current[i] == Catch::Approx(old[i]).margin(0.0002));
}

TEST_CASE("Cloud history rejects changed transport and never resurrects a cleared layer", "[client][render][cloud]")
{
	auto frame = cameraFrame();
	auto parameters = cloudParameters();
	CloudHistory history;
	history.begin(frame, parameters, {});
	history.commit();
	frame.time += 16;
	history.begin(frame, parameters, {});
	REQUIRE(history.valid);
	auto changed = parameters;
	for (int i = 0; i < 11; ++i) {
		changed = parameters;
		switch (i) {
		case 0: changed.ready = false; break;
		case 1: changed.density.coverage = 0; break;
		case 2: changed.density.thickness *= 2; break;
		case 3: changed.density.extinction *= 2; break;
		case 4: changed.density.seed.X += 1; break;
		case 5: changed.bright *= 0.5f; break;
		case 6: changed.light_direction = v3f(0, -1, 0); break;
		case 7: changed.light_intensity = 0; break;
		case 8: changed.distance *= 0.5f; break;
		case 9: changed.samples /= 2; break;
		case 10: changed.density.wind.X += 100; break;
		}
		history.begin(frame, changed, {});
		CHECK_FALSE(history.valid);
	}
	changed = parameters;
	changed.density.coverage = 0;
	history.begin(frame, changed, {});
	history.commit();
	frame.time += 16;
	history.begin(frame, parameters, {});
	CHECK_FALSE(history.valid);
	history.commit();
	frame.time += 16;
	history.begin(frame, parameters, {});
	CHECK(history.valid);
	frame.size.X += 1;
	history.begin(frame, parameters, {});
	CHECK_FALSE(history.valid);
}
