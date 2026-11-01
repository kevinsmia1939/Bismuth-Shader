// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "voxel_lighting.h"
#include "client/client.h"
#include "client/clientenvironment.h"
#include "client/clientmap.h"
#include "client/camera.h"
#include "client/content_cao.h"
#include "client/item_visuals_manager.h"
#include "client/localplayer.h"
#include "client/node_visuals.h"
#include "client/renderingengine.h"
#include "exceptions.h"
#include "inventory.h"
#include "itemdef.h"
#include "settings.h"
#include "profiler.h"
#include "log.h"
#include <IVideoDriver.h>
#include <ITexture.h>
#include <ISceneManager.h>
#include <ISceneNode.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>

bool voxelLightingEnabled()
{
	auto *driver = RenderingEngine::get_video_driver();
	return g_settings->getBool("enable_voxel_lighting") &&
		(driver->getDriverType() == video::EDT_OPENGL || driver->getDriverType() == video::EDT_OPENGL3) &&
		driver->queryTextureFormat(video::ECF_A32B32G32R32F);
}

bool voxelDynamicDirectEnabled()
{
	return voxelLightingEnabled() && g_settings->getBool("enable_voxel_dynamic_direct") &&
		RenderingEngine::get_video_driver()->getLimits().GLVersion.X >= 3;
}

namespace {
v3f linearColor(video::SColor color)
{
	return v3f(std::pow(color.getRed() / 255.0f, 2.2f),
		std::pow(color.getGreen() / 255.0f, 2.2f), std::pow(color.getBlue() / 255.0f, 2.2f));
}

v3f nodeEmission(const ContentFeatures &feature, video::SColor color)
{
	if (!feature.light_source) return {};
	v3f emission = linearColor(feature.light_source_color_set ? feature.light_source_color : color);
	if (!feature.light_source_color_set && emission.getLengthSQ() < 0.00001f)
		emission = v3f(1.0f);
	const float peak = std::max({emission.X, emission.Y, emission.Z, 0.001f});
	return emission * (2.0f * std::pow(feature.light_source / 14.0f, 2.0f) / peak);
}

video::SColor tintedColor(video::SColor color, video::SColor tint)
{
	color.setRed(color.getRed() * tint.getRed() / 255);
	color.setGreen(color.getGreen() * tint.getGreen() / 255);
	color.setBlue(color.getBlue() * tint.getBlue() / 255);
	return color;
}

voxel_light::Cell nodeMaterial(MapNode node, const ContentFeatures &feature, bool transmission)
{
	voxel_light::Cell cell;
	cell.solid = node.getContent() == CONTENT_IGNORE || !feature.light_propagates;
	video::SColor color(255, 128, 128, 128);
	if (feature.visuals) {
		color = feature.visuals->minimap_color;
		const auto tint = feature.visuals->getColor(feature, node.param2);
		cell.tint = linearColor(tint);
		color = tintedColor(color, tint);
	}
	cell.albedo = linearColor(color);
	if (feature.visuals)
		cell.albedo *= feature.visuals->tiles[0].layers[0].diffuse_fraction;
	cell.emission = nodeEmission(feature, color);
	if (transmission && !cell.solid) {
		if (feature.light_transmission_color_set) {
			const auto t = feature.light_transmission_color;
			cell.transmission = v3f(t.getRed(), t.getGreen(), t.getBlue()) / 255.0f;
		} else if (feature.drawtype == NDT_GLASSLIKE ||
				feature.drawtype == NDT_GLASSLIKE_FRAMED ||
				feature.drawtype == NDT_GLASSLIKE_FRAMED_OPTIONAL) {
			// Infer hue without treating neutral texture brightness as absorption.
			const auto hue = linearColor(color);
			const float peak = std::max({hue.X, hue.Y, hue.Z, 0.001f});
			cell.transmission = hue * (0.96f / peak);
		}
	}
	return cell;
}
}

