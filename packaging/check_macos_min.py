"""Controlla che nessun file eseguibile di un'app per Mac richieda un macOS più recente di --max.

Uso: python packaging/check_macos_min.py "dist/Stem Splitter.app" --max 10.13

Legge l'intestazione Mach-O (LC_BUILD_VERSION / LC_VERSION_MIN_MACOSX) di ogni libreria ed
eseguibile x86_64 del pacchetto. Le funzioni più recenti collegate in modo "debole" non contano:
su un macOS più vecchio vengono semplicemente saltate.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

LC_VERSION_MIN_MACOSX, LC_BUILD_VERSION = 0x24, 0x32
CPU_X86_64, CPU_ARM64 = 0x01000007, 0x0100000C


def _min_version(data: bytes, cpu: int) -> tuple[int, int] | None:
    if len(data) < 32:
        return None
    if struct.unpack_from(">I", data)[0] == 0xCAFEBABE:  # file "fat" con più architetture
        for i in range(struct.unpack_from(">I", data, 4)[0]):
            c, _, off, size, _ = struct.unpack_from(">iiIII", data, 8 + i * 20)
            if c == cpu:
                return _min_version(data[off:off + size], cpu)
        return None
    if struct.unpack_from("<I", data)[0] != 0xFEEDFACF:
        return None
    if struct.unpack_from("<i", data, 4)[0] != cpu:
        return None
    ncmds, off = struct.unpack_from("<I", data, 16)[0], 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd in (LC_VERSION_MIN_MACOSX, LC_BUILD_VERSION):
            v = struct.unpack_from("<I", data, off + (8 if cmd == LC_VERSION_MIN_MACOSX else 12))[0]
            return v >> 16, (v >> 8) & 0xFF
        off += size
    return 0, 0  # nessuna indicazione: nessun vincolo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("app")
    ap.add_argument("--max", default="10.13", help="versione di macOS più vecchia da supportare")
    ap.add_argument("--arch", default="x86_64", choices=["x86_64", "arm64"])
    args = ap.parse_args()
    limit = tuple(int(x) for x in args.max.split("."))
    cpu = CPU_X86_64 if args.arch == "x86_64" else CPU_ARM64
    checked, too_new = 0, []
    for f in Path(args.app).rglob("*"):
        if not f.is_file() or f.is_symlink() or f.stat().st_size < 4096:
            continue
        with open(f, "rb") as fh:
            head = fh.read(4)
        if head not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            continue
        v = _min_version(f.read_bytes(), cpu)
        if v is None:
            continue
        checked += 1
        if v > limit:
            too_new.append((v, f))
    print(f"{checked} file Mach-O {args.arch} controllati (limite macOS {args.max})")
    for v, f in sorted(too_new, reverse=True):
        print(f"  ✗ richiede macOS {v[0]}.{v[1]}: {f}")
    if too_new:
        return 1
    print("  ✓ tutti compatibili")
    return 0


if __name__ == "__main__":
    sys.exit(main())
