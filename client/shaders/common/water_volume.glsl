// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_WATER_VOLUME
uniform sampler2D texture6;
uniform vec3 waterVolumeOrigin; // first cell center, relative to the camera origin
uniform vec3 waterAbsoluteOrigin;
uniform vec4 waterVolumeParams; // ready, grid size, maximum world path, caustic strength
uniform vec4 waterLight; // direction toward the light, brightness
uniform vec3 waterLightColor;
uniform vec3 waterWaves; // enabled wave height, wavelength, animated phase
uniform vec4 waterMediumParams; // camera inside, absorption strength, reserved

bool waterVolumeInside(vec3 cell)
{
	return min(cell.x, min(cell.y, cell.z)) >= 0.0 &&
		max(cell.x, max(cell.y, cell.z)) < waterVolumeParams.y;
}

vec4 waterVolumeCell(vec3 cell)
{
	if (!waterVolumeInside(cell)) return vec4(0.0);
	float n = waterVolumeParams.y;
	return texture2D(texture6, (vec2(cell.x, cell.z * n + cell.y) + 0.5) / vec2(2.0*n, n*n));
}

vec4 waterVolumeCorners(vec3 cell)
{
	if (!waterVolumeInside(cell)) return vec4(0.0);
	float n = waterVolumeParams.y;
	return texture2D(texture6, (vec2(n+cell.x, cell.z*n+cell.y)+0.5)/vec2(2.0*n, n*n));
}

void waterCellPlanes(vec3 cell, vec4 material, bool upper, out vec3 bottom, out vec3 top)
{
	vec3 waves = material.r > 0.92 ? waterWaves : vec3(0.0);
	bottom = vec3(0, 0, cell.y);
	if (waves.x > 0.0) bottom = waterWavePlane(cell, cell.y, upper, waterAbsoluteOrigin, waves);
	// Sources retain a constant rest height; flowing water uses the actual four
	// mesh corners, including full-height connections to the liquid above.
	if (material.r > 0.99)
		top = waterWavePlane(cell, cell.y+1.0, upper, waterAbsoluteOrigin, waves);
	else
		top = waterLiquidPlane(cell, waterVolumeCorners(cell), upper, waterAbsoluteOrigin, waves);
}

// Clip an interval by value + rate*t >= 0, preserving parallel rays.
void waterClip(float value, float rate, inout float a, inout float b)
{
	if (abs(rate) < 0.0000001) { if (value < 0.0) b = a; }
	else if (rate > 0.0) a = max(a, -value / rate);
	else b = min(b, -value / rate);
}

vec2 waterCellInterval(vec3 start, vec3 direction, vec3 cell, vec4 material,
		float a, float b, bool upper)
{
	vec3 bottom, top;
	waterCellPlanes(cell, material, upper, bottom, top);
	vec3 local = vec3(start.xz - cell.xz, 1.0);
	waterClip(start.y - dot(bottom, local), direction.y - dot(bottom.xy, direction.xz), a, b);
	waterClip(dot(top, local) - start.y, dot(top.xy, direction.xz) - direction.y, a, b);
	return vec2(a, b);
}

bool waterAt(vec3 position)
{
	if (waterVolumeParams.x < 0.5) return false;
	vec3 p = (position - waterVolumeOrigin) / 10.0 + 0.5;
	vec3 base = floor(p);
	vec4 here = waterVolumeCell(base);
	if (here.r < 0.1 || (here.r > 0.4 && here.r < 0.7)) return false;
	for (int j = 0; j < 3; ++j) {
		if (float(j) > ceil(waterWaves.x * 0.5)) break;
		vec3 cell = base + vec3(0, j, 0);
		vec4 material = waterVolumeCell(cell);
		if (material.r <= 0.8 || (j > 0 && material.r < 0.92)) continue;
		vec3 bottom, top;
		waterCellPlanes(cell, material, fract(p.x)+fract(p.z)>1.0, bottom, top);
		vec3 local = vec3(p.xz-cell.xz, 1.0);
		if (p.y >= dot(bottom, local) && p.y < dot(top, local)) return true;
	}
	return false;
}

