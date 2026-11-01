// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Shared displacement for the liquid mesh and refracted-light focusing.
// Noise formulation: https://gist.github.com/patriciogonzalezvivo/670c22f3966e662d2f83
vec4 waterWavePerm(vec4 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }

float waterWaveNoise(vec3 p)
{
	vec3 cell = floor(p);
	// Reduce the lattice before polynomial hashing to avoid large-coordinate
	// multiplication losing integer precision. The field is periodic every 289 cells.
	vec3 a = mod(cell, 289.0);
	vec3 d = p - cell;
	d = d * d * (3.0 - 2.0 * d);
	vec4 b = a.xxyy + vec4(0.0, 1.0, 0.0, 1.0);
	vec4 k1 = waterWavePerm(b.xyxy);
	vec4 k2 = waterWavePerm(k1.xyxy + b.zzww);
	vec4 c = k2 + a.zzzz;
	vec4 k3 = waterWavePerm(c);
	vec4 k4 = waterWavePerm(c + 1.0);
	vec4 o1 = fract(k3 * (1.0 / 41.0));
	vec4 o2 = fract(k4 * (1.0 / 41.0));
	vec4 o3 = o2 * d.z + o1 * (1.0 - d.z);
	vec2 o4 = o3.yw * d.x + o3.xz * (1.0 - d.x);
	return o4.y * d.y + o4.x * (1.0 - d.y);
}

float waterWaveHeight(vec3 absolute, vec3 waves)
{
	if (waves.x <= 0.0) return 0.0;
	vec3 p = absolute;
	// Reduce in world units before division. Quantizing the entire repeat period
	// to 1/32 world unit keeps period*integer exact within map coordinates, despite
	// CPU/GPU differences in reciprocal approximation and multiply-add fusion.
	vec2 period = floor(max(waves.y, 0.1) * vec2(867.0, 578.0) * 32.0 + 0.5) / 32.0;
	p.xz = mod(p.xz, period) * (289.0 / period);
	// Preserve vertical ordering, including 0.02-node shoreline sheets. The
	// cubic noise's Y derivative is bounded by 1.5; at maximum amplitude 4,
	// |d(displacement)/dy| <= 20*1.5/64 < 1, so water cannot turn inside out.
	p.y *= 1.0 / 64.0;
	p.z += waves.z;
	return (waterWaveNoise(p) - 1.0) * waves.x * 5.0;
}

// Plane of a displaced liquid triangle in node units. Heights are ordered
// (0,0), (1,0), (0,1), (1,1), relative to the node bottom. Wave noise samples
// each original corner's Y, matching the vertex shader on sloping flow.
vec3 waterLiquidPlane(vec3 cell, vec4 heights, bool upper, vec3 origin, vec3 waves)
{
	vec3 p = origin + (cell-0.5)*10.0;
	float b = cell.y + heights.y + waterWaveHeight(p + vec3(10, heights.y*10.0, 0), waves)/10.0;
	float c = cell.y + heights.z + waterWaveHeight(p + vec3(0, heights.z*10.0, 10), waves)/10.0;
	if (upper) {
		float d = cell.y + heights.w + waterWaveHeight(p + vec3(10, heights.w*10.0, 10), waves)/10.0;
		return vec3(d-c, d-b, b+c-d);
	}
	float a = cell.y + heights.x + waterWaveHeight(p + vec3(0, heights.x*10.0, 0), waves)/10.0;
	return vec3(b-a, c-a, a);
}

// Fixed X/Z diagonal, joining (0,1) to (1,0), on source top/bottom faces.
vec3 waterWavePlane(vec3 cell, float restY, bool upper, vec3 origin, vec3 waves)
{
	return waterLiquidPlane(cell, vec4(restY-cell.y), upper, origin, waves);
}
