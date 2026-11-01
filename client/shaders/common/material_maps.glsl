// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_MATERIAL_MAPS
#define normalMap texture4
#define ormMap texture5
uniform sampler2D normalMap;
uniform sampler2D ormMap;
uniform vec3 materialMapFlags; // normal bound, ORM bound, authored normal strength
uniform float materialNormalMipmaps; // alpha contains normal standard deviation

vec3 readMaterialORM(vec2 uv, float fallbackRoughness)
{
	if (materialMapFlags.y < 0.5)
		return vec3(1.0, fallbackRoughness, 0.0);
	vec3 channels = texture2D(ormMap, uv).rgb;
	return vec3(clamp(channels.r, 0.0, 1.0), clamp(channels.g, 0.045, 1.0), clamp(channels.b, 0.0, 1.0));
}

vec3 decodeMaterialNormal(vec3 encoded, float strength)
{
	vec3 tangentNormal = encoded * 2.0 - 1.0;
	tangentNormal.xy *= strength;
	tangentNormal.z = max(tangentNormal.z, 0.001);
	return tangentNormal;
}

vec3 mappedMaterialNormal(vec3 normal, vec3 position, vec2 uv, vec3 encoded, float strength)
{
	vec3 tangentNormal = decodeMaterialNormal(encoded, strength);
	vec3 dx = dFdx(position);
	vec3 dy = dFdy(position);
	vec2 du = dFdx(uv);
	vec2 dv = dFdy(uv);
	vec3 a = cross(dy, normal);
	vec3 b = cross(normal, dx);
	vec3 tangent = a * du.x + b * dv.x;
	vec3 bitangent = a * du.y + b * dv.y;
	float scale = max(dot(tangent, tangent), dot(bitangent, bitangent));
	if (scale < 0.00000001)
		return normal;
	float invScale = inversesqrt(scale);
	return normalize((tangent * tangentNormal.x + bitangent * tangentNormal.y) * invScale +
		normal * tangentNormal.z);
}

vec3 readMaterialNormal(vec3 normal, vec3 position, vec2 uv, out vec3 filterNormal, out float mipVariance)
{
	filterNormal = vec3(0.0, 0.0, 1.0);
	mipVariance = 0.0;
	if (materialMapFlags.x < 0.5)
		return normal;
	vec4 sampleNormal = texture2D(normalMap, uv);
	vec3 encoded = sampleNormal.rgb;
	if (materialNormalMipmaps > 0.5)
		mipVariance = min(0.5*sampleNormal.a*sampleNormal.a*materialMapFlags.z*materialMapFlags.z,0.25);
	filterNormal = normalize(decodeMaterialNormal(encoded, materialMapFlags.z));
	return mappedMaterialNormal(normal, position, uv, encoded, materialMapFlags.z);
}

vec3 readMaterialNormal(vec3 normal, vec3 position, vec2 uv, out vec3 filterNormal)
{
	float unused;
	return readMaterialNormal(normal,position,uv,filterNormal,unused);
}

vec3 readMaterialNormal(vec3 normal, vec3 position, vec2 uv)
{
	vec3 unused;
	return readMaterialNormal(normal, position, uv, unused);
}

vec3 materialFresnel(vec3 f0, float cosine)
{
	return f0 + (1.0 - f0) * pow(1.0 - clamp(cosine, 0.0, 1.0), 5.0);
}

float filterMaterialRoughness(vec3 normal, vec3 tangentNormal, float roughness, float mipVariance)
{
	// Approximate normal variance over a square pixel footprint. Add it in
	// GGX alpha-squared space (perceptual roughness^4), not gamma/color space.
	// Evaluate before discard or divergent lighting/visibility branches.
	vec3 dx = dFdx(normal);
	vec3 dy = dFdy(normal);
	// Differentiate sampled tangent normals, not the derivative-built frame:
	// higher-order derivatives of the cotangent frame are undefined in GLSL.
	vec3 tx = dFdx(tangentNormal);
	vec3 ty = dFdy(tangentNormal);
	float variance = min((dot(dx, dx) + dot(dy, dy) + dot(tx, tx) + dot(ty, ty)) / 12.0 + mipVariance, 0.25);
	float r = clamp(roughness, 0.045, 1.0);
	return pow(min(r * r * r * r + variance, 1.0), 0.25);
}

float filterMaterialRoughness(vec3 normal, vec3 tangentNormal, float roughness)
{
	return filterMaterialRoughness(normal,tangentNormal,roughness,0.0);
}

vec3 materialSpecular(vec3 normal, vec3 view, vec3 light, float roughness, vec3 f0)
{
	float nl = max(dot(normal, light), 0.0);
	float nv = max(dot(normal, view), 0.0);
	if (nl <= 0.0 || nv <= 0.0 || dot(view + light, view + light) < 0.000001)
		return vec3(0.0);
	vec3 halfway = normalize(view + light);
	float nh = max(dot(normal, halfway), 0.0);
	float vh = max(dot(view, halfway), 0.0);
	float a2 = pow(clamp(roughness, 0.045, 1.0), 4.0);
	// |N x H|^2 = 1-(N.H)^2 for unit vectors, without cancellation at
	// smooth normal incidence (some drivers reassociate 1-nh2+nh2*a2).
	vec3 normalCrossHalf = cross(normal, halfway);
	float denominator = dot(normalCrossHalf, normalCrossHalf) + nh * nh * a2;
	float distribution = a2 / max(3.14159265 * denominator * denominator, 0.000000000001);
	float gv = nl * sqrt(nv * nv * (1.0 - a2) + a2);
	float gl = nv * sqrt(nl * nl * (1.0 - a2) + a2);
	float visibility = 0.5 / max(gv + gl, 0.00001);
	// Bound point-sun peaks to keep low-roughness assets stable through bloom/exposure.
	return min(distribution * visibility * materialFresnel(f0, vh) * nl, vec3(32.0));
}

vec3 materialEnvironment(vec3 normal, vec3 view, vec3 f0, float roughness, float occlusion,
		vec3 sky, vec3 daylight)
{
	vec3 reflected = reflect(-view, normal);
	float skyVisibility = mix(clamp(reflected.y * 0.5 + 0.5, 0.0, 1.0), 0.5, roughness);
	vec3 radiance = pow(max(sky, vec3(0.0)), vec3(2.2)) * mix(0.15, 1.0, skyVisibility);
	float nv = max(dot(normal, view), 0.0);
	return radiance * materialFresnel(f0, nv) * mix(1.0, 0.65, roughness) * occlusion *
		clamp(dot(daylight, vec3(0.2126, 0.7152, 0.0722)) * 2.0, 0.0, 1.0);
}

vec3 composeMaterialLighting(vec3 nativeLight, vec3 directSpecular, vec3 environment,
		float metallic, float nativeEmission)
{
	// Native baked lighting cannot separate self emission from diffuse radiance.
	// Emissive node variants retain that term rather than suppressing their glow.
	float diffuse = mix((1.0 - metallic) * 0.96, 1.0, step(0.5, nativeEmission));
	return nativeLight * diffuse + directSpecular + environment;
}
#endif
