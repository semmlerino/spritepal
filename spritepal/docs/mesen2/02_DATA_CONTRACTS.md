# 02 Data Contracts

This document defines the **canonical schema** for capture and mapping data.

## sprite_capture*.json

### Top-Level
- `frame` (int): capture frame counter used by the script
- `timestamp` (int, optional): Unix timestamp
- `visible_count` (int)
- `obsel` (object, required)
- `entries` (array, required)
- `palettes` (object, required)

### obsel
- `raw` (int): raw $2101 value
- `name_base` (int)
- `name_select` (int)
- `size_select` (int)
- `tile_base_addr` (int, **byte address** for VRAM reads)
- `oam_base_addr` (int, **word address** used in PPU math)
- `oam_addr_offset` (int, **word address** used in PPU math)
- Invariants (byte/word conversion):
  - `tile_base_addr == oam_base_addr * 2`
  - `oam_offset_bytes == oam_addr_offset * 2` (derive when needed)

### entries[]
- `id` (int)
- `x` (int), `y` (int)
- `tile` (int): OAM tile index (0-255)
- `width` (int), `height` (int)
- `palette` (int)
- `priority` (int)
- `flip_h` (bool), `flip_v` (bool)
- `tile_page` (int, optional): OAM attr bit 0 (tile index bit 8 / second table)
- `name_table` (int, legacy): same as `tile_page` for backward compatibility
- `tiles` (array, required)

### tiles[]
- `tile_index` (int): **per-subtile** index (0-255) after row/column wrap
- `vram_addr` (int, **byte address**)
- `pos_x` (int), `pos_y` (int)
- `data_hex` (string): **exactly 64 hex chars** (32 bytes), uppercase, no separators

### palettes
- Keys: strings "0".."7"
- Values: arrays of 16 ints, **15-bit BGR** words, little-endian `lo | (hi << 8)`

## Validation / Fail-Fast Rules
- `data_hex` length must be 64 hex chars (32 bytes) for 4bpp.
- If **all odd bytes are zero** across captured tiles, abort the capture. This indicates a
  bad VRAM read path and guarantees hash mismatches.
- If tiles are not 32 bytes, do not hash them.

## Naming Conventions
- Prefer `tile_page` over `name_table`. Treat `name_table` as legacy input only.
- Use `*_addr` units consistently:
  - `*_addr` in **bytes** unless explicitly marked as word address.

## Tile Hash Contract (4bpp)
- Tile size: **32 bytes** (4bpp). Sprites (OBJ) are always 4bpp; other bpp modes apply to BG tiles.
- Hash algorithm: **MD5** over raw 32-byte tile data.
- Flip normalization: optional lookup mode that tests **N/H/V/HV** variants; candidates are
  de-duplicated by `(rom_offset, tile_index)`. Default mapping uses **unflipped** tiles
  because OAM flip bits are applied at render time.
- Low-information tiles may be ignored during scoring (**<= 2 unique byte values**).

## Mapper Output (CaptureMapResult)
These fields are produced by `CaptureToROMMapper.map_capture()` for diagnostics and scoring.
- `matched_tiles`: tiles with any hash hits (including low-info tiles)
- `scored_tiles`: tiles that contributed positive weight to scoring
- `ignored_low_info_tiles`: tiles ignored due to low-information heuristic

## tile_hash_database.json
Database files include metadata to guard against ROM/header mismatches.
- `metadata.rom_title` (string | null)
- `metadata.rom_checksum` (int | null)
- `metadata.rom_size` (int)
- `metadata.rom_header_offset` (int): 0 or 512 (SMC header)
