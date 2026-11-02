// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include "pipeline.h"
#include <array>
#include <fstream>

// Opt-in acceptance-test telemetry: read one reduced RGBA32F texel per frame.
// Installed only by benchmark_scene_log or benchmark_final_scene_log.
class SceneStatisticsStep : public TrivialRenderStep
{
public:
	SceneStatisticsStep(RenderSource *source, u8 texture, const std::string &path);
	~SceneStatisticsStep() override;
	void run(PipelineContext &context) override;
private:
	struct Sample { u64 time; std::array<float, 4> values; };
	RenderSource *m_source;
	u8 m_texture;
	std::ofstream m_output;
	std::vector<Sample> m_samples;
	bool m_failed = false;
};
