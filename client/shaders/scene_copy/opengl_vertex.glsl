// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
CENTROID_ VARYING_ mediump vec2 varTexCoord;
void main(void)
{
	varTexCoord = inTexCoord0.st;
	gl_Position = inVertexPosition;
}
