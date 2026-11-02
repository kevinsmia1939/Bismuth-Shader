// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include "nodedef.h"
#include <algorithm>

// Appearance hints use existing synchronized node groups. Texture packs need
// no extra maps, and a game can override inference without changing its art.
struct SurfaceMaterial {
	float translucency = 0.0f;
	u8 sparkle = 0; // 0 ordinary, 1 sand, 2 snow

	static SurfaceMaterial fromNode(const ContentFeatures &node)
	{
		SurfaceMaterial result;
		const bool plant = node.drawtype == NDT_PLANTLIKE || node.drawtype == NDT_PLANTLIKE_ROOTED ||
			node.drawtype == NDT_MESH || node.drawtype == NDT_NODEBOX;
		const bool leaves = node.getGroup("leaves") > 0 ||
			((node.drawtype == NDT_ALLFACES_OPTIONAL || node.drawtype == NDT_ALLFACES) && node.waving > 0);
		if (leaves)
			result.translucency = 0.35f;
		else if (plant && (node.getGroup("grass") > 0 || node.waving == 1))
			result.translucency = 0.5f;
		if (const auto it = node.groups.find("shader_translucency"); it != node.groups.end())
			result.translucency = std::clamp(it->second, 0, 100) / 100.0f;

		if (node.getGroup("snowy") > 0)
			result.sparkle = 2;
		else if (node.getGroup("sand") > 0)
			result.sparkle = 1;
		if (const auto it = node.groups.find("shader_sparkle"); it != node.groups.end())
			result.sparkle = std::clamp(it->second, 0, 2);
		return result;
	}
};
