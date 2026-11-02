// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#define currentFrame texture0
#define historyFrame texture1
#define depthmap texture2
#define surfaceMap texture3
uniform sampler2D currentFrame;
uniform sampler2D historyFrame;
#ifdef ENABLE_VOLUMETRIC_CLOUDS
uniform sampler2D texture4;
#endif
#ifdef ENABLE_FOG_DENOISING
#ifdef ENABLE_VOLUMETRIC_CLOUDS
#define fogTransmission texture5
#else
#define fogTransmission texture4
#endif
uniform sampler2D fogTransmission;
#endif
uniform sampler2D depthmap;
#ifdef ENABLE_SCENE_SURFACE
uniform sampler2D surfaceMap;
#endif
uniform mat4 taaReprojection;
uniform mat4 taaSkyReprojection;
uniform mat4 taaInverseProjection;
uniform vec4 taaParams; // jitter UV, history valid, history weight
uniform float taaWaterReactive;
uniform vec2 texelSize0;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

vec3 linearColor(vec3 color)
{
	return pow(max(color, vec3(0.0)), vec3(2.2));
}

vec3 toYCoCg(vec3 color)
{
	return vec3(dot(color, vec3(0.25, 0.5, 0.25)),
		dot(color, vec3(0.5, 0.0, -0.5)),
		dot(color, vec3(-0.25, 0.5, -0.25)));
}

vec3 fromYCoCg(vec3 color)
{
	return vec3(color.x + color.y - color.z, color.x + color.z, color.x - color.y - color.z);
}

void main(void)
{
	vec2 uv = varTexCoord;
	// Resolve onto an unjittered pixel grid. History uses that same grid.
	vec2 sourceUV = clamp(uv + taaParams.xy, texelSize0 * 0.5, 1.0 - texelSize0 * 0.5);
	vec3 current = linearColor(texture2D(currentFrame, sourceUV).rgb);
	float depth = texture2D(depthmap, sourceUV).r;
	vec4 clip = vec4(sourceUV * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	vec4 view = taaInverseProjection * clip;
	bool sky = depth >= 1.0;
	float linearDepth = sky ? 0.0 : clamp(view.z / view.w, 0.0, 60000.0);
	vec3 resolved = current;

	// Never sample uninitialised history on first use, resize or camera cut.
	if (taaParams.z > 0.5) {
		vec4 previous = sky ? taaSkyReprojection * vec4(clip.xy, 1.0, 1.0) : taaReprojection * clip;
		vec2 historyUV = previous.xy / max(previous.w, 0.000001) * 0.5 + 0.5;
		bool inside = previous.w > 0.0 && min(historyUV.x, historyUV.y) > 0.0 &&
			max(historyUV.x, historyUV.y) < 1.0;
		if (inside) {
			vec4 history = texture2D(historyFrame, historyUV);
			float expectedDepth = previous.w / max(view.w, 0.0000001);
			bool depthMatch = sky ? history.a < 0.001 : history.a > 0.0 &&
				abs(history.a - expectedDepth) < max(0.5, expectedDepth * 0.01);
			if (depthMatch) {
				vec3 minimum = vec3(1e20);
				vec3 maximum = vec3(-1e20);
				vec3 mean = vec3(0.0);
				vec3 squareMean = vec3(0.0);
				for (int y = -1; y <= 1; y++)
				for (int x = -1; x <= 1; x++) {
					vec3 sampleColor = toYCoCg(linearColor(texture2D(currentFrame,
						sourceUV + vec2(float(x), float(y)) * texelSize0).rgb));
					minimum = min(minimum, sampleColor);
					maximum = max(maximum, sampleColor);
					mean += sampleColor / 9.0;
					squareMean += sampleColor * sampleColor / 9.0;
				}
				vec3 deviation = sqrt(max(squareMean - mean * mean, vec3(0.0)));
				vec3 lower = max(minimum, mean - deviation * 1.25);
				vec3 upper = min(maximum, mean + deviation * 1.25);
				vec3 oldColor = clamp(toYCoCg(linearColor(history.rgb)), lower, upper);
				vec3 nowColor = toYCoCg(current);
				float contrast = abs(oldColor.x - nowColor.x) /
					max(0.1, max(oldColor.x, nowColor.x));
				// Animated cutouts and textures can change hue at equal brightness.
				// Luminance-only rejection retains their obsolete color for many
				// frames even when depth and the local color bounds still match.
				float chromaChange = dot(abs(oldColor.yz - nowColor.yz), vec2(1.0));
				float chromaScale = max(0.1, max(dot(abs(oldColor.yz), vec2(1.0)),
					dot(abs(nowColor.yz), vec2(1.0))));
				contrast = max(contrast, chromaChange / chromaScale);
				float movement = length((historyUV - uv) / texelSize0);
				float weight = taaParams.w * exp(-movement * 0.03) *
					(1.0 - min(contrast, 1.0) * 0.8);
				if (taaWaterReactive > 0.5)
					weight = min(weight, 0.35);
#ifdef ENABLE_SCENE_SURFACE
				// Water changes independently of camera motion; avoid long reflection trails.
				if (texture2D(surfaceMap, sourceUV).b > 1.0)
					weight = min(weight, 0.35);
#endif

#ifdef ENABLE_VOLUMETRIC_CLOUDS
				// Clouds move and have finite depth even behind sky pixels.
				float cloudOpacity = clamp(1.0 - texture2D(texture4, sourceUV).a, 0.0, 1.0);
				weight = mix(weight, min(weight, 0.25), cloudOpacity);
#endif
#ifdef ENABLE_FOG_DENOISING
				float fogOpacity = clamp(1.0 - dot(texture2D(fogTransmission, sourceUV).rgb, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
				weight = mix(weight, min(weight, 0.35), fogOpacity);
#endif
				resolved = mix(current, max(fromYCoCg(oldColor), vec3(0.0)), weight);
			}
		}
	}
	// Alpha carries linear depth solely for next frame's history rejection.
	gl_FragColor = vec4(pow(max(resolved, vec3(0.0)), vec3(1.0 / 2.2)), linearDepth);
}
