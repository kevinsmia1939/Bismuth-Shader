// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
uniform sampler2D texture0, texture1, texture2, texture3, texture4;
uniform mat4 inverseProjection;
uniform vec2 fogTextureSize;
uniform float atmosphereEnabled;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

vec3 fogCompositePosition(vec2 uv, float depth)
{
	vec4 p = inverseProjection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	return p.xyz / p.w;
}

void main(void)
{
	vec2 uv = varTexCoord;
	vec4 original = texture2D(texture0, uv);
	if (atmosphereEnabled < 0.5) { gl_FragColor = original; return; }
	float depth = texture2D(texture3, uv).r;
	vec3 p = fogCompositePosition(uv, min(depth, 0.99999));
	float guide = depth < 0.99999 ? min(length(p), 60000.0) : 0.0;
#ifdef ENABLE_SCENE_SURFACE
	vec4 surface = texture2D(texture4, uv);
	if (abs(surface.b) > 1.0 && abs(surface.b) < 60000.0 && surface.a >= 1.0 &&
			abs(surface.b) <= p.z + max(0.5, p.z * 0.002)) {
		vec3 ray = fogCompositePosition(uv, 0.5);
		p = ray * (abs(surface.b) / max(ray.z, 0.0001));
		guide = min(length(p), 60000.0);
	}
#endif
	vec2 coordinate = uv * fogTextureSize - 0.5;
	vec2 base = floor(coordinate), fraction = fract(coordinate);
	vec3 scatter = vec3(0), transmit = vec3(0);
	float total = 0.0;
	for (int y = 0; y < 2; ++y) for (int x = 0; x < 2; ++x) {
		vec2 offset = vec2(float(x), float(y));
		vec2 sampleUV = clamp((base + offset + 0.5) / fogTextureSize, 0.5 / fogTextureSize, 1.0 - 0.5 / fogTextureSize);
		vec4 s = texture2D(texture1, sampleUV), t = texture2D(texture2, sampleUV);
		if (t.a < 0.0 || (guide == 0.0 ? t.a != 0.0 : t.a <= 0.0)) continue;
		vec2 weights = mix(1.0 - fraction, fraction, offset);
		float weight = weights.x * weights.y * exp(-abs(t.a - guide) / max(0.5, guide * 0.015));
		scatter += s.rgb * weight; transmit += t.rgb * weight; total += weight;
	}
	if (total < 0.0001) { gl_FragColor = original; return; }
	vec3 color = pow(max(original.rgb, vec3(0)), vec3(2.2)) * (transmit / total) + scatter / total;
	gl_FragColor = vec4(pow(max(color, vec3(0)), vec3(1.0 / 2.2)), original.a);
}
