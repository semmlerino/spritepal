# Sprite Pipeline Verification Report

**Date:** January 12, 2026
**Scope:** End-to-end verification of the SpritePal pipeline (Mesen 2 Capture → Import → Edit → Inject).

## Executive Summary

The SpritePal sprite pipeline is **mechanically sound** and **mathematically correct** for its core purpose: handling SNES 4bpp HAL-compressed sprites. The critical bitplane encoding/decoding logic is invertible and verified by new unit tests.

However, three significant risks were identified regarding **data identity** and **implicit assumptions**:
1.  **Identity Gap:** No verification that Mesen 2 captures match the loaded ROM.
2.  **Destructive Import:** Importing RGB PNGs silently destroys palette indices.
3.  **Compression Assumption:** The workflow strictly requires HAL-compressed sprites; raw sprites are not supported.

---

## Detailed Verification by Stage

### 1. Mesen 2 Capture
*   **Source:** `mesen2_integration/lua_scripts/sprite_rom_finder.lua`
*   **Data:** Writes `last_offset.txt` with format `FILE OFFSET: 0xNNNNNN`.
*   **Verification:**
    *   **Pass:** Coordinate mapping (`cpu_to_file_offset`) correctly handles Kirby Super Star's SA-1 LoROM mapping (Banks `C0-FF` → File Offset).
    *   **Risk:** The output **lacks ROM identity** (Checksum/Title). A capture from "Game A" will be blindly accepted by SpritePal even if "Game B" is loaded, leading to garbage data display.

### 2. Import Logic
*   **Source:** `core/mesen_integration/log_watcher.py`
*   **Data:** Parses hex string from log/text file.
*   **Verification:**
    *   **Pass:** Robust regex parsing and directory watching.
    *   **Risk:** No validation of offset bounds against the currently loaded ROM size until attempted use.

### 3. Asset Browser & Extraction
*   **Source:** `core/rom_extractor.py`
*   **Assumption:** Strictly assumes **HAL Compression**.
*   **Verification:**
    *   Calls `HALCompressor.decompress_from_rom()`.
    *   **Limit:** If decompression fails (e.g., raw sprite, different compression), the operation fails. There is no fallback for uncompressed data.

### 4. Bitplane Integrity (Edit Round-Trip)
*   **Source:** `core/tile_utils.py` (Decode) ↔ `core/injector.py` (Encode)
*   **Verification:**
    *   **Pass:** Logic is mathematically invertible.
    *   `decode_4bpp_tile` and `encode_4bpp_tile` correctly map between SNES planar format (bitplanes 0/1 at bytes 0-15, 2/3 at 16-31) and packed pixel indices.
    *   **Evidence:** Verified by `tests/unit/test_bitplane_integrity.py` (random noise + pattern tests).

### 5. Injection
*   **Source:** `core/rom_injector.py`
*   **Verification:**
    *   **Pass:** ROM Checksum is correctly recalculated and updated.
    *   **Pass:** Slack space detection prevents overwriting valid data unless explicitly forced.

### 6. External Import Risk (Critical)
*   **Source:** `core/injector.py` -> `convert_png_to_4bpp`
*   **Risk:**
    *   When importing a standard RGB PNG (not Indexed/Grayscale), the system **converts to Grayscale (`L`)** and divides by 17 to map 0-255 to 0-15.
    *   **Impact:** This destroys the original palette indices. A red pixel (Index 3) and a blue pixel (Index 3) will become the same grayscale value, making it impossible to restore the correct colors later.
    *   **Mitigation:** Users *must* use Indexed (Palette-based) PNGs to preserve exact indices.

## Actionable Recommendations

1.  **Fix Identity Gap:** Update Lua script to output ROM Checksum; update `LogWatcher` to parse it; add UI warning on mismatch.
2.  **Import Safety:** Add a strict mode or warning when importing non-indexed PNGs, explaining that color data will be lost.
3.  **Raw Support:** If non-HAL games are targeted in the future, `ROMExtractor` needs a fallback strategy for uncompressed tiles.
