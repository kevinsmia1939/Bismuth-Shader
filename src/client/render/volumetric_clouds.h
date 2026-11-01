// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "cloud_field.h"

namespace video { class IVideoDriver; class ITexture; class IImage; }

// Padded periodic slices allow trilinear 3D noise with two ordinary 2D fetches.
class CloudNoise
{
public:
	static constexpr int SIZE = cloud_field::NOISE_SIZE;
	static constexpr int WIDTH = SIZE + 2;
	static constexpr int HEIGHT = WIDTH * SIZE;
	static u8 value(int x, int y, int z);
	// Caller owns the image; also used to validate periodic padding without a GPU.
	static video::IImage *createImage(video::IVideoDriver *driver);
	explicit CloudNoise(video::IVideoDriver *driver);
	~CloudNoise();
	video::ITexture *getTexture() const { return texture; }
private:
	video::IVideoDriver *driver;
	video::ITexture *texture = nullptr;
};
