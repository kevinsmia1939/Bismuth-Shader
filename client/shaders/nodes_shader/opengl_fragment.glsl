#ifdef USE_ARRAY_TEXTURE
	uniform mediump sampler2DArray baseTexture;
#else
	uniform sampler2D baseTexture;
#endif
#ifndef SCENE_SKY_DIVISOR
#define SCENE_SKY_DIVISOR 1.0
#endif
#define crackTexture texture1
uniform sampler2D crackTexture;
#if defined(ENABLE_WATER_REFRACTION) && (MATERIAL_TYPE == TILE_MATERIAL_LIQUID_TRANSPARENT || MATERIAL_TYPE == TILE_MATERIAL_WAVING_LIQUID_TRANSPARENT)
#ifndef ENABLE_VOXEL_LIGHTING
uniform sampler2D texture2;
#endif
#define REFRACTIVE_WATER
#endif

uniform vec3 dayLight;
#if defined(ENABLE_MATERIAL_SHADING) || defined(ENABLE_WATER_REFLECTIONS)
uniform vec4 surfaceLight; // World direction toward the source, illumination strength.
uniform vec3 surfaceLightColor; // Linear native daylight color.
#endif
#if defined(ENABLE_SCENE_SURFACE) || defined(ENABLE_WATER_REFRACTION)
uniform mat4 sceneView;

vec2 encodeSurfaceNormal(vec3 normal)
{
	normal /= max(abs(normal.x) + abs(normal.y) + abs(normal.z), 0.00001);
	vec2 encoded = normal.xy;
	if (normal.z < 0.0)
		encoded = (1.0 - abs(encoded.yx)) * (step(vec2(0.0), encoded) * 2.0 - 1.0);
	return encoded * 0.5 + 0.5;
}
#endif

#ifdef ENABLE_MATERIAL_SHADING
// Surface-gradient bump mapping from albedo luminance; no extra texture assets.
vec3 detailNormal(vec3 normal, vec3 position, float height)
{
	vec3 dpdx = dFdx(position);
	vec3 dpdy = dFdy(position);
	vec3 r1 = cross(dpdy, normal);
	vec3 r2 = cross(normal, dpdx);
	float determinant = dot(dpdx, r1);
	vec3 gradient = (r1 * dFdx(height) + r2 * dFdy(height)) *
		sign(determinant) / max(abs(determinant), 0.00001);
	gradient = clamp(gradient, vec3(-1.0), vec3(1.0));
	return normalize(normal - MATERIAL_NORMAL_STRENGTH * gradient);
}

vec3 dielectricHighlight(vec3 normal, vec3 view, vec3 light, float roughness)
{
	float nl = max(dot(normal, light), 0.0);
	float nv = max(dot(normal, view), 0.0);
	if (nl <= 0.0 || nv <= 0.0 || dot(view + light, view + light) < 0.000001)
		return vec3(0.0);
	vec3 halfway = normalize(view + light);
	float nh = max(dot(normal, halfway), 0.0);
	float vh = max(dot(view, halfway), 0.0);
	float a2 = pow(roughness, 4.0);
	vec3 normalCrossHalf = cross(normal, halfway);
	float denominator = dot(normalCrossHalf, normalCrossHalf) + nh * nh * a2;
	float distribution = a2 / max(3.14159265 * denominator * denominator, 0.0001);
	float k = (roughness + 1.0) * (roughness + 1.0) / 8.0;
	float geometry = nv / (nv * (1.0 - k) + k) * nl / (nl * (1.0 - k) + k);
	float fresnel = 0.04 + 0.96 * pow(1.0 - vh, 5.0);
	return vec3(min(distribution * geometry * fresnel / max(4.0 * nv, 0.001), 0.5));
}
#endif
uniform lowp vec4 fogColor;
uniform float fogDistance;
uniform float fogShadingParameter;

// The cameraOffset is the current center of the visible world.
uniform highp vec3 cameraOffset;
uniform vec3 cameraPosition;
uniform float animationTimer;
uniform vec3 waterMeshWaves;
uniform float crackAnimationLength;
uniform float crackLevel;
uniform float crackTextureScale;

#ifdef ENABLE_DYNAMIC_SHADOWS
	// shadow texture
	uniform sampler2D ShadowMapSampler;
	// shadow uniforms
	uniform vec3 v_LightDirection;
	uniform float f_textureresolution;
	uniform mat4 m_ShadowViewProj;
	uniform float f_shadowfar;
	uniform float f_shadow_strength;
	uniform vec4 CameraPos;
	uniform float xyPerspectiveBias0;
	uniform float xyPerspectiveBias1;
	uniform vec3 shadow_tint;

	VARYING_ float adj_shadow_strength;
	VARYING_ float cosLight;
	VARYING_ float f_normal_length;
	VARYING_ vec3 shadow_position;
	VARYING_ float perspective_factor;
