// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "irr_ptr.h"
#include <irrlicht.h>
#include <ITexture.h>
#include <IVideoDriver.h>
#include <array>
#include <cstring>
#include <limits>
#include <vector>

// Opt-in GPU test: bin/luanti --run-tests '[texture-region]'
// Only numeric texture data is read; no screenshot or input APIs are used.
TEST_CASE("Texture regions preserve radiance while replacing live optics", "[.][client][render][texture-region]")
{
	for (auto type : {video::EDT_OPENGL3, video::EDT_OPENGL}) {
		CAPTURE(type);
		SIrrlichtCreationParameters params;
		params.DriverType = type;
		params.WindowSize = {64, 64};
		params.Vsync = false;
		irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
		REQUIRE(device);
		auto *driver = device->getVideoDriver();
		driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, false);
		driver->setTextureCreationFlag(video::ETCF_ALLOW_MEMORY_COPY, false);
		auto *texture = driver->addTexture({32, 64}, "region_test", video::ECF_A32B32G32R32F);
		REQUIRE(texture);
		REQUIRE(texture->getColorFormat() == video::ECF_A32B32G32R32F);
		auto *pixels = static_cast<unsigned char *>(texture->lock(video::ETLM_WRITE_ONLY));
		REQUIRE(pixels);
		for (u32 y = 0; y < 64; ++y) {
			auto *row = reinterpret_cast<float *>(pixels + y * texture->getPitch());
			for (u32 x = 0; x < 32; ++x) for (u32 c = 0; c < 4; ++c)
				row[x*4+c] = float(x+32*y+c) / 1000.0f;
		}
		texture->unlock();
		std::vector<std::array<float, 4>> replacement(3*5);
		for (u32 i = 0; i < replacement.size(); ++i)
			replacement[i] = {float(i), 0.25f, 0.75f, float(i % 2)};
		REQUIRE(texture->updateRegion({29, 59}, {3, 5}, replacement.data()));
		CHECK_FALSE(texture->updateRegion({30, 59}, {3, 5}, replacement.data()));
		CHECK_FALSE(texture->updateRegion({29, 60}, {3, 5}, replacement.data()));
		CHECK_FALSE(texture->updateRegion({std::numeric_limits<u32>::max(), 0}, {1, 1}, replacement.data()));
		CHECK_FALSE(texture->updateRegion({0, 0}, {0, 1}, replacement.data()));
		CHECK_FALSE(texture->updateRegion({0, 0}, {1, 1}, nullptr));
		pixels = static_cast<unsigned char *>(texture->lock(video::ETLM_READ_ONLY));
		REQUIRE(pixels);
		CHECK_FALSE(texture->updateRegion({0, 0}, {1, 1}, replacement.data()));
		for (u32 y = 0; y < 64; ++y) {
			const auto *row = reinterpret_cast<const float *>(pixels + y * texture->getPitch());
			for (u32 x = 0; x < 32; ++x) for (u32 c = 0; c < 4; ++c) {
				const float expected = x >= 29 && y >= 59 ? replacement[x-29+3*(y-59)][c] :
					float(x+32*y+c) / 1000.0f;
				REQUIRE(row[x*4+c] == expected);
			}
		}
		texture->unlock();
		// CPU copies and mip chains must never silently become stale.
		driver->setTextureCreationFlag(video::ETCF_ALLOW_MEMORY_COPY, true);
		auto *retained = driver->addTexture({4, 4}, "retained_test", video::ECF_A32B32G32R32F);
		REQUIRE(retained);
		CHECK_FALSE(retained->updateRegion({0, 0}, {1, 1}, replacement.data()));
		driver->setTextureCreationFlag(video::ETCF_ALLOW_MEMORY_COPY, false);
		driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, true);
		auto *mipped = driver->addTexture({4, 4}, "mipped_test", video::ECF_A8R8G8B8);
		REQUIRE(mipped);
		CHECK_FALSE(mipped->updateRegion({0, 0}, {1, 1}, replacement.data()));
	}
}
