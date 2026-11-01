// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (C) 2013 celeron55, Perttu Ahola <celeron55@gmail.com>

#include "gamedef.h"
#include "nodedef.h"
#include "network/networkprotocol.h"

#include "catch.h"

#include <ios>
#include <sstream>


TEST_CASE("Given a node definition, "
		"when we serialize and then deserialize it, "
		"then the deserialized one should be equal to the original.",
		"[nodedef]")
{
	ContentFeatures f;
	f.name = "default:stone";
	for (TileDef &tiledef : f.tiledef)
		tiledef.name = "default_stone.png";
	f.is_ground_content = true;

	std::ostringstream os(std::ios::binary);
	f.serialize(os, LATEST_PROTOCOL_VERSION);
	std::istringstream is(os.str(), std::ios::binary);
	ContentFeatures f2;
	f2.deSerialize(is, LATEST_PROTOCOL_VERSION);

	CHECK(f.walkable == f2.walkable);
	CHECK(f.node_box.type == f2.node_box.type);
}

TEST_CASE("Emissive node colors survive transport and default safely for older definitions", "[nodedef]")
{
	ContentFeatures source;
	source.name = "test:colored_lamp";
	source.light_source = 14;
	source.light_source_color_set = true;
	source.light_source_color = video::SColor(255, 12, 34, 230);
	std::ostringstream os(std::ios::binary);
	source.serialize(os, LATEST_PROTOCOL_VERSION);
	ContentFeatures received;
	std::istringstream full(os.str(), std::ios::binary);
	received.deSerialize(full, LATEST_PROTOCOL_VERSION);
	CHECK(received.light_source_color_set);
	CHECK(received.light_source_color == source.light_source_color);
	// Old peers omit the optional, length-wrapped five-byte color suffix.
	std::istringstream old(os.str().substr(0, os.str().size()-5), std::ios::binary);
	received.deSerialize(old, LATEST_PROTOCOL_VERSION);
	CHECK_FALSE(received.light_source_color_set);
	CHECK(received.light_source_color == video::SColor(255,255,255,255));
	CHECK(received.light_source == source.light_source);
}

TEST_CASE("Material maps survive transport on base, overlay and special tiles", "[nodedef]")
{
	ContentFeatures source;
	source.name = "test:material";
	source.tiledef[0].name = "base.png";
	source.tiledef[0].normal_texture = "base_normal.png";
	source.tiledef[0].material_texture = "base_orm.png";
	source.tiledef_overlay[5].normal_texture = "overlay_normal.png";
	source.tiledef_special[2].material_texture = "special_orm.png";
	source.light_source_color_set = true;
	source.light_source_color = video::SColor(255, 80, 120, 250);
	std::ostringstream stream(std::ios::binary);
	source.serialize(stream, LATEST_PROTOCOL_VERSION);
	const auto payload = stream.str();
	ContentFeatures received;
	std::istringstream full(payload, std::ios::binary);
	received.deSerialize(full, LATEST_PROTOCOL_VERSION);
	CHECK(received.tiledef[0].normal_texture == source.tiledef[0].normal_texture);
	CHECK(received.tiledef[0].material_texture == source.tiledef[0].material_texture);
	CHECK(received.tiledef_overlay[5].normal_texture == source.tiledef_overlay[5].normal_texture);
	CHECK(received.tiledef_special[2].material_texture == source.tiledef_special[2].material_texture);
	CHECK(received.light_source_color == source.light_source_color);
	// The original payload before either extension is unchanged byte for byte.
	source.tiledef[0].normal_texture.clear();
	source.tiledef[0].material_texture.clear();
	source.tiledef_overlay[5].normal_texture.clear();
	source.tiledef_special[2].material_texture.clear();
	std::ostringstream legacy_stream(std::ios::binary);
	source.serialize(legacy_stream, LATEST_PROTOCOL_VERSION);
	const auto legacy = legacy_stream.str();
	CHECK(payload.substr(0, legacy.size()) == legacy);
	std::istringstream old(legacy, std::ios::binary);
	received.deSerialize(old, LATEST_PROTOCOL_VERSION);
	CHECK(received.tiledef[0].normal_texture.empty());
	CHECK(received.tiledef[0].material_texture.empty());
	CHECK(received.tiledef_overlay[5].normal_texture.empty());
	CHECK(received.tiledef_special[2].material_texture.empty());
	CHECK(received.light_source_color_set);
	std::istringstream oldest(legacy.substr(0, legacy.size() - 5), std::ios::binary);
	received.deSerialize(oldest, LATEST_PROTOCOL_VERSION);
	CHECK_FALSE(received.light_source_color_set);
	CHECK(received.tiledef[0].normal_texture.empty());
}

TEST_CASE("Optical transmission survives transport without changing legacy material prefixes", "[nodedef]")
{
	for (const bool maps : {false, true}) {
		ContentFeatures source;
		source.name = "test:colored_glass";
		if (maps) source.tiledef[0].material_texture = "glass_orm.png";
		source.light_transmission_color_set = true;
		source.light_transmission_color = video::SColor(12, 255, 64, 0);
		std::ostringstream stream(std::ios::binary);
		source.serialize(stream, LATEST_PROTOCOL_VERSION);
		const auto payload = stream.str();
		ContentFeatures received;
		std::istringstream full(payload, std::ios::binary);
		received.deSerialize(full, LATEST_PROTOCOL_VERSION);
		CHECK(received.light_transmission_color_set);
		CHECK(received.light_transmission_color == source.light_transmission_color);
		CHECK(received.tiledef[0].material_texture == source.tiledef[0].material_texture);
		// Older material-aware peers stop before this five-byte suffix.
		std::istringstream older(payload.substr(0, payload.size() - 5), std::ios::binary);
		received.deSerialize(older, LATEST_PROTOCOL_VERSION);
		CHECK_FALSE(received.light_transmission_color_set);
		CHECK(received.light_transmission_color == video::SColor(255, 255, 255, 255));
		CHECK(received.tiledef[0].material_texture == source.tiledef[0].material_texture);
		source.light_transmission_color_set = false;
		std::ostringstream original(std::ios::binary);
		source.serialize(original, LATEST_PROTOCOL_VERSION);
		CHECK(payload.substr(0, original.str().size()) == original.str());
	}
}
