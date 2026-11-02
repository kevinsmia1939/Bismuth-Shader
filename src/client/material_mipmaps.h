// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include "irr_v3d.h"
#include "texture_data.h"
#include <IImage.h>
#include <ITexture.h>
#include <IVideoDriver.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace material_mipmaps {
struct Level {
	core::dimension2du size;
	std::vector<video::SColor> pixels;
};

inline bool supported(video::ECOLOR_FORMAT format)
{
	return format == video::ECF_A8R8G8B8 || format == video::ECF_R8G8B8 ||
		format == video::ECF_A1R5G5B5 || format == video::ECF_R5G6B5;
}

// Equal-area boxes retain every texel, including odd sizes and one-pixel axes.
// Keep unquantized moments between levels. Renormalizing a normal mip or
// averaging already encoded roughness would lose the next level's statistics.
inline std::vector<v3f> resize(const std::vector<v3f> &input,
		core::dimension2du from, core::dimension2du to)
{
	if (from == to) return input;
	std::vector<v3f> output(to.getArea());
	const double sx = double(from.Width)/to.Width, sy = double(from.Height)/to.Height;
	for (u32 y = 0; y < to.Height; ++y) for (u32 x = 0; x < to.Width; ++x) {
		const double left = x*sx, right = (x+1)*sx, top = y*sy, bottom = (y+1)*sy;
		std::array<double,3> sum{};
		for (u32 iy = u32(top); iy < std::min(u32(std::ceil(bottom)),from.Height); ++iy)
			for (u32 ix = u32(left); ix < std::min(u32(std::ceil(right)),from.Width); ++ix) {
				const double weight = (std::min(right,double(ix+1))-std::max(left,double(ix))) *
					(std::min(bottom,double(iy+1))-std::max(top,double(iy)));
				const auto &n = input[iy*from.Width+ix];
				sum[0] += n.X*weight; sum[1] += n.Y*weight; sum[2] += n.Z*weight;
			}
		output[y*to.Width+x] = v3f(sum[0]/(sx*sy),sum[1]/(sx*sy),sum[2]/(sx*sy));
	}
	return output;
}

inline std::vector<Level> build(const video::IImage &image,
		core::dimension2du target, bool mipmaps, TextureData type = TextureData::NORMAL)
{
	if (!supported(image.getColorFormat()) || !target.Width || !target.Height)
		return {};
	const auto original = image.getDimension();
	if (!original.Width || !original.Height) return {};
	std::vector<v3f> means(original.getArea());
	for (u32 y = 0; y < original.Height; ++y) for (u32 x = 0; x < original.Width; ++x) {
		const auto color = image.getPixel(x,y);
		if (type == TextureData::NORMAL) {
			v3f n(color.getRed()/127.5f-1, color.getGreen()/127.5f-1,
				std::max(color.getBlue()/127.5f-1,0.001f));
			n.normalize();
			means[y*original.Width+x] = n;
		} else {
			// GGX alpha-squared is perceptual roughness^4. Average that
			// footprint before encoding roughness again; a color average
			// would make mixed smooth/rough texels excessively glossy.
			const float roughness = std::max(color.getGreen()/255.0f, 0.045f);
			means[y*original.Width+x] = v3f(color.getRed()/255.0f,
				std::pow(roughness, 4.0f), color.getBlue()/255.0f);
		}
	}
	means = resize(means,original,target);
	std::vector<Level> levels;
	for (;;) {
		Level level{target,{}};
		level.pixels.reserve(means.size());
		const auto encode = [](float value) {
			return u32(std::lround(std::clamp(value,0.0f,1.0f)*255));
		};
		for (const auto &mean : means) {
			if (type == TextureData::NORMAL) {
				const float variance = std::max(0.0f,1.0f-mean.getLengthSQ());
				level.pixels.emplace_back(encode(std::sqrt(variance)),
					encode(mean.X*0.5f+0.5f),encode(mean.Y*0.5f+0.5f),encode(mean.Z*0.5f+0.5f));
			} else {
				level.pixels.emplace_back(255, encode(mean.X),
					encode(std::pow(mean.Y, 0.25f)), encode(mean.Z));
			}
		}
		levels.push_back(std::move(level));
		if (!mipmaps || (target.Width == 1 && target.Height == 1)) break;
		const core::dimension2du next(std::max(1u,target.Width/2),std::max(1u,target.Height/2));
		means = resize(means,target,next);
		target = next;
	}
	return levels;
}

inline bool upload(const video::IImage &image, video::ITexture &texture,
		TextureData type = TextureData::NORMAL)
{
	if (texture.getType() != video::ETT_2D || texture.getColorFormat() != video::ECF_A8R8G8B8)
		return false;
	const auto levels = build(image,texture.getSize(),texture.hasMipMaps(),type);
	if (levels.empty()) return false;
	for (u32 level = 0; level < levels.size(); ++level) {
		auto *data = texture.lock(video::ETLM_WRITE_ONLY,level);
		if (!data) {
			texture.regenerateMipMapLevels();
			return false;
		}
		// Lock images use their mip width, whereas getPitch() describes level 0.
		auto *dest = static_cast<u32 *>(data);
		for (size_t i = 0; i < levels[level].pixels.size(); ++i)
			dest[i] = levels[level].pixels[i].color;
		texture.unlock();
	}
	return true;
}

inline video::ITexture *create(video::IVideoDriver &driver, const io::path &name, video::IImage &image)
{
	// RGBA8 retains normal variance in alpha and full precision in ORM channels.
	// Restore all mutually exclusive format flags, including the all-unset case.
	struct Flags {
		video::IVideoDriver &driver;
		std::array<video::E_TEXTURE_CREATION_FLAG,5> flags{{video::ETCF_ALWAYS_16_BIT,
			video::ETCF_ALWAYS_32_BIT,video::ETCF_OPTIMIZED_FOR_QUALITY,
			video::ETCF_OPTIMIZED_FOR_SPEED,video::ETCF_NO_ALPHA_CHANNEL}};
		std::array<bool,5> values{};
		explicit Flags(video::IVideoDriver &d) : driver(d)
		{
			for (size_t i = 0; i < flags.size(); ++i) values[i] = driver.getTextureCreationFlag(flags[i]);
			driver.setTextureCreationFlag(video::ETCF_ALWAYS_32_BIT,true);
			driver.setTextureCreationFlag(video::ETCF_NO_ALPHA_CHANNEL,false);
		}
		~Flags()
		{
			for (auto flag : flags) driver.setTextureCreationFlag(flag,false);
			for (size_t i = 0; i < flags.size(); ++i) if (values[i]) driver.setTextureCreationFlag(flags[i],true);
		}
	} restore(driver);
	return driver.addTexture(name,&image);
}
} // namespace material_mipmaps
