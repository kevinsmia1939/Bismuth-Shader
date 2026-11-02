// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "client/tile.h"
#include "client/shader.h"
#include "client/render/surface_light.h"
#include "client/material_mipmaps.h"
#include "porting.h"
#include "irr_ptr.h"
#include <irrlicht.h>
#include <IVideoDriver.h>
#include <IGPUProgrammingServices.h>
#include <IRenderTarget.h>
#include <unordered_set>
#include <limits>

TEST_CASE("Normal mipmaps retain variance without renormalizing intermediate means", "[client][render][material]")
{
	SIrrlichtCreationParameters params;
	params.DriverType = video::EDT_NULL;
	irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
	REQUIRE(device);
	auto *driver = device->getVideoDriver();
	for (auto size : {core::dimension2du(8,8),core::dimension2du(7,3),core::dimension2du(1,9)}) {
		irr_ptr<video::IImage> image(driver->createImage(video::ECF_A8R8G8B8,size));
		REQUIRE(image);
		v3f expected;
		for (u32 y = 0; y < size.Height; ++y) for (u32 x = 0; x < size.Width; ++x) {
			video::SColor color((x+y)%2 ? 12 : 240,(x+y)%2 ? 218 : 37,128,218);
			image->setPixel(x,y,color);
			v3f n(color.getRed()/127.5f-1,color.getGreen()/127.5f-1,color.getBlue()/127.5f-1);
			expected += n.normalize();
		}
		expected /= float(size.getArea());
		auto levels = material_mipmaps::build(*image,size,true);
		REQUIRE(levels.size() >= 3);
		CHECK(levels.front().size == size);
		CHECK(levels.back().size == core::dimension2du(1,1));
		for (const auto &pixel : levels.front().pixels) CHECK(pixel.getAlpha() == 0);
		const auto last = levels.back().pixels.front();
		CHECK(last.getRed()/127.5f-1 == Catch::Approx(expected.X).margin(1.0/255+1e-7));
		CHECK(last.getGreen()/127.5f-1 == Catch::Approx(expected.Y).margin(1.0/255+1e-7));
		CHECK(last.getBlue()/127.5f-1 == Catch::Approx(expected.Z).margin(1.0/255+1e-7));
		CHECK(last.getAlpha()/255.0f == Catch::Approx(std::sqrt(1-expected.getLengthSQ())).margin(0.5/255));
		CHECK(image->getPixel(0,0).getAlpha() == 240); // Author alpha is untouched.
		auto reduced = material_mipmaps::build(*image,{1,1},false);
		REQUIRE(reduced.size() == 1);
		CHECK(reduced[0].pixels[0] == last);
		CHECK(material_mipmaps::build(*image,size,false).size() == 1);
		for (u32 y = 0; y < size.Height; ++y) for (u32 x = 0; x < size.Width; ++x)
			image->setPixel(x,y,{173,180,170,240});
		for (const auto &level : material_mipmaps::build(*image,size,true))
			for (const auto &pixel : level.pixels) CHECK(pixel.getAlpha() == 0);
	}
}

