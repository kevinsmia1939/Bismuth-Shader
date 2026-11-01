// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/water_volume.h"
#include "client/render/water_waves.h"
#include "client/liquid_geometry.h"
#include "client/node_visuals.h"
#include "nodedef.h"
#include "mapnode.h"

TEST_CASE("Water geometry distinguishes liquids, partial flow, solid and unknown cells", "[client][render][water]")
{
	NodeDefManager ndef;
	const auto makeWater = [](const char *name) {
		ContentFeatures water;
		water.name = name;
		water.drawtype = NDT_LIQUID;
		water.liquid_type = LIQUID_SOURCE;
		water.alpha = ALPHAMODE_BLEND;
		water.light_propagates = true;
		water.param_type = CPT_LIGHT;
		water.waving = 3;
		water.post_effect_color = video::SColor(64, 12, 34, 56);
		return water;
	};
	const auto source = ndef.set("test:water", makeWater("test:water"));
	MapNode node(source, 15, 0);
	CHECK(WaterVolume::eligible(node, &ndef));
	CHECK(WaterVolume::encodeCell(node, &ndef) == video::SColor(64, 255, 255, 255));
	auto water = makeWater("test:flow");
	water.drawtype = NDT_FLOWINGLIQUID;
	water.liquid_type = LIQUID_FLOWING;
	water.param_type_2 = CPT2_FLOWINGLIQUID;
	water.liquid_range = 8;
	water.waving = 0;
	const auto flow = ndef.set("test:flow", std::move(water));
	const auto shallow = WaterVolume::encodeCell(MapNode(flow, 0, 0), &ndef);
	CHECK(shallow.getRed() == 224);
	CHECK(shallow.getGreen() == 16);
	CHECK(WaterVolume::encodeCell(MapNode(flow, 0, 7), &ndef).getGreen() == 239);
	CHECK(WaterVolume::encodeCell(MapNode(flow, 0, LIQUID_FLOW_DOWN_MASK), &ndef).getGreen() == 255);
	water = makeWater("test:waving_flow");
	water.drawtype = NDT_FLOWINGLIQUID;
	water.liquid_type = LIQUID_FLOWING;
	water.liquid_range = 8;
	const auto waving_flow = ndef.set("test:waving_flow", std::move(water));
	const auto flowing_cell = WaterVolume::encodeCell(MapNode(waving_flow), &ndef);
	CHECK(WaterVolume::eligible(MapNode(waving_flow), &ndef));
	CHECK(flowing_cell.getRed() == 240); // Waving flow uses its four rest-height corners.
	CHECK(flowing_cell.getGreen() == 16);
	water = makeWater("test:lava");
	water.light_source = 14;
	const auto lava = ndef.set("test:lava", std::move(water));
	CHECK_FALSE(WaterVolume::eligible(MapNode(lava), &ndef));
	CHECK(WaterVolume::encodeCell(MapNode(lava), &ndef).getRed() == 128);
	water = makeWater("test:opaque");
	water.light_source = 0;
	water.alpha = ALPHAMODE_OPAQUE;
	const auto opaque = ndef.set("test:opaque", std::move(water));
	CHECK_FALSE(WaterVolume::eligible(MapNode(opaque), &ndef));
	water = makeWater("test:clipped");
	water.alpha = ALPHAMODE_CLIP;
	const auto clipped = ndef.set("test:clipped", std::move(water));
	CHECK_FALSE(WaterVolume::eligible(MapNode(clipped), &ndef));
	CHECK(WaterVolume::encodeCell(MapNode(CONTENT_IGNORE), &ndef) == video::SColor(0));
	CHECK(WaterVolume::encodeCell(MapNode(CONTENT_AIR), &ndef).getRed() == 64);
	CHECK(WaterVolume::encodeCell(MapNode(CONTENT_UNKNOWN), &ndef).getRed() == 128);
}

