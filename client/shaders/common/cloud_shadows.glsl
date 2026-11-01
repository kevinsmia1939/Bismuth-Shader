// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_CLOUD_SHADOWS
uniform sampler2D texture7;
uniform vec3 cloudShadowOrigin; // entry-plane center, camera relative
uniform vec3 cloudShadowDirection;
uniform vec3 cloudShadowSlab; // thickness, Y sign, reserved
uniform vec4 cloudShadowParams; // bound/ready, reciprocal span, strength, horizon fade

float cloudSunTransmission(vec3 position)
{
	if (cloudShadowParams.x < 0.5 || cloudShadowParams.z <= 0.0 || cloudShadowParams.w <= 0.0)
		return 1.0;
	float h = (position.y-cloudShadowOrigin.y)*cloudShadowSlab.y/cloudShadowSlab.x;
	if (h >= 1.0) return 1.0;
	vec2 entry = position.xz+cloudShadowDirection.xz*(cloudShadowOrigin.y-position.y)/cloudShadowDirection.y;
	vec2 uv = (entry-cloudShadowOrigin.xz)*cloudShadowParams.y+0.5;
	float edge = min(min(uv.x, uv.y), min(1.0-uv.x, 1.0-uv.y));
	if (edge <= 0.0) return 1.0;
	// Height interpolation is linear in optical depth; spatial filtering was
	// already linear in transmission at the texture lookup.
	vec4 depths = -log(max(texture2D(texture7, uv), vec4(0.000001)));
	float layer = clamp(h, 0.0, 1.0)*3.0;
	float tau = layer < 1.0 ? mix(depths.r, depths.g, layer) :
		(layer < 2.0 ? mix(depths.g, depths.b, layer-1.0) : mix(depths.b, depths.a, layer-2.0));
	float strength = cloudShadowParams.z*cloudShadowParams.w*smoothstep(0.0, 0.04, edge);
	return mix(1.0, exp(-max(tau, 0.0)), strength);
}

vec3 cloudShadeNative(vec3 color, float transmission, vec3 normal, float nightRatio, vec3 geometryVisibility)
{
	if (transmission >= 1.0) return color;
	float cosine = length(normal) > 0.001 ? max(dot(normalize(normal), cloudShadowDirection), 0.0) : 1.0;
	// Baked day lighting combines direct sunlight and diffuse skylight. Preserve
	// an ambient share and native artificial light; only estimate the direct share.
	float direct = 0.65*cosine*(1.0-pow(clamp(nightRatio, 0.0, 1.0), 0.6));
	vec3 factor = vec3(1.0)-(1.0-transmission)*direct*clamp(geometryVisibility, vec3(0), vec3(1));
	return pow(pow(max(color, vec3(0)), vec3(2.2))*factor, vec3(1.0/2.2));
}
#endif
