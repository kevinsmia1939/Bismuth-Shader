// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/render/volumetric_clouds.h"
#include "irr_ptr.h"
#include <irrlicht.h>
#include <IVideoDriver.h>
#include <IImage.h>

TEST_CASE("Cloud noise slices preserve periodic trilinear boundaries", "[client][render][clouds]")
{
	SIrrlichtCreationParameters params;
	params.DriverType = video::EDT_NULL;
	irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
	REQUIRE(device);
	auto *driver = device->getVideoDriver();
	irr_ptr<video::IImage> image(CloudNoise::createImage(driver));
	REQUIRE(image);
	CHECK(image->getDimension() == core::dimension2du(CloudNoise::WIDTH, CloudNoise::HEIGHT));
	for (int z = 0; z < CloudNoise::SIZE; ++z) {
		for (int i = 0; i < CloudNoise::SIZE; ++i) {
			const int y = z * CloudNoise::WIDTH + i + 1;
			CHECK(image->getPixel(0,y) == image->getPixel(CloudNoise::SIZE,y));
			CHECK(image->getPixel(CloudNoise::WIDTH-1,y) == image->getPixel(1,y));
			CHECK(image->getPixel(i+1,z*CloudNoise::WIDTH) == image->getPixel(i+1,z*CloudNoise::WIDTH+CloudNoise::SIZE));
			CHECK(image->getPixel(i+1,(z+1)*CloudNoise::WIDTH-1) == image->getPixel(i+1,z*CloudNoise::WIDTH+1));
			CHECK(CloudNoise::value(i,-1,z) == CloudNoise::value(i,CloudNoise::SIZE-1,z));
			CHECK(CloudNoise::value(i,0,z) == CloudNoise::value(i+CloudNoise::SIZE,0,z+CloudNoise::SIZE));
		}
	}
	const bool mipmaps = driver->getTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS);
	CloudNoise noise(driver);
	REQUIRE(noise.getTexture());
	CHECK(noise.getTexture()->getSize() == image->getDimension());
	CHECK(driver->getTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS) == mipmaps);
}