#endif


VARYING_ vec3 vNormal;
// World position in the visible world (i.e. relative to the cameraOffset.)
// This can be used for many shader effects without loss of precision.
// If the absolute position is required it can be calculated with
// cameraOffset + worldPosition (for large coordinates the limits of float
// precision must be considered).
VARYING_ vec3 worldPosition;
CENTROID_ VARYING_ lowp vec4 varColor;
CENTROID_ VARYING_ mediump vec2 varTexCoord;
// Conditional because 'flat' is not available on old GLSL
#ifdef USE_ARRAY_TEXTURE
flat VARYING_ uint varTexLayer;
#endif
CENTROID_ VARYING_ float nightRatio;
VARYING_ highp vec3 eyeVec;

#if __VERSION__ >= 130
#define mtsmoothstep smoothstep
#else
float mtsmoothstep(in float edge0, in float edge1, in float x)
{
	float t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0);
	return t * t * (3.0 - 2.0 * t);
}
#endif

#ifdef ENABLE_DYNAMIC_SHADOWS
// assuming near is always 1.0
float getLinearDepth()
{
	return 2.0 * f_shadowfar / (f_shadowfar + 1.0 - (2.0 * gl_FragCoord.z - 1.0) * (f_shadowfar - 1.0));
}

vec3 getLightSpacePosition()
{
	return shadow_position * 0.5 + 0.5;
}

float shadowCutoff(float x) {
	#if defined(ENABLE_TRANSLUCENT_FOLIAGE) && MATERIAL_TYPE == TILE_MATERIAL_WAVING_LEAVES
		return mtsmoothstep(0.0, 0.002, x);
	#else
		return step(0.0, x);
	#endif
}

#ifdef COLORED_SHADOWS

// c_precision of 128 fits within 7 base-10 digits
const float c_precision = 128.0;
const float c_precisionp1 = c_precision + 1.0;

float packColor(vec3 color)
{
	return floor(color.b * c_precision + 0.5)
		+ floor(color.g * c_precision + 0.5) * c_precisionp1
		+ floor(color.r * c_precision + 0.5) * c_precisionp1 * c_precisionp1;
}

vec3 unpackColor(float value)
{
	vec3 color;
	color.b = mod(value, c_precisionp1) / c_precision;
	color.g = mod(floor(value / c_precisionp1), c_precisionp1) / c_precision;
	color.r = floor(value / (c_precisionp1 * c_precisionp1)) / c_precision;
	return color;
}

vec4 getHardShadowColor(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
	vec4 texDepth = texture2D(shadowsampler, smTexCoord.xy).rgba;

	float visibility = shadowCutoff(realDistance - texDepth.r);
	vec4 result = vec4(visibility, vec3(0.0,0.0,0.0));//unpackColor(texDepth.g));
	if (visibility < 0.1) {
		visibility = shadowCutoff(realDistance - texDepth.b);
		result = vec4(visibility, unpackColor(texDepth.a));
	}
	return result;
}

#else

float getHardShadow(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
	float texDepth = texture2D(shadowsampler, smTexCoord.xy).r;
	float visibility = shadowCutoff(realDistance - texDepth);
	return visibility;
}

#endif


#if SHADOW_FILTER == 2
	#define PCFBOUND 2.0 // 5x5
	#define PCFSAMPLES 25
#elif SHADOW_FILTER == 1
	#define PCFBOUND 1.0 // 3x3
	#define PCFSAMPLES 9
#else
	#define PCFBOUND 0.0
	#define PCFSAMPLES 1
#endif

#ifdef COLORED_SHADOWS
float getHardShadowDepth(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
	vec4 texDepth = texture2D(shadowsampler, smTexCoord.xy);
	float depth = max(realDistance - texDepth.r, realDistance - texDepth.b);
	return depth;
}
#else
float getHardShadowDepth(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
	float texDepth = texture2D(shadowsampler, smTexCoord.xy).r;
	float depth = realDistance - texDepth;
	return depth;
}
#endif

#define BASEFILTERRADIUS 1.0

float getPenumbraRadius(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
	// Return fast if sharp shadows are requested
	if (PCFBOUND == 0.0 || SOFTSHADOWRADIUS <= 0.0)
		return 0.0;

	vec2 clampedpos;
	float y, x;
	float depth = getHardShadowDepth(shadowsampler, smTexCoord.xy, realDistance);
	// A factor from 0 to 1 to reduce blurring of short shadows
	float sharpness_factor = 1.0;
	// conversion factor from shadow depth to blur radius
	float depth_to_blur = f_shadowfar / SOFTSHADOWRADIUS / xyPerspectiveBias0;
	if (depth > 0.0 && f_normal_length > 0.0)
		// 5 is empirical factor that controls how fast shadow loses sharpness
		sharpness_factor = clamp(5.0 * depth * depth_to_blur, 0.0, 1.0);
	depth = 0.0;

	float world_to_texture = xyPerspectiveBias1 / perspective_factor / perspective_factor
			* f_textureresolution / 2.0 / f_shadowfar;
	float world_radius = 0.2; // shadow blur radius in world float coordinates, e.g. 0.2 = 0.02 of one node

	return max(BASEFILTERRADIUS * f_textureresolution / 4096.0,  sharpness_factor * world_radius * world_to_texture * SOFTSHADOWRADIUS);
}

