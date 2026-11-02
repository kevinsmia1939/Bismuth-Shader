// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_VOXEL_LIGHTING
#ifndef VOXEL_ATLAS_TEXTURE
#if defined(ENABLE_VOXEL_FOG_LIGHTING) || defined(ENABLE_VOXEL_WATER_LIGHTING)
#define VOXEL_ATLAS_TEXTURE texture4
#else
#define VOXEL_ATLAS_TEXTURE texture2
#endif
#endif
#define voxelAtlas VOXEL_ATLAS_TEXTURE
uniform sampler2D voxelAtlas;
uniform vec3 voxelOrigin;
uniform vec4 voxelParams; // ready, direct strength, bounce strength, grid size
#ifndef VOXEL_LIGHT_SOFT_FALLOFF
#define VOXEL_LIGHT_SOFT_FALLOFF 1
#endif

float voxelLightAttenuation(float squaredDistance)
{
#if VOXEL_LIGHT_SOFT_FALLOFF
	// A two-node soft core avoids a clipped hotspot beside small emitters.
	// The quartic window preserves the middle range and reaches zero with a
	// zero derivative at 16 nodes, instead of fading sharply from the source.
	float range = squaredDistance / 256.0;
	float window = max(0.0, 1.0 - range * range);
	return window * window / (squaredDistance + 4.0);
#else
	float fade = max(0.0, 1.0 - sqrt(squaredDistance) / 16.0);
	return fade * fade / max(squaredDistance, 1.0);
#endif
}
#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
#define VOXEL_ATLAS_COLUMNS 14.0
#if defined(ENABLE_VOXEL_MATERIAL_SPECULAR) && !MATERIAL_WATER_REFLECTIONS && (MATERIAL_TYPE != TILE_MATERIAL_WAVING_LEAVES && MATERIAL_TYPE != TILE_MATERIAL_WAVING_PLANTS)
#define VOXEL_POINT_GGX
#endif
uniform float voxelDynamicCount;
uniform vec4 voxelDynamicPosition[MAX_VOXEL_DYNAMIC_LIGHTS]; // grid-node coordinates
uniform vec4 voxelDynamicEmission[MAX_VOXEL_DYNAMIC_LIGHTS]; // linear RGB
#else
#define VOXEL_ATLAS_COLUMNS 13.0
#endif

vec4 voxelProbe(vec3 p, float group)
{
	float n = voxelParams.w;
	p = clamp(p, vec3(0.0), vec3(n - 1.0));
	float z = floor(p.z);
	vec2 uv = vec2(group * n + p.x + 0.5, z * n + p.y + 0.5) / vec2(n * VOXEL_ATLAS_COLUMNS, n * n);
	vec2 nextUV = vec2(uv.x, (min(z + 1.0, n - 1.0) * n + p.y + 0.5) / (n * n));
	return mix(texture2D(voxelAtlas, uv), texture2D(voxelAtlas, nextUV), fract(p.z));
}

#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
bool voxelInside(vec3 p)
{
	return all(greaterThanEqual(p, vec3(-0.5))) &&
		all(lessThan(p, vec3(voxelParams.w - 0.5)));
}

vec4 voxelCellOptics(vec3 cell)
{
	float n = voxelParams.w;
	vec2 uv = vec2(13.0 * n + cell.x + 0.5, cell.z * n + cell.y + 0.5) /
		vec2(n * VOXEL_ATLAS_COLUMNS, n * n);
	return texture2D(voxelAtlas, uv);
}