TEST_CASE("Flow corners share source, shore, falling and unloaded-neighbor rules", "[client][render][water]")
{
	using Catch::Approx;
	constexpr content_t source = 10, flow = 11, stone = 12;
	LiquidGeometry::Neighbor neighbors[3][3];
	for (int z = 0; z < 3; ++z) for (int x = 0; x < 3; ++x)
		neighbors[z][x] = LiquidGeometry::neighbor(MapNode(flow, 0, x+2*z),
			MapNode(CONTENT_AIR), source, flow, 8);
	const auto heights = LiquidGeometry::cornerHeights(neighbors, source, flow);
	CHECK(heights == std::array<float, 4>{0.25f, 0.375f, 0.5f, 0.625f});
	neighbors[0][0] = LiquidGeometry::neighbor(MapNode(source), MapNode(CONTENT_AIR), source, flow, 8);
	CHECK(LiquidGeometry::cornerLevel(neighbors, 0, 0, source, flow) == 0.5f);
	CHECK(LiquidGeometry::cornerLevel(neighbors, 1, 1, source, flow)+0.5f == heights[3]);
	for (int x = 0; x < 2; ++x)
		neighbors[0][x] = LiquidGeometry::neighbor(MapNode(CONTENT_AIR), MapNode(CONTENT_AIR), source, flow, 8);
	CHECK(LiquidGeometry::cornerLevel(neighbors, 0, 0, source, flow)+0.5f == Approx(0.02f));
	for (int x = 0; x < 2; ++x)
		neighbors[0][x] = LiquidGeometry::neighbor(MapNode(CONTENT_IGNORE), MapNode(source), source, flow, 8);
	CHECK_FALSE(neighbors[0][0].top_is_same_liquid); // Unknown neighbors never borrow their upper node.
	CHECK(LiquidGeometry::cornerLevel(neighbors, 0, 0, source, flow)+0.5f == Approx(0.375f));
	neighbors[0][0] = LiquidGeometry::neighbor(MapNode(stone), MapNode(flow), source, flow, 8);
	CHECK_FALSE(neighbors[0][0].is_same_liquid);
	CHECK(LiquidGeometry::cornerLevel(neighbors, 0, 0, source, flow) == 0.5f);
	const auto falling = LiquidGeometry::neighbor(MapNode(flow, 0, LIQUID_FLOW_DOWN_MASK | 3),
		MapNode(CONTENT_AIR), source, flow, 8);
	CHECK(falling.level+0.5f == Approx(3.5f/8)); // Falling alone doesn't flatten the mesh top.
	CHECK(LiquidGeometry::neighbor(MapNode(flow, 0, 7), MapNode(flow), source, flow, 8).top_is_same_liquid);
	CHECK(LiquidGeometry::neighbor(MapNode(flow, 0, 0), MapNode(CONTENT_AIR), source, flow, 0).level == 0.0f);
}

TEST_CASE("Source water uses the displaced mesh triangles for medium boundaries", "[client][render][water]")
{
	using Catch::Approx;
	const v3f waves(1, 20, 0);
	CHECK(WaterWaves::height(v3f(0), waves) == Approx(-5.0f));
	CHECK(WaterWaves::height(v3f(0, 0, 40), waves) == Approx(-30.0f / 41.0f).margin(0.00001f));
	CHECK(WaterWaves::height(v3f(60, 0, 0), waves) == Approx(-100.0f / 41.0f).margin(0.00001f));
	CHECK(WaterWaves::height(v3f(60, 0, 0), v3f(0, 20, 0)) == 0.0f);
	for (const v3f min : {v3f(0), v3f(-105, 35, -215), v3f(309985, 75, -309995)}) {
		const float a = WaterWaves::height(min, waves) + min.Y;
		const float b = WaterWaves::height(min+v3f(10, 0, 0), waves) + min.Y;
		const float c = WaterWaves::height(min+v3f(0, 0, 10), waves) + min.Y;
		const float d = WaterWaves::height(min+v3f(10, 0, 10), waves) + min.Y;
		CHECK(WaterWaves::surface(min, 0, 0, waves) == Approx(a));
		CHECK(WaterWaves::surface(min, 1, 1, waves) == Approx(d));
		CHECK(WaterWaves::surface(min, 0.2f, 0.3f, waves) == Approx(a*0.5f+b*0.2f+c*0.3f));
		CHECK(WaterWaves::surface(min, 0.7f, 0.6f, waves) == Approx(b*0.4f+c*0.3f+d*0.3f));
		CHECK(WaterWaves::surface(min, 0.25f, 0.75f, waves) == Approx(b*0.25f+c*0.75f));
		const v3f shifted = min+v3f(0, 289*64*16, 0);
		CHECK(WaterWaves::height(shifted, waves) == Approx(a-min.Y).margin(0.0001f));
	}
}

TEST_CASE("Waves preserve shoreline thickness through maximum amplitude", "[client][render][water]")
{
	for (float amplitude : {1.0f, 4.0f}) for (float length : {0.1f, 7.123f, 20.0f})
	for (float phase : {0.0f, 0.9f, 4.5f}) for (float x : {-105.0f, 5.0f, 95.0f})
	for (float y : {-25.0f, 15.0f, 105.0f}) for (float z : {-55.0f, -35.0f, 45.0f})
	for (float depth : {0.2f, 0.625f, 5.0f, 10.0f}) {
		const v3f p(x, y, z), waves(amplitude, length, phase);
		const float displaced = depth + WaterWaves::height(p+v3f(0, depth, 0), waves) - WaterWaves::height(p, waves);
		// |d(displacement)/dy| <= 20*1.5/64 = 0.46875 at maximum amplitude.
		// A small float margin also covers arithmetic at the sampled origins.
		CHECK(displaced > depth*0.53f - 0.0001f);
		CHECK(displaced < depth*1.47f + 0.0001f);
	}
}