// Voxel DDA, additionally split at the liquid mesh's X/Z triangle diagonal.
// Waving prisms can move into the two cells below their original location.
// Result: water length, turbidity-weighted length, travelled distance, sky visibility.
vec4 traceWaterVolume(vec3 position, vec3 direction, float distance, out float firstExit, bool stopAtExit,
		out vec2 firstWater)
{
	firstExit = -1.0;
	firstWater = vec2(-1.0);
	if (waterVolumeParams.x < 0.5 || distance <= 0.0) return vec4(0.0);
	vec3 start = (position - waterVolumeOrigin) / 10.0 + 0.5;
	vec3 cell = floor(start);
	if (!waterVolumeInside(cell)) return vec4(0.0);
	vec3 signs = step(vec3(0.0), direction) * 2.0 - 1.0;
	vec3 inverseDirection = signs / max(abs(direction), vec3(0.0000001));
	vec3 increment = abs(inverseDirection);
	vec3 next = (cell + step(vec3(0.0), direction) - start) * inverseDirection;
	float limit = min(distance, waterVolumeParams.z) / 10.0;
	float t = 0.0, wet = 0.0, weighted = 0.0, lastWetEnd = -1.0, sky = 0.0;
	for (int i = 0; i < 325; ++i) {
		if (!waterVolumeInside(cell)) break;
		vec4 here = waterVolumeCell(cell);
		if (here.r < 0.1 || (here.r > 0.4 && here.r < 0.7)) { sky = 0.0; break; }
		// Interior source columns remain completely wet under the bounded vertical
		// deformation. Avoid evaluating boundary noise on every submerged ray step.
		bool fullColumn = here.r > 0.99 && here.g > 0.999;
		for (int j = 1; j < 3; ++j) {
			if (float(j) > ceil(waterWaves.x * 0.5)) break;
			vec4 above = waterVolumeCell(cell + vec3(0, j, 0));
			if (above.r < 0.99 || above.g < 0.999 || abs(above.a-here.a) > 0.001) fullColumn = false;
		}
		float boundary = min(next.x, min(next.y, next.z));
		float end = min(limit, boundary);
		// Intersections with shared planes acquire a few float ULPs of error
		// along long rays. Do not turn those seams into physical water exits.
		float seamTolerance = 0.000001*max(1.0,end);
		if (fullColumn) {
			// The whole cell is wet with one turbidity. Interior pool rays need
			// neither triangle clipping nor sorting/union of displaced prisms.
			if (lastWetEnd >= 0.0 && t > lastWetEnd+seamTolerance && firstExit < 0.0)
				firstExit = lastWetEnd*10.0;
			if (stopAtExit && firstExit >= 0.0) { t = firstExit/10.0; break; }
			if (end > t) {
				if (firstWater.x < 0.0) firstWater = vec2(t,end)*10.0;
				wet += end-t;
				weighted += (end-t)*mix(0.3,2.0,here.a);
				lastWetEnd = end;
			}
			sky = 0.0;
		} else {
			float diagonalRate = direction.x + direction.z;
			if ((here.r > 0.8 || waterWaves.x > 0.0) && abs(diagonalRate) > 0.0000001) {
				float diagonal = (cell.x + cell.z + 1.0 - start.x - start.z) / diagonalRate;
				if (diagonal > t + 0.000001) end = min(end, diagonal);
			}
			vec2 middle = start.xz + direction.xz * (t + end) * 0.5 - cell.xz;
			bool upper = middle.x + middle.y > 1.0;
			vec3 intervals[3];
			for (int j = 0; j < 3; ++j) {
				intervals[j] = vec3(end, t, 0);
				if (float(j) > ceil(waterWaves.x * 0.5)) continue;
				vec3 candidate = cell + vec3(0, j, 0);
				vec4 material = j == 0 ? here : waterVolumeCell(candidate);
				if (material.r <= 0.8 || (j > 0 && material.r < 0.92)) continue;
				intervals[j] = vec3(waterCellInterval(start, direction, candidate, material, t, end, upper),
						mix(0.3, 2.0, material.a));
			}
			// Union sorted intervals, so overlapping liquid definitions cannot count
			// the same water path twice. The first interval supplies overlapping turbidity.
			if (intervals[1].x < intervals[0].x) { vec3 swap = intervals[0]; intervals[0] = intervals[1]; intervals[1] = swap; }
			if (intervals[2].x < intervals[1].x) { vec3 swap = intervals[1]; intervals[1] = intervals[2]; intervals[2] = swap; }
			if (intervals[1].x < intervals[0].x) { vec3 swap = intervals[0]; intervals[0] = intervals[1]; intervals[1] = swap; }
			float covered = t;
			for (int j = 0; j < 3; ++j) {
				float a = max(intervals[j].x, covered), b = intervals[j].y;
				if (b <= a) continue;
				if (lastWetEnd >= 0.0 && a > lastWetEnd + seamTolerance && firstExit < 0.0)
					firstExit = lastWetEnd * 10.0;
				if (stopAtExit && firstExit >= 0.0) break;
				if (firstWater.x < 0.0) firstWater = vec2(a,b)*10.0;
				wet += b-a;
				weighted += (b-a) * intervals[j].z;
				covered = b;
				lastWetEnd = b;
			}
			if (lastWetEnd >= 0.0 && lastWetEnd < end - seamTolerance && firstExit < 0.0)
				firstExit = lastWetEnd * 10.0;
			sky = covered < end - seamTolerance ? step(0.99, here.b) : 0.0;
			if (stopAtExit && firstExit >= 0.0) { t = firstExit / 10.0; break; }
		}
		t = end;
		if (t >= limit) break;
		if (boundary <= t + 0.000001) {
			vec3 advance = step(next, vec3(boundary + 0.000001));
			cell += signs * advance;
			next += increment * advance;
		}
	}
	return vec4(wet * 10.0, weighted * 10.0, t * 10.0, sky);
}

