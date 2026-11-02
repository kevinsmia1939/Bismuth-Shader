// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#define rendered texture0
#define depthmap texture1
#define surfaceMap texture2
#ifndef SCENE_SKY_DIVISOR
#define SCENE_SKY_DIVISOR 1.0
#endif
uniform sampler2D rendered;
uniform sampler2D depthmap;
uniform sampler2D surfaceMap;
uniform mat4 inverseProjection;
uniform mat4 sceneProjection;
uniform mat4 inverseView;
uniform vec2 texelSize0;
uniform vec2 projectionScale;
uniform vec4 sceneParams; // haze density, reflection strength, bounce strength, bounce radius
uniform vec4 surfaceLight; // shared world source direction, smooth horizon strength
uniform vec3 surfaceLightColor; // linear daylight, including sunset tint
uniform vec3 cameraPosition;
uniform vec3 dayLight;
uniform vec4 fogColor;
uniform float atmosphereEnabled;
uniform float waterCameraInside;
uniform vec3 waterScatterColor;
#ifdef FOG_TRANSPORT_PASS
uniform float animationTimer;
#endif
CENTROID_ VARYING_ mediump vec2 varTexCoord;

vec3 viewPosition(vec2 uv, float depth)
{
	vec4 p = inverseProjection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
	return p.xyz / p.w;
}

vec3 decodeNormal(vec2 encoded)
{
	vec2 e = encoded * 2.0 - 1.0;
	vec3 n = vec3(e, 1.0 - abs(e.x) - abs(e.y));
	vec2 signs = step(vec2(0.0), n.xy) * 2.0 - 1.0;
	n.xy += signs * -clamp(-n.z, 0.0, 1.0);
	return normalize(n);
}

vec3 surfacePosition(vec2 uv, float z)
{
	vec3 ray = viewPosition(uv, 0.5);
	return ray * (z / max(ray.z, 0.0001));
}

vec3 linearColor(vec2 uv)
{
	return pow(max(texture2D(rendered, uv).rgb, vec3(0.0)), vec3(2.2));
}

vec2 projectPosition(vec3 p)
{
	vec4 clip = sceneProjection * vec4(p, 1.0);
	return clip.xy / clip.w * 0.5 + 0.5;
}

bool insideScreen(vec2 uv)
{
	return min(uv.x, uv.y) > 0.001 && max(uv.x, uv.y) < 0.999;
}

// Integral of exp(-max(height,0)/scale) over a straight segment. Splitting
// at sea level avoids a midpoint approximation changing haze as the camera
// crosses the height clamp. The short-interval limit avoids cancellation.
float hazeDensityIntegral(float startHeight, float endHeight, float distanceToCamera)
{
	const float scale = 640.0;
	float low = min(startHeight, endHeight);
	float high = max(startHeight, endHeight);
	float span = high - low;
	if (span < 0.01)
		return distanceToCamera * exp(-max((low + high) * 0.5, 0.0) / scale);
	float underground = clamp(-low / span, 0.0, 1.0);
	float aboveSpan = max(high, 0.0) - max(low, 0.0);
	float a = aboveSpan / scale;
	float average = a < 0.001 ? 1.0 - a * 0.5 + a * a / 6.0 : (1.0 - exp(-a)) / a;
	return distanceToCamera * (underground + (1.0 - underground) *
		exp(-max(low, 0.0) / scale) * average);
}

