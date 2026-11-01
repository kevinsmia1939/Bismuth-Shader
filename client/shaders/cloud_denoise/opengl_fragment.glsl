// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#define currentCloud texture0
#define currentGuide texture1
#define historyCloud texture2
#define historyGuide texture3
uniform sampler2D currentCloud;
uniform sampler2D currentGuide;
uniform sampler2D historyCloud;
uniform sampler2D historyGuide;
uniform mat4 cloudInverseProjection;
uniform mat4 cloudInverseView;
uniform mat4 cloudReprojection;
uniform vec3 cloudPreviousCamera;
uniform vec2 cloudWindDelta;
uniform vec2 cloudHistoryParams; // valid, frame-rate adjusted weight
uniform vec2 texelSize0;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

bool sameEndpoint(float a, float b, float tolerance)
{
	return a == 0.0 ? b == 0.0 : b > 0.0 && abs(a - b) < max(2.0, a * tolerance);
}

bool sameCloud(vec4 a, vec4 b)
{
	return b.r > 0.0 && b.a > 0.00001 && sameEndpoint(a.g, b.g, 0.02) &&
		abs(a.r - b.r) < max(4.0, a.r * 0.04 + a.b * 0.05);
}

void main(void)
{
	vec2 uv = varTexCoord;
	vec4 center = texture2D(currentCloud, uv);
	vec4 guide = texture2D(currentGuide, uv);
	// Never fill a current empty ray with old or neighboring cloud radiance.
	if (guide.r <= 0.0 || guide.a <= 0.00001) {
		gl_FragColor = center;
		return;
	}
	vec4 minimum = center;
	vec4 maximum = center;
	vec4 filtered = vec4(0.0);
	float total = 0.0;
	for (int y = -1; y <= 1; ++y) for (int x = -1; x <= 1; ++x) {
		vec2 sampleUV = clamp(uv + vec2(float(x), float(y)) * texelSize0,
			texelSize0 * 0.5, 1.0 - texelSize0 * 0.5);
		vec4 neighborGuide = texture2D(currentGuide, sampleUV);
		if (!sameCloud(guide, neighborGuide)) continue;
		vec4 sampleValue = texture2D(currentCloud, sampleUV);
		float weight = (2.0 - abs(float(x))) * (2.0 - abs(float(y))) * exp(-abs(sampleValue.a - center.a) * 10.0);
		filtered += sampleValue * weight;
		total += weight;
		minimum = min(minimum, sampleValue);
		maximum = max(maximum, sampleValue);
	}
	filtered = total > 0.0 ? filtered / total : center;
	if (cloudHistoryParams.x > 0.5 && cloudHistoryParams.y > 0.0) {
		vec4 view = cloudInverseProjection * vec4(uv * 2.0 - 1.0, 1.0, 1.0);
		vec3 ray = normalize((cloudInverseView * vec4(normalize(view.xyz / view.w), 0.0)).xyz);
		vec3 origin = (cloudInverseView * vec4(0, 0, 0, 1)).xyz;
		vec3 anchor = origin + ray * guide.r - vec3(cloudWindDelta.x, 0.0, cloudWindDelta.y);
		vec4 previous = cloudReprojection * vec4(anchor, 1.0);
		vec2 historyUV = previous.xy / max(previous.w, 0.000001) * 0.5 + 0.5;
		if (previous.w > 0.0 && min(historyUV.x, historyUV.y) > 0.0 && max(historyUV.x, historyUV.y) < 1.0) {
			float expectedCloud = length(anchor - cloudPreviousCamera);
			float expectedEndpoint = length(origin + ray * guide.g - cloudPreviousCamera);
			vec2 coordinate = historyUV / texelSize0 - 0.5;
			vec2 base = floor(coordinate), fraction = fract(coordinate);
			vec4 old = vec4(0.0);
			float oldTotal = 0.0;
			// Reject each history tap before filtering; bilinear depth interpolation
			// must not merge an occluded foreground with background cloud radiance.
			for (int y = 0; y < 2; ++y) for (int x = 0; x < 2; ++x) {
				vec2 offset = vec2(float(x), float(y));
				vec2 sampleUV = clamp((base + offset + 0.5) * texelSize0,
					texelSize0 * 0.5, 1.0 - texelSize0 * 0.5);
				vec4 oldGuide = texture2D(historyGuide, sampleUV);
				bool endpoint = guide.g == 0.0 ? oldGuide.g == 0.0 : sameEndpoint(expectedEndpoint, oldGuide.g, 0.02);
				bool visible = oldGuide.r > 0.0 && oldGuide.a > 0.00001 && endpoint &&
					abs(oldGuide.r - expectedCloud) < max(4.0, expectedCloud * 0.025 + guide.b * 0.05) &&
					(oldGuide.g == 0.0 || oldGuide.g > expectedCloud - 2.0);
				if (!visible) continue;
				vec2 weights = mix(1.0 - fraction, fraction, offset);
				float weight = weights.x * weights.y;
				old += texture2D(historyCloud, sampleUV) * weight;
				oldTotal += weight;
			}
			if (oldTotal > 0.001) {
				old = clamp(old / oldTotal, minimum, maximum);
				float motion = length((historyUV - uv) / texelSize0);
				float weight = cloudHistoryParams.y * exp(-motion * 0.01 - abs(old.a - filtered.a) * 8.0);
				filtered = mix(filtered, old, weight);
			}
		}
	}
	gl_FragColor = vec4(max(filtered.rgb, vec3(0.0)), clamp(filtered.a, 0.0, 1.0));
}