vec4 traceWaterVolume(vec3 position, vec3 direction, float distance, out float firstExit, bool stopAtExit)
{
	vec2 unused;
	return traceWaterVolume(position,direction,distance,firstExit,stopAtExit,unused);
}

vec4 traceWaterVolume(vec3 position, vec3 direction, float distance, out float firstExit)
{
	return traceWaterVolume(position, direction, distance, firstExit, false);
}

vec3 waterTransmission(float weightedLength, float strength)
{
	return exp(-vec3(0.32, 0.085, 0.035) * strength * max(weightedLength, 0.0) / 10.0);
}

vec3 waterCausticNormal(vec3 surface, vec2 restSlope)
{
	vec3 absolute = waterAbsoluteOrigin + surface - waterVolumeOrigin;
	const float epsilon = 0.5;
	vec3 xOffset = vec3(epsilon, restSlope.x * epsilon, 0);
	vec3 zOffset = vec3(0, restSlope.y * epsilon, epsilon);
	float dx = restSlope.x + (waterWaveHeight(absolute + xOffset, waterWaves) -
		waterWaveHeight(absolute - xOffset, waterWaves)) / (2.0 * epsilon);
	float dz = restSlope.y + (waterWaveHeight(absolute + zOffset, waterWaves) -
		waterWaveHeight(absolute - zOffset, waterWaves)) / (2.0 * epsilon);
	return normalize(vec3(-dx, 1.0, -dz));
}

vec3 waterRefractedLight(vec3 surface, vec2 restSlope)
{
	return refract(-waterLight.xyz, waterCausticNormal(surface, restSlope), 1.0 / 1.333);
}

vec2 waterPhotonPosition(vec3 surface, float receiverHeight, vec2 restSlope)
{
	vec3 ray = waterRefractedLight(surface, restSlope);
	vec3 absolute = waterAbsoluteOrigin + surface - waterVolumeOrigin;
	float distance = (receiverHeight - surface.y - waterWaveHeight(absolute, waterWaves)) / min(ray.y, -0.001);
	return surface.xz + ray.xz * max(distance, 0.0);
}

