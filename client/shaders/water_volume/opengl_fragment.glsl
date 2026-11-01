// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
uniform sampler2D texture0;
uniform sampler2D texture1;
uniform mat4 inverseProjection;
uniform mat4 inverseView;
uniform vec3 waterScatterColor;
CENTROID_ VARYING_ mediump vec2 varTexCoord;

void main()
{
	vec2 uv = varTexCoord;
	vec4 original = texture2D(texture0, uv);
	if (waterVolumeParams.x < 0.5 || waterMediumParams.x < 0.5 || waterMediumParams.y <= 0.0) {
		gl_FragColor = original; return;
	}
	float depth = texture2D(texture1, uv).r;
	vec4 view = inverseProjection * vec4(uv * 2.0 - 1.0, min(depth, 0.99999) * 2.0 - 1.0, 1.0);
	vec3 p = view.xyz / view.w;
	vec3 origin = (inverseView * vec4(0, 0, 0, 1)).xyz;
	vec3 direction = normalize((inverseView * vec4(normalize(p), 0.0)).xyz);
	float distance = depth >= 1.0 ? waterVolumeParams.z : length(p);
	vec3 transmission, localScatter = vec3(0);
#ifdef ENABLE_VOXEL_WATER_LIGHTING
	if (voxelParams.x > 0.5 && voxelWaterParams.x > 0.0 && max(voxelParams.y,voxelParams.z) > 0.0)
		localScatter = integrateVoxelWater(origin,direction,distance,transmission);
	else
#endif
	{
		float firstExit;
		vec4 path = traceWaterVolume(origin,direction,distance,firstExit);
		transmission = waterTransmission(path.y,waterMediumParams.y);
	}
	vec3 color = pow(max(original.rgb, vec3(0.0)), vec3(2.2));
	vec3 scatter = pow(max(waterScatterColor, vec3(0.0)), vec3(2.2));
	gl_FragColor = vec4(pow(max(color * transmission + scatter * (1.0 - transmission) + localScatter, vec3(0.0)),
		vec3(1.0 / 2.2)), original.a);
}
