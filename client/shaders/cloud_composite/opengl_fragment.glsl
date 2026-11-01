// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#define rendered texture0
#define sceneDepth texture1
#define cloudScatter texture2
uniform sampler2D rendered;
uniform sampler2D sceneDepth;
uniform sampler2D cloudScatter;
uniform mat4 inverseProjection;
uniform vec2 cloudTextureSize;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

float cloudGuideDepth(vec2 uv)
{
	float depth = texture2D(sceneDepth, uv).r;
	if (depth >= 0.99999)
		return 1000000.0;
	vec4 view = inverseProjection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	return abs(view.z / view.w);
}

void main(void)
{
	vec2 uv = varTexCoord;
	vec4 original = texture2D(rendered, uv);
	float guide = cloudGuideDepth(uv);
	vec2 coordinate = uv * cloudTextureSize - 0.5;
	vec2 base = floor(coordinate);
	vec2 fraction = fract(coordinate);
	vec4 cloud = vec4(0.0);
	float total = 0.0;
	for (int y = 0; y < 2; ++y) for (int x = 0; x < 2; ++x) {
		vec2 offset = vec2(float(x), float(y));
		vec2 sampleUV = clamp((base + offset + 0.5) / cloudTextureSize,
			0.5 / cloudTextureSize, 1.0 - 0.5 / cloudTextureSize);
		vec2 weights = mix(1.0 - fraction, fraction, offset);
		float depthWeight = exp(-abs(cloudGuideDepth(sampleUV) - guide) / max(0.5, guide * 0.015));
		float weight = weights.x * weights.y * depthWeight;
		cloud += texture2D(cloudScatter, sampleUV) * weight;
		total += weight;
	}
	// A thin foreground object may have no matching low-resolution sample.
	// Preserve it rather than pulling background cloud radiance through its silhouette.
	if (total < 0.0001) {
		gl_FragColor = original;
		return;
	}
	cloud /= total;
	vec3 color = pow(max(original.rgb, vec3(0.0)), vec3(2.2)) * cloud.a + cloud.rgb;
	gl_FragColor = vec4(pow(max(color, vec3(0.0)), vec3(1.0 / 2.2)), original.a);
}