vec3 voxelDynamicTransmission(vec3 start, vec3 end, vec3 ignoredCell)
{
	if (voxelParams.x < 0.5 || !voxelInside(start) || !voxelInside(end)) return vec3(0.0);
	vec3 delta = end - start;
	float distance = length(delta);
	vec3 endCell = floor(end + 0.5);
	// A stale/unknown/solid source location must not illuminate through a wall.
	if (voxelCellOptics(endCell).a < 0.5) return vec3(0.0);
	vec3 cell = floor(start + 0.5);
	vec3 direction = delta / max(distance, 0.000001);
	vec3 rayStep = mix(vec3(-1.0), vec3(1.0), step(vec3(0.0), direction));
	vec3 increment = 1.0 / max(abs(direction), vec3(1e-20));
	vec3 next = (cell + rayStep * 0.5 - start) * rayStep * increment;
	vec3 transmission = vec3(1.0);
	float traveled = 0.0;
	// A <=16-node ray crosses at most 16*sqrt(3)+3 grid planes.
	// A varying bound also keeps drivers from expanding every step at compile time.
	int maxSteps = int(min(48.0, ceil(distance * 1.732051) + 4.0));
	for (int iteration = 0; iteration < maxSteps; ++iteration) {
		if (!voxelInside(cell)) return vec3(0.0);
		vec4 optics = voxelCellOptics(cell);
		bool ignored = all(equal(cell, ignoredCell));
		if (optics.a < 0.5 && !ignored) return vec3(0.0);
		int axis = next.x < next.y ? 0 : 1;
		if (next.z < next[axis]) axis = 2;
		float finish = min(next[axis], distance);
		float segment = max(finish - traveled, 0.0);
		if (!ignored && segment > 0.0 && any(lessThan(optics.rgb, vec3(1.0))))
			transmission *= pow(clamp(optics.rgb, 0.0, 1.0), vec3(segment));
		if (next[axis] >= distance) return transmission;
		traveled = finish;
		cell[axis] += rayStep[axis];
		next[axis] += increment[axis];
	}
	return vec3(0.0); // Exhausted traversal never becomes an unoccluded light.
}

vec3 voxelDynamicIrradiance(vec3 q, vec3 normal, vec3 geometric, bool nodeSurface,
	vec3 view, float roughness, vec3 f0, bool specularEnabled, out vec3 specular)
{
	specular = vec3(0.0);
	if (voxelParams.x < 0.5 || voxelParams.y <= 0.0 || voxelDynamicCount < 0.5) return vec3(0.0);
	vec3 result = vec3(0.0);
	vec3 ignored = nodeSurface ? floor(q - geometric * 0.1 + 0.5) : vec3(-2.0);
	float normalLength = length(normal);
	vec3 unitNormal = normal / max(normalLength, 0.000001);
#ifdef VOXEL_POINT_GGX
	float viewLength = length(view);
	vec3 unitView = view / max(viewLength, 0.000001);
#endif
	int sourceCount = int(clamp(voxelDynamicCount, 0.0, float(MAX_VOXEL_DYNAMIC_LIGHTS)));
	for (int i = 0; i < sourceCount; ++i) {
		vec3 emission = voxelDynamicEmission[i].rgb;
		if (dot(emission, emission) <= 0.0) continue;
		vec3 source = voxelDynamicPosition[i].xyz;
		vec3 delta = source - q;
		float squaredDistance = dot(delta, delta);
		if (squaredDistance >= 256.0) continue;
		float distance = sqrt(squaredDistance);
		vec3 direction = delta / max(distance, 0.000001);
		float cosine = distance < 0.01 ? 1.0 : (normalLength < 0.001 ?
			dot(abs(direction), vec3(1.0)) / 6.0 : max(dot(unitNormal, direction), 0.0));
		if (cosine <= 0.0) continue;
#ifdef VOXEL_POINT_GGX
		// Normal maps may tilt towards a light behind the actual opaque face.
		// Do not let the receiver-cell exception transmit that light through it.
		if (specularEnabled && distance > 0.000001 && dot(geometric, geometric) > 0.001 &&
			dot(geometric, direction) <= 0.0) continue;
#endif
		vec3 transmission = voxelDynamicTransmission(q + geometric * 0.001, source, ignored);
		vec3 incident = emission * transmission * voxelLightAttenuation(squaredDistance);
		result += incident * cosine;
#ifdef VOXEL_POINT_GGX
		if (specularEnabled && normalLength > 0.001 && viewLength > 0.000001)
			specular += incident * materialSpecular(unitNormal, unitView, direction, roughness, f0);
#if defined(ENABLE_MATERIAL_SPARKLE) && defined(MATERIAL_SPARKLE)
		if (specularEnabled && normalLength > 0.001 && viewLength > 0.000001)
			specular += incident * grainResponse(unitNormal, unitView, direction);
#endif
#endif
	}
	return result;
}

vec3 voxelDynamicIrradiance(vec3 q, vec3 normal, vec3 geometric, bool nodeSurface)
{
	vec3 unused;
	return voxelDynamicIrradiance(q, normal, geometric, nodeSurface,
		vec3(0.0), 0.8, vec3(0.04), false, unused);
}
#endif