#ifdef ENABLE_SCREEN_SPACE_REFLECTIONS
vec4 traceReflection(vec3 p, vec3 n)
{
	vec3 direction = reflect(normalize(p), n);
	vec3 start = p + n * 0.3;
	vec3 previous = start;
	// Quadratic spacing keeps detail near contact while covering up to 64 nodes.
	for (int i = 1; i <= 40; i++) {
		float t = float(i) / 40.0;
		vec3 q = start + direction * (0.4 + t * t * 640.0);
		if (q.z <= 1.0)
			break;
		vec2 uv = projectPosition(q);
		bool leavingScreen = !insideScreen(uv);
		if (leavingScreen) {
			// A coarse step may leave the screen after crossing a valid donor
			// just inside its edge. Test the clipped segment before falling back.
			if (!insideScreen(projectPosition(previous)))
				return vec4(0.0);
			vec3 lo = previous, hi = q;
			for (int j = 0; j < 8; ++j) {
				vec3 mid = (lo + hi) * 0.5;
				if (insideScreen(projectPosition(mid))) lo = mid;
				else hi = mid;
			}
			q = lo;
			uv = projectPosition(q);
		}
		float depth = texture2D(depthmap, uv).r;
		float hitZ = viewPosition(uv, depth).z;
		float gap = q.z - hitZ;
		float thickness = max(0.5, hitZ * 0.008);
		if (depth < 1.0 && gap > 0.0) {
			// The first crossing is authoritative. A large depth discontinuity
			// is a silhouette, not permission to march through the foreground
			// until an unrelated background surface happens to match.
			if (gap >= thickness + length(q - previous))
				return vec4(0.0);
			vec3 lo = previous;
			vec3 hi = q;
			for (int j = 0; j < 8; j++) {
				vec3 mid = (lo + hi) * 0.5;
				vec2 midUV = projectPosition(mid);
				float midZ = viewPosition(midUV, texture2D(depthmap, midUV).r).z;
				if (mid.z > midZ)
					hi = mid;
				else
					lo = mid;
			}
			uv = projectPosition(hi);
			float finalDepth = texture2D(depthmap, uv).r;
			float finalGap = hi.z - viewPosition(uv, finalDepth).z;
			// Reject jumps across silhouettes and reflection of the water itself.
			vec4 hitSurface = texture2D(surfaceMap, uv);
			if (finalDepth < 1.0 && finalGap >= 0.0 && finalGap < thickness && hitSurface.b <= 1.0) {
				vec2 edge = min(uv, 1.0 - uv);
				float confidence = smoothstep(0.0, 0.08, min(edge.x, edge.y));
				confidence *= 1.0 - smoothstep(0.7, 1.0, t);
				return vec4(linearColor(uv), confidence);
			}
			// An ambiguous first intersection falls back to sky rather than
			// tracing through a rejected foreground surface. At most 48 depth tests.
			return vec4(0.0);
		}
		previous = q;
		if (leavingScreen)
			break;
	}
	return vec4(0.0);
}
#endif

#ifdef ENABLE_INDIRECT_LIGHTING
vec3 gatherBounce(vec2 uv, vec3 p, vec3 n, vec3 receiver)
{
	float radius = sceneParams.w;
	vec2 screenRadius = min(0.5 * radius * abs(projectionScale) / max(p.z, 1.0), vec2(0.2));
	vec3 bounce = vec3(0.0);
	for (int i = 0; i < 12; i++) {
		float t = (float(i) + 0.5) / 12.0;
		float angle = float(i) * 2.39996323;
		vec2 sampleUV = uv + vec2(cos(angle), sin(angle)) * sqrt(t) * screenRadius;
		if (!insideScreen(sampleUV))
			continue;
		vec4 donor = texture2D(surfaceMap, sampleUV);
		// Only opaque nodes provide a reliable normal and diffuse radiance.
		if (donor.b >= -1.0 || donor.a < 1.0)
			continue;
		vec3 q = surfacePosition(sampleUV, -donor.b);
		vec3 delta = q - p;
		float distanceToSample = length(delta);
		if (distanceToSample < 0.5 || distanceToSample > radius)
			continue;
		vec3 direction = delta / distanceToSample;
		float formFactor = max(dot(n, direction) - 0.04, 0.0) *
			max(dot(decodeNormal(donor.rg), -direction), 0.0);
		// A midpoint visibility check reduces bleeding through thin walls.
		vec3 midpoint = (p + q) * 0.5;
		vec2 midUV = projectPosition(midpoint);
		float midZ = viewPosition(midUV, texture2D(depthmap, midUV).r).z;
		if (midZ + 0.5 < midpoint.z)
			continue;
		float falloff = 1.0 - smoothstep(radius * 0.2, radius, distanceToSample);
		bounce += min(linearColor(sampleUV), vec3(1.0)) * formFactor * falloff;
	}
	// Bounded, single-bounce diffuse approximation; never feeds back into itself.
	// Recover a conservative diffuse reflectance from the lit receiver. Using
	// its dark scene radiance directly would suppress bounce inside shadows.
	float receiverPeak = max(max(receiver.r, receiver.g), receiver.b);
	vec3 reflectance = min(receiver / max(receiverPeak, 0.08), vec3(0.8));
	return reflectance * bounce * (sceneParams.z * 2.0 / 12.0);
}
#endif

#ifdef ENABLE_VOLUMETRIC_FOG
uniform vec4 volumeParams; // max distance, height falloff, density variation, steps
uniform vec3 volumeLightDirection;
uniform vec3 volumeLightColor;
uniform vec3 cameraOffset;
uniform float volumeShadowReady;
#ifdef ENABLE_DYNAMIC_SHADOWS
uniform sampler2D ShadowMapSampler;
uniform mat4 m_ShadowViewProj;
uniform vec4 CameraPos;
uniform float xyPerspectiveBias0;
uniform float xyPerspectiveBias1;
uniform float zPerspectiveBias;
#endif