TEST_CASE("Normal mip uploads retain every level and restore texture flags", "[.][client][render][normal-mips]")
{
	for (auto type : {video::EDT_OPENGL3,video::EDT_OPENGL}) {
		SIrrlichtCreationParameters params;
		params.DriverType = type;
		params.WindowSize = {64,64};
		params.OGLES2ShaderPath = (porting::path_share + "/client/shaders/Irrlicht/").c_str();
		irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
		REQUIRE(device);
		auto *driver = device->getVideoDriver();
		for (bool mips : {false,true}) {
			driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS,mips);
			driver->setTextureCreationFlag(video::ETCF_OPTIMIZED_FOR_SPEED,true);
			driver->setTextureCreationFlag(video::ETCF_NO_ALPHA_CHANNEL,true);
			irr_ptr<video::IImage> image(driver->createImage(video::ECF_A8R8G8B8,{7,3}));
			for (u32 y = 0; y < 3; ++y) for (u32 x = 0; x < 7; ++x)
				image->setPixel(x,y,{255,x%2 ? 37u : 218u,128,218});
			auto *texture = material_mipmaps::create(*driver,mips ? "normal_mips" : "normal_base",*image);
			REQUIRE(texture);
			CHECK(texture->getColorFormat() == video::ECF_A8R8G8B8);
			CHECK(driver->getTextureCreationFlag(video::ETCF_OPTIMIZED_FOR_SPEED));
			CHECK_FALSE(driver->getTextureCreationFlag(video::ETCF_ALWAYS_32_BIT));
			CHECK(driver->getTextureCreationFlag(video::ETCF_NO_ALPHA_CHANNEL));
			REQUIRE(material_mipmaps::upload(*image,*texture));
			const auto expected = material_mipmaps::build(*image,texture->getSize(),mips);
			for (u32 level = 0; level < expected.size(); ++level) {
				auto *data = static_cast<u32 *>(texture->lock(video::ETLM_READ_ONLY,level));
				REQUIRE(data);
				for (size_t i = 0; i < expected[level].pixels.size(); ++i)
					REQUIRE(data[i] == expected[level].pixels[i].color);
				texture->unlock();
			}
			// Reload every mip, including clearing variance when detail disappears.
			for (u32 y = 0; y < 3; ++y) for (u32 x = 0; x < 7; ++x)
				image->setPixel(x,y,{255,128,128,255});
			REQUIRE(material_mipmaps::upload(*image,*texture));
			auto *last = static_cast<u32 *>(texture->lock(video::ETLM_READ_ONLY,expected.size()-1));
			REQUIRE(last);
			CHECK(video::SColor(last[0]).getAlpha() == 0);
			texture->unlock();
		}
	}
}

TEST_CASE("ORM mipmaps average GGX width while retaining linear occlusion and metal", "[client][render][material]")
{
	SIrrlichtCreationParameters params;
	params.DriverType = video::EDT_NULL;
	irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
	REQUIRE(device);
	for (auto size : {core::dimension2du(8, 8), core::dimension2du(7, 3), core::dimension2du(1, 9)}) {
		irr_ptr<video::IImage> image(device->getVideoDriver()->createImage(video::ECF_A8R8G8B8, size));
		double occlusion = 0, alpha2 = 0, metal = 0;
		for (u32 y = 0; y < size.Height; ++y) for (u32 x = 0; x < size.Width; ++x) {
			const video::SColor pixel(17, x % 2 ? 255 : 80, (x + y) % 2 ? 255 : 51, y % 2 ? 255 : 0);
			image->setPixel(x, y, pixel);
			occlusion += pixel.getRed() / 255.0;
			alpha2 += std::pow(pixel.getGreen() / 255.0, 4);
			metal += pixel.getBlue() / 255.0;
		}
		const auto levels = material_mipmaps::build(*image, size, true, TextureData::ORM);
		REQUIRE(levels.back().size == core::dimension2du(1, 1));
		const auto last = levels.back().pixels.front();
		CHECK(last.getRed() / 255.0 == Catch::Approx(occlusion / size.getArea()).margin(0.5 / 255 + 1e-7));
		CHECK(last.getGreen() / 255.0 == Catch::Approx(std::pow(alpha2 / size.getArea(), 0.25)).margin(0.5 / 255 + 1e-7));
		CHECK(last.getBlue() / 255.0 == Catch::Approx(metal / size.getArea()).margin(0.5 / 255 + 1e-7));
		CHECK(last.getGreen() > 180); // A color average (~0.6) would be too glossy.
		for (u32 y = 0; y < size.Height; ++y) for (u32 x = 0; x < size.Width; ++x) {
			const auto before = image->getPixel(x, y);
			const auto base = levels.front().pixels[y * size.Width + x];
			CHECK(base.getRed() == before.getRed());
			CHECK(base.getGreen() == before.getGreen());
			CHECK(base.getBlue() == before.getBlue());
			CHECK(base.getAlpha() == 255);
			CHECK(before.getAlpha() == 17); // No reinterpretation of color alpha.
		}
		const auto reduced = material_mipmaps::build(*image, {1, 1}, false, TextureData::ORM);
		REQUIRE(reduced.size() == 1);
		CHECK(reduced[0].pixels[0] == last);
		CHECK(material_mipmaps::build(*image, size, false, TextureData::ORM).size() == 1);
	}
}

