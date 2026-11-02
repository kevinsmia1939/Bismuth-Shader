#!/usr/bin/env python3
"""Write original, constant ORM data maps; no albedo assets or dependencies."""
# SPDX-License-Identifier: LGPL-2.1-or-later
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
MAPS = {
    'default_stone': (230, 0),
    'default_cobble': (240, 0),
    'default_steel_block': (107, 255),
    'default_gold_block': (87, 255),
    'default_copper_block': (122, 255),
    'default_meselamp': (217, 0),
    'default_mese_block': (204, 0),
}


def png(roughness, metallic):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes((0, 255, roughness, metallic, 255)))) + chunk(b'IEND', b''))


if __name__ == '__main__':
    target = ROOT / 'textures/bismuth-minetest-game'
    target.mkdir(parents=True, exist_ok=True)
    for name, (roughness, metallic) in MAPS.items():
        (target / (name + '_orm.png')).write_bytes(png(roughness, metallic))
    print(f'Wrote {len(MAPS)} ORM companions to {target}')
