// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Scatter alpha stores extinction-event mean distance; transmission alpha stores
// geometric endpoint distance (zero sky, negative bypass). Never filter metadata.
uniform sampler2D texture0, texture1, texture2, texture3;
uniform mat4 fogInverseProjection, fogInverseView, fogReprojection;
uniform vec3 fogPreviousCamera;
uniform vec2 fogHistoryParams;
uniform vec2 texelSize0;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

bool fogSameEndpoint(float a, float b)
{
	return a == 0.0 ? b == 0.0 : b > 0.0 && abs(a - b) < max(2.0, a * 0.02);
}

void main(void)
{
	vec2 uv = varTexCoord;
	vec4 centerS = texture2D(texture0, uv), centerT = texture2D(texture1, uv);
	vec3 scatter = centerS.rgb, transmit = centerT.rgb;
	if (centerS.a > 0.0 && centerT.a >= 0.0) {
		vec3 loS = scatter, hiS = scatter, loT = transmit, hiT = transmit;
		vec3 sumS = vec3(0), sumT = vec3(0);
		float total = 0.0;
		for (int y = -1; y <= 1; ++y) for (int x = -1; x <= 1; ++x) {
			vec2 sampleUV = clamp(uv + vec2(float(x), float(y)) * texelSize0, texelSize0 * 0.5, 1.0 - texelSize0 * 0.5);
			vec4 s = texture2D(texture0, sampleUV), t = texture2D(texture1, sampleUV);
			if (s.a <= 0.0 || !fogSameEndpoint(centerT.a, t.a) || abs(s.a - centerS.a) > max(4.0, centerS.a * 0.05)) continue;
			float lightDifference = length(s.rgb - centerS.rgb) / max(0.05, min(length(s.rgb), length(centerS.rgb)));
			float lightWeight = exp(-max(lightDifference - 0.5, 0.0) * 4.0);
			float weight = (2.0 - abs(float(x))) * (2.0 - abs(float(y))) * exp(-length(t.rgb - centerT.rgb) * 6.0) * lightWeight;
			sumS += s.rgb * weight; sumT += t.rgb * weight; total += weight;
			if (lightWeight > 0.01) {
				loS = min(loS, s.rgb); hiS = max(hiS, s.rgb);
				loT = min(loT, t.rgb); hiT = max(hiT, t.rgb);
			}
		}
		if (total > 0.0) { scatter = sumS / total; transmit = sumT / total; }
		if (fogHistoryParams.x > 0.5 && fogHistoryParams.y > 0.0) {
			vec4 view = fogInverseProjection * vec4(uv * 2.0 - 1.0, 1.0, 1.0);
			vec3 ray = normalize((fogInverseView * vec4(normalize(view.xyz / view.w), 0.0)).xyz);
			vec3 origin = (fogInverseView * vec4(0, 0, 0, 1)).xyz;
			vec3 anchor = origin + ray * centerS.a;
			vec4 previous = fogReprojection * vec4(anchor, 1.0);
			vec2 oldUV = previous.xy / max(previous.w, 0.000001) * 0.5 + 0.5;
			if (previous.w > 0.0 && min(oldUV.x, oldUV.y) > 0.0 && max(oldUV.x, oldUV.y) < 1.0) {
				float expectedMean = length(anchor - fogPreviousCamera);
				float expectedEndpoint = centerT.a == 0.0 ? 0.0 : length(origin + ray * centerT.a - fogPreviousCamera);
				vec2 coordinate = oldUV / texelSize0 - 0.5;
				vec2 base = floor(coordinate), fraction = fract(coordinate);
				vec3 oldS = vec3(0), oldT = vec3(0);
				float oldTotal = 0.0;
				for (int y = 0; y < 2; ++y) for (int x = 0; x < 2; ++x) {
					vec2 offset = vec2(float(x), float(y));
					vec2 sampleUV = clamp((base + offset + 0.5) * texelSize0, texelSize0 * 0.5, 1.0 - texelSize0 * 0.5);
					vec4 s = texture2D(texture2, sampleUV), t = texture2D(texture3, sampleUV);
					if (s.a <= 0.0 || !fogSameEndpoint(expectedEndpoint, t.a) ||
						abs(s.a - expectedMean) > max(4.0, expectedMean * 0.04) || (t.a > 0.0 && t.a < expectedMean - 2.0)) continue;
					vec2 weights = mix(1.0 - fraction, fraction, offset);
					float weight = weights.x * weights.y;
					oldS += s.rgb * weight; oldT += t.rgb * weight; oldTotal += weight;
				}
				if (oldTotal > 0.001) {
					oldS = clamp(oldS / oldTotal, loS, hiS); oldT = clamp(oldT / oldTotal, loT, hiT);
					float change = length(oldS - scatter) / max(0.05, length(scatter)) + length(oldT - transmit);
					float motion = length((oldUV - uv) / texelSize0);
					float weight = fogHistoryParams.y * exp(-change * 4.0 - motion * 0.02);
					scatter = mix(scatter, oldS, weight); transmit = mix(transmit, oldT, weight);
				}
			}
		}
	}
	gl_FragColor = vec4(max(scatter, vec3(0)), centerS.a);
	gl_FragData[1] = vec4(clamp(transmit, 0.0, 1.0), centerT.a);
}
