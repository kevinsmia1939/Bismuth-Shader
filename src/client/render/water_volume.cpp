// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "water_volume.h"
#include "water_waves.h"
#include "voxel_lighting.h"
#include "client/liquid_geometry.h"
#include "client/client.h"
#include "client/clientenvironment.h"
#include "client/clientmap.h"
#include "client/camera.h"
#include "client/renderingengine.h"
#include "mapnode.h"
#include "nodedef.h"
#include "settings.h"
#include "profiler.h"
#include "log.h"
#include <IVideoDriver.h>
#include <ITexture.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>

bool waterVolumeEnabled()
{
	auto *driver = RenderingEngine::get_video_driver();
	return g_settings->getBool("enable_post_processing") &&
		g_settings->getBool("enable_water_volume") &&
		g_settings->getBool("translucent_liquids") &&
		(driver->getDriverType() == video::EDT_OPENGL || driver->getDriverType() == video::EDT_OPENGL3) &&
		driver->getLimits().MaxMaterialTextures >= 7 && driver->getLimits().MaxTextureSize >= 4096 &&
		driver->queryTextureFormat(video::ECF_A32B32G32R32F);
}

bool useVoxelWaterLighting()
{
	return waterVolumeEnabled() && voxelLightingEnabled() &&
		g_settings->getBool("enable_voxel_water_lighting");
}

bool WaterVolume::eligible(const MapNode &node, const NodeDefManager *ndef)
{
	const auto &f = ndef->get(node);
	return f.isLiquid() && f.alpha == ALPHAMODE_BLEND && !f.light_source &&
		(f.drawtype == NDT_LIQUID || f.drawtype == NDT_FLOWINGLIQUID);
}

WaterVolume::WaterVolume(video::IVideoDriver *driver) : m_driver(driver),
	m_waving(g_settings->getBool("enable_waving_water"))
{}

v3f WaterVolume::waveParameters(u64 frame_time, bool enabled)
{
	return v3f(enabled ? g_settings->getFloat("water_wave_height", 0.0f, 4.0f) : 0.0f,
		std::max(0.1f, g_settings->getFloat("water_wave_length")),
		float(frame_time % 1000000) / 100000.0f * g_settings->getFloat("water_wave_speed") * 10.0f);
}

video::SColor WaterVolume::encodeCell(const MapNode &node, const NodeDefManager *ndef)
{
	if (node.getContent() == CONTENT_IGNORE) return video::SColor(0);
	const auto &f = ndef->get(node);
	const u8 sky = node.getLightRaw(LIGHTBANK_DAY, ndef->getLightingFlags(node)) * 17;
	if (!eligible(node, ndef))
		return video::SColor(0, f.light_propagates && !f.isLiquid() ? 64 : 128, 0, sky);
	float height = 1.0f;
	if (f.liquid_type == LIQUID_FLOWING && !(node.param2 & LIQUID_FLOW_DOWN_MASK)) {
		const int range = core::clamp(int(f.liquid_range), 1, 8);
		const int level = std::max(0, int(node.param2 & LIQUID_LEVEL_MASK) - (8 - range));
		height = (level + 0.5f) / range;
	}
	return video::SColor(f.post_effect_color.getAlpha(), f.waving == 3 ?
		(f.drawtype == NDT_LIQUID ? 255 : 240) : 224,
		core::clamp(int(std::round(height * 255.0f)), 1, 255), sky);
}

WaterVolume::~WaterVolume()
{
	if (m_snapshots)
		infostream << "Water volume snapshots: mean=" << m_total_ms / m_snapshots << " ms max="
			<< m_max_ms << " ms count=" << m_snapshots << std::endl;
	if (m_texture) m_driver->removeTexture(m_texture);
}

bool WaterVolume::containsWater(v3f position) const
{
	return findWater(position, nullptr);
}

