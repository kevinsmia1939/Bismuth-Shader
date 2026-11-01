// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_WATER_REFRACTION
uniform mat4 inverseProjection;
uniform mat4 sceneProjection;
uniform vec4 waterParams; // bound scene, absorption, maximum ray length, bending strength
uniform vec2 waterTexelSize;
uniform float waterCameraInside;
#ifdef ENABLE_WATER_VOLUME
uniform mat4 inverseView;
#endif

vec3 waterViewPosition(vec2 uv, float depth)
{
 vec4 p = inverseProjection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
 return p.xyz / p.w;
}

vec2 waterProject(vec3 p)
{
 vec4 clip = sceneProjection * vec4(p, 1.0);
 return clip.xy / clip.w * 0.5 + 0.5;
}

bool waterInsideScreen(vec2 uv)
{
 vec2 margin = max(waterTexelSize, vec2(0.001));
 return min(uv.x - margin.x, uv.y - margin.y) > 0.0 &&
  max(uv.x + margin.x, uv.y + margin.y) < 1.0;
}

vec4 refractWater(sampler2D opaqueColor, sampler2D opaqueDepth,
  vec3 position, vec3 normal, vec3 scatterColor, float opacity)
{
 // Guard before sampler access: hand/inventory/solid liquids retain native rendering.
 if (waterParams.x < 0.5 || position.z <= 0.0)
  return vec4(0.0);
 vec2 uv = gl_FragCoord.xy * waterTexelSize;
 float backgroundDepth = texture2D(opaqueDepth, uv).r;
 vec3 background = waterViewPosition(uv, min(backgroundDepth, 0.99999));
 // Conservative silhouette rejection prevents a foreground object being pulled into water.
 if (backgroundDepth < 1.0 && background.z <= position.z)
  return vec4(0.0);
 float rayLength = waterParams.z;
 float path = backgroundDepth < 1.0 ? min(length(background - position), rayLength) : rayLength;
 vec2 sampleUV = uv;
 float sampleConfidence = 0.0;
 vec3 incident = normalize(position);
 if (dot(normal, incident) > 0.0)
  normal = -normal;
 float indexRatio = waterCameraInside > 0.5 ? 1.333 : 1.0 / 1.333;
 vec3 bent = refract(incident, normal, indexRatio);
 // No transmitted radiance beyond the critical angle. The reflection pass handles TIR.
 if (dot(bent, bent) < 0.000001 && waterParams.w > 0.0)
  return vec4(0.0);
 vec3 direction = normalize(mix(incident, bent, waterParams.w));
 vec3 travelDirection = normalize(background - position);
 vec3 start = position + direction * 0.1;
 vec3 previous = start;
 for (int i = 1; i <= 32; i++) {
  float fraction = float(i) / 32.0;
  vec3 q = start + direction * (0.1 + rayLength * fraction * fraction);
  if (q.z <= 0.01)
   break;
  vec2 candidateUV = waterProject(q);
  bool leavingScreen = !waterInsideScreen(candidateUV);
  if (leavingScreen) {
   if (!waterInsideScreen(waterProject(previous))) break;
   vec3 lo = previous, hi = q;
   for (int j = 0; j < 8; ++j) {
    vec3 mid = (lo + hi) * 0.5;
    if (waterInsideScreen(waterProject(mid))) lo = mid;
    else hi = mid;
   }
   q = lo;
   candidateUV = waterProject(q);
  }
  float depth = texture2D(opaqueDepth, candidateUV).r;
  vec3 surface = waterViewPosition(candidateUV, min(depth, 0.99999));
  float thickness = max(0.3, surface.z * 0.003);
  float gap = q.z - surface.z;
  if (depth < 1.0 && gap >= 0.0) {
   if (surface.z <= position.z + 0.05 || gap > thickness + length(q - previous))
    break;
   vec3 lo = previous;
   vec3 hi = q;
   for (int j = 0; j < 5; j++) {
    vec3 mid = (lo + hi) * 0.5;
    vec2 midUV = waterProject(mid);
    float midZ = waterViewPosition(midUV, texture2D(opaqueDepth, midUV).r).z;
    if (mid.z >= midZ)
     hi = mid;
    else
     lo = mid;
   }
   vec2 hitUV = waterProject(hi);
   float hitDepth = texture2D(opaqueDepth, hitUV).r;
   vec3 hit = waterViewPosition(hitUV, hitDepth);
   if (hitDepth < 1.0 && hit.z > position.z + 0.05 && hi.z - hit.z >= 0.0 && hi.z - hit.z < thickness) {
    vec2 margin = max(waterTexelSize, vec2(0.001));
    vec2 edge = min(hitUV - margin, 1.0 - margin - hitUV);
    float confidence = smoothstep(0.0, 0.04, min(edge.x, edge.y));
    // Crossfade radiance, never UV coordinates: an interpolated coordinate
    // can pass over unrelated foreground terrain between two valid samples.
    sampleUV = hitUV;
    sampleConfidence = confidence;
    path = mix(path, min(length(hit - position), rayLength), confidence);
    travelDirection = normalize(mix(travelDirection, normalize(hit - position), confidence));
   }
   break;
  }
  previous = q;
  if (leavingScreen) break;
 }
 // Per-node texture alpha controls turbidity; actual distance controls attenuation.
 // Red is absorbed fastest. Scene/world units are ten per node.
#ifdef ENABLE_WATER_VOLUME
 if (waterVolumeParams.x > 0.5) {
  vec3 worldStart = (inverseView * vec4(position, 1.0)).xyz;
  vec3 worldDirection = normalize((inverseView * vec4(travelDirection, 0.0)).xyz);
  vec3 sampleStart = worldStart + worldDirection * 0.02;
  vec3 cell = floor((sampleStart - waterVolumeOrigin) / 10.0 + 0.5);
  if (waterVolumeInside(cell) && waterVolumeCell(cell).r > 0.1) {
   float firstExit;
   path = traceWaterVolume(sampleStart, worldDirection, path, firstExit).x;
  }
 }
#endif
 vec3 extinction = vec3(0.32, 0.085, 0.035) * waterParams.y * mix(0.3, 2.0, opacity) / 10.0;
 vec3 transmission = exp(-extinction * max(path, 0.0));
 vec3 straightSource = pow(max(texture2D(opaqueColor, uv).rgb, vec3(0.0)), vec3(2.2));
 vec3 refractedSource = pow(max(texture2D(opaqueColor, sampleUV).rgb, vec3(0.0)), vec3(2.2));
 vec3 source = mix(straightSource, refractedSource, sampleConfidence);
 vec3 scatter = pow(max(scatterColor, vec3(0.0)), vec3(2.2));
 return vec4(pow(max(source * transmission + scatter * (1.0 - transmission), vec3(0.0)),
  vec3(1.0 / 2.2)), 1.0);
}
#endif
