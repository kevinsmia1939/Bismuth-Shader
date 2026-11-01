// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#define cloudNoise texture2
uniform sampler2D cloudNoise;
uniform vec2 cloudTextureSize;
uniform vec4 cloudLayer; // bottom, thickness, coverage, extinction per world unit
uniform vec4 cloudParams; // ready, view samples, maximum distance, detail strength
uniform vec4 cloudWind; // wind X/Z, seed offsets X/Z
uniform vec4 cloudLight; // toward directional light XYZ, visible intensity
uniform vec3 cloudBright;
uniform vec3 cloudAmbient;
uniform vec3 cloudShadow;

float cloudNoise3D(vec3 p)
{
	float n = cloudTextureSize.x - 2.0;
	p = mod(p, n);
	float z = floor(p.z);
	vec2 a = vec2(p.x + 1.5, z * (n + 2.0) + p.y + 1.5) / cloudTextureSize;
	vec2 b = vec2(a.x, (mod(z + 1.0, n) * (n + 2.0) + p.y + 1.5) / cloudTextureSize.y);
	return mix(texture2D(cloudNoise, a).r, texture2D(cloudNoise, b).r, fract(p.z));
}

float cloudDensity(vec3 position)
{
	float h = (position.y - cloudLayer.x) / max(cloudLayer.y, 0.001);
	if (h <= 0.0 || h >= 1.0 || cloudLayer.z <= 0.0)
		return 0.0;
	vec3 p = vec3((position.x - cloudWind.x) / 320.0 + cloudWind.z,
		h * 2.0, (position.z - cloudWind.y) / 320.0 + cloudWind.w);
	float threshold = mix(1.1, -0.1, cloudLayer.z);
	float shape = smoothstep(threshold - 0.1, threshold + 0.1, cloudNoise3D(p));
	if (shape <= 0.0)
		return 0.0;
	float detail = 1.0;
	if (cloudParams.w > 0.0)
		detail = mix(1.0, clamp(cloudNoise3D(p * 3.11 + 17.0) * 1.5 + 0.1, 0.0, 1.0), cloudParams.w);
	float profile = smoothstep(0.0, 0.18, h) * (1.0 - smoothstep(0.72, 1.0, h));
	return shape * detail * profile;
}

float cloudLightTransmission(vec3 position)
{
	float verticalDistance = cloudLight.y >= 0.0 ? cloudLayer.x + cloudLayer.y - position.y : position.y - cloudLayer.x;
	float distanceToTop = max(verticalDistance, 0.0) / max(abs(cloudLight.y), 0.05);
	distanceToTop = min(distanceToTop, cloudLayer.y * 16.0);
	float stepLength = distanceToTop / 3.0;
	float opticalDepth = 0.0;
	for (int j = 0; j < 3; ++j) {
		vec3 q = position + cloudLight.xyz * (float(j) + 0.5) * stepLength;
		opticalDepth += cloudDensity(q) * stepLength * cloudLayer.w;
	}
	return exp(-opticalDepth);
}

vec4 integrateCloudsWithMoments(vec3 origin, vec3 direction, float maximumDistance, float jitter,
	out vec2 moments)
{
	moments = vec2(0.0);
	// No sampler access when unavailable, disabled, transparent or geometrically empty.
	if (cloudParams.x < 0.5 || cloudLayer.z <= 0.0 || cloudLayer.y <= 0.0 || cloudLayer.w <= 0.0)
		return vec4(0.0, 0.0, 0.0, 1.0);
	float first = 0.0;
	float last = min(maximumDistance, cloudParams.z);
	if (abs(direction.y) < 0.00001) {
		if (origin.y <= cloudLayer.x || origin.y >= cloudLayer.x + cloudLayer.y)
			return vec4(0.0, 0.0, 0.0, 1.0);
	} else {
		float a = (cloudLayer.x - origin.y) / direction.y;
		float b = (cloudLayer.x + cloudLayer.y - origin.y) / direction.y;
		first = max(0.0, min(a, b));
		last = min(last, max(a, b));
	}
	if (last <= first)
		return vec4(0.0, 0.0, 0.0, 1.0);
	vec3 bright = pow(max(cloudBright, vec3(0.0)), vec3(2.2));
	vec3 ambient = max(pow(max(cloudAmbient, vec3(0.0)), vec3(2.2)),
		bright * pow(max(cloudShadow, vec3(0.0)), vec3(2.2)) * 0.18);
	float cosine = dot(direction, cloudLight.xyz);
	const float g = 0.65;
	float phase = (1.0 - g * g) / pow(max(1.0 + g * g - 2.0 * g * cosine, 0.001), 1.5);
	float steps = clamp(cloudParams.y, 8.0, 64.0);
	float segmentLength = (last - first) / steps;
	vec3 scattering = vec3(0.0);
	float transmission = 1.0;
	float eventSum = 0.0;
	for (int i = 0; i < 64; ++i) {
		if (float(i) >= steps)
			break;
		float t = first + (float(i) + jitter) * segmentLength;
		vec3 position = origin + direction * t;
		float density = cloudDensity(position);
		if (density <= 0.0001)
			continue;
		float segmentT = exp(-density * cloudLayer.w * segmentLength);
		vec3 source = ambient;
		if (cloudLight.w > 0.0)
			source += bright * cloudLightTransmission(position) * cloudLight.w * (0.65 + phase * 0.1);
		scattering += transmission * (1.0 - segmentT) * source;
		float eventWeight = transmission * (1.0 - segmentT);
		if (eventWeight > 0.0) {
			eventSum += eventWeight;
			float delta = t - moments.x;
			moments.x += delta * (eventWeight / eventSum);
			moments.y += eventWeight * delta * (t - moments.x);
		}
		transmission *= segmentT;
		if (transmission < 0.005)
			break;
	}
	// Smooth the far entry boundary without changing transport for nearby/inside rays.
	float fade = 1.0 - smoothstep(cloudParams.z * 0.8, cloudParams.z, first);
	if (eventSum > 0.0)
		moments.y = sqrt(max(moments.y / eventSum, 0.0));
	return vec4(scattering * fade, mix(1.0, transmission, fade));
}

vec4 integrateClouds(vec3 origin, vec3 direction, float maximumDistance, float jitter)
{
	vec2 unused;
	return integrateCloudsWithMoments(origin, direction, maximumDistance, jitter, unused);
}
