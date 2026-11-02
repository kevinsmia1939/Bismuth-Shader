// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later

#if defined(ENABLE_TRANSLUCENT_FOLIAGE) && defined(MATERIAL_FOLIAGE)
vec3 foliageTransmission(vec3 base, vec3 normal, vec3 view, vec3 light)
{
	// Orient a thin sheet toward the viewer, so either face transmits when
	// backlit. Plant sprites without normals use the forward-scattering lobe.
	float n2 = dot(normal, normal);
	vec3 sheet = normal / sqrt(max(n2, 0.000001));
	// Blend the two sheet orientations near grazing incidence. A hard normal
	// flip at N.V=0 makes animated leaves pop as the viewer crosses the plane.
	float side = smoothstep(-0.15, 0.15, dot(sheet, view));
	float nl = dot(sheet, light);
	float back = n2 > 0.000001 ? mix(smoothstep(-0.2, 0.8, nl),
		smoothstep(-0.2, 0.8, -nl), side) : 0.0;
	float forward = pow(max(dot(-light, view), 0.0), 6.0);
	vec3 tint = pow(clamp(base, vec3(0.0), vec3(1.0)), vec3(2.2));
	return tint * (MATERIAL_FOLIAGE * (0.4 * back + 0.6 * forward));
}
#endif

#if defined(ENABLE_MATERIAL_SPARKLE) && defined(MATERIAL_SPARKLE)
vec4 surfaceGrain = vec4(0.0);

float grainHash(vec3 p)
{
	p = fract(p * vec3(0.1031, 0.1030, 0.0973));
	p += dot(p, p.yxz + 33.33);
	return fract((p.x + p.y) * p.z);
}

vec4 sampleSurfaceGrain(vec3 position, vec3 normal, vec3 base)
{
	// Work in node coordinates and wrap the cell hash at the same period as
	// the camera offset. Rebased origins therefore keep identical grain seeds.
	const float density = MATERIAL_SPARKLE == 2 ? 6.0 : 8.0;
	vec3 p = position * density;
	vec3 weights = abs(normal);
	vec2 uv = weights.y >= max(weights.x, weights.z) ? p.xz :
		(weights.x >= weights.z ? p.zy : p.xy);
	vec3 cell = mod(floor(p + normal * 0.001), vec3(1024.0 * density));
	float seed = grainHash(cell);
	float footprint = max(length(dFdx(uv)), length(dFdy(uv)));
	float fade = 1.0 - smoothstep(0.35, 1.1, footprint);
	float selection = smoothstep(0.91, 0.96, seed);
	vec2 center = vec2(grainHash(cell + 17.0), grainHash(cell + 43.0)) * 0.6 + 0.2;
	float radius = MATERIAL_SPARKLE == 2 ? 0.16 : 0.12;
	float disk = 1.0 - smoothstep(radius * 0.35, radius + footprint * 0.5,
		length(fract(uv) - center));
	float energy = radius * radius / (radius * radius + footprint * footprint);
	vec3 perturbation = vec3(grainHash(cell + 5.0), grainHash(cell + 11.0), grainHash(cell + 29.0)) - 0.5;
	vec3 grainNormal = normalize(normal + perturbation * 0.6);
	float materialMask = 1.0;
#if MATERIAL_SPARKLE == 2
	// The snowy group also includes snow-covered dirt. Restrict that response
	// to pale upward-facing snow, preserving its brown side and bottom tiles.
	materialMask = smoothstep(0.5, 0.9, normal.y) * smoothstep(0.55, 0.85, min(base.r, min(base.g, base.b)));
#endif
	float strength = MATERIAL_SPARKLE == 2 ? 0.18 : 0.10;
	return vec4(grainNormal, selection * disk * energy * fade * strength * materialMask);
}

vec3 grainResponse(vec3 normal, vec3 view, vec3 light)
{
	if (surfaceGrain.a <= 0.0 || dot(normal, light) <= 0.0 || dot(normal, view) <= 0.0)
		return vec3(0.0);
	vec3 halfway = view + light;
	float h2 = dot(halfway, halfway);
	float alignment = max(dot(surfaceGrain.xyz, halfway / sqrt(max(h2, 0.000001))), 0.0);
	float glint = pow(alignment, MATERIAL_SPARKLE == 2 ? 140.0 : 80.0);
	vec3 tint = MATERIAL_SPARKLE == 2 ? vec3(0.86, 0.94, 1.0) : vec3(1.0, 0.85, 0.62);
	return tint * (surfaceGrain.a * glint * max(dot(normal, light), 0.0));
}
#endif