void waterPhotonJacobian(vec3 surface, float height, vec2 slope, out vec2 jx, out vec2 jz)
{
	const float epsilon = 0.5;
	vec3 dx = vec3(epsilon, slope.x*epsilon, 0), dz = vec3(0, slope.y*epsilon, epsilon);
	jx = (waterPhotonPosition(surface+dx,height,slope)-waterPhotonPosition(surface-dx,height,slope))/(2.0*epsilon);
	jz = (waterPhotonPosition(surface+dz,height,slope)-waterPhotonPosition(surface-dz,height,slope))/(2.0*epsilon);
}

float waterPhotonDensity(vec3 receiver, vec3 surface, vec2 slope)
{
	vec2 jx, jz;
	waterPhotonJacobian(surface,receiver.y,slope,jx,jz);
	float determinant = abs(jx.x*jz.y-jz.x*jx.y);
	float residual = length(waterPhotonPosition(surface,receiver.y,slope)-receiver.xz);
	float convergence = 1.0-smoothstep(0.5,2.0,residual);
	vec3 normal = waterCausticNormal(surface,slope);
	// Incident density on the sloping projected surface divided by its outgoing Jacobian.
	float incident = max(dot(normal,waterLight.xyz),0.0)/max(normal.y*waterLight.y,0.0001);
	return mix(1.0,clamp(incident/max(determinant,0.0001),0.0,4.0),convergence);
}

float waterFocusing(vec3 receiver, vec3 surface, vec2 restSlope, out vec3 solvedSurface)
{
	// Invert the refracted-ray map locally. A bounded Newton solve avoids divergent
	// caustic roots; folds/multiple photon paths remain a single-root approximation.
	vec3 reference = surface;
	for (int i = 0; i < 3; ++i) {
		vec2 error = waterPhotonPosition(surface, receiver.y, restSlope) - receiver.xz;
		vec2 jx, jz;
		waterPhotonJacobian(surface,receiver.y,restSlope,jx,jz);
		float determinant = jx.x * jz.y - jz.x * jx.y;
		if (abs(determinant) < 0.05) break;
		vec2 correction = vec2(jz.y * error.x - jz.x * error.y,
			-jx.y * error.x + jx.x * error.y) / determinant;
		surface.xz -= clamp(correction, vec2(-10.0), vec2(10.0));
		surface.y = reference.y + dot(restSlope, surface.xz - reference.xz);
	}
	solvedSurface = surface;
	return waterPhotonDensity(receiver,surface,restSlope);
}

float waterFocusing(vec3 receiver, vec3 surface, out vec3 solvedSurface)
{
	return waterFocusing(receiver, surface, vec2(0.0), solvedSurface);
}

// Recover the source/flow face's rest plane from a displaced top exit. Side and
// bottom exits are rejected: only a sunlit top interface produces this caustic.
bool waterRestSurface(vec3 position, out vec3 surface, out vec2 restSlope)
{
	vec3 p = (position-waterVolumeOrigin)/10.0+0.5;
	vec3 base = floor(p);
	for (int j = -1; j < 3; ++j) {
		vec3 cell = base + vec3(0, j, 0);
		vec4 material = waterVolumeCell(cell);
		if (material.r < 0.92) continue;
		bool upper = fract(p.x)+fract(p.z)>1.0;
		vec3 bottom, top;
		waterCellPlanes(cell, material, upper, bottom, top);
		vec3 local = vec3(p.xz-cell.xz, 1);
		if (abs(p.y-dot(top, local)) > 0.002) continue;
		vec3 rest = material.r > 0.99 ? vec3(0, 0, cell.y+1.0) :
			waterLiquidPlane(cell, waterVolumeCorners(cell), upper, waterAbsoluteOrigin, vec3(0.0));
		surface = vec3(position.x, (dot(rest, local)-0.5)*10.0+waterVolumeOrigin.y, position.z);
		restSlope = rest.xy;
		return true;
	}
	return false;
}

