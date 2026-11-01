// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/cloud_denoise.h"
#include "client/render/fog_denoise.h"

namespace {
class TrackedAA : public TemporalAAState
{
public:
	explicit TrackedAA(bool &destroyed) : TemporalAAState(v2f(1, 1)), destroyed(destroyed) {}
	~TrackedAA() override { destroyed = true; }
private:
	bool &destroyed;
};
}

TEST_CASE("Volume filters retain borrowed AA state through independent teardown", "[client][render][volume]")
{
	for (bool fog_first : {false, true}) {
		bool destroyed = false;
		auto aa = make_irr<TrackedAA>(destroyed);
		auto cloud = make_irr<CloudDenoiseState>(v2f(0.5f, 0.5f), aa.get());
		auto fog = make_irr<FogDenoiseState>(v2f(0.5f, 0.5f), aa.get());
		CHECK(aa->getReferenceCount() == 3);
		aa.reset();
		CHECK_FALSE(destroyed);
		if (fog_first) fog.reset(); else cloud.reset();
		CHECK_FALSE(destroyed);
		if (fog_first) cloud.reset(); else fog.reset();
		CHECK(destroyed);
	}
}