bool WaterVolume::hasGeometry(v3f position) const
{
	if (m_failed || !m_size) return false;
	const v3f q = position / BS - v3f(m_origin.X, m_origin.Y, m_origin.Z) + v3f(0.5f);
	const int x = int(std::floor(q.X)), y = int(std::floor(q.Y)), z = int(std::floor(q.Z));
	return x >= 0 && y >= 0 && z >= 0 && x < m_size && y < m_size && z < m_size &&
		video::SColor(m_pixels[x + m_size*(y + m_size*z)]).getRed() != 0;
}

bool WaterVolume::findWater(v3f position, v3s16 *node) const
{
	if (m_failed || !m_size) return false;
	const v3f q = position / BS - v3f(m_origin.X, m_origin.Y, m_origin.Z) + v3f(0.5f);
	const int x = int(std::floor(q.X)), y = int(std::floor(q.Y)), z = int(std::floor(q.Z));
	if (x < 0 || y < 0 || z < 0 || x >= m_size || y >= m_size || z >= m_size) return false;
	const video::SColor cell(m_pixels[x + m_size*(y + m_size*z)]);
	// Solid/unknown geometry takes precedence over displaced liquid.
	if (cell.getRed() < 64 || (cell.getRed() > 100 && cell.getRed() < 200)) return false;
	for (int j = 0; j <= int(std::ceil(m_waves.X * 0.5f)); ++j) {
		if (y + j >= m_size) break;
		const int index = x + m_size*(y + j + m_size*z);
		const video::SColor candidate(m_pixels[index]);
		if (candidate.getRed() < 224 || (j > 0 && candidate.getRed() < 240)) continue;
		const v3f min((m_origin.X + x - 0.5f) * BS,
			(m_origin.Y + y + j - 0.5f) * BS, (m_origin.Z + z - 0.5f) * BS);
		const v3f waves = candidate.getRed() >= 240 ? m_waves : v3f(0);
		const float bottom = WaterWaves::surface(min, q.X - x, q.Z - z, waves);
		const float top = WaterWaves::surface(min, q.X - x, q.Z - z, waves, m_heights[index]);
		if (position.Y < bottom || position.Y >= top) continue;
		if (node) *node = v3s16(m_origin.X+x, m_origin.Y+y+j, m_origin.Z+z);
		return true;
	}
	return false;
}