bool waterAnimatedSurface(vec3 surface, vec2 restSlope, out vec3 animated)
{
	vec3 p = (surface-waterVolumeOrigin)/10.0+0.5;
	vec3 base = floor(p);
	for (int j = -1; j < 2; ++j) {
		vec3 cell = base + vec3(0, j, 0);
		vec4 material = waterVolumeCell(cell);
		if (material.r < 0.92) continue;
		bool upper = fract(p.x)+fract(p.z)>1.0;
		vec3 rest = material.r > 0.99 ? vec3(0, 0, cell.y+1.0) :
			waterLiquidPlane(cell, waterVolumeCorners(cell), upper, waterAbsoluteOrigin, vec3(0.0));
		vec3 local = vec3(p.xz-cell.xz, 1);
		// Validate the final face before projection; a stale slope must not be
		// extended through a different triangle, wall or waterfall.
		if (abs(p.y-dot(rest, local)) > 0.002 || any(greaterThan(abs(rest.xy-restSlope), vec2(0.002)))) continue;
		vec3 bottom, top;
		waterCellPlanes(cell, material, upper, bottom, top);
		animated = vec3(surface.x, (dot(top, local)-0.5)*10.0+waterVolumeOrigin.y, surface.z);
		return true;
	}
	return false;
}

// Bias chooses the side of an edge; compare heights at the exact shared boundary.
bool waterRestFace(inout vec3 surface, vec2 bias, out vec2 restSlope)
{
	vec3 p = (surface-waterVolumeOrigin)/10.0+0.5;
	vec2 samplePoint = p.xz+bias, column = floor(samplePoint);
	bool upper = fract(samplePoint.x)+fract(samplePoint.y)>1.0;
	for (int j = -1; j < 2; ++j) {
		vec3 cell = vec3(column.x,floor(p.y)+float(j),column.y);
		vec4 material = waterVolumeCell(cell);
		if (material.r < 0.92 || waterVolumeCell(cell+vec3(0,1,0)).r > 0.8) continue;
		vec3 rest = material.r > 0.99 ? vec3(0,0,cell.y+1.0) :
			waterLiquidPlane(cell,waterVolumeCorners(cell),upper,waterAbsoluteOrigin,vec3(0.0));
		float height = dot(rest,vec3(p.xz-cell.xz,1));
		if (abs(p.y-height) > 0.002) continue;
		surface.y = (height-0.5)*10.0+waterVolumeOrigin.y;
		restSlope = rest.xy;
		return true;
	}
	return false;
}

bool waterWalkSurface(inout vec3 surface, inout vec2 restSlope, vec2 displacement)
{
	if (max(abs(displacement.x),abs(displacement.y)) > 10.001) return false;
	vec2 origin = surface.xz, gridOrigin = (origin-waterVolumeOrigin.xz)/10.0+0.5;
	vec2 direction = displacement/10.0, bias = sign(direction)*0.00001;
	float t = 0.0;
	// A one-cell correction crosses at most two cell edges and their diagonals.
	// The uniform bound prevents expansion of this walk inside Newton's loop.
	int maxFaces = int(min(8.0,waterVolumeParams.y+1.0));
	for (int i = 0; i < maxFaces; ++i) {
		if (!waterRestFace(surface,bias,restSlope)) return false;
		vec2 cell = floor(gridOrigin+direction*t+bias);
		float finish = 1.0;
		for (int axis = 0; axis < 2; ++axis) {
			if (abs(direction[axis]) < 0.0000001) continue;
			float crossing = (cell[axis]+step(0.0,direction[axis])-gridOrigin[axis])/direction[axis];
			if (crossing > t+0.000001) finish = min(finish,crossing);
		}
		float diagonalRate = direction.x+direction.y;
		if (abs(diagonalRate) > 0.0000001) {
			float crossing = (cell.x+cell.y+1.0-gridOrigin.x-gridOrigin.y)/diagonalRate;
			if (crossing > t+0.000001) finish = min(finish,crossing);
		}
		surface.xz = origin+displacement*finish;
		surface.y += dot(restSlope,displacement*(finish-t));
		if (finish >= 1.0) return waterRestFace(surface,vec2(0),restSlope);
		t = finish;
	}
	return false;
}

