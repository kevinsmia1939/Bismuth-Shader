#!/usr/bin/env python3
"""Require rendered client coverage for every scripted material state."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import json
from pathlib import Path
import re
import sys


def audit(text):
    stages = []
    current = None
    for line in text.splitlines():
        if 'Material stage: {' in line:
            current = json.loads(line.split('Material stage: ', 1)[1])
            current['completed_frame_checkpoints'] = 0
            stages.append(current)
        match = re.search(r'Frame benchmark: progress time_us=(\d+)', line)
        if current and match and int(match[1]) > current['time_us'] + 500000:
            current['completed_frame_checkpoints'] += 1
    assert stages and stages[0]['name'] == 'baseline', 'Missing baseline stage'
    assert stages[-1]['name'] == 'unmapped replacement', 'Missing final fallback stage'
    assert [s['index'] for s in stages] == list(range(1, len(stages) + 1)), 'Incomplete material stages'
    for stage in stages:
        assert stage['completed_frame_checkpoints'] >= 2, f'Insufficient rendered coverage: {stage}'
    assert 'Irrlicht: Quit SDL' in text, 'Missing clean client shutdown'
    for error in ('ERROR[', 'GL_INVALID', 'failed to generate shaders'):
        assert error not in text, error
    return stages


if __name__ == '__main__':
    for name in sys.argv[1:]:
        stages = audit(Path(name).read_text())
        print(f'PASS: {len(stages)} material stages, each with at least two completed client frame checkpoints: {name}')
