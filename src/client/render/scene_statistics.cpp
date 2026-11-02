// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "scene_statistics.h"
#include "log.h"
#include "porting.h"
#include <cmath>
#include <iomanip>

SceneStatisticsStep::SceneStatisticsStep(RenderSource *source, u8 texture, const std::string &path) :
	m_source(source), m_texture(texture), m_output(path)
{
	if (!m_output)
		errorstream << "Scene statistics: cannot open " << path << std::endl;
	m_samples.reserve(4096);
}

void SceneStatisticsStep::run(PipelineContext &context)
{
	if (!m_output || m_failed) return;
	auto *texture = m_source->getTexture(m_texture);
	if (!texture || texture->getSize() != core::dimension2du(1, 1) ||
			texture->getColorFormat() != video::ECF_A32B32G32R32F) {
		m_failed = true;
		errorstream << "Scene statistics: expected a reduced RGBA32F texel" << std::endl;
		return;
	}
	auto *values = static_cast<const float *>(texture->lock(video::ETLM_READ_ONLY));
	if (!values) {
		m_failed = true;
		errorstream << "Scene statistics: scalar readback failed" << std::endl;
		return;
	}
	Sample sample{porting::getTimeUs(), {values[0], values[1], values[2], values[3]}};
	texture->unlock();
	for (float value : sample.values) {
		if (!std::isfinite(value) || value < 0) m_failed = true;
	}
	if (m_failed || m_samples.size() >= 100000) {
		m_failed = true;
		errorstream << "Scene statistics: invalid values or sample limit exceeded" << std::endl;
		return;
	}
	m_samples.push_back(sample);
}

SceneStatisticsStep::~SceneStatisticsStep()
{
	if (!m_output) return;
	m_output << "time_us,mean_r,mean_g,mean_b,peak_luminance\n" << std::setprecision(10);
	for (const auto &sample : m_samples) {
		m_output << sample.time;
		for (float value : sample.values) m_output << ',' << value;
		m_output << '\n';
	}
	m_output.flush();
	if (!m_output) errorstream << "Scene statistics: failed to write samples" << std::endl;
	else infostream << "Scene statistics: wrote " << m_samples.size() << " scalar samples" << std::endl;
}