VoxelLighting::~VoxelLighting()
{
	if (m_geometry_scans)
		infostream << "Voxel geometry snapshots: mean=" << m_geometry_total_ms / m_geometry_scans <<
			" ms max=" << m_geometry_max_ms << " ms scans=" << m_geometry_scans <<
			" uploads=" << m_geometry_uploads << std::endl;
	// The worker owns a map snapshot and never references Client or the driver.
	if (m_job.valid()) m_job.wait();
	// Scene nodes may outlive the core during shutdown/reconfiguration.
	std::vector<scene::ISceneNode *> nodes { RenderingEngine::get_raw_device()->getSceneManager()->getRootSceneNode() };
	while (!nodes.empty()) {
		auto *node = nodes.back(); nodes.pop_back();
		for (u32 i = 0; i < node->getMaterialCount(); ++i)
			if (node->getMaterial(i).getTexture(2) == m_texture)
				node->getMaterial(i).setTexture(2, nullptr);
		for (auto *child : node->getChildren()) nodes.push_back(child);
	}
	if (m_texture) m_driver->removeTexture(m_texture);
}

void VoxelLighting::upload(const JobResult &result)
{
	const int n = result.solution.size;
	const int columns = m_dynamic_direct ? 14 : 13;
	const core::dimension2du dimensions(n * columns, n * n);
	if (!m_texture || m_texture->getSize() != dimensions) {
		if (m_texture) m_driver->removeTexture(m_texture);
		const bool mipmaps = m_driver->getTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS);
		const bool cpu_copy = m_driver->getTextureCreationFlag(video::ETCF_ALLOW_MEMORY_COPY);
		m_driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, false);
		m_driver->setTextureCreationFlag(video::ETCF_ALLOW_MEMORY_COPY, false);
		m_texture = m_driver->addTexture(dimensions, "voxel_radiance_atlas", video::ECF_A32B32G32R32F);
		m_driver->setTextureCreationFlag(video::ETCF_CREATE_MIP_MAPS, mipmaps);
		m_driver->setTextureCreationFlag(video::ETCF_ALLOW_MEMORY_COPY, cpu_copy);
	}
	if (!m_texture) return;
	auto *pixels = static_cast<unsigned char *>(m_texture->lock(video::ETLM_WRITE_ONLY));
	if (!pixels) return;
	for (int z = 0; z < n; ++z) for (int y = 0; y < n; ++y) {
		auto *row = reinterpret_cast<float *>(pixels + (z * n + y) * m_texture->getPitch());
		for (int x = 0; x < n; ++x) {
			const int index = x + n * (y + n * z);
			const auto &cell = result.solution.cells[index];
			for (int group = 0; group < columns; ++group) {
				v3f rgb;
				float alpha = cell.solid ? 0.0f : 1.0f;
				if (group < 6) rgb = result.solution.fields[index].direct[group];
				else if (group < 12) rgb = result.solution.fields[index].indirect[group - 6];
				else if (group == 12) { rgb = cell.tint; alpha = cell.emission.getLengthSQ() > 0 ? 1.0f : 0.0f; }
				else rgb = cell.transmission; // Geometry/optics for frame-direct visibility.
				const int offset = (group * n + x) * 4;
				row[offset] = rgb.X; row[offset + 1] = rgb.Y; row[offset + 2] = rgb.Z; row[offset + 3] = alpha;
			}
		}
	}
	m_texture->unlock();
	if (m_filter_count != int(result.solution.filter_count) ||
			m_min_transmission != result.solution.min_transmission) {
		const auto t = result.solution.min_transmission;
		infostream << "Voxel GI: filters=" << result.solution.filter_count
			<< " transmission=" << t.X << "," << t.Y << "," << t.Z << std::endl;
		m_filter_count = result.solution.filter_count;
		m_min_transmission = t;
	}
	if (result.solution.sunlight_faces > 0) {
		const int active = result.solution.min_sun_transmission < 0.999f;
		if (active != m_cloud_active) {
			infostream << "Voxel GI: cloud attenuation active=" << active
				<< " sunlit_faces=" << result.solution.sunlight_faces
				<< " transmission=" << result.solution.min_sun_transmission
				<< "," << result.solution.max_sun_transmission << std::endl;
			m_cloud_active = active;
		}
	}
	if (m_size == 0)
		infostream << "Voxel GI: uploaded " << n << "^3 probes, "
			<< result.solution.solve_ms << " ms worker solve, atlas columns=" << columns << std::endl;
	if (m_source_count != int(result.solution.source_count) ||
			m_emission_sum.getDistanceFromSQ(result.solution.emission_sum) > 0.00000001f) {
		++m_light_revision;
		const auto emission = result.solution.emission_sum;
		infostream << "Voxel GI: sources=" << result.solution.source_count << " emission="
			<< emission.X << "," << emission.Y << "," << emission.Z << std::endl;
		m_source_count = result.solution.source_count;
		m_emission_sum = emission;
	}
	if (m_dynamic_source_count != int(result.solution.dynamic_source_count) ||
			m_held_source_count != int(result.solution.held_source_count) ||
			m_dynamic_emission_sum.getDistanceFromSQ(result.solution.dynamic_emission_sum) > 0.00000001f) {
		const auto &solution = result.solution;
		const auto emission = solution.dynamic_emission_sum;
		const auto centroid = solution.dynamic_source_count ?
			solution.dynamic_position_sum / float(solution.dynamic_source_count) +
			v3f(result.origin.X, result.origin.Y, result.origin.Z) : v3f();
		infostream << "Voxel GI: dynamic sources=" << solution.dynamic_source_count
			<< " held=" << solution.held_source_count << " emission=" << emission.X
			<< "," << emission.Y << "," << emission.Z << " centroid=" << centroid.X
			<< "," << centroid.Y << "," << centroid.Z << std::endl;
		m_dynamic_source_count = solution.dynamic_source_count;
		m_held_source_count = solution.held_source_count;
		m_dynamic_emission_sum = emission;
	}
	m_origin = result.origin;
	m_size = n;
	m_geometry_dirty = true; // The worker's optics column may predate live edits.
	m_solve_ms = result.solution.solve_ms;
	g_profiler->avg("Voxel GI solve [ms]", m_solve_ms);
}