TEST_CASE("ORM uploads replace all mips without changing source data", "[.][client][render][material-mips]")
{
	for (auto type : {video::EDT_OPENGL3, video::EDT_OPENGL}) {
		SIrrlichtCreationParameters params;
		params.DriverType = type;
		params.WindowSize = {64, 64};
		params.OGLES2ShaderPath = (porting::path_share + "/client/shaders/Irrlicht/").c_str();
		irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
		REQUIRE(device);
		auto *driver = device->getVideoDriver();
		driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, true);
		irr_ptr<video::IImage> image(driver->createImage(video::ECF_A8R8G8B8, {8, 8}));
		for (u32 y = 0; y < 8; ++y) for (u32 x = 0; x < 8; ++x)
			image->setPixel(x, y, {17, 255, (x + y) % 2 ? 255u : 51u, 255});
		auto *texture = material_mipmaps::create(*driver, "orm_mips", *image);
		REQUIRE(texture);
		REQUIRE(material_mipmaps::upload(*image, *texture, TextureData::ORM));
		for (u32 level = 1; level <= 3; ++level) {
			auto *pixels = static_cast<u32 *>(texture->lock(video::ETLM_READ_ONLY, level));
			REQUIRE(pixels);
			CHECK(video::SColor(pixels[0]) == video::SColor(255, 255, 215, 255));
			texture->unlock();
		}
		image->fill({3, 80, 128, 0});
		REQUIRE(material_mipmaps::upload(*image, *texture, TextureData::ORM));
		auto *pixels = static_cast<u32 *>(texture->lock(video::ETLM_READ_ONLY, 3));
		REQUIRE(pixels);
		CHECK(video::SColor(pixels[0]) == video::SColor(255, 80, 128, 0));
		texture->unlock();
		CHECK(image->getPixel(0, 0).getAlpha() == 3);
	}
}

TEST_CASE("Surface sunlight remains independent of shadow settings and supports sky/custom selection", "[client][render][material]")
{
	const v3f up(0, 1, 0), down(0, -1, 0);
	const video::SColorf color(0.8f, 0.6f, 0.4f);
	auto sun = surface_light::select(up, down, true, true, {}, color);
	CHECK(sun.source == surface_light::Source::SUN);
	CHECK(sun.direction == up);
	CHECK(sun.strength == 1.0f);
	CHECK(sun.color.X == Catch::Approx(std::pow(0.8f, 2.2f)));
	CHECK(sun.color.Y == Catch::Approx(std::pow(0.6f, 2.2f)));
	CHECK(sun.color.Z == Catch::Approx(std::pow(0.4f, 2.2f)));
	CHECK(surface_light::select(up, down, false, true, {}, color).strength == 0);
	auto moon = surface_light::select(down, up, true, true, {}, color);
	CHECK(moon.source == surface_light::Source::MOON);
	CHECK(moon.direction == up);
	CHECK(moon.strength == 0.5f);
	CHECK(surface_light::select(down, up, true, false, {}, color).strength == 0);
	auto custom = surface_light::select(up, down, false, false, v3f(3, -4, 0), color);
	CHECK(custom.source == surface_light::Source::CUSTOM);
	CHECK(custom.strength == 1);
	CHECK(custom.direction.X == Catch::Approx(0.6f));
	CHECK(custom.direction.Y == Catch::Approx(-0.8f));
	for (float scale : {1e-30f, 1e30f}) {
		auto scaled = surface_light::select(up, down, false, false, v3f(3, 4, 0) * scale, color);
		CHECK(scaled.strength == 1);
		CHECK(scaled.direction.X == Catch::Approx(0.6f));
		CHECK(scaled.direction.Y == Catch::Approx(0.8f));
	}
	for (float invalid : {std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN()})
		CHECK(surface_light::select(up, down, true, true, v3f(invalid, 0, 0), color).strength == 0);
	float previous = 0;
	for (float y : {-0.01f, 0.0f, 0.01f, 0.03f, 0.06f, 0.12f, 0.2f}) {
		auto light = surface_light::select(v3f(1, y, 0), down, true, true, {}, color);
		CHECK(light.strength >= previous);
		CHECK(light.strength <= 1);
		previous = light.strength;
	}
	// A complete sunset/source exchange must be continuous in emitted linear
	// radiance, including the warm tint and weaker moon. Custom sources bypass it.
	v3f previous_radiance;
	for (int i = -1000; i <= 1000; ++i) {
		const float y = i * 0.0002f;
		auto light = surface_light::select(v3f(1, y, 0), v3f(-1, -y, 0), true, true, {}, color);
		const v3f radiance = light.color * light.strength;
		if (i > -1000)
			CHECK(radiance.getDistanceFrom(previous_radiance) < 0.003f);
		previous_radiance = radiance;
	}
	auto low_sun = surface_light::select(v3f(1, 0.1f, 0), down, true, true, {}, video::SColorf(1, 1, 1));
	CHECK(low_sun.color.X > low_sun.color.Y);
	CHECK(low_sun.color.Y > low_sun.color.Z);
	CHECK(custom.color == sun.color); // No warm tint applied to authored lights.
}