#ifdef POISSON_FILTER
const vec2[64] poissonDisk = vec2[64](
	vec2(0.170019, -0.040254),
	vec2(-0.299417, 0.791925),
	vec2(0.645680, 0.493210),
	vec2(-0.651784, 0.717887),
	vec2(0.421003, 0.027070),
	vec2(-0.817194, -0.271096),
	vec2(-0.705374, -0.668203),
	vec2(0.977050, -0.108615),
	vec2(0.063326, 0.142369),
	vec2(0.203528, 0.214331),
	vec2(-0.667531, 0.326090),
	vec2(-0.098422, -0.295755),
	vec2(-0.885922, 0.215369),
	vec2(0.566637, 0.605213),
	vec2(0.039766, -0.396100),
	vec2(0.751946, 0.453352),
	vec2(0.078707, -0.715323),
	vec2(-0.075838, -0.529344),
	vec2(0.724479, -0.580798),
	vec2(0.222999, -0.215125),
	vec2(-0.467574, -0.405438),
	vec2(-0.248268, -0.814753),
	vec2(0.354411, -0.887570),
	vec2(0.175817, 0.382366),
	vec2(0.487472, -0.063082),
	vec2(0.355476, 0.025357),
	vec2(-0.084078, 0.898312),
	vec2(0.488876, -0.783441),
	vec2(0.470016, 0.217933),
	vec2(-0.696890, -0.549791),
	vec2(-0.149693, 0.605762),
	vec2(0.034211, 0.979980),
	vec2(0.503098, -0.308878),
	vec2(-0.016205, -0.872921),
	vec2(0.385784, -0.393902),
	vec2(-0.146886, -0.859249),
	vec2(0.643361, 0.164098),
	vec2(0.634388, -0.049471),
	vec2(-0.688894, 0.007843),
	vec2(0.464034, -0.188818),
	vec2(-0.440840, 0.137486),
	vec2(0.364483, 0.511704),
	vec2(0.034028, 0.325968),
	vec2(0.099094, -0.308023),
	vec2(0.693960, -0.366253),
	vec2(0.678884, -0.204688),
	vec2(0.001801, 0.780328),
	vec2(0.145177, -0.898984),
	vec2(0.062655, -0.611866),
	vec2(0.315226, -0.604297),
	vec2(-0.780145, 0.486251),
	vec2(-0.371868, 0.882138),
	vec2(0.200476, 0.494430),
	vec2(-0.494552, -0.711051),
	vec2(0.612476, 0.705252),
	vec2(-0.578845, -0.768792),
	vec2(-0.772454, -0.090976),
	vec2(0.504440, 0.372295),
	vec2(0.155736, 0.065157),
	vec2(0.391522, 0.849605),
	vec2(-0.620106, -0.328104),
	vec2(0.789239, -0.419965),
	vec2(-0.545396, 0.538133),
	vec2(-0.178564, -0.596057)
);

#ifdef COLORED_SHADOWS

vec4 getShadowColor(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
#ifdef ENABLE_CONTACT_HARDENING_SHADOWS
	return contactHardeningShadow(shadowsampler, smTexCoord, realDistance,
		vec4(CameraPos.xy, xyPerspectiveBias0, xyPerspectiveBias1), f_textureresolution);
#endif
	float radius = getPenumbraRadius(shadowsampler, smTexCoord, realDistance);
	if (radius < 0.1) {
		// we are in the middle of even brightness, no need for filtering
		return getHardShadowColor(shadowsampler, smTexCoord.xy, realDistance);
	}

	vec2 clampedpos;
	vec4 visibility = vec4(0.0);
	float scale_factor = radius / f_textureresolution;

	int samples = (1 + 1 * int(SOFTSHADOWRADIUS > 1.0)) * PCFSAMPLES; // scale max samples for the soft shadows
	samples = int(clamp(pow(4.0 * radius + 1.0, 2.0), 1.0, float(samples)));
	int init_offset = int(floor(mod(((smTexCoord.x * 34.0) + 1.0) * smTexCoord.y, 64.0-float(samples))));
	int end_offset = int(samples) + init_offset;

	for (int x = init_offset; x < end_offset; x++) {
		clampedpos = poissonDisk[x] * scale_factor + smTexCoord.xy;
		visibility += getHardShadowColor(shadowsampler, clampedpos.xy, realDistance);
	}

	return visibility / float(samples);
}

