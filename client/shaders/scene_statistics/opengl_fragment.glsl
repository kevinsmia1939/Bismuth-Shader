// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
uniform sampler2D texture0;

void main(void)
{
	// Fixed stratified probes of the composed scene before exposure/TAA.
	// Output only mean linear RGB and peak sampled luminance, never an image.
	vec3 mean = vec3(0.0);
	float peak = 0.0;
	for (int y = 0; y < 9; ++y) for (int x = 0; x < 16; ++x) {
		vec2 uv = (vec2(float(x), float(y)) + 0.5) / vec2(16.0, 9.0);
		vec3 sampleColor = pow(max(texture2D(texture0, uv).rgb, vec3(0.0)), vec3(2.2));
		mean += sampleColor / 144.0;
		peak = max(peak, dot(sampleColor, vec3(0.2126, 0.7152, 0.0722)));
	}
	gl_FragColor = vec4(mean, peak);
}
