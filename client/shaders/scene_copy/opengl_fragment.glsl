// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
uniform sampler2D texture0;
CENTROID_ VARYING_ mediump vec2 varTexCoord;
void main(void)
{
	gl_FragColor = texture2D(texture0, varTexCoord);
}
