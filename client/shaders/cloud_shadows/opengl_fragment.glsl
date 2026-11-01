// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
uniform vec3 cloudShadowOrigin; // absolute center on the entry boundary
uniform vec4 cloudShadowParams; // unused, reciprocal span, unused, unused
uniform vec3 cloudShadowSlab; // unused, unused, reciprocal map resolution
CENTROID_ VARYING_ mediump vec2 varTexCoord;

void main()
{
	if (cloudParams.x < 0.5 || cloudLayer.y <= 0.0 || cloudLayer.z <= 0.0 ||
			cloudLayer.w <= 0.0 || cloudLight.w <= 0.0 || abs(cloudLight.y) < 0.02) {
		gl_FragColor = vec4(1.0); return;
	}
	// Use physical texel coordinates, independent of the fullscreen quad's UV
	// convention. Sampling texture7 then uses exactly the same X/Z orientation.
	vec2 uv = gl_FragCoord.xy*cloudShadowSlab.z;
	vec3 start = cloudShadowOrigin + vec3((uv.x-0.5)/cloudShadowParams.y,
		0, (uv.y-0.5)/cloudShadowParams.y);
	float ds = cloudLayer.y / abs(cloudLight.y) / 24.0;
	vec3 opticalDepth = vec3(0.0);
	for (int i = 0; i < 24; ++i) {
		float tau = cloudDensity(start+cloudLight.xyz*(float(i)+0.5)*ds)*cloudLayer.w*ds;
		if (i < 8) opticalDepth.x += tau;
		else if (i < 16) opticalDepth.y += tau;
		else opticalDepth.z += tau;
	}
	// Transmission toward the light at normalized heights 0, 1/3, 2/3, 1.
	// Filter transmission spatially to preserve energy across cloud edges.
	gl_FragColor = exp(-min(vec4(opticalDepth.x+opticalDepth.y+opticalDepth.z,
		opticalDepth.y+opticalDepth.z, opticalDepth.z, 0), vec4(64.0)));
}
