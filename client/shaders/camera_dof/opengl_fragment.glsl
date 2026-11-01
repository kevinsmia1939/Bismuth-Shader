// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
uniform sampler2D texture0;
uniform sampler2D texture1;
uniform vec2 texelSize0;
uniform mat4 cameraInverseProjection;
uniform vec2 cameraDepthJitter;
uniform vec2 cameraPixelScale;
uniform vec3 cameraDOFParams; // focus distance/range in world units, max output-pixel radius
CENTROID_ VARYING_ mediump vec2 varTexCoord;

float dofDepth(vec2 uv)
{
	float depth = texture2D(texture1, uv + cameraDepthJitter).r;
	if (depth >= 1.0) return 1000000.0;
	vec4 view = cameraInverseProjection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	return abs(view.z / view.w);
}

float dofCircle(float depth)
{
	float difference = depth - cameraDOFParams.x;
	float defocus = max(abs(difference) - cameraDOFParams.y, 0.0) /
		max(depth, max(cameraDOFParams.x * 0.1, 0.0001));
	return sign(difference) * clamp(defocus, 0.0, 1.0) * cameraDOFParams.z;
}

void main()
{
	vec2 uv = varTexCoord;
	vec4 original = texture2D(texture0, uv);
	if (cameraDOFParams.z <= 0.0) { gl_FragColor = original; return; }
	float depth = dofDepth(uv);
	float circle = dofCircle(depth);
	float radius = abs(circle);
	if (radius < 0.5) { gl_FragColor = original; return; }
	vec3 color = pow(max(original.rgb, vec3(0.0)), vec3(2.2));
	float total = 1.0;
	for (int i = 0; i < 24; ++i) {
		float sampleRadius = sqrt((float(i) + 0.5) / 24.0) * radius;
		float angle = float(i) * 2.39996323;
		vec2 sampleUV = uv + vec2(cos(angle), sin(angle)) * sampleRadius * texelSize0 * cameraPixelScale;
		if (min(sampleUV.x, sampleUV.y) < 0.0 || max(sampleUV.x, sampleUV.y) > 1.0) continue;
		float sampleDepth = dofDepth(sampleUV);
		float weight = 1.0;
		float tolerance = max(0.5, depth * 0.02);
		// Conservative occlusion: don't pull background through foreground silhouettes.
		if (circle < 0.0 && sampleDepth > depth + tolerance) continue;
		if (sampleDepth < depth - tolerance)
			weight = clamp(abs(min(dofCircle(sampleDepth), 0.0)) - sampleRadius + 0.5, 0.0, 1.0);
		color += pow(max(texture2D(texture0, sampleUV).rgb, vec3(0.0)), vec3(2.2)) * weight;
		total += weight;
	}
	gl_FragColor = vec4(pow(color / total, vec3(1.0 / 2.2)), original.a);
}