vec3 voxelIrradiance(vec3 p, vec3 normal, float baseGroup)
{
	if (length(normal) < 0.001) {
		vec3 isotropic = vec3(0.0);
		for (int d = 0; d < 6; ++d) {
			vec4 sampleValue = voxelProbe(p, baseGroup + float(d));
			isotropic += sampleValue.rgb / max(sampleValue.a, 0.05) / 6.0;
		}
		return isotropic;
	}
	vec3 weights = abs(normal);
	weights /= max(weights.x + weights.y + weights.z, 0.00001);
	vec3 result = vec3(0.0);
	for (int axis = 0; axis < 3; ++axis) {
		if (weights[axis] < 0.0001) continue;
		float group = baseGroup + float(axis * 2) + (normal[axis] < 0.0 ? 1.0 : 0.0);
		vec4 sampleValue = voxelProbe(p, group);
		result += sampleValue.rgb / max(sampleValue.a, 0.05) * weights[axis];
	}
	return result;
}

#if defined(ENABLE_MATERIAL_SPARKLE) && defined(MATERIAL_SPARKLE)
vec3 voxelStaticGrainIrradiance(vec3 probe, vec3 normal, vec3 geometric, vec3 view, vec3 faceIrradiance)
{
	// Recover the dominant incident direction from the six existing direct
	// lobes. A single placed light reconstructs its direction and spectrum;
	// multiple lights share an approximate first moment, without new sources
	// or an extra atlas. Moving lights are excluded from this field when their
	// exact per-frame path is active, so neither path counts them twice.
	vec3 moment = vec3(0.0);
	for (int axis = 0; axis < 3; ++axis) {
		vec4 positive = voxelProbe(probe, float(axis * 2));
		vec4 negative = voxelProbe(probe, float(axis * 2 + 1));
		vec3 a = positive.rgb / max(positive.a, 0.05);
		vec3 b = negative.rgb / max(negative.a, 0.05);
		// Surface-anchored lobes and air-center lobes can disagree very close
		// to a lamp. Light behind the receiver must not reverse its front lobe.
		a *= geometric[axis] < 0.0 ? 0.0 : 1.0;
		b *= geometric[axis] > 0.0 ? 0.0 : 1.0;
		moment[axis] = dot(a - b, vec3(0.2126, 0.7152, 0.0722));
	}
	float lengthSquared = dot(moment, moment);
	if (lengthSquared < 0.0000000001) return vec3(0.0);
	vec3 direction = moment / sqrt(lengthSquared);
	// Normalize by receiving irradiance instead of an isotropic probe's six-lobe
	// sum. This bounds glints beside low lamps and retains volume-edge coverage.
	vec3 incident = faceIrradiance / max(dot(normal, direction), 0.1);
	return incident * grainResponse(normal, normalize(view), direction);
}
#endif

#if defined(ENABLE_VOXEL_FOG_LIGHTING) || defined(ENABLE_VOXEL_WATER_LIGHTING)
float voxelVolumePhase(float cosine, float anisotropy)
{
	float g = clamp(anisotropy, -0.85, 0.85);
	return (1.0 - g*g) / pow(max(1.0 + g*g - 2.0*g*clamp(cosine, -1.0, 1.0), 0.001), 1.5);
}

void voxelVolumePhaseWeights(vec3 viewRay, float anisotropy, out vec3 positive, out vec3 negative)
{
	// This depends only on the ray and medium, not the integration position.
	// Normalize the quadrature so an isotropic probe field stays invariant.
	positive = vec3(voxelVolumePhase(viewRay.x,anisotropy), voxelVolumePhase(viewRay.y,anisotropy), voxelVolumePhase(viewRay.z,anisotropy));
	negative = vec3(voxelVolumePhase(-viewRay.x,anisotropy), voxelVolumePhase(-viewRay.y,anisotropy), voxelVolumePhase(-viewRay.z,anisotropy));
	float total = dot(positive + negative, vec3(1.0));
	positive /= total;
	negative /= total;
}

vec3 voxelVolumeField(vec3 p, float baseGroup, vec3 positive, vec3 negative)
{
	vec3 result = vec3(0.0);
	for (int axis = 0; axis < 3; ++axis) {
		float group = baseGroup + float(axis * 2);
		vec4 a = voxelProbe(p, group), b = voxelProbe(p, group + 1.0);
		result += a.rgb / max(a.a, 0.05) * positive[axis] + b.rgb / max(b.a, 0.05) * negative[axis];
	}
	return result;
}