TEST_CASE("Material map identity survives mesh grouping and animation", "[client][render][material]")
{
	SIrrlichtCreationParameters params;
	params.DriverType = video::EDT_NULL;
	irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
	REQUIRE(device);
	auto *driver = device->getVideoDriver();
	const auto texture = [&](const char *name) {
		auto *result = driver->addTexture(core::dimension2du(1, 1), name, video::ECF_A8R8G8B8);
		REQUIRE(result);
		return result;
	};
	auto *base0 = texture("material_base0");
	auto *base1 = texture("material_base1");
	auto *normal0 = texture("material_normal0");
	auto *normal1 = texture("material_normal1");
	auto *orm0 = texture("material_orm0");
	auto *orm1 = texture("material_orm1");
	TileLayer a;
	a.texture = base0;
	a.texture_id = 1;
	a.normal_texture = normal0;
	a.material_texture = orm0;
	auto b = a;
	b.normal_texture = normal1;
	auto c = a;
	c.material_texture = orm1;
	CHECK_FALSE(a == b);
	CHECK_FALSE(a == c);
	CHECK(a == TileLayer(a));
	std::unordered_set<TileLayer> groups{a, b, c, a};
	CHECK(groups.size() == 3);
	video::SMaterial material;
	CHECK(material.AuxiliaryBlendMask == 0xff);
	a.material_flags = 0;
	a.applyMaterialOptions(material, 0);
	CHECK(material.AuxiliaryBlendMask == 0xff);
	auto blended = material;
	blended.AuxiliaryBlendMask = 0xfd;
	CHECK_FALSE(blended == material);
	CHECK(material.getTexture(0) == base0);
	CHECK(material.getTexture(4) == normal0);
	CHECK(material.getTexture(5) == orm0);
	CHECK(material.TextureLayers[4].TextureWrapU == video::ETC_CLAMP_TO_EDGE);
	CHECK(material.TextureLayers[5].TextureWrapV == video::ETC_CLAMP_TO_EDGE);
	std::vector<FrameSpec> frames{{1, base0, normal0, orm0}, {2, base1, normal1, orm1}};
	AnimationInfo animation(&frames, 100);
	animation.updateTexture(material, 0.11f);
	CHECK(material.getTexture(0) == base1);
	CHECK(material.getTexture(4) == normal1);
	CHECK(material.getTexture(5) == orm1);
	animation.updateTexture(material, 0.21f);
	CHECK(material.getTexture(0) == base0);
	CHECK(material.getTexture(4) == normal0);
	CHECK(material.getTexture(5) == orm0);
	frames[1].normal_texture = nullptr;
	frames[1].material_texture = nullptr;
	animation.updateTexture(material, 0.11f);
	CHECK(material.getTexture(4) == nullptr);
	CHECK(material.getTexture(5) == nullptr);
	ShaderFeatures emissive;
	emissive.emissive_surface = true;
	ShaderConstants constants;
	emissive.setConstants(constants);
	CHECK(std::get<int>(constants.at("MATERIAL_EMISSIVE")) == 1);
	ShaderConstants ordinary;
	ShaderFeatures{}.setConstants(ordinary);
	CHECK(ordinary.count("MATERIAL_EMISSIVE") == 0);
}

