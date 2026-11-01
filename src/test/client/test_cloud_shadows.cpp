// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/cloud_shadows.h"
#include <cmath>

TEST_CASE("Cloud shadow projection follows the light and snaps to world texels", "[client][render][cloud]")
{
	using Catch::Approx;
	CloudShadowFrame frame;
	frame.prepare(v3f(13, 0, -27), 100, 20, v3f(0, 1, 0), 64, 128);
	REQUIRE(frame.enabled);
	CHECK(frame.origin == v3f(13, 100, -27));
	CHECK(frame.span == 128);
	CHECK(frame.thickness == 20);
	frame.prepare(v3f(13, 0, -27), 100, 20, v3f(0.6f, 0.8f, 0), 64, 128);
	CHECK(frame.origin.X == Approx(88));
	CHECK(frame.origin.Y == 100);
	CHECK(frame.sign == 1);
	frame.prepare(v3f(13, 0, -27), 100, 20, v3f(0.6f, -0.8f, 0), 64, 128);
	CHECK(frame.origin.X == Approx(-77));
	CHECK(frame.origin.Y == 120);
	CHECK(frame.sign == -1);
	frame.prepare(v3f(13.49f, 0, -26.51f), 100, 20, v3f(0, 1, 0), 64, 128);
	CHECK(frame.origin == v3f(13, 100, -27));
	frame.prepare(v3f(13.51f, 0, -26.49f), 100, 20, v3f(0, 1, 0), 64, 128);
	CHECK(frame.origin == v3f(14, 100, -26));
	for (const v3f camera : {v3f(-310005, 500, 309995), v3f(310005, 1500, -309995)}) {
		frame.prepare(camera, 1000, 200, v3f(0.6f, 0.8f, 0), 2560, 256);
		REQUIRE(frame.enabled);
		const float x = camera.X + frame.direction.X*(frame.origin.Y-camera.Y)/frame.direction.Y;
		CHECK(std::abs(x-frame.origin.X) <= frame.span/256*0.5f);
	}
	frame.prepare(v3f(0), 100, 20, v3f(1, 0, 0), 64, 128);
	CHECK_FALSE(frame.enabled);
	frame.prepare(v3f(0), 100, 0, v3f(0, 1, 0), 64, 128);
	CHECK_FALSE(frame.enabled);
	frame.prepare(v3f(0), 100, 20, v3f(0), 64, 128);
	CHECK_FALSE(frame.enabled);
}