float voxelVolumeCoverage(vec3 position, out vec3 q)
{
	q = (position-voxelOrigin)/10.0;
	if (voxelParams.x < 0.5 || !all(greaterThanEqual(q,vec3(-0.5))) ||
			!all(lessThan(q,vec3(voxelParams.w-0.5)))) return 0.0;
#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
	if (voxelCellOptics(floor(q+0.5)).a < 0.5) return 0.0;
#else
	if (voxelProbe(floor(q+0.5),0.0).a < 0.5) return 0.0;
#endif
	vec3 edges = min(q,voxelParams.w-1.0-q);
	return smoothstep(0.0,2.0,min(edges.x,min(edges.y,edges.z)));
}
#endif

#ifdef ENABLE_VOXEL_FOG_LIGHTING
uniform float voxelFogStrength;
uniform float voxelFogAnisotropy;

float voxelFogPhase(float cosine) { return voxelVolumePhase(cosine,voxelFogAnisotropy); }
void voxelFogPhaseWeights(vec3 ray, out vec3 positive, out vec3 negative)
{
	voxelVolumePhaseWeights(ray,voxelFogAnisotropy,positive,negative);
}
vec3 voxelFogField(vec3 p, float group, vec3 positive, vec3 negative)
{
	return voxelVolumeField(p,group,positive,negative);
}

#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
vec3 voxelFogMovingLight(vec3 q, vec3 viewRay)
{
	vec3 result = vec3(0.0);
	int count = int(clamp(voxelDynamicCount, 0.0, float(MAX_VOXEL_DYNAMIC_LIGHTS)));
	for (int i = 0; i < count; ++i) {
		vec3 emission = voxelDynamicEmission[i].rgb;
		if (dot(emission, emission) <= 0.0) continue;
		vec3 source = voxelDynamicPosition[i].xyz;
		vec3 delta = source - q;
		float squaredDistance = dot(delta, delta);
		if (squaredDistance >= 256.0) continue;
		float distance = sqrt(squaredDistance);
		vec3 direction = delta / max(distance, 0.000001);
		// Incoming photons travel against direction, and outgoing photons toward
		// the eye against viewRay: their scattering cosine is direction.viewRay.
		float phase = mix(1.0, voxelFogPhase(dot(direction, viewRay)), smoothstep(0.0, 1.0, distance));
		vec3 transmission = voxelDynamicTransmission(q, source, vec3(-2.0));
		// Keep the previous axial isotropic scale, without its six-axis cosine
		// sum: a point emitter must not brighten when rotated toward a diagonal.
		result += emission * transmission * (phase * voxelLightAttenuation(squaredDistance) / 6.0);
	}
	return result;
}
#endif

vec3 voxelFogRadiance(vec3 position, vec3 viewRay, vec3 positive, vec3 negative)
{
	if (voxelParams.x < 0.5 || voxelFogStrength <= 0.0 || max(voxelParams.y, voxelParams.z) <= 0.0) return vec3(0.0);
	vec3 q;
	float coverage = voxelVolumeCoverage(position,q);
	if (coverage <= 0.0) return vec3(0.0);
	vec3 result = vec3(0.0);
	// Empty-cell direct probes contain emission, not direct sun. Skip inactive
	// lobes before texture reads and moving-light visibility traversal.
	if (voxelParams.y > 0.0) {
		vec3 direct = voxelFogField(q, 0.0, positive, negative);
#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
		direct += voxelFogMovingLight(q, viewRay);
#endif
		result += direct * voxelParams.y;
	}
	if (voxelParams.z > 0.0)
		result += voxelFogField(q, 6.0, positive, negative) * voxelParams.z;
	return result * (coverage * voxelFogStrength);
}
#endif