bool waterFocusingOnMesh(vec3 receiver, inout vec3 surface, inout vec2 restSlope, out float focus)
{
	focus = 1.0;
	for (int i = 0; i < 3; ++i) {
		vec2 error = waterPhotonPosition(surface,receiver.y,restSlope)-receiver.xz;
		// Converged roots need no further Jacobian samples or topology walks.
		if (dot(error,error) < 0.00000001) break;
		vec2 jx, jz;
		waterPhotonJacobian(surface,receiver.y,restSlope,jx,jz);
		float determinant = jx.x*jz.y-jz.x*jx.y;
		if (abs(determinant) < 0.05) break;
		vec2 correction = vec2(jz.y*error.x-jz.x*error.y,-jx.y*error.x+jx.x*error.y)/determinant;
		if (!waterWalkSurface(surface,restSlope,-clamp(correction,vec2(-10),vec2(10)))) return false;
	}
	focus = waterPhotonDensity(receiver,surface,restSlope);
	return true;
}

vec3 applyWaterCaustics(vec3 color, vec3 position, vec3 normal, float nightRatio, vec3 shadowVisibility)
{
	if (waterVolumeParams.x < 0.5 || waterVolumeParams.w <= 0.0 || waterWaves.x <= 0.0 ||
			waterLight.w <= 0.0 || waterLight.y <= 0.01 || length(normal) < 0.01) return color;
	vec3 start = position + normalize(normal) * 0.1;
	if (!waterAt(start)) return color;
	vec3 upRay = -refract(-waterLight.xyz, vec3(0, 1, 0), 1.0 / 1.333);
	float firstExit;
	vec4 path = traceWaterVolume(start, upRay, waterVolumeParams.z, firstExit, true);
	if (firstExit < 0.0) return color;
	vec3 surface;
	vec2 restSlope;
	if (!waterRestSurface(start + upRay * firstExit, surface, restSlope)) return color;
	vec3 solvedSurface = surface;
	float focus;
	if (!waterFocusingOnMesh(position,solvedSurface,restSlope,focus)) return color;
	vec3 sceneSurface;
	if (!waterAnimatedSurface(solvedSurface, restSlope, sceneSurface)) return color;
	if (!waterAt(sceneSurface - vec3(0.0, 0.1, 0.0))) return color;
	vec3 interfaceNormal = waterCausticNormal(solvedSurface, restSlope);
	if (dot(interfaceNormal, waterLight.xyz) <= 0.0 || waterRefractedLight(solvedSurface, restSlope).y >= -0.001) return color;
	// The search ray only seeds the root. Visibility and absorption must follow
	// the solved interface-to-receiver segment, including its actual mesh height.
	vec3 toSurface = sceneSurface - start;
	float solvedDistance = length(toSurface);
	if (solvedDistance < 0.2) return color;
	vec3 solvedDirection = toSurface / solvedDistance;
	path = traceWaterVolume(start, solvedDirection, solvedDistance-0.1, firstExit, true);
	if (path.z < solvedDistance-0.2 || path.x < solvedDistance-0.2) return color;
	float ignoredExit;
	vec4 airPath = traceWaterVolume(sceneSurface + waterLight.xyz * 0.1, waterLight.xyz,
		waterVolumeParams.z, ignoredExit);
	// Additional water on the air-side segment needs another Snell interface.
	// Do not treat a sunlit but submerged/overlapped surface as a single entry.
	if (airPath.w < 0.5 || airPath.x > 0.02) return color;
	float cosine = max(dot(normalize(normal), solvedDirection), 0.0);
	float brightness = clamp(dot(waterLightColor, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
	float strength = min(waterVolumeParams.w * waterLight.w * brightness * cosine *
		(1.0 - clamp(nightRatio, 0.0, 1.0)), 1.0);
	vec3 edges = min((start - waterVolumeOrigin) / 10.0, waterVolumeParams.y - 1.0 - (start - waterVolumeOrigin) / 10.0);
	strength *= smoothstep(0.0, 2.0, min(edges.x, min(edges.y, edges.z)));
	vec3 transmission = waterTransmission(path.y, waterMediumParams.y);
	vec3 modulation = vec3(1.0) + (focus - 1.0) * strength * transmission * shadowVisibility;
	vec3 linear = pow(max(color, vec3(0.0)), vec3(2.2));
	return pow(max(linear * modulation, vec3(0.0)), vec3(1.0 / 2.2));
}
#endif