void VoxelLighting::refreshGeometry(Client *client)
{
	if (!m_texture || !m_size) return;
	const auto began = std::chrono::steady_clock::now();
	const int n = m_size;
	m_next_optics.resize(n * n * n);
	const bool resized = m_optics.size() != m_next_optics.size();
	const bool transmission = g_settings->getBool("enable_voxel_transmission");
	std::unordered_map<u32, voxel_light::Cell> materials;
	const auto *ndef = client->ndef();
	unsigned int changed = 0, blocked = 0, filtered = 0;
	v3f minimum(1.0f);
	auto &map = client->getEnv().getClientMap();
	map.forEachNodeInArea(v3s16(m_origin.X, m_origin.Y, m_origin.Z),
		v3s16(m_origin.X+n-1, m_origin.Y+n-1, m_origin.Z+n-1),
		[&](v3s16 p, MapNode node) {
			const u32 key = (u32(node.getContent()) << 8) | node.param2;
			auto found = materials.find(key);
			if (found == materials.end())
				found = materials.emplace(key, nodeMaterial(node, ndef->get(node), transmission)).first;
			const auto &cell = found->second;
			const auto t = cell.transmission;
			const int index = p.X-m_origin.X + n*(p.Y-m_origin.Y+n*(p.Z-m_origin.Z));
			auto &optics = m_next_optics[index];
			optics = {t.X, t.Y, t.Z, cell.solid ? 0.0f : 1.0f};
			changed += resized || optics != m_optics[index];
			blocked += cell.solid;
			filtered += !cell.solid && (t.X < 1 || t.Y < 1 || t.Z < 1);
			if (!cell.solid) for (int axis = 0; axis < 3; ++axis)
				minimum[axis] = std::min(minimum[axis], t[axis]);
			return true;
		});
	if (changed || m_geometry_dirty) {
		// Only the contiguous optics column changes. Radiance remains immutable
		// until its solve completes; no GPU readback or full-atlas copy is needed.
		if (m_texture->updateRegion({u32(13*n), 0}, {u32(n), u32(n*n)}, m_next_optics.data())) {
			++m_geometry_uploads;
			m_optics.swap(m_next_optics);
			m_geometry_dirty = false;
			if (changed) {
				++m_geometry_revision;
				++m_light_revision;
				const bool pending = m_job.valid() &&
					m_job.wait_for(std::chrono::milliseconds(0)) != std::future_status::ready;
				infostream << "Voxel geometry: revision=" << m_geometry_revision <<
					" changed=" << changed << " blocked=" << blocked << " filters=" << filtered <<
					" transmission=" << minimum.X << "," << minimum.Y << "," << minimum.Z <<
					" solve_pending=" << pending << std::endl;
			}
		}
	}
	const double elapsed = std::chrono::duration<double, std::milli>(
		std::chrono::steady_clock::now() - began).count();
	++m_geometry_scans;
	m_geometry_total_ms += elapsed;
	m_geometry_max_ms = std::max(m_geometry_max_ms, elapsed);
	g_profiler->avg("Voxel direct geometry [ms]", elapsed);
}