float fogHash(vec3 p)
{
	p = fract(p * 0.1031);
	p += dot(p, p.yzx + 33.33);
	return fract((p.x + p.y) * p.z);
}

float fogNoise(vec3 p)
{
	vec3 cell = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(fogHash(cell), fogHash(cell + vec3(1, 0, 0)), f.x),
		mix(fogHash(cell + vec3(0, 1, 0)), fogHash(cell + vec3(1, 1, 0)), f.x), f.y),
		mix(mix(fogHash(cell + vec3(0, 0, 1)), fogHash(cell + vec3(1, 0, 1)), f.x),
		mix(fogHash(cell + vec3(0, 1, 1)), fogHash(cell + vec3(1, 1, 1)), f.x), f.y), f.z);
}

vec3 fogSunVisibility(vec3 position, float skyAccess)
{
#ifdef ENABLE_DYNAMIC_SHADOWS
	// Never sample an absent/stale shadow map, including when shadows are disabled.
	if (volumeShadowReady > 0.5) {
		vec4 light = m_ShadowViewProj * vec4(position, 1.0);
		vec2 delta = light.xy - CameraPos.xy;
		// Same perspective warp as the shadow caster. sign(0) avoids 0/0 on-axis.
		vec2 scale = max(1.0 - sign(delta) * CameraPos.xy, vec2(0.00001));
		vec2 relative = delta / scale;
		float factor = length(relative) * xyPerspectiveBias0 + xyPerspectiveBias1;
		light.xy = relative / max(factor, 0.00001) * scale + CameraPos.xy;
		vec3 uvz = vec3(light.xy, light.z * zPerspectiveBias) * 0.5 + 0.5;
		// No directional scattering outside known shadow coverage. This avoids
		// unoccluded shafts through terrain beyond the captured light frustum.
		if (min(uvz.x, uvz.y) <= 0.0 || max(uvz.x, uvz.y) >= 1.0 ||
			uvz.z <= 0.0 || uvz.z >= 1.0)
			return vec3(0.0);
		vec4 blocker = texture2D(ShadowMapSampler, uvz.xy);
		float receiver = uvz.z - 0.00015;
		if (receiver > blocker.r)
			return vec3(0.0);
#ifdef COLORED_SHADOWS
		if (receiver > blocker.b) {
			// Existing shadow format packs premultiplied transparent transmission.
			const float colorLevels = 128.0;
			const float radix = 129.0;
			return vec3(floor(blocker.a / (radix * radix)),
				mod(floor(blocker.a / radix), radix), mod(blocker.a, radix)) / colorLevels * skyAccess;
		}
#endif
		float edge = min(min(uvz.x, uvz.y), min(1.0 - uvz.x, 1.0 - uvz.y));
		return vec3(smoothstep(0.0, 0.04, edge) * skyAccess);
	}
#endif
	// An absent map is not evidence of an unoccluded outdoor light path.
	return vec3(skyAccess);
}

