// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_VOXEL_WATER_LIGHTING
uniform vec3 voxelWaterParams; // strength, anisotropy, view steps

#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
vec3 voxelWaterMovingLight(vec3 position, vec3 q, vec3 viewRay)
{
	vec3 result = vec3(0);
	int count = int(clamp(voxelDynamicCount,0.0,float(MAX_VOXEL_DYNAMIC_LIGHTS)));
	for (int i = 0; i < count; ++i) {
		vec3 emission = voxelDynamicEmission[i].rgb;
		if (dot(emission,emission) <= 0.0) continue;
		vec3 source = voxelDynamicPosition[i].xyz, delta = source-q;
		float squaredDistance = dot(delta,delta);
		if (squaredDistance >= 256.0) continue;
		float distance = sqrt(squaredDistance);
		vec3 direction = delta/max(distance,0.000001);
		vec3 visibility = voxelDynamicTransmission(q,source,vec3(-2));
		if (max(visibility.r,max(visibility.g,visibility.b)) <= 0.0) continue;
		float ignoredExit;
		vec4 path = traceWaterVolume(position,direction,distance*10.0,ignoredExit);
		// Unknown, truncated or solid water geometry never becomes clear space.
		if (path.z < distance*10.0-0.02) continue;
		visibility *= waterTransmission(path.y,waterMediumParams.y);
		float phase = mix(1.0,voxelVolumePhase(dot(direction,viewRay),voxelWaterParams.y),smoothstep(0.0,1.0,distance));
		float fade = max(0.0,1.0-distance/16.0);
		result += emission*visibility*(phase*fade*fade/(6.0*max(squaredDistance,1.0)));
	}
	return result;
}
#endif

vec3 voxelWaterRadiance(vec3 position, vec3 ray, vec3 positive, vec3 negative)
{
	vec3 q;
	float coverage = voxelVolumeCoverage(position,q);
	if (coverage <= 0.0) return vec3(0);
	vec3 result = vec3(0);
	if (voxelParams.y > 0.0) {
		vec3 direct = voxelVolumeField(q,0.0,positive,negative);
#ifdef ENABLE_VOXEL_DYNAMIC_DIRECT
		direct += voxelWaterMovingLight(position,q,ray);
#endif
		result += direct*voxelParams.y;
	}
	if (voxelParams.z > 0.0)
		result += voxelVolumeField(q,6.0,positive,negative)*voxelParams.z;
	return result*(coverage*voxelWaterParams.x);
}

vec3 integrateVoxelWater(vec3 origin, vec3 direction, float distance, out vec3 transmission)
{
	transmission = vec3(1);
	vec3 scatter = vec3(0), positive, negative;
	voxelVolumePhaseWeights(direction,voxelWaterParams.y,positive,negative);
	int steps = int(clamp(voxelWaterParams.z,4.0,32.0));
	float stepLength = min(distance,waterVolumeParams.z)/float(steps);
	// Neutral scattering coefficient bounded by the smallest extinction channel.
	// The remaining red/green extinction is absorption, not redistributed energy.
	const vec3 albedo = vec3(0.035)/vec3(0.32,0.085,0.035);
	for (int i = 0; i < steps; ++i) {
		vec3 start = origin+direction*(float(i)*stepLength);
		float ignoredExit; vec2 firstWater;
		vec4 path = traceWaterVolume(start,direction,stepLength,ignoredExit,false,firstWater);
		vec3 segmentTransmission = waterTransmission(path.y,waterMediumParams.y);
		if (path.x > 0.0) {
			vec3 samplePoint = start+direction*(min(stepLength,path.z)*0.5);
			if (!waterAt(samplePoint)) samplePoint = start+direction*((firstWater.x+firstWater.y)*0.5);
			if (waterAt(samplePoint))
				scatter += transmission*(vec3(1)-segmentTransmission)*albedo*
					voxelWaterRadiance(samplePoint,direction,positive,negative);
		}
		transmission *= segmentTransmission;
		if (path.z < stepLength-0.02) break;
	}
	return scatter;
}
#endif
