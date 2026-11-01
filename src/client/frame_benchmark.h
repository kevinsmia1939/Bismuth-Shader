// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include "log.h"
#include <fstream>
#include <iomanip>
#include <string>
#include <vector>

// Opt-in development telemetry. Buffer samples so per-frame file I/O cannot
// stall measured frames. The clock is shared with server core.get_us_time().
class FrameBenchmark {
	struct Frame {
		u64 time, busy, sleep, draw;
		float elapsed;
		u32 width, height, drawcalls;
	};
	std::ofstream m_output;
	std::vector<Frame> m_frames;
	bool m_full = false;
	bool m_reported = false;
	bool m_progress = false;
public:
	explicit FrameBenchmark(const std::string &path, bool progress = false) : m_progress(progress)
	{
		if (path.empty()) return;
		m_output.open(path,std::ios::trunc);
		if (!m_output) errorstream << "Frame benchmark: cannot open " << path << std::endl;
		else m_frames.reserve(4096);
	}
	void record(u64 time, float elapsed, u64 busy, u64 sleep, u64 draw,
			u32 width, u32 height, u32 drawcalls)
	{
		if (!m_output.is_open() || m_full) return;
		if (!m_reported && !m_frames.empty()) {
			infostream << "Frame benchmark: active time_us=" << time << std::endl;
			m_reported = true;
		}
		if (m_frames.size() >= 1000000) {
			m_full = true;
			errorstream << "Frame benchmark: sample limit exceeded" << std::endl;
			return;
		}
		m_frames.push_back({time,busy,sleep,draw,elapsed,width,height,drawcalls});
		// Integration fixtures can wait for completed client frames after every
		// scene change. Disabled for timing runs, which retain buffered-only I/O.
		if (m_progress && m_frames.size() % 30 == 0)
			infostream << "Frame benchmark: progress time_us=" << time << std::endl;
	}
	~FrameBenchmark()
	{
		if (!m_output.is_open()) return;
		m_output << "time_us,frame_ms,busy_ms,sleep_ms,draw_cpu_ms,width,height,drawcalls\n" << std::setprecision(10);
		for (const auto &f : m_frames)
			m_output << f.time << ',' << f.elapsed*1000.0 << ',' << f.busy/1000.0 << ','
				<< f.sleep/1000.0 << ',' << f.draw/1000.0 << ',' << f.width << ',' << f.height
				<< ',' << f.drawcalls << '\n';
		m_output.flush();
		if (!m_output) errorstream << "Frame benchmark: failed to write samples" << std::endl;
		else infostream << "Frame benchmark: wrote " << m_frames.size() << " samples" << std::endl;
	}
};
