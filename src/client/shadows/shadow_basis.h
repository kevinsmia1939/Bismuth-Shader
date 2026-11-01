// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "irr_v3d.h"
#include <cmath>

// Carry the previous light-camera up vector onto the new light plane. Using
// world Y except at exactly noon makes the shadow basis flip on either side
// of the zenith. World Z starts perpendicular to the normal solar path; the
// projection also handles tilted/custom lights without a pole at world Y.
inline v3f stableShadowUp(v3f direction, v3f previous)
{
	if (direction.getLengthSQ() < 0.000001f)
		return v3f(0, 0, 1);
	direction.normalize();
	v3f up = previous - direction * previous.dotProduct(direction);
	if (up.getLengthSQ() < 0.000001f) {
		const v3f seed = std::abs(direction.Z) < 0.9f ? v3f(0, 0, 1) : v3f(1, 0, 0);
		up = seed - direction * seed.dotProduct(direction);
	}
	return up.normalize();
}