void integrateFogTransport(vec3 endpoint, float skyAccess, out vec3 scattering, out vec3 transmission, out float meanDistance)
{
	float distanceToCamera = min(length(endpoint), volumeParams.x);
	scattering = vec3(0.0);
	transmission = vec3(1.0);
	meanDistance = 0.0;
	if (distanceToCamera <= 0.0) return;
	vec3 viewRay = normalize(endpoint);
	vec3 worldRay = normalize((inverseView * vec4(viewRay, 0.0)).xyz);
	vec3 origin = (inverseView * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	vec3 ambient = pow(max(fogColor.rgb, vec3(0.0)), vec3(2.2)) * (0.65 * skyAccess);
	// Henyey-Greenstein phase, normalized relative to an isotropic phase.
	const float g = 0.55;
	float cosine = dot(worldRay, volumeLightDirection);
	float phase = (1.0 - g * g) / pow(max(1.0 + g * g - 2.0 * g * cosine, 0.001), 1.5);
	vec3 direct = volumeLightColor * (0.25 * phase);
	float eventSum = 0.0;
	float steps = clamp(volumeParams.w, 8.0, 64.0);
	// Stratification is stable in screen space; TAA integrates subpixel shifts.
	float jitter = fract(dot(gl_FragCoord.xy, vec2(0.754877666, 0.569840296)));
#ifdef FOG_TRANSPORT_PASS
	jitter = fract(jitter + animationTimer * 6553.6);
#endif
#ifdef ENABLE_VOXEL_FOG_LIGHTING
	vec3 localPositive, localNegative;
	voxelFogPhaseWeights(worldRay, localPositive, localNegative);
#endif
	for (int i = 0; i < 64; i++) {
		if (float(i) >= steps)
			break;
		float a = float(i) / steps;
		float b = (float(i) + 1.0) / steps;
		float start = distanceToCamera * a * a;
		float end = distanceToCamera * b * b;
		float t = mix(start, end, jitter);
		vec3 position = origin + worldRay * t;
		float height = max(cameraPosition.y + worldRay.y * t, 0.0);
		float density = sceneParams.x * exp(-height / max(volumeParams.y, 1.0));
		if (volumeParams.z > 0.0)
			density *= mix(1.0, 0.3 + 1.4 * fogNoise((position + cameraOffset) / 160.0), volumeParams.z);
		vec3 stepTransmission = exp(-density * (end - start) * vec3(0.65, 0.9, 1.25));
		vec3 visibility = vec3(0.0);
		if (max(max(direct.r, direct.g), direct.b) > 0.0)
			visibility = fogSunVisibility(position, skyAccess);
#ifdef ENABLE_CLOUD_SHADOWS
		visibility *= cloudSunTransmission(position);
#endif
		vec3 incident = ambient + direct * visibility;
#ifdef ENABLE_VOXEL_FOG_LIGHTING
		incident += voxelFogRadiance(position, worldRay, localPositive, localNegative);
#endif
		scattering += transmission * (1.0 - stepTransmission) * incident;
		float weight = dot(transmission * (1.0 - stepTransmission), vec3(0.2126, 0.7152, 0.0722));
		if (weight > 0.0) {
			eventSum += weight;
			meanDistance += (t - meanDistance) * weight / eventSum;
		}
		transmission *= stepTransmission;
		if (max(max(transmission.r, transmission.g), transmission.b) < 0.005)
			break;
	}
}

vec3 integrateFog(vec3 color, vec3 endpoint, float skyAccess)
{
	vec3 scattering, transmission;
	float unused;
	integrateFogTransport(endpoint, skyAccess, scattering, transmission, unused);
	return color * transmission + scattering;
}

vec3 integrateFog(vec3 color, vec3 endpoint)
{
	return integrateFog(color, endpoint, 1.0);
}
#endif

float waterInterfaceFresnel(float cosine, float incidentIndex, float transmittedIndex)
{
	float ratio = incidentIndex / transmittedIndex;
	float sinSquared = ratio * ratio * max(1.0 - cosine * cosine, 0.0);
	if (sinSquared >= 1.0) return 1.0;
	float transmittedCosine = sqrt(max(1.0 - sinSquared, 0.0));
	float rs = (incidentIndex * cosine - transmittedIndex * transmittedCosine) /
		max(incidentIndex * cosine + transmittedIndex * transmittedCosine, 0.000001);
	float rp = (transmittedIndex * cosine - incidentIndex * transmittedCosine) /
		max(transmittedIndex * cosine + incidentIndex * transmittedCosine, 0.000001);
	return 0.5 * (rs * rs + rp * rp);
}

float waterInternalReflectionWeight(float fresnel, float strength)
{
	// Keep the artistic gain at ordinary angles, but approach full reflection
	// continuously before TIR. Scaling every subcritical sample and switching
	// to 1 at the critical angle creates a visible jump of 1-strength.
	return fresnel * mix(strength, 1.0, smoothstep(0.5, 1.0, fresnel));
}

void main(void)
{
	vec2 uv = varTexCoord;
	vec4 original = texture2D(rendered, uv);
	float depth = texture2D(depthmap, uv).r;
	vec3 color = pow(max(original.rgb, vec3(0.0)), vec3(2.2));
	vec3 p = viewPosition(uv, min(depth, 0.99999));
	bool water = false;
	bool representedSurface = false;
	// Unknown foreground geometry cannot establish a path to the sky. Nodes
	// carry their native skylight in the existing floating-point surface alpha.
	float skyAccess = depth < 0.99999 ? 0.0 : 1.0;
#ifdef ENABLE_SCENE_SURFACE
	vec4 surface = texture2D(surfaceMap, uv);
	water = surface.b > 1.0 && surface.b < 60000.0 && surface.a >= 1.0;
	bool opaque = surface.b < -1.0 && surface.b > -60000.0 && surface.a >= 1.0;
	// A later object may write nearer depth without node-surface metadata.
	bool inFrontOfDepth = abs(surface.b) <= p.z + max(0.5, p.z * 0.002);
	water = water && inFrontOfDepth;
	opaque = opaque && inFrontOfDepth;
	representedSurface = water || opaque;
	if (representedSurface)
		skyAccess = clamp((surface.a - 1.0) * SCENE_SKY_DIVISOR, 0.0, 1.0);
	if (water || opaque)
		p = surfacePosition(uv, abs(surface.b));
#endif
#ifdef FOG_TRANSPORT_PASS
	vec3 scattering = vec3(0.0), transmission = vec3(1.0);
	float meanDistance = 0.0;
	bool fogActive = atmosphereEnabled > 0.5 && sceneParams.x > 0.0;
	if (fogActive) integrateFogTransport(p, skyAccess, scattering, transmission, meanDistance);
	gl_FragColor = vec4(scattering, min(meanDistance, 60000.0));
	// Endpoint zero marks sky, negative marks a disabled/bypassed volume.
	gl_FragData[1] = vec4(transmission, fogActive ? (depth < 0.99999 || representedSurface ? min(length(p), 60000.0) : 0.0) : -1.0);
	return;
#endif
#ifdef ENABLE_SCENE_SURFACE
	vec3 normal = decodeNormal(surface.rg);
#ifdef ENABLE_SCREEN_SPACE_REFLECTIONS
	if (water && sceneParams.y > 0.0) {
		vec3 ray = reflect(normalize(p), normal);
		vec3 worldRay = normalize((inverseView * vec4(ray, 0.0)).xyz);
		// Sky fallback follows the game's fog tint and daylight, including night.
		vec3 sky = pow(max(fogColor.rgb, vec3(0.0)), vec3(2.2));
		sky *= mix(0.65, 1.1, clamp(worldRay.y, 0.0, 1.0));
		sky *= skyAccess;
		if (waterCameraInside > 0.5)
			sky = pow(max(waterScatterColor, vec3(0.0)), vec3(2.2));
		vec4 reflection = traceReflection(p, normal);
		vec3 reflected = mix(sky, reflection.rgb, reflection.a);
		float cosine = clamp(abs(dot(normalize(-p), normal)), 0.0, 1.0);
		// Schlick approximation for air/water, with F0 = 0.02.
		float fresnel = 0.02 + 0.98 * pow(1.0 - cosine, 5.0);
		float reflectionWeight = fresnel * sceneParams.y;
		if (waterCameraInside > 0.5) {
			float physical = waterInterfaceFresnel(cosine, 1.333, 1.0);
			reflectionWeight = waterInternalReflectionWeight(physical, sceneParams.y);
		}
		color = mix(color, reflected, reflectionWeight);
	}
#endif
#ifdef ENABLE_INDIRECT_LIGHTING
	if (opaque && sceneParams.z > 0.0)
		color += gatherBounce(uv, p, normal, color);
#endif
#endif

#ifdef ENABLE_ATMOSPHERE
#ifdef ENABLE_VOLUMETRIC_FOG
#ifndef ENABLE_FOG_DENOISING
	if (atmosphereEnabled > 0.5 && sceneParams.x > 0.0)
		color = integrateFog(color, p, skyAccess);
#endif
#else
	if (atmosphereEnabled > 0.5 && sceneParams.x > 0.0 && (depth < 1.0 || water)) {
		vec3 worldRay = normalize((inverseView * vec4(normalize(p), 0.0)).xyz);
		float distanceToCamera = length(p);
		// Height-integrated exponential density. World units are ten per node.
		float opticalDepth = min(sceneParams.x * hazeDensityIntegral(cameraPosition.y,
			cameraPosition.y + worldRay.y * distanceToCamera, distanceToCamera), 8.0);
		float forward = pow(max(dot(worldRay, surfaceLight.xyz), 0.0), 12.0);
		vec3 sky = pow(max(fogColor.rgb, vec3(0.0)), vec3(2.2));
		vec3 scatter = (sky + surfaceLightColor * (forward * surfaceLight.w * 0.25)) * skyAccess;
		vec3 transmission = exp(-opticalDepth * vec3(0.65, 0.9, 1.25));
		color = color * transmission + scatter * (1.0 - transmission);
	}
#endif
#endif
	gl_FragColor = vec4(pow(max(color, vec3(0.0)), vec3(1.0 / 2.2)), original.a);
}
