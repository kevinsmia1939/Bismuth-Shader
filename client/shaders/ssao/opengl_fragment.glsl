// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later

#define rendered texture0
#define depthmap texture1
uniform sampler2D rendered;
uniform sampler2D depthmap;
#ifdef ENABLE_SCENE_SURFACE
uniform sampler2D texture2;
uniform float ssaoSurfaceReady;
#endif
#ifdef ENABLE_SCENE_EMISSION_MASK
#ifdef ENABLE_SCENE_SURFACE
#define ssaoEmissionMask texture3
#else
#define ssaoEmissionMask texture2
#endif
uniform sampler2D ssaoEmissionMask;
uniform float ssaoEmissionReady;
#endif
uniform vec2 texelSize0;
uniform mat4 inverseProjection;
uniform vec2 projectionScale;
// Radius in world units, strength.
uniform vec2 ssaoParams;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

// Camera-relative view space avoids precision loss at large world coordinates.
vec3 viewPosition(vec2 uv, float depth)
{
	vec4 p = inverseProjection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	return p.xyz / p.w;
}

vec3 positionAt(vec2 uv)
{
	return viewPosition(uv, texture2D(depthmap, uv).r);
}

void main(void)
{
	vec2 uv = varTexCoord;
	vec4 color = texture2D(rendered, uv);
	float depth = texture2D(depthmap, uv).r;
	// Leave the sky untouched, and avoid reconstructing the far plane.
	if (depth >= 1.0 || ssaoParams.y <= 0.0) {
		gl_FragColor = color;
		return;
	}

	vec3 p = viewPosition(uv, depth);
	float emission = 0.0;
#ifdef ENABLE_SCENE_EMISSION_MASK
	if (ssaoEmissionReady > 0.5) {
		emission = clamp(texture2D(ssaoEmissionMask, uv).r, 0.0, 1.0);
		if (emission >= 0.999) { gl_FragColor = color; return; }
	}
#endif
#ifdef ENABLE_SCENE_SURFACE
	if (ssaoSurfaceReady > 0.5) {
		vec4 surface = texture2D(texture2, uv);
		// Refraction already contains transmitted/scattered light. Do not shade
		// that composite using the depth of the floor behind the water. A closer
		// object may overwrite depth while leaving an older water marker behind.
		if (surface.b > 0.0 && surface.b < 60000.0 && surface.a > 0.99 &&
				surface.b <= p.z + max(0.5, p.z * 0.002)) {
			gl_FragColor = color;
			return;
		}
	}
#endif
	vec3 left = p - positionAt(uv - vec2(texelSize0.x, 0.0));
	vec3 right = positionAt(uv + vec2(texelSize0.x, 0.0)) - p;
	vec3 down = p - positionAt(uv - vec2(0.0, texelSize0.y));
	vec3 up = positionAt(uv + vec2(0.0, texelSize0.y)) - p;
	// Choose the nearest depth on each axis to avoid silhouette halos.
	vec3 dx = abs(left.z) < abs(right.z) ? left : right;
	vec3 dy = abs(down.z) < abs(up.z) ? down : up;
	vec3 normal = cross(dx, dy);
	normal /= max(length(normal), 0.00001);
	if (dot(normal, p) > 0.0)
		normal = -normal;

	float radius = ssaoParams.x;
	vec2 screenRadius = min(0.5 * radius * abs(projectionScale) / max(abs(p.z), 0.001), vec2(0.15));
	float occlusion = 0.0;
	// A fixed spiral is stable while moving, without requiring temporal history.
	for (int i = 0; i < 16; i++) {
		float t = (float(i) + 0.5) / 16.0;
		float angle = float(i) * 2.39996323;
		vec2 sampleUV = uv + vec2(cos(angle), sin(angle)) * sqrt(t) * screenRadius;
		// Do not repeat edge texels beyond the viewport.
		if (sampleUV.x <= 0.0 || sampleUV.x >= 1.0 || sampleUV.y <= 0.0 || sampleUV.y >= 1.0)
			continue;
		float sampleDepth = texture2D(depthmap, sampleUV).r;
		if (sampleDepth >= 1.0)
			continue;
		vec3 delta = viewPosition(sampleUV, sampleDepth) - p;
		float distanceToSample = length(delta);
		// World-space falloff excludes unrelated surfaces across depth discontinuities.
		float falloff = 1.0 - smoothstep(radius * 0.25, radius, distanceToSample);
		float horizon = max(dot(normal, delta) / max(distanceToSample, 0.001) - 0.08, 0.0);
		occlusion += horizon * falloff;
	}
	float visibility = clamp(1.0 - ssaoParams.y * occlusion * (2.0 / 16.0), 0.25, 1.0);
	visibility = mix(visibility, 1.0, emission);
	// Apply attenuation in linear light, preserving the source alpha.
	color.rgb *= pow(visibility, 1.0 / 2.2);
	gl_FragColor = color;
}