vec3 applyVoxelLighting(vec3 color, vec3 base, vec3 position, vec3 shadingNormal,
	vec3 geometricNormal, float nightRatio, vec3 dayLight, bool nodeSurface, float occlusion,
	vec3 view, float roughness, vec3 f0, bool specularEnabled, out vec3 directSpecular)
{
	directSpecular = vec3(0.0);
	if (voxelParams.x < 0.5 || max(voxelParams.y, voxelParams.z) <= 0.0) return color;
	vec3 geometric = length(geometricNormal) > 0.001 ? normalize(geometricNormal) : vec3(0.0);
	vec3 normal = length(geometricNormal) > 0.001 ? shadingNormal : vec3(0.0);
	vec3 q = (position - voxelOrigin) / 10.0;
	vec3 probe = q + geometric * 0.6;
	vec3 edges = min(probe, voxelParams.w - 1.0 - probe);
	float coverage = smoothstep(0.0, 2.0, min(edges.x, min(edges.y, edges.z)));
	// Most outdoor pixels are beyond this deliberately local field. Do not
	// fetch twelve probe lobes and material tint only to multiply them by zero.
	if (coverage <= 0.0) return color;
	vec4 validity = voxelProbe(probe, 0.0);
	float bakedCoverage = coverage * smoothstep(0.0, 0.25, validity.a);
	vec3 direct = vec3(0.0);
	if (voxelParams.y > 0.0)
		direct = voxelIrradiance(probe, normal, 0.0) * bakedCoverage;
#if defined(ENABLE_MATERIAL_SPARKLE) && defined(MATERIAL_SPARKLE)
	vec3 bakedDirect = direct;
#endif
#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
	direct += voxelDynamicIrradiance(q, normal, geometric, nodeSurface,
		view, roughness, f0, specularEnabled, directSpecular) * coverage;
	directSpecular *= voxelParams.y * coverage;
#endif
#if defined(ENABLE_MATERIAL_SPARKLE) && defined(MATERIAL_SPARKLE)
	if (specularEnabled && voxelParams.y > 0.0 && bakedCoverage > 0.0 &&
			surfaceGrain.a > 0.0 && any(greaterThan(bakedDirect, vec3(0.0))) && dot(view, view) > 0.000001)
		directSpecular += voxelStaticGrainIrradiance(probe, normal, geometric, view, bakedDirect) * voxelParams.y;
#endif
	vec3 bounce = vec3(0.0);
	if (voxelParams.z > 0.0)
		bounce = voxelIrradiance(probe, normal, 6.0) * bakedCoverage;
	// Tint follows the solved snapshot; emission classification belongs to the
	// material currently being drawn, never a stale or zero-RGB source marker.
	// Entities use their own texture color, independent of the occupied map cell.
	vec4 material = nodeSurface ? voxelProbe(floor(q - geometric * 0.1 + 0.5), 12.0) : vec4(1.0, 1.0, 1.0, 0.0);
	float emissive = 0.0;
#ifdef MATERIAL_EMISSIVE
	emissive = 1.0;
#endif
	vec3 linear = pow(max(color, vec3(0.0)), vec3(2.2));
	vec3 albedo = pow(max(base, vec3(0.0)), vec3(2.2)) * material.rgb;
	float dayBrightness = dot(dayLight, vec3(0.2126, 0.7152, 0.0722));
	float artificial = clamp(nightRatio * 1.04 /
		max(mix(dayBrightness, 1.04, nightRatio), 0.001), 0.0, 1.0);
	float replacement = bakedCoverage * min(voxelParams.y, 1.0) * (1.0 - step(0.5, emissive));
	linear *= 1.0 - artificial * replacement;
	linear += albedo * (direct * voxelParams.y + bounce * voxelParams.z * occlusion);
	return pow(max(linear, vec3(0.0)), vec3(1.0 / 2.2));
}

vec3 applyVoxelLighting(vec3 color, vec3 base, vec3 position, vec3 shadingNormal,
	vec3 geometricNormal, float nightRatio, vec3 dayLight, bool nodeSurface, float occlusion)
{
	vec3 unused;
	return applyVoxelLighting(color, base, position, shadingNormal, geometricNormal,
		nightRatio, dayLight, nodeSurface, occlusion, vec3(0.0), 0.8, vec3(0.04), false, unused);
}

vec3 applyVoxelLighting(vec3 color, vec3 base, vec3 position, vec3 shadingNormal,
	vec3 geometricNormal, float nightRatio, vec3 dayLight, bool nodeSurface)
{
	return applyVoxelLighting(color, base, position, shadingNormal, geometricNormal,
		nightRatio, dayLight, nodeSurface, 1.0);
}
#endif
