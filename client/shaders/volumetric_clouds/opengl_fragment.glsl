// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#define sceneDepth texture1
uniform sampler2D sceneDepth;
uniform mat4 inverseProjection;
uniform mat4 inverseView;
uniform vec3 cameraOffset;
uniform float animationTimer;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

void main(void)
{
	vec2 uv = varTexCoord;
	float depth = texture2D(sceneDepth, uv).r;
	vec4 view = inverseProjection * vec4(uv * 2.0 - 1.0, min(depth, 0.99999) * 2.0 - 1.0, 1.0);
	vec3 position = view.xyz / view.w;
	vec3 ray = normalize((inverseView * vec4(normalize(position), 0.0)).xyz);
	vec3 origin = (inverseView * vec4(0.0, 0.0, 0.0, 1.0)).xyz + cameraOffset;
	float distanceToSurface = depth < 1.0 ? length(position) : cloudParams.z;
	float temporal = 0.0;
#ifdef CLOUD_TEMPORAL_JITTER
	temporal = animationTimer * 6553.6;
#endif
	float jitter = fract(dot(gl_FragCoord.xy, vec2(0.754877666, 0.569840296)) + temporal);
#ifdef ENABLE_CLOUD_DENOISING
	vec2 moments;
	vec4 cloud = integrateCloudsWithMoments(origin, ray, distanceToSurface, jitter, moments);
	gl_FragColor = cloud;
	// Extinction-event mean and spread, geometric endpoint (zero for sky), opacity.
	gl_FragData[1] = vec4(clamp(moments.x, 0.0, 60000.0),
		depth < 0.99999 ? min(distanceToSurface, 60000.0) : 0.0,
		clamp(moments.y, 0.0, 60000.0), 1.0 - cloud.a);
#else
	gl_FragColor = integrateClouds(origin, ray, distanceToSurface, jitter);
#endif
}