std::vector<voxel_light::DynamicSource> VoxelLighting::collectDynamicSources(
		Client *client, v3s32 origin, int n)
{
	std::vector<voxel_light::DynamicSource> sources;
	auto &map = client->getEnv().getClientMap();
	const auto *ndef = client->ndef();
	if (g_settings->getBool("enable_voxel_dynamic_lighting")) {
		const v3f grid_origin(origin.X, origin.Y, origin.Z);
		auto append = [&](v3f position, v3f emission, bool held = false) {
			const auto relative = position / BS - grid_origin;
			if (!std::isfinite(relative.X) || !std::isfinite(relative.Y) || !std::isfinite(relative.Z) ||
					emission.getLengthSQ() <= 0 || relative.X < -0.5f || relative.Y < -0.5f ||
					relative.Z < -0.5f || relative.X >= n - 0.5f || relative.Y >= n - 0.5f || relative.Z >= n - 0.5f)
				return;
			const auto node = map.getNode(floatToInt(position, BS));
			if (node.getContent() == CONTENT_IGNORE || !ndef->get(node).light_propagates) return;
			sources.push_back({position / BS, emission, held});
		};
		auto item_emission = [&](const ItemStack &item) {
			const auto &feature = ndef->get(item.getDefinition(client->idef()).name);
			if (item.empty() || !feature.light_source) return v3f();
			const auto average = feature.visuals ? feature.visuals->minimap_color :
				video::SColor(255, 128, 128, 128);
			return nodeEmission(feature, tintedColor(average,
				client->getItemVisualsManager()->getItemstackColor(item, client)));
		};
		// Anchor to the player, not the orbiting third-person camera or HUD mesh.
		if (auto *player = client->getEnv().getLocalPlayer()) {
			ItemStack selected;
			player->getWieldedItem(&selected, nullptr);
			append(player->getEyePosition() - v3f(0, 0.35f * BS, 0), item_emission(selected), true);
		}
		std::vector<DistanceSortedActiveObject> objects;
		client->getEnv().getActiveObjects((grid_origin + v3f((n - 1) * 0.5f)) * BS,
			n * 0.87f * BS, objects);
		for (const auto &entry : objects) {
			if (entry.obj->getType() != ACTIVEOBJECT_TYPE_GENERIC) continue;
			auto *object = static_cast<GenericCAO *>(entry.obj);
			const auto &prop = object->getProperties();
			if (!prop.is_visible || object->isLocalPlayer()) continue;
			// Local wield-display attachments duplicate the held inventory source.
			bool attached_to_local = false;
			auto *parent = object->getParent();
			for (int depth = 0; parent && depth < 64; ++depth, parent = parent->getParent())
				attached_to_local |= parent->isLocalPlayer();
			if (attached_to_local && prop.visual == OBJECTVISUAL_WIELDITEM) continue;
			v3f emission;
			if (prop.visual == OBJECTVISUAL_NODE) {
				const auto &feature = ndef->get(prop.node);
				const auto average = feature.visuals ? feature.visuals->minimap_color :
					video::SColor(255, 128, 128, 128);
				const auto tint = feature.visuals ? feature.visuals->getColor(feature, prop.node.param2) : feature.color;
				emission = nodeEmission(feature, tintedColor(average, tint));
			} else if (prop.visual == OBJECTVISUAL_ITEM || prop.visual == OBJECTVISUAL_WIELDITEM) {
				ItemStack item;
				try {
					if (!prop.wield_item.empty()) item.deSerialize(prop.wield_item, client->idef());
					else if (!prop.textures.empty()) item = ItemStack(prop.textures[0], 1, 0, client->idef());
				} catch (const SerializationError &) {
					continue;
				}
				emission = item_emission(item);
			}
			append(object->getPosition(), emission);
		}
	}
	return sources;
}

