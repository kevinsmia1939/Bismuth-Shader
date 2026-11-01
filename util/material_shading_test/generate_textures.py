"""Generate exact byte-valued material test data, not preview images."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import struct
import sys
import zlib
from pathlib import Path


def main():
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)

    def png(name, height, pixel):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        data = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(16)) for y in range(height))
        payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, height, 8, 6, 0, 0, 0))
        payload += chunk(b"IDAT", zlib.compress(data)) + chunk(b"IEND", b"")
        (target / name).write_bytes(payload)

    png("material_test_base.png", 16, lambda x, y: (190, 100, 35, 255))
    png("material_test_cutout.png", 16, lambda x, y: (190, 100, 35, 255 if (x // 2 + y // 2) % 2 else 0))
    png("material_test_normal.png", 16, lambda x, y: (180 if x % 4 < 2 else 76, 128, 244, 255))
    png("material_test_rough.png", 16, lambda x, y: (255, 220, 0, 255))
    png("material_test_metal.png", 16, lambda x, y: (255, 50, 255, 255))
    png("material_test_auto.png", 16, lambda x, y: (100, 180, 210, 255))
    png("material_test_auto_normal.png", 16, lambda x, y: (128, 175 if y % 4 < 2 else 81, 246, 255))
    png("material_test_auto_orm.png", 16, lambda x, y: (190, 130, 128, 255))
    png("material_test_animated.png", 32, lambda x, y: (190, 100, 35, 255) if y < 16 else (50, 130, 210, 255))
    png("material_test_animated_normal.png", 32, lambda x, y: (128, 128, 255, 255) if y < 16 else (190, 128, 239, 255))
    png("material_test_animated_orm.png", 32, lambda x, y: (255, 220, 0, 255) if y < 16 else (255, 50, 255, 255))


if __name__ == "__main__":
    main()
