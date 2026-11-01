// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "cloud_field.h"
#include <memory>

class Client;
class TextureBuffer;
class TextureBufferOutput;
class PostProcessingStep;
struct PipelineContext;
namespace video { class ITexture; }

bool useCloudShadows();

// View-independent transmission map, rendered once before either eye.
class CloudShadows
{
public:
	explicit CloudShadows(Client *client);
	~CloudShadows();
	void render(PipelineContext &context);
	void prepare(const cloud_field::Density &density, v3f direction, bool enabled);
	cloud_field::ShadowField snapshot() const;
	video::ITexture *getTexture() const;
	const CloudShadowFrame &getFrame() const { return frame; }
	bool ready() const { return rendered && frame.enabled; }
private:
	Client *client;
	int resolution;
	u32 shader_id;
	CloudShadowFrame frame;
	cloud_field::Density density;
	bool rendered = false;
	bool reported = false;
	bool last_active = false;
	std::unique_ptr<TextureBuffer> buffer;
	std::unique_ptr<TextureBufferOutput> target;
	std::unique_ptr<PostProcessingStep> step;
};