void VoxelLighting::update(Client *client, v3f sun_direction, v3f sunlight, u32 time,
		cloud_field::ShadowField clouds)
{
	// Size is fixed for the core lifetime so scene materials never retain a
	// removed atlas during a frame. Changing it requires a restart.
	const int n = m_size ? m_size : core::clamp(g_settings->getS32("voxel_lighting_size"), 16, 48);
	const v3f center = client->getCamera()->getPosition() / BS +
		client->getCamera()->getDirection() * (n * 0.25f);
	v3s32 origin;
	origin.X = core::clamp(int(std::floor(center.X)) - n / 2, -32768, 32767 - n);
	origin.Y = core::clamp(int(std::floor(center.Y)) - n / 2, -32768, 32767 - n);
	origin.Z = core::clamp(int(std::floor(center.Z)) - n / 2, -32768, 32767 - n);
	if (m_dynamic_direct) {
		const auto began = std::chrono::steady_clock::now();
		m_frame_sources = voxel_light::selectDynamicSources(collectDynamicSources(client, origin, n),
			v3f(origin.X, origin.Y, origin.Z) + v3f((n - 1) * 0.5f), MAX_DYNAMIC_LIGHTS);
		v3f emission;
		int held = 0;
		for (const auto &source : m_frame_sources) { emission += source.emission; held += source.held; }
		if (m_frame_count != int(m_frame_sources.size()) || m_frame_held != held || emission != m_frame_emission) {
			infostream << "Voxel dynamic direct: sources=" << m_frame_sources.size() << " held=" << held
				<< " emission=" << emission.X << "," << emission.Y << "," << emission.Z << std::endl;
			m_frame_count = m_frame_sources.size();
			m_frame_held = held;
			m_frame_emission = emission;
		}
		g_profiler->avg("Voxel dynamic sources [ms]", std::chrono::duration<double, std::milli>(
			std::chrono::steady_clock::now() - began).count());
	}
	if (m_job.valid() && m_job.wait_for(std::chrono::milliseconds(0)) == std::future_status::ready)
		upload(m_job.get());
	if (m_dynamic_direct) refreshGeometry(client);
	if (m_job.valid()) return;
	if (m_started && time - m_last_update < 250) return;
	m_started = true;
	m_last_update = time;

	voxel_light::Grid grid(n);
	grid.sun_direction = sun_direction;
	if (grid.sun_direction.getLengthSQ() > 0.00001f) {
		grid.sun_direction.normalize();
		// Already linear, including the shared horizon fade and source strength.
		grid.sun_irradiance = sunlight;
	}
	const auto snapshot_began = std::chrono::steady_clock::now();
	// Cache material/palette conversion within this snapshot; no texture readback.
	std::unordered_map<u32, voxel_light::Cell> materials;
	auto &map = client->getEnv().getClientMap();
	const auto *ndef = client->ndef();
	const bool transmission = g_settings->getBool("enable_voxel_transmission");
	map.forEachNodeInArea(v3s16(origin.X, origin.Y, origin.Z),
		v3s16(origin.X + n - 1, origin.Y + n - 1, origin.Z + n - 1),
		[&](v3s16 p, MapNode node) {
			const auto content = node.getContent();
			const u32 key = (u32(content) << 8) | node.param2;
			auto material = materials.find(key);
			if (material == materials.end()) {
				material = materials.emplace(key, nodeMaterial(node, ndef->get(content), transmission)).first;
			}
			const int index = grid.index(p.X - origin.X, p.Y - origin.Y, p.Z - origin.Z);
			grid.cells[index] = material->second;
			grid.cells[index].sky = node.getLightRaw(LIGHTBANK_DAY, ndef->getLightingFlags(node)) == LIGHT_SUN;
			return true;
		});
	grid.dynamic_sources = m_dynamic_direct ? m_frame_sources : collectDynamicSources(client, origin, n);
	for (auto &source : grid.dynamic_sources) source.position -= v3f(origin.X, origin.Y, origin.Z);
	grid.bake_dynamic_direct = !m_dynamic_direct;
	g_profiler->avg("Voxel GI snapshot [ms]", std::chrono::duration<double, std::milli>(
		std::chrono::steady_clock::now() - snapshot_began).count());
	const unsigned int bounces = core::clamp(g_settings->getS32("voxel_gi_bounces"), 1, 4);
	m_job = std::async(std::launch::async, [grid = std::move(grid), origin, bounces, clouds]() mutable {
		cloud_field::ShadowSampler sampler(clouds);
		auto transmission = [&](v3f p) { return sampler.transmission((p + v3f(origin.X, origin.Y, origin.Z)) * BS); };
		return JobResult { voxel_light::solve(std::move(grid), bounces, 64, transmission), origin };
	});
}