#else

float getShadow(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
#ifdef ENABLE_CONTACT_HARDENING_SHADOWS
	return contactHardeningShadow(shadowsampler, smTexCoord, realDistance,
		vec4(CameraPos.xy, xyPerspectiveBias0, xyPerspectiveBias1), f_textureresolution).x;
#endif
	float radius = getPenumbraRadius(shadowsampler, smTexCoord, realDistance);
	if (radius < 0.1) {
		// we are in the middle of even brightness, no need for filtering
		return getHardShadow(shadowsampler, smTexCoord.xy, realDistance);
	}

	vec2 clampedpos;
	float visibility = 0.0;
	float scale_factor = radius / f_textureresolution;

	int samples = (1 + 1 * int(SOFTSHADOWRADIUS > 1.0)) * PCFSAMPLES; // scale max samples for the soft shadows
	samples = int(clamp(pow(4.0 * radius + 1.0, 2.0), 1.0, float(samples)));
	int init_offset = int(floor(mod(((smTexCoord.x * 34.0) + 1.0) * smTexCoord.y, 64.0-float(samples))));
	int end_offset = int(samples) + init_offset;

	for (int x = init_offset; x < end_offset; x++) {
		clampedpos = poissonDisk[x] * scale_factor + smTexCoord.xy;
		visibility += getHardShadow(shadowsampler, clampedpos.xy, realDistance);
	}

	return visibility / float(samples);
}

#endif

#else
/* poisson filter disabled */

#ifdef COLORED_SHADOWS

vec4 getShadowColor(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
#ifdef ENABLE_CONTACT_HARDENING_SHADOWS
	return contactHardeningShadow(shadowsampler, smTexCoord, realDistance,
		vec4(CameraPos.xy, xyPerspectiveBias0, xyPerspectiveBias1), f_textureresolution);
#endif
	float radius = getPenumbraRadius(shadowsampler, smTexCoord, realDistance);
	if (radius < 0.1) {
		// we are in the middle of even brightness, no need for filtering
		return getHardShadowColor(shadowsampler, smTexCoord.xy, realDistance);
	}

	vec2 clampedpos;
	vec4 visibility = vec4(0.0);
	float x, y;
	float bound = (1 + 0.5 * int(SOFTSHADOWRADIUS > 1.0)) * PCFBOUND; // scale max bound for soft shadows
	bound = clamp(0.5 * (4.0 * radius - 1.0), 0.5, bound);
	float scale_factor = radius / bound / f_textureresolution;
	float n = 0.0;

	// basic PCF filter
	for (y = -bound; y <= bound; y += 1.0)
	for (x = -bound; x <= bound; x += 1.0) {
		clampedpos = vec2(x,y) * scale_factor + smTexCoord.xy;
		visibility += getHardShadowColor(shadowsampler, clampedpos.xy, realDistance);
		n += 1.0;
	}

	return visibility / max(n, 1.0);
}

#else
float getShadow(sampler2D shadowsampler, vec2 smTexCoord, float realDistance)
{
#ifdef ENABLE_CONTACT_HARDENING_SHADOWS
	return contactHardeningShadow(shadowsampler, smTexCoord, realDistance,
		vec4(CameraPos.xy, xyPerspectiveBias0, xyPerspectiveBias1), f_textureresolution).x;
#endif
	float radius = getPenumbraRadius(shadowsampler, smTexCoord, realDistance);
	if (radius < 0.1) {
		// we are in the middle of even brightness, no need for filtering
		return getHardShadow(shadowsampler, smTexCoord.xy, realDistance);
	}

	vec2 clampedpos;
	float visibility = 0.0;
	float x, y;
	float bound = (1 + 0.5 * int(SOFTSHADOWRADIUS > 1.0)) * PCFBOUND; // scale max bound for soft shadows
	bound = clamp(0.5 * (4.0 * radius - 1.0), 0.5, bound);
	float scale_factor = radius / bound / f_textureresolution;
	float n = 0.0;

	// basic PCF filter
	for (y = -bound; y <= bound; y += 1.0)
	for (x = -bound; x <= bound; x += 1.0) {
		clampedpos = vec2(x,y) * scale_factor + smTexCoord.xy;
		visibility += getHardShadow(shadowsampler, clampedpos.xy, realDistance);
		n += 1.0;
	}

	return visibility / max(n, 1.0);
}

#endif

#endif
#endif

// maps [0, N] to [0, 1] like GL_REPEAT would
vec2 uv_repeat(vec2 v)
{
	if (v.x > 1.0)
		v.x = fract(v.x);
	if (v.y > 1.0)
		v.y = fract(v.y);
	return v;
}

