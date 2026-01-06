#!/usr/bin/env python3

"""
small utility script to extract screenshots from fallout 3 and new vegas saves (will auto detect)
supports PC .fos files and Xbox 360 .fxs saves (based on some ported logic from wxPirs)
thanks to the fallout wiki for documenting fallout 3's format, xbox and new vegas support is my own.

usage: extract.py [PATH_TO_FILE]
"""

import sys
import struct
from pathlib import Path

import os
from typing import List

from PIL import Image

PIPE = 0x7C
MAGIC = b"FO3SAVEGAME"


def read_exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise ValueError(f"Unexpected EOF (wanted {n} bytes, got {len(b)})")
    return b


def read_u32_le(f):
    return struct.unpack("<I", read_exact(f, 4))[0]


def read_u16_le(f):
    return struct.unpack("<H", read_exact(f, 2))[0]


def read_divider(f):
    c = read_exact(f, 1)[0]
    if c != PIPE:
        raise ValueError(f"Expected divider '|' (0x7C), found 0x{c:02X}")



def read_bzstring(f, size):
    if size == 0:
        return ""
    raw = read_exact(f, size)
    return raw.decode("latin-1", errors="replace")


def parse_header(f):
    start_pos = f.tell()
    file_id = read_exact(f, 11)
    if file_id != MAGIC:
        raise ValueError(f"Bad magic: expected {MAGIC!r}, got {file_id!r}")

    save_header_size = read_u32_le(f)
    unknown1 = read_u32_le(f)

    read_divider(f)
    val = read_u32_le(f)
    if val > 16384:
        f.seek(60, os.SEEK_CUR)
        read_divider(f)
        width = read_u32_le(f)
    else:
        width = val

    read_divider(f)
    height = read_u32_le(f)

    read_divider(f)
    save_index = read_u32_le(f)

    read_divider(f)
    pc_name_size = read_u16_le(f)

    read_divider(f)
    pc_name = read_bzstring(f, pc_name_size)

    read_divider(f)
    pc_karma_size = read_u16_le(f)

    read_divider(f)
    pc_karma = read_bzstring(f, pc_karma_size)

    read_divider(f)
    pc_level = read_u32_le(f)

    read_divider(f)
    pc_location_size = read_u16_le(f)

    read_divider(f)
    pc_location = read_bzstring(f, pc_location_size)

    read_divider(f)
    playtime_size = read_u16_le(f)

    read_divider(f)
    playtime = read_bzstring(f, playtime_size)

    screenshot_offset = 4 + save_header_size

    return {
        "width": width,
        "height": height,
        "save_index": save_index,
        "pc_name": pc_name,
        "pc_karma": pc_karma,
        "pc_level": pc_level,
        "pc_location": pc_location,
        "playtime": playtime,
        "unknown1": unknown1,
        "screenshot_offset": screenshot_offset,
        "header_end_pos": f.tell(),
        "header_start_pos": start_pos,
    }

MAGIC_CON  = b"CON "

def read_exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise EOFError(f"Unexpected EOF (wanted %d, got %d)" % (n, len(b)))
    return b

def r_u8(f):     return struct.unpack("<B", read_exact(f, 1))[0]
def r_u16le(f):  return struct.unpack("<H", read_exact(f, 2))[0]
def r_u32le(f):  return struct.unpack("<I", read_exact(f, 4))[0]
def r_i32le(f):  return struct.unpack("<i", read_exact(f, 4))[0]

def read_fixed_str(f, n):
    raw = read_exact(f, n)
    i = raw.find(b"\x00")
    if i != -1:
        raw = raw[:i]
    return raw.decode("utf-8", "replace").strip()

def dos_datetime_from_u32(v):
    d = (v >> 16) & 0xFFFF
    t = v & 0xFFFF
    year  = ((d >> 9) & 0x7F) + 1980
    month = (d >> 5) & 0x0F
    day   = d & 0x1F
    hour  = (t >> 11) & 0x1F
    minute= (t >> 5)  & 0x3F
    sec2  = (t & 0x1F) * 2
    return (year, month, day, hour, minute, sec2)


class PirsEntry:
    __slots__ = ("Filename","Unknow","BlockLen","Cluster","Parent","Size","DateTime1","DateTime2","is_dir")
    def __init__(self): pass

