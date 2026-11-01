// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
uniform sampler2D texture0;
uniform sampler2D texture1;
uniform vec2 texelSize0;
uniform mat4 cameraReprojection;
uniform mat4 cameraSkyReprojection;
uniform mat4 cameraInverseProjection;
uniform vec2 cameraDepthJitter;
uniform vec2 cameraPixelScale;
uniform vec4 cameraMotionParams; // history valid, normalized shutter, max output pixels, samples
CENTROID_ VARYING_ mediump vec2 varTexCoord;

float motionViewDepth(vec2 uv, float depth)
{
	vec4 view = cameraInverseProjection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	return abs(view.z / view.w);
}

void main()
{
	vec2 uv = varTexCoord;
	vec4 original = texture2D(texture0, uv);
	if (cameraMotionParams.x < 0.5 || cameraMotionParams.y <= 0.0 || cameraMotionParams.z <= 0.0) {
		gl_FragColor = original;
		return;
	}
	float depth = texture2D(texture1, uv + cameraDepthJitter).r;
	bool sky = depth >= 1.0;
	vec4 clip = vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	vec4 previous = sky ? cameraSkyReprojection * vec4(clip.xy, 1.0, 1.0) : cameraReprojection * clip;
	if (previous.w <= 0.000001) { gl_FragColor = original; return; }
	vec2 velocity = (uv - (previous.xy / previous.w * 0.5 + 0.5)) * cameraMotionParams.y;
	vec2 outputPixels = velocity / (texelSize0 * cameraPixelScale);
	float lengthPixels = length(outputPixels);
	if (lengthPixels < 0.25) { gl_FragColor = original; return; }
	velocity *= min(1.0, cameraMotionParams.z / max(lengthPixels, 0.0001));
	float centerDepth = sky ? 0.0 : motionViewDepth(uv, depth);
	vec3 color = pow(max(original.rgb, vec3(0.0)), vec3(2.2));
	float total = 1.0;
	float samples = clamp(cameraMotionParams.w, 4.0, 24.0);
	for (int i = 0; i < 24; ++i) {
		if (float(i) >= samples) break;
		vec2 sampleUV = uv + velocity * ((float(i) + 0.5) / samples - 0.5);
		if (min(sampleUV.x, sampleUV.y) < 0.0 || max(sampleUV.x, sampleUV.y) > 1.0) continue;
		float sampleDepth = texture2D(texture1, sampleUV + cameraDepthJitter).r;
		if (sky != (sampleDepth >= 1.0)) continue;
		if (!sky && abs(motionViewDepth(sampleUV, sampleDepth) - centerDepth) > max(0.5, centerDepth * 0.02))
			continue;
		color += pow(max(texture2D(texture0, sampleUV).rgb, vec3(0.0)), vec3(2.2));
		total += 1.0;
	}
	gl_FragColor = vec4(pow(color / total, vec3(1.0 / 2.2)), original.a);
}
