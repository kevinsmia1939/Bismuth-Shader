// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#ifdef ENABLE_SCENE_EMISSION_MASK
void writeSceneEmission(float alpha)
{
	float emission = 0.0;
#ifdef MATERIAL_EMISSIVE
	emission = 1.0;
#endif
	// The separate R8 target follows scene coverage through normal alpha blending.
	// The normal/depth/skylight attachment disables blending independently.
	gl_FragData[SCENE_EMISSION_ATTACHMENT] = vec4(emission, 0.0, 0.0, alpha);
}
#endif