class PirsType2:
    def __init__(self, path):
        self.path = Path(path)
        self.f = self.path.open("rb")
        self.f.seek(0, os.SEEK_END)
        self._pkg_size = self.f.tell()
        self.f.seek(0)
        self.magic = read_exact(self.f, 4)
        if self.magic != MAGIC_CON:
            raise ValueError("Not a CON package")

        self.con_start  = 49152
        self.con_offset = 8192

        self.entries: List[PirsEntry] = self._read_entries()

    def _get_offset(self, cluster):
        num  = self.con_start + cluster * 4096
        n2   = cluster // 170
        n3   = n2 // 170
        if n2 > 0:
            num += (n2 + 1) * self.con_offset
        if n3 > 0:
            num += (n3 + 1) * self.con_offset
        return num

    def _read_entry(self):
        e = PirsEntry()
        e.Filename = read_fixed_str(self.f, 38)
        if e.Filename == "":
            return e
        e.Unknow    = r_i32le(self.f)
        e.BlockLen  = r_i32le(self.f)
        raw_cluster = r_u32le(self.f)
        e.Cluster   = raw_cluster >> 8
        e.Parent    = r_u16le(self.f)
        e.Size      = r_u32le(self.f)
        dt1         = r_u32le(self.f)
        dt2         = r_u32le(self.f)
        e.DateTime1 = dos_datetime_from_u32(dt1)
        e.DateTime2 = dos_datetime_from_u32(dt2)
        
        e.is_dir    = (e.Size == 0 and e.Cluster == 0)
        return e

    def _read_entries(self):
        entries: List[PirsEntry] = []
        idx = 0
        while True:
            self.f.seek(self.con_start + idx * 64)
            e = self._read_entry()
            if e.Filename == "":
                break
            entries.append(e)
            idx += 1
        return entries

    def list(self):
        return self.entries

    def extract_all(self, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        for e in self.entries:
            if e.is_dir:
                continue
            self._extract_entry(e, out_dir / e.Filename)

    def _extract_entry(self, e, dst):
        size = int(e.Size)
        if size <= 0:
            return
        
        start_cluster = int(e.Cluster)
        
        blocks_by_size = size >> 12
        blocks_by_blocklen = max(0, int(getattr(e, "BlockLen", 0)))
        full_blocks = blocks_by_size
        if blocks_by_blocklen:
            full_blocks = min(full_blocks, blocks_by_blocklen)
        
        remainder = size - (full_blocks << 12)
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        with open(dst, "wb") as w:
            last_off = -1
        
            for i in range(full_blocks):
                off = self._get_offset(start_cluster + i)
        
                if off <= last_off:
                    break
                last_off = off
        
                if off >= self._pkg_size:
                    remainder = 0
                    break
                    
                to_read = min(4096, self._pkg_size - off)
                if to_read <= 0:
                    remainder = 0
                    break
                    
                self.f.seek(off)
                w.write(read_exact(self.f, to_read))
                if to_read < 4096:
                    remainder = 0
                    break
                    
            if remainder > 0:
                off = self._get_offset(start_cluster + full_blocks)
                if off < self._pkg_size:
                    to_read = min(remainder, self._pkg_size - off)
                    if to_read > 0:
                        self.f.seek(off)
                        w.write(read_exact(self.f, to_read))


def reorder_channels(buf):
    out = bytearray(len(buf))
    r_i, g_i, b_i = (2, 0, 1)
    for i in range(0, len(buf), 3):
        out[i + 0] = buf[i + r_i]
        out[i + 1] = buf[i + g_i]
        out[i + 2] = buf[i + b_i]
    return bytes(out)


def shift_channel(buf, w, h, channel, shift_px):
    ch_idx = {"r": 0, "g": 1, "b": 2}.get(channel)

    shift = shift_px % w
    if shift == 0:
        return buf

    out = bytearray(buf)
    row_stride = w * 3
    for y in range(h):
        row0 = y * row_stride
        ch_row = out[row0 + ch_idx : row0 + row_stride : 3]
        rotated = ch_row[-shift:] + ch_row[:-shift]
        out[row0 + ch_idx : row0 + row_stride : 3] = rotated
    return bytes(out)


def extract_image(
    save_path: Path,
    out_dir: Path,
):
    with save_path.open("rb") as f:
        meta = parse_header(f)
        w, h = meta["width"], meta["height"]

        print(f"[{save_path.name}] {w}x{h}")

        f.seek(meta["screenshot_offset"])
        expected = w * h * 3
        data = read_exact(f, expected)

        data = reorder_channels(data)

        data = shift_channel(data, w, h, "r", -3)
        data = shift_channel(data, w, h, "g", -4)
        data = shift_channel(data, w, h, "b", -4)

        img = Image.frombytes("RGB", (w, h), data)

        base = f"fo3_{meta['save_index']:03d}_{w}x{h}"
        if meta["pc_name"]:
            base += "_" + "".join(
                ch for ch in meta["pc_name"] if ch.isalnum() or ch in " -_"
            ).strip().replace(" ", "_")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{base}.png"
        img.save(out_path)
        print(f"Saved {out_path}")


def main():
    args = sys.argv[1:]
    out_dir = Path("extracted_images")
    for save_file in args:
        if '.fxs' in save_file.lower():
            p = PirsType2(Path(save_file))
            for e in p.list():
                kind = "DIR " if e.is_dir else "FILE"
                print(f"{kind:4} {e.Size:10}  cl={e.Cluster:6}  {e.Filename}")
            p.extract_all(out_dir)
            save_file = out_dir / 'Savegame.dat'
        extract_image(
            Path(save_file),
            out_dir
        )


if __name__ == "__main__":
    main()