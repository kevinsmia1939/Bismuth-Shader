// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "volumetric_clouds.h"
#include <IVideoDriver.h>
#include <IImage.h>
#include "irr_ptr.h"
#include "log.h"

u8 CloudNoise::value(int x, int y, int z)
{
	return cloud_field::noiseValue(x, y, z);
}

video::IImage *CloudNoise::createImage(video::IVideoDriver *driver)
{
	auto *image = driver->createImage(video::ECF_A8R8G8B8, core::dimension2du(WIDTH, HEIGHT));
	if (!image) return nullptr;
	for (int z = 0; z < SIZE; ++z) for (int y = -1; y <= SIZE; ++y)
		for (int x = -1; x <= SIZE; ++x) {
			const u8 v = value(x, y, z);
			image->setPixel(x + 1, z * WIDTH + y + 1, video::SColor(255, v, v, v));
		}
	return image;
}

CloudNoise::CloudNoise(video::IVideoDriver *driver) : driver(driver)
{
	irr_ptr<video::IImage> image(createImage(driver));
	if (!image) return;
	const bool mipmaps = driver->getTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS);
	driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, false);
	texture = driver->addTexture("volumetric_cloud_noise", image.get());
	driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, mipmaps);
	if (texture)
		infostream << "Volumetric clouds: periodic noise atlas ready" << std::endl;
	else
		warningstream << "Cloud noise allocation failed; retaining native clouds." << std::endl;
}

CloudNoise::~CloudNoise()
{
	if (texture) driver->removeTexture(texture);
}