void main(void)
{
	vec2 uv = varTexCoord.st;

#ifdef USE_ARRAY_TEXTURE
	vec4 base = texture(baseTexture, vec3(uv, float(varTexLayer))).rgba;
#else
	vec4 base = texture2D(baseTexture, uv).rgba;
#endif

	// Keep the original alpha for cutout testing after normal derivatives.
	float cutoutAlpha = base.a;

	// Apply crack overlay
	float crack_progress = min(crackLevel, crackAnimationLength - 1.0);
#ifdef REFRACTIVE_WATER
	if (waterParams.x > 0.5)
		crack_progress = -1.0;
#endif
	if (crack_progress >= 0.0) {
		// undo scaling of e.g. world-aligned nodes
		vec2 orig_uv = uv_repeat(uv * vec2(crackTextureScale));

		vec2 cuv_offset = vec2(0.0, crack_progress / crackAnimationLength);
		vec2 cuv_factor = vec2(1.0, 1.0 / crackAnimationLength);
		vec4 crack = texture2D(crackTexture, cuv_offset + orig_uv * cuv_factor);
		base = mix(base, crack, crack.a);
	}

	vec4 col = vec4(base.rgb * varColor.rgb, 1.0);
	vec3 waterSpecular = vec3(0.0);
	vec3 cloudExplicitSun = vec3(0.0);
	vec3 waterSunVisibility = vec3(1.0);
	vec3 surfaceSunVisibility = vec3(1.0);
	vec3 cloudGeometryVisibility = vec3(1.0);
	vec3 materialData = vec3(1.0, 0.8, 0.0);
	vec3 materialSun = vec3(0.0);
	vec3 materialPoint = vec3(0.0);
	bool authoredMaterial = false;
	// Native light banks distinguish skylight from lamps. Global sky color is
	// not evidence that a covered surface can see that sky.
	float nativeSky = clamp((1.0 - nightRatio) *
		max(max(varColor.r, varColor.g), varColor.b), 0.0, 1.0);

	// Fragment normal shared by direct shading and the screen-space surface buffer.
	vec3 fNormal = normalize(vNormal + vec3(0.0, 0.000001, 0.0));
#ifdef ENABLE_MATERIAL_SHADING
#if !MATERIAL_WATER_REFLECTIONS && (MATERIAL_TYPE != TILE_MATERIAL_WAVING_LEAVES && MATERIAL_TYPE != TILE_MATERIAL_WAVING_PLANTS)
	vec3 geometricNormal = fNormal;
	float surfaceRoughness = MATERIAL_ROUGHNESS;
#ifdef ENABLE_MATERIAL_MAPS
	vec3 materialFilterNormal = vec3(0.0, 0.0, 1.0);
	float materialMipVariance = 0.0;
	materialData = readMaterialORM(uv, MATERIAL_ROUGHNESS);
	authoredMaterial = materialMapFlags.x > 0.5 || materialMapFlags.y > 0.5;
	if (materialMapFlags.x > 0.5)
		fNormal = readMaterialNormal(fNormal, worldPosition, uv, materialFilterNormal, materialMipVariance);
	else
#endif
	fNormal = detailNormal(fNormal, worldPosition, dot(base.rgb, vec3(0.2126, 0.7152, 0.0722)));
#ifdef ENABLE_MATERIAL_MAPS
	materialData.g = filterMaterialRoughness(geometricNormal, materialFilterNormal, materialData.g, materialMipVariance);
	surfaceRoughness = materialData.g;
#endif
	// Retain the mesh's baked lighting; add only the change caused by microgeometry.
	vec3 detailLight = normalize(vec3(0.35, 0.8, 0.25));
	float detail = clamp(dot(fNormal, detailLight) - dot(geometricNormal, detailLight), -0.15, 0.15);
	col.rgb *= 1.0 + detail;
#endif
#endif
#if MATERIAL_WATER_REFLECTIONS && (!defined(GL_ES) || __VERSION__ >= 300)
	// All water consumers use the actual displaced triangle, including sloped
	// flow and side faces. Align with the mesh normal on either viewing side.
	vec3 waterNormal = cross(dFdx(worldPosition), dFdy(worldPosition));
	if (dot(waterNormal, waterNormal) > 0.00000001) {
		waterNormal = normalize(waterNormal);
		fNormal = dot(waterNormal, fNormal) < 0.0 ? -waterNormal : waterNormal;
	}
#endif

	// Derivatives need neighboring lanes, including those outside a cutout.
#ifdef USE_DISCARD
	if (cutoutAlpha == 0.0)
		discard;
#endif
#ifdef USE_DISCARD_REF
	if (cutoutAlpha < 0.5)
		discard;
#endif

#ifdef ENABLE_DYNAMIC_SHADOWS

	if (f_shadow_strength > 0.0) {
		float shadow_int = 0.0;
		vec3 shadow_color = vec3(0.0, 0.0, 0.0);
		vec3 posLightSpace = getLightSpacePosition();

		float distance_rate = (1.0 - pow(clamp(2.0 * length(posLightSpace.xy - 0.5),0.0,1.0), 10.0));
		if (max(abs(posLightSpace.x - 0.5), abs(posLightSpace.y - 0.5)) > 0.5)
			distance_rate = 0.0;
		float f_adj_shadow_strength = max(adj_shadow_strength - mtsmoothstep(0.9, 1.1, posLightSpace.z),0.0);

		if (distance_rate > 1e-7) {

#ifdef COLORED_SHADOWS
			vec4 visibility;
			if (cosLight > 0.0 || f_normal_length < 1e-3)
				visibility = getShadowColor(ShadowMapSampler, posLightSpace.xy, posLightSpace.z);
			else
				visibility = vec4(1.0, 0.0, 0.0, 0.0);
			shadow_int = visibility.r;
			shadow_color = visibility.gba;
#else
			if (cosLight > 0.0 || f_normal_length < 1e-3)
				shadow_int = getShadow(ShadowMapSampler, posLightSpace.xy, posLightSpace.z);
			else
				shadow_int = 1.0;
#endif
			shadow_int *= distance_rate;
			shadow_int = clamp(shadow_int, 0.0, 1.0);

		}

		// turns out that nightRatio falls off much faster than
		// actual brightness of artificial light in relation to natual light.
		// Power ratio was measured on torches in MTG (brightness = 14).
		float adjusted_night_ratio = pow(max(0.0, nightRatio), 0.6);

		float shadow_uncorrected = shadow_int;
		waterSunVisibility = vec3(1.0) - shadow_int * (vec3(1.0) - shadow_color);

		// Apply self-shadowing when light falls at a narrow angle to the surface
		// Cosine of the cut-off angle.
		const float self_shadow_cutoff_cosine = 0.035;
		if (f_normal_length != 0.0 && cosLight < self_shadow_cutoff_cosine) {
			shadow_int = max(shadow_int, 1.0 - clamp(cosLight, 0.0, self_shadow_cutoff_cosine)/self_shadow_cutoff_cosine);
			shadow_color = mix(vec3(0.0), shadow_color, min(cosLight, self_shadow_cutoff_cosine)/self_shadow_cutoff_cosine);

#if (MATERIAL_TYPE == TILE_MATERIAL_WAVING_LEAVES || MATERIAL_TYPE == TILE_MATERIAL_WAVING_PLANTS)
			// Prevents foliage from becoming insanely bright outside the shadow map.
			shadow_uncorrected = mix(shadow_int, shadow_uncorrected, clamp(distance_rate * 4.0 - 3.0, 0.0, 1.0));
#endif
		}

		cloudGeometryVisibility = vec3(1.0)-shadow_int*(vec3(1.0)-shadow_color);
		shadow_int *= f_adj_shadow_strength;
		surfaceSunVisibility = clamp(vec3(1.0) - shadow_int * (vec3(1.0) - shadow_color), vec3(0.0), vec3(1.0));

		// calculate fragment color from components:
		col.rgb =
				adjusted_night_ratio * col.rgb + // artificial light
				(1.0 - adjusted_night_ratio) * ( // natural light
						col.rgb * (1.0 - shadow_int * (1.0 - shadow_color) * (1.0 - shadow_tint)) +  // filtered texture color
						dayLight * shadow_color * shadow_int);                 // reflected filtered sunlight/moonlight


		vec3 reflect_ray = -normalize(v_LightDirection - fNormal * dot(v_LightDirection, fNormal) * 2.0);

		vec3 viewVec = normalize(worldPosition + cameraOffset - cameraPosition);

#if (defined(ENABLE_NODE_SPECULAR) && !MATERIAL_WATER_REFLECTIONS)
		// Apply specular to blocks.
		if (dot(v_LightDirection, vNormal) < 0.0) {
			float intensity = 2.0 * (1.0 - (base.r * varColor.r));
			const float specular_exponent = 5.0;
			const float fresnel_exponent =  4.0;

			vec3 highlightLight =
				intensity * dayLight * (1.0 - nightRatio) * (1.0 - shadow_uncorrected) * f_adj_shadow_strength *
				pow(max(dot(reflect_ray, viewVec), 0.0), fresnel_exponent) * pow(1.0 - abs(dot(viewVec, fNormal)), specular_exponent);
			col.rgb += highlightLight;
			cloudExplicitSun += highlightLight;
		}
#endif

#if (MATERIAL_TYPE == TILE_MATERIAL_WAVING_PLANTS || MATERIAL_TYPE == TILE_MATERIAL_WAVING_LEAVES) && defined(ENABLE_TRANSLUCENT_FOLIAGE)
		// Simulate translucent foliage.
		vec3 foliageLight = 4.0 * dayLight * base.rgb * normalize(base.rgb * varColor.rgb * varColor.rgb) * f_adj_shadow_strength * pow(max(-dot(v_LightDirection, viewVec), 0.0), 4.0) * max(1.0 - shadow_uncorrected, 0.0);
		col.rgb += foliageLight;
		cloudExplicitSun += foliageLight;
#endif
	}
#endif


#if defined(ENABLE_MATERIAL_SHADING) || defined(ENABLE_WATER_REFLECTIONS)
	vec3 surfaceViewVector = cameraPosition - cameraOffset - worldPosition;
	float surfaceViewLength = length(surfaceViewVector);
	vec3 surfaceView = surfaceViewVector / max(surfaceViewLength, 0.000001);
	float naturalShare = 1.0 - pow(clamp(nightRatio, 0.0, 1.0), 0.6);
#endif

// Surface illumination remains available with shadows disabled or faded.
// Shadow strength changes visibility above, never the source's radiance.
#if defined(ENABLE_MATERIAL_SHADING) && !MATERIAL_WATER_REFLECTIONS && (MATERIAL_TYPE != TILE_MATERIAL_WAVING_LEAVES && MATERIAL_TYPE != TILE_MATERIAL_WAVING_PLANTS)
	if (surfaceLight.w > 0.0 && surfaceViewLength > 0.000001 &&
			dot(vNormal, vNormal) > 0.000001 && dot(geometricNormal, surfaceLight.xyz) > 0.0) {
#ifdef ENABLE_MATERIAL_MAPS
		vec3 f0 = mix(vec3(0.04), pow(max(base.rgb, vec3(0.0)), vec3(2.2)), materialData.b);
		materialSun = materialSpecular(fNormal, surfaceView, surfaceLight.xyz,
			materialData.g, f0) * surfaceLightColor *
			(surfaceLight.w * naturalShare) * surfaceSunVisibility;
#else
		materialSun = dielectricHighlight(fNormal, surfaceView, surfaceLight.xyz, surfaceRoughness) *
			surfaceLightColor * (surfaceLight.w * naturalShare) * surfaceSunVisibility;
#endif
	}
#endif

#if defined(ENABLE_WATER_REFLECTIONS) && MATERIAL_WATER_REFLECTIONS && ENABLE_WAVING_WATER
	if (surfaceViewLength > 0.000001) {
		float fresnel = dot(fNormal, surfaceView);
		fresnel = clamp(pow(max(1.0 - fresnel * fresnel, 0.0), 8.0), 0.0, 1.0) * 0.8 + 0.2;
#ifndef ENABLE_SCREEN_SPACE_REFLECTIONS
		col.rgb *= 1.0 - 0.5 * naturalShare;
		col.rgb += fogColor.rgb * (fresnel * fresnel * 0.5 * naturalShare);
#endif
		if (surfaceLight.w > 0.0 && dot(fNormal, surfaceLight.xyz) > 0.0) {
			vec3 reflected = reflect(-surfaceLight.xyz, fNormal);
			float peak = mtsmoothstep(0.85, 0.9, pow(clamp(dot(reflected, surfaceView), 0.0, 1.0), 32.0));
			vec3 highlight = 12.0 * pow(max(surfaceLightColor, vec3(0.0)), vec3(1.0 / 2.2)) * fresnel * peak;
			highlight /= clamp(max(highlight.r, max(highlight.g, highlight.b)) * 0.375, 1.0, 400.0);
			waterSpecular = highlight * (surfaceLight.w * naturalShare) * surfaceSunVisibility;
			col.rgb += waterSpecular;
		}
	}
#endif

#if defined(ENABLE_CLOUD_SHADOWS)
	float cloudTransmission = cloudSunTransmission(worldPosition);
#ifdef MATERIAL_EMISSIVE
	// Keep self illumination while attenuating separately tracked reflections.
	col.rgb = max(col.rgb-waterSpecular-cloudExplicitSun, vec3(0)) + (waterSpecular+cloudExplicitSun)*cloudTransmission;
#else
	col.rgb = cloudShadeNative(max(col.rgb-waterSpecular-cloudExplicitSun, vec3(0)), cloudTransmission,
		fNormal, nightRatio, cloudGeometryVisibility) + (waterSpecular+cloudExplicitSun)*cloudTransmission;
#endif
	waterSpecular *= cloudTransmission;
	materialSun *= cloudTransmission;
	waterSunVisibility *= cloudTransmission;
#endif

#ifdef ENABLE_VOXEL_LIGHTING
#if defined(ENABLE_VOXEL_MATERIAL_SPECULAR) && !MATERIAL_WATER_REFLECTIONS && (MATERIAL_TYPE != TILE_MATERIAL_WAVING_LEAVES && MATERIAL_TYPE != TILE_MATERIAL_WAVING_PLANTS)
	vec3 pointView = cameraPosition - cameraOffset - worldPosition;
	vec3 pointF0 = mix(vec3(0.04), pow(max(base.rgb, vec3(0.0)), vec3(2.2)), materialData.b);
	col.rgb = applyVoxelLighting(col.rgb, base.rgb, worldPosition, fNormal, vNormal,
		nightRatio, dayLight, true, materialData.r, pointView, materialData.g, pointF0, true, materialPoint);
#else
	col.rgb = applyVoxelLighting(col.rgb, base.rgb, worldPosition, fNormal, vNormal, nightRatio, dayLight, true, materialData.r);
#endif
#endif
#ifdef ENABLE_MATERIAL_MAPS
	if (authoredMaterial) {
		vec3 f0 = mix(vec3(0.04), pow(max(base.rgb, vec3(0.0)), vec3(2.2)), materialData.b);
		vec3 viewVector = cameraPosition - cameraOffset - worldPosition;
		vec3 view = viewVector / max(length(viewVector), 0.000001);
		vec3 environment = materialEnvironment(fNormal, view, f0, materialData.g,
			materialData.r, fogColor.rgb, dayLight) * nativeSky;
		float nativeEmission = 0.0;
#ifdef MATERIAL_EMISSIVE
		nativeEmission = 1.0;
#endif
		vec3 linear = composeMaterialLighting(pow(max(col.rgb, vec3(0.0)), vec3(2.2)),
			materialSun + materialPoint, environment, materialData.b, nativeEmission);
		col.rgb = pow(max(linear, vec3(0.0)), vec3(1.0 / 2.2));
	}
	else
#endif
	if (any(greaterThan(materialSun + materialPoint, vec3(0.0))))
		col.rgb = pow(pow(max(col.rgb, vec3(0.0)), vec3(2.2)) + materialSun + materialPoint, vec3(1.0 / 2.2));
	float outputAlpha = base.a;
#ifdef REFRACTIVE_WATER
	if (waterParams.x > 0.5) {
		vec3 viewNormal = normalize((sceneView * vec4(fNormal, 0.0)).xyz);
		vec4 transmission = refractWater(crackTexture, texture2, -eyeVec,
			viewNormal, max(col.rgb - waterSpecular, vec3(0.0)), base.a);
		if (transmission.a > 0.5) {
			col.rgb = transmission.rgb + waterSpecular;
			// The opaque background is already included in the transmission term.
			outputAlpha = 1.0;
		}
	}
#endif

#if defined(ENABLE_WATER_VOLUME) && !MATERIAL_WATER_REFLECTIONS
	col.rgb = applyWaterCaustics(col.rgb, worldPosition, fNormal, nightRatio, waterSunVisibility);
#endif
	// Due to a bug in some (older ?) graphics stacks (possibly in the glsl compiler ?),
	// the fog will only be rendered correctly if the last operation before the
	// clamp() is an addition. Else, the clamp() seems to be ignored.
	// E.g. the following won't work:
	//      float clarity = clamp(fogShadingParameter
	//		* (fogDistance - length(eyeVec)) / fogDistance), 0.0, 1.0);
	// As additions usually come for free following a multiplication, the new formula
	// should be more efficient as well.
	// Note: clarity = (1 - fogginess)
	float clarity = clamp(fogShadingParameter
		- fogShadingParameter * length(eyeVec) / fogDistance, 0.0, 1.0);
	float fogColorMax = max(max(fogColor.r, fogColor.g), fogColor.b);
	// Prevent zero division.
	if (fogColorMax < 0.0000001) fogColorMax = 1.0;
	// For high clarity (light fog) we tint the fog color.
	// For this to not make the fog color artificially dark we need to normalize using the
	// fog color's brightest value. We then blend our base color with this to make the fog.
	vec4 tintedFog = fogColor * pow(fogColor / fogColorMax, vec4(2.0 * clarity));
	tintedFog.rgb *= nativeSky;
	col = mix(tintedFog, col, clarity);
	col = vec4(col.rgb, outputAlpha);

	gl_FragColor = col;
#ifdef ENABLE_SCENE_SURFACE
	vec3 viewNormal = normalize((sceneView * vec4(fNormal, 0.0)).xyz);
	// Attachment 1 disables blending independently, including on translucent
	// water. Alpha stores coverage (>=1) plus local skylight for fog transport.
	// Signed view depth identifies water (+) versus opaque diffuse nodes (-).
	float surfaceDepth = -eyeVec.z;
#if !MATERIAL_WATER_REFLECTIONS
	surfaceDepth = -surfaceDepth;
#endif
	gl_FragData[1] = vec4(encodeSurfaceNormal(viewNormal), surfaceDepth, 1.0 + nativeSky / SCENE_SKY_DIVISOR);
#endif
#ifdef ENABLE_SCENE_EMISSION_MASK
	writeSceneEmission(col.a);
#endif
}