void WaterVolume::update(Client *client, u32 time)
{
	if (m_failed) return;
	// Geometry refresh is throttled; animation and camera classification are not.
	m_waves = waveParameters(client->getEnv().getFrameTime(), m_waving);
	const v3f camera = client->getCamera()->getPosition() / BS;
	const int n = m_size ? m_size : core::clamp(g_settings->getS32("water_volume_size"), 32, 64);
	v3s32 origin;
	for (int axis = 0; axis < 3; ++axis)
		origin[axis] = core::clamp(int(std::floor(camera[axis])) - n / 2, -32768, 32767 - n);
	const v3f relative = camera - v3f(m_origin.X, m_origin.Y, m_origin.Z);
	const bool recenter = !m_size || (origin != m_origin && (relative.X < 4 || relative.Y < 4 || relative.Z < 4 ||
		relative.X > m_size - 5 || relative.Y > m_size - 5 || relative.Z > m_size - 5));
	if (m_started && !recenter && time - m_last_update < 250) return;
	m_started = true;
	m_last_update = time;
	const auto began = std::chrono::steady_clock::now();
	std::vector<u32> snapshot(n * n * n, 0);
	std::vector<std::array<float, 4>> heights(n * n * n);
	// One loaded-node walk, including a halo for flow corners and their upper
	// neighbors. Avoid repeated map lookups for every flowing node in a waterfall.
	const int h = n+2;
	std::vector<MapNode> nodes(h*h*h, MapNode(CONTENT_IGNORE));
	v3s16 minp, maxp;
	for (int axis = 0; axis < 3; ++axis) {
		minp[axis] = std::max(origin[axis]-1, -32768);
		maxp[axis] = origin[axis]+n;
	}
	auto &map = client->getEnv().getClientMap();
	const auto *ndef = client->ndef();
	map.forEachNodeInArea(minp, maxp, [&](v3s16 p, MapNode node) {
		nodes[(p.X-origin.X+1) + h*((p.Y-origin.Y+1) + h*(p.Z-origin.Z+1))] = node;
		return true;
	});
	const auto at = [&](int x, int y, int z) { return nodes[x+h*(y+h*z)]; };
	unsigned int water = 0, flowing = 0;
	for (int z = 0; z < n; ++z) for (int y = 0; y < n; ++y) for (int x = 0; x < n; ++x) {
		const int index = x+n*(y+n*z);
		const MapNode node = at(x+1, y+1, z+1);
		auto cell = encodeCell(node, ndef);
		if (cell.getRed() >= 224) {
			++water;
			const auto &f = ndef->get(node);
			if (f.drawtype == NDT_FLOWINGLIQUID) {
				++flowing;
				LiquidGeometry::Neighbor neighbors[3][3];
				const auto source = f.liquid_alternative_source_id, flow = f.liquid_alternative_flowing_id;
				const int range = ndef->get(flow).liquid_range;
				for (int dz = 0; dz < 3; ++dz) for (int dx = 0; dx < 3; ++dx)
					neighbors[dz][dx] = LiquidGeometry::neighbor(at(x+dx, y+1, z+dz),
						at(x+dx, y+2, z+dz), source, flow, range);
				heights[index] = LiquidGeometry::cornerHeights(neighbors, source, flow);
				if (neighbors[1][1].top_is_same_liquid) cell.setGreen(255);
			} else heights[index] = {1, 1, 1, 1};
		}
		snapshot[index] = cell.color;
	}
	if (!m_texture) {
		const bool mipmaps = m_driver->getTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS);
		m_driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, false);
		m_texture = m_driver->addTexture(core::dimension2du(2*n, n*n), "water_geometry", video::ECF_A32B32G32R32F);
		m_driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, mipmaps);
	}
	if (!m_texture) {
		warningstream << "Water geometry allocation failed; retaining native liquid effects." << std::endl;
		m_failed = true;
		return;
	}
	auto *pixels = static_cast<unsigned char *>(m_texture->lock(video::ETLM_WRITE_ONLY));
	if (!pixels) {
		warningstream << "Water geometry upload failed; retaining native liquid effects." << std::endl;
		m_failed = true;
		return;
	}
	for (int row_index = 0; row_index < n*n; ++row_index) {
		auto *row = reinterpret_cast<float *>(pixels + row_index*m_texture->getPitch());
		for (int x = 0; x < n; ++x) {
			const int index = row_index*n+x;
			const video::SColor c(snapshot[index]);
			row[4*x] = c.getRed()/255.0f;
			row[4*x+1] = c.getGreen()/255.0f;
			row[4*x+2] = c.getBlue()/255.0f;
			row[4*x+3] = c.getAlpha()/255.0f;
			std::memcpy(row + 4*(n+x), heights[index].data(), 4*sizeof(float));
		}
	}
	m_texture->unlock();
	if (!m_size)
		infostream << "Water volume: uploaded " << n << "^3 cells, water=" << water << std::endl;
	if (m_water_cells != int(water)) {
		infostream << "Water volume: water cells=" << water << std::endl;
		m_water_cells = int(water);
	}
	if (m_flowing_cells != int(flowing)) {
		infostream << "Water volume: flowing cells=" << flowing << std::endl;
		m_flowing_cells = int(flowing);
	}
	m_origin = origin;
	m_size = n;
	m_pixels = std::move(snapshot);
	m_heights = std::move(heights);
	const double elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - began).count();
	m_total_ms += elapsed;
	m_max_ms = std::max(m_max_ms, elapsed);
	++m_snapshots;
	g_profiler->avg("Water geometry snapshot [ms]", elapsed);
}
