// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "mapnode.h"
#include "constants.h"
#include <algorithm>
#include <array>

// Shared by the flowing-liquid mesh and the optical geometry snapshot. Levels
// are relative to the node center; normalized corner heights are relative to its bottom.
namespace LiquidGeometry {
struct Neighbor {
	float level = -0.5f;
	content_t content = CONTENT_IGNORE;
	bool is_same_liquid = false;
	bool top_is_same_liquid = false;
};

inline Neighbor neighbor(MapNode node, MapNode above, content_t source, content_t flow, int range)
{
	Neighbor result;
	result.content = node.getContent();
	if (result.content == CONTENT_IGNORE) return result;
	if (result.content == source) {
		result.level = 0.5f;
		result.is_same_liquid = true;
	} else if (result.content == flow) {
		range = std::clamp(range, 1, 8);
		const int level = std::max(0, int(node.param2 & LIQUID_LEVEL_MASK) - (8-range));
		result.level = -0.5f + (level+0.5f)/range;
		result.is_same_liquid = true;
	}
	result.top_is_same_liquid = above.getContent() == source || above.getContent() == flow;
	return result;
}

inline float cornerLevel(const Neighbor (&neighbors)[3][3], int x, int z,
		content_t source, content_t flow)
{
	float sum = 0.0f;
	int count = 0, air = 0;
	for (int dz = 0; dz < 2; ++dz) for (int dx = 0; dx < 2; ++dx) {
		const auto &n = neighbors[z+dz][x+dx];
		if (n.top_is_same_liquid || n.content == source) return 0.5f;
		if (n.content == flow) { sum += n.level; ++count; }
		else if (n.content == CONTENT_AIR) ++air;
	}
	if (air >= 2) return -0.5f + 0.2f/BS;
	return count ? sum/count : 0.0f;
}

inline std::array<float, 4> cornerHeights(const Neighbor (&neighbors)[3][3],
		content_t source, content_t flow)
{
	return {cornerLevel(neighbors, 0, 0, source, flow)+0.5f,
		cornerLevel(neighbors, 1, 0, source, flow)+0.5f,
		cornerLevel(neighbors, 0, 1, source, flow)+0.5f,
		cornerLevel(neighbors, 1, 1, source, flow)+0.5f};
}
}
