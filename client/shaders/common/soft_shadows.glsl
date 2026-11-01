// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_CONTACT_HARDENING_SHADOWS
// World units per normalized depth, and the unwarped orthographic map width.
uniform vec2 shadowPcssScale;
// tan(light angular diameter / 2), maximum blocker/receiver separation in world units.
uniform vec2 shadowPcssParams;

#if SHADOW_FILTER == 2
#define BLOCKER_SAMPLES 16
#define PENUMBRA_SAMPLES 32
#else
#define BLOCKER_SAMPLES 8
#define PENUMBRA_SAMPLES 16
#endif

// warp = camera position in light clip space, XY bias0, XY bias1.
vec2 softShadowWarp(vec2 position, vec4 warp)
{
	vec2 relative = position - warp.xy;
	vec2 side = 1.0 - sign(relative) * warp.xy;
	relative /= max(side, vec2(0.00001));
	return (relative / (length(relative) * warp.z + warp.w) * side + warp.xy) * 0.5 + 0.5;
}

vec2 softShadowUnwarp(vec2 uv, vec4 warp)
{
	vec2 relative = uv * 2.0 - 1.0 - warp.xy;
	vec2 side = 1.0 - sign(relative) * warp.xy;
	vec2 q = relative / max(side, vec2(0.00001));
	return q * warp.w / max(1.0 - length(q) * warp.z, 0.00001) * side + warp.xy;
}

bool softShadowInMap(vec2 uv)
{
	return min(uv.x, uv.y) >= 0.0 && max(uv.x, uv.y) <= 1.0;
}

vec3 softShadowUnpack(float value)
{
	return vec3(floor(value / (129.0 * 129.0)),
		mod(floor(value / 129.0), 129.0), mod(value, 129.0)) / 128.0;
}

float softShadowOcclusion(float difference)
{
#if defined(ENABLE_TRANSLUCENT_FOLIAGE) && MATERIAL_TYPE == TILE_MATERIAL_WAVING_LEAVES
	float t = clamp(difference / 0.002, 0.0, 1.0);
	return t * t * (3.0 - 2.0 * t);
#else
	return step(0.0, difference);
#endif
}

// Returns shadow amount and the transmitted tint when actually shadowed.
vec4 softShadowSample(sampler2D map, vec2 uv, float receiver)
{
	if (!softShadowInMap(uv)) return vec4(0.0);
	vec4 sampleDepth = texture2D(map, uv);
	float opaque = softShadowOcclusion(receiver - sampleDepth.r);
#ifdef COLORED_SHADOWS
	if (opaque > 0.1) return vec4(opaque, 0.0, 0.0, 0.0);
	float transparent = softShadowOcclusion(receiver - sampleDepth.b);
	return vec4(transparent, transparent > 0.0 ? softShadowUnpack(sampleDepth.a) : vec3(0.0));
#else
	return vec4(opaque, 0.0, 0.0, 0.0);
#endif
}

vec2 softShadowDisk(int index, int count)
{
	// A fixed Vogel disk in light space stays independent of camera/screen motion.
	float radius = sqrt((float(index) + 0.5) / float(count));
	float angle = float(index) * 2.39996323;
	return radius * vec2(cos(angle), sin(angle));
}

vec4 contactHardeningShadow(sampler2D map, vec2 uv, float receiver,
		vec4 warp, float resolution)
{
	if (SHADOW_FILTER == 0 || shadowPcssParams.x <= 0.0 ||
			shadowPcssScale.x <= 0.0 || shadowPcssScale.y <= 0.0)
		return softShadowSample(map, uv, receiver);
	vec2 center = softShadowUnwarp(uv, warp);
	vec3 dx = dFdx(vec3(center, receiver));
	vec3 dy = dFdy(vec3(center, receiver));
	float determinant = dx.x * dy.y - dx.y * dy.x;
	vec2 receiverGradient = vec2(0.0);
	if (abs(determinant) > 0.0000000001)
		receiverGradient = vec2(dx.z * dy.y - dy.z * dx.y,
			dy.z * dx.x - dx.z * dy.x) / determinant;
	// Bound degenerate/grazing receiver planes; retain the existing caster bias.
	float gradientLimit = shadowPcssScale.y / shadowPcssScale.x;
	receiverGradient = clamp(receiverGradient, vec2(-gradientLimit), vec2(gradientLimit));
	float worldToClip = 2.0 / shadowPcssScale.y;
	float searchRadius = shadowPcssParams.x * shadowPcssParams.y * worldToClip;
	float separation = 0.0;
	float blockers = 0.0;
	for (int i = 0; i < BLOCKER_SAMPLES; ++i) {
		vec2 offset = i == 0 ? vec2(0.0) : softShadowDisk(i - 1, BLOCKER_SAMPLES - 1) * searchRadius;
		vec2 sampleUV = softShadowWarp(center + offset, warp);
		if (!softShadowInMap(sampleUV)) continue;
		vec4 depth = texture2D(map, sampleUV);
		float localReceiver = receiver + dot(receiverGradient, offset);
		float blockerDepth = depth.r;
		float opacity = 1.0;
#ifdef COLORED_SHADOWS
		if (depth.b < depth.r) {
			blockerDepth = depth.b;
			opacity = clamp(1.0 - dot(softShadowUnpack(depth.a), vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
			// Fully transparent foreground texels must not hide opaque blockers behind them.
			if (opacity <= 0.001) { blockerDepth = depth.r; opacity = 1.0; }
		}
#endif
		if (blockerDepth < localReceiver && opacity > 0.001) {
			separation += min((localReceiver - blockerDepth) * shadowPcssScale.x,
				shadowPcssParams.y) * opacity;
			blockers += opacity;
		}
	}
	if (blockers < 0.001) return softShadowSample(map, uv, receiver);
	float radius = separation / blockers * shadowPcssParams.x * worldToClip;
	// A half-texel floor provides contact antialiasing without a fixed world blur.
	vec2 relative = center - warp.xy;
	vec2 side = max(1.0 - sign(relative) * warp.xy, vec2(0.00001));
	float factor = length(relative / side) * warp.z + warp.w;
	float texelRadius = factor * factor / max(warp.w * resolution, 0.00001);
	radius = min(searchRadius, max(radius, texelRadius));
	vec4 sum = vec4(0.0);
	for (int i = 0; i < PENUMBRA_SAMPLES; ++i) {
		vec2 offset = softShadowDisk(i, PENUMBRA_SAMPLES) * radius;
		vec4 sampleShadow = softShadowSample(map, softShadowWarp(center + offset, warp),
			receiver + dot(receiverGradient, offset));
		sum += vec4(sampleShadow.x, sampleShadow.yzw * sampleShadow.x);
	}
	return vec4(sum.x / float(PENUMBRA_SAMPLES), sum.yzw / max(sum.x, 0.0001));
}
#endif