TEST_CASE("MRT geometry metadata bypasses blending while color and emission retain coverage", "[.][client][render][surface-blend]")
{
	for (auto type : {video::EDT_OPENGL3, video::EDT_OPENGL}) {
		SIrrlichtCreationParameters params;
		params.DriverType = type;
		params.WindowSize = {64, 64};
		params.OGLES2ShaderPath = (porting::path_share + "/client/shaders/Irrlicht/").c_str();
		irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
		REQUIRE(device);
		auto *driver = device->getVideoDriver();
		REQUIRE(driver->queryFeature(video::EVDF_MRT_BLEND));
		const char *vertex = type == video::EDT_OPENGL3 ?
			"#version 130\nin vec3 inVertexPosition; void main(){gl_Position=vec4(inVertexPosition,1);}" :
			"#version 120\nvoid main(){gl_Position=gl_Vertex;}";
		const char *fragment = "#version 120\nvoid main(){"
			"gl_FragData[0]=vec4(0.8,0.4,0.2,0.5);"
			"gl_FragData[1]=vec4(0.25,0.75,-10,2);"
			"gl_FragData[2]=vec4(0.6,0,0,0.5);}";
		const s32 shader = driver->getGPUProgrammingServices()->addHighLevelShaderMaterial(
			vertex, fragment, "surface_blend", nullptr, video::EMT_TRANSPARENT_ALPHA_CHANNEL);
		REQUIRE(shader >= 0);
		core::array<video::ITexture *> textures;
		for (const char *name : {"blend_color", "blend_surface", "blend_emission"}) {
			auto *texture = driver->addRenderTargetTexture({4, 4}, name, video::ECF_A32B32G32R32F);
			REQUIRE(texture);
			textures.push_back(texture);
		}
		auto *target = driver->addRenderTarget();
		REQUIRE(target);
		target->setTexture(textures, nullptr);
		video::SMaterial material;
		material.MaterialType = static_cast<video::E_MATERIAL_TYPE>(shader);
		material.BackfaceCulling = false;
		material.ZBuffer = video::ECFN_ALWAYS;
		video::S3DVertex vertices[3];
		vertices[0].Pos = {-1, -1, 0}; vertices[1].Pos = {3, -1, 0}; vertices[2].Pos = {-1, 3, 0};
		const u16 indices[] = {0, 1, 2};
		for (u8 mask : {u8(0xfd), u8(0xff), u8(0xfd)}) {
			REQUIRE(driver->setRenderTargetEx(target, video::ECBF_COLOR, video::SColor(0)));
			material.AuxiliaryBlendMask = mask;
			driver->setMaterial(material);
			driver->drawVertexPrimitiveList(vertices, 3, indices, 1);
			driver->setRenderTargetEx(nullptr, 0);
			const float multiplier = mask == 0xfd ? 1.0f : 2.0f;
			const std::array<std::array<float, 4>, 3> expected{{
				{{0.4f, 0.2f, 0.1f, 0.25f}},
				{{0.25f * multiplier, 0.75f * multiplier, -10.f * multiplier, 2.f * multiplier}},
				{{0.3f, 0.f, 0.f, 0.25f}}
			}};
			for (u32 attachment = 0; attachment < textures.size(); ++attachment) {
				auto *pixels = static_cast<float *>(textures[attachment]->lock(video::ETLM_READ_ONLY));
				REQUIRE(pixels);
				for (u32 channel = 0; channel < 4; ++channel)
					CHECK(pixels[channel] == Catch::Approx(expected[attachment][channel]).margin(1e-5));
				textures[attachment]->unlock();
			}
		}
	}
}
