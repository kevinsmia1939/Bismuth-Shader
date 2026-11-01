// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "irr_v3d.h"
#include <SColor.h>
#include <vector>
#include <array>

class Client;
struct MapNode;
class NodeDefManager;
namespace video { class ITexture; class IVideoDriver; }

bool waterVolumeEnabled();
bool useVoxelWaterLighting();

// Camera-local loaded geometry, shared by both eyes. R: unknown/air/solid/water,
// G: nominal liquid height, B: raw skylight, A: game-defined liquid turbidity.
// The float atlas's second column group stores the four mesh corner heights.
class WaterVolume
{
public:
	explicit WaterVolume(video::IVideoDriver *driver);
	~WaterVolume();
	void update(Client *client, u32 time);
	video::ITexture *getTexture() const { return m_failed ? nullptr : m_texture; }
	v3s32 getOrigin() const { return m_origin; }
	int getSize() const { return m_size; }
	v3f getWaves() const { return m_waves; }
	static v3f waveParameters(u64 frame_time, bool enabled);
	bool containsWater(v3f position) const;
	bool findWater(v3f position, v3s16 *node) const;
	bool hasGeometry(v3f position) const;
	static video::SColor encodeCell(const MapNode &node, const NodeDefManager *ndef);
	static bool eligible(const MapNode &node, const NodeDefManager *ndef);
private:
	video::IVideoDriver *m_driver;
	video::ITexture *m_texture = nullptr;
	v3s32 m_origin;
	int m_size = 0;
	u32 m_last_update = 0;
	bool m_started = false;
	bool m_failed = false;
	int m_water_cells = -1;
	double m_total_ms = 0;
	double m_max_ms = 0;
	u32 m_snapshots = 0;
	std::vector<u32> m_pixels;
	std::vector<std::array<float, 4>> m_heights;
	int m_flowing_cells = -1;
	const bool m_waving;
	v3f m_waves;
};
