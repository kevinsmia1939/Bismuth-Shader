"""Resize only the disposable client's own SDL window on its render thread.

No keyboard, pointer, focus, screenshot or input-device APIs are used. The small
test hook is built into the output directory and loaded only by that client.
"""
# SPDX-License-Identifier: LGPL-2.1-or-later
import hashlib
from pathlib import Path
import subprocess


class TestWindowResize:
    def __init__(self, output):
        self.pid = None
        self.sequence = 0
        self.request = output/'resize-request.txt'
        self.library = output/'resize-test-client.so'
        source = Path(__file__).with_name('resize_test_client.c')
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(source), '-o', str(self.library), '-ldl'], check=True)
        self.source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        self.library_sha256 = hashlib.sha256(self.library.read_bytes()).hexdigest()

    def configure(self, environment):
        environment['BISMUTH_RESIZE_REQUEST'] = str(self.request)
        previous = environment.get('LD_PRELOAD', '')
        environment['LD_PRELOAD'] = str(self.library) + (':'+previous if previous else '')

    def resize(self, width, height):
        assert self.pid is not None
        self.sequence += 1
        temporary = self.request.with_suffix('.tmp')
        temporary.write_text(f'{self.sequence} {width} {height}\n')
        temporary.replace(self.request)
        return {'pid': self.pid, 'sequence': self.sequence, 'width': width, 'height': height}

    def close(self):
        pass
