# Poppy Bros Sprite Attribution Investigation

## Problem Statement

**Symptom:** The `sprite_rom_finder.lua` script correctly identifies sprite ROM offsets on Level 1 (e.g., Waddle Dee), but returns **wrong FILE offsets** for Poppy Bros Jr and Sr on Level 2.

**Observed behavior:**
- `idx=(unmatched)` displayed for Poppy Bros sprites
- FILE offsets like `0x2CC016` and `0x26377C` point to wrong sprite data
- Level 1 sprites work correctly

---

## Resolution Summary (v43)

**STATUS: NOW WITH VERIFICATION** (2026-01-15)

Multiple bugs were fixed across v38-v43:

1. **Direct ROM DMAs (v38)**: Poppy Bros sprites are DMA'd directly from ROM banks (ED/EE/EF) to VRAM, bypassing the staging buffer
2. **DMA callbacks registered too late (v38)**: Callbacks were registered at frame 2800, missing level-load DMAs
3. **`vram_words` not populated (v38)**: Fast-path in `map_dma_vram_words()` skipped populating `entry.vram_words`
4. **Click handler ignored `file_offset` (v38)**: Only checked `owner.idx`, missing direct ROM DMAs
5. **Tile address calculation (v39)**: Column overflow wasn't carrying into row in multi-tile sprites
6. **Stale staging attribution during WRITE (v40)**: Old idx attributions persisted when staging buffer was reused
7. **Stale staging attribution during READ (v41)**: DMA handler was applying attributions >1000 frames old
8. **Aggressive staging clear (v42)**: v40's 1000-frame window was too permissive - now ALWAYS clears when no session matches
9. **Callback double-registration (v43)**: Callbacks were registered at script start AND in `activate_tracking()`, causing duplicate processing
10. **Byte-compare verification (v43)**: New "VERIFY" step compares VRAM tile bytes against ROM bytes at reported offset

**New in v43 - Byte-Compare Verification:**
When clicking a sprite, the log now shows:
```
VERIFY: ✓ MATCH (32/32 bytes = 100%)
        Attribution is CORRECT - VRAM matches ROM
```
OR:
```
VERIFY: ✗ MISMATCH (5/32 bytes = 15%)
        First mismatch at byte 0
        VRAM: 00 00 FF FF 00 00 FF FF ...
        ROM:  12 34 56 78 9A BC DE F0 ...
        Attribution may be WRONG - investigate offset
```

This provides **deterministic proof** of attribution correctness without manual hex-editor verification.

**Known working reference:**
- Waddle Dee (Level 1): `0x25AD84` (bank E5) - **CONFIRMED CORRECT**

---

## Investigation Timeline

### Hypothesis 1: SA-1 Bank Register Changes (REJECTED)

**Theory:** The SA-1 chip uses bank registers ($2220-$2223) to remap ROM banks C0-FF. Level 1 works because it uses power-on defaults, but Level 2 changes these registers.

**Bank Register Details:**
- `$2220` (CXB) - Controls C0-CF bank mapping (default: 0)
- `$2221` (DXB) - Controls D0-DF bank mapping (default: 1)
- `$2222` (EXB) - Controls E0-EF bank mapping (default: 2)
- `$2223` (FXB) - Controls F0-FF bank mapping (default: 3)

**Result:** After fixing all issues, bank register log showed only power-on defaults:
```
[Bank] frame=1 $002220 <- 0x00 (CXB)
[Bank] frame=1 $002221 <- 0x01 (DXB)
[Bank] frame=1 $002222 <- 0x02 (EXB)
[Bank] frame=1 $002223 <- 0x03 (FXB)
```

**Conclusion:** Bank registers stay at power-on defaults throughout gameplay. **NOT the root cause.**

---

### Hypothesis 2: Staging Buffer Range (PARTIALLY CORRECT)

**Theory:** Kirby Super Star uses two staging buffers, and we were only tracking one.

**Staging Buffer Ranges:**
| Range | Purpose | VRAM Destination |
|-------|---------|------------------|
| `$7E2000-$7E2FFF` | Staging buffer 1 | VRAM $4xxx/$5xxx |
| `$7F8000-$7FFFFF` | Staging buffer 2 | VRAM $6xxx |

**Fix implemented:** Added `STAGING2_START` and `STAGING2_END` constants, extended callbacks.

**Conclusion:** Staging buffer tracking works, but **Poppy Bros don't use staging buffers at all** - they're DMA'd directly from ROM.

---

### Hypothesis 3: Wrong Pointer Being Captured (PARTIALLY CORRECT)

**Theory:** The DP pointer we capture (`E6:377C`) is NOT the graphics pointer.

This was correct for staging-based sprites, leading to FE52 table hook implementation. But Poppy Bros use a **completely different data path**.

---

### Hypothesis 4: Direct ROM DMA (ROOT CAUSE - FIXED)

**Discovery:** Poppy Bros sprites are DMA'd **directly from ROM to VRAM**, bypassing the staging buffer entirely.

**Evidence from log:**
```
DBG DIRECT_ROM: src=EE9D00 file=0x2E9D00 vram=$60C0
DBG DIRECT_ROM: src=ED5DC0 file=0x2D5DC0 vram=$6000
DBG DIRECT_ROM: src=EF2820 file=0x2F2820 vram=$61D0
```

**Data flow for Poppy Bros:**
```
ROM (ED/EE/EF banks) ──DMA──> VRAM $6xxx
       ↑
   No staging buffer!
   No FE52 table lookup!
```

**Why this differs from Level 1 sprites:**
- Level 1 (Waddle Dee): ROM → Decompress → Staging → VRAM (uses FE52 table)
- Level 2 (Poppy Bros): ROM → VRAM directly (pre-rendered, no decompression)

---

## Bugs Fixed (v38)

### Bug 1: DMA Callbacks Registered Too Late

**Problem:** DMA callbacks were registered inside `activate_tracking()` which ran at frame 2800. Level-load DMAs happened earlier.

**Fix:** Register DMA callbacks at script start (frame 0):
```lua
-- v38 FIX: Register DMA-related callbacks at script start
emu.addMemoryCallback(on_dma_enable, emu.callbackType.write, DMA_ENABLE_REG, ...)
emu.addMemoryCallback(on_vram_addr_write, emu.callbackType.write, 0x2116, 0x2117, ...)
emu.addMemoryCallback(on_vmain_write, emu.callbackType.write, 0x2115, ...)
emu.addMemoryCallback(on_dma_reg_write, emu.callbackType.write, 0x4300, 0x437F, ...)
```

### Bug 2: `vram_words` Not Populated in Fast-Path

**Problem:** `map_dma_vram_words()` had a fast-path for `vram_remap_mode == 0 and inc == 1` that didn't populate `entry.vram_words`. Then `write_vram_attribution()` did nothing:

```lua
local words = entry.vram_words
if words then  -- This was nil in fast-path!
    for _, w in ipairs(words) do
        vram_owner_map[w] = { ... }
    end
end
```

**Fix:** Always populate `entry.vram_words`:
```lua
if vram_remap_mode == 0 and inc == 1 then
    entry.vram_words = {}  -- v38 FIX: Added this
    for w = entry.vram_start, entry.vram_end - 1 do
        vram_upload_map[w] = entry
        entry.vram_words[#entry.vram_words + 1] = w  -- v38 FIX: Added this
    end
    return entry.vram_logical_end
end
```

### Bug 3: Click Handler Ignored `file_offset`

**Problem:** Click handler only checked `owner.idx`, ignoring `owner.file_offset`:
```lua
if owner and owner.idx then  -- Direct ROM has file_offset but no idx!
```

**Fix:** Check both:
```lua
if owner and (owner.idx or owner.file_offset) then
```

### Bug 4: Direct ROM Attribution Not Implemented

**Problem:** Non-staging DMAs with source in ROM bank range (C0-FF) weren't attributed.

**Fix:** Added direct ROM attribution path:
```lua
else
    -- v38 FIX: Direct ROM→VRAM DMA (no staging buffer)
    local src_bank = (src_addr >> 16) & 0xFF
    if src_bank >= 0xC0 and src_bank <= 0xFF then
        session_ptr = src_addr
        file_off = cpu_to_file_offset(src_addr)
        session_idx = ptr_to_idx[src_addr]  -- Usually nil for direct ROM
        attrib_mode = "direct_rom"
    end
end
```

---

## Current Implementation State (v38)

### Files Modified
- `mesen2_integration/lua_scripts/sprite_rom_finder.lua`

### What's Working
- ✅ SA-1 bank register shadow tracking
- ✅ Staging buffer 1 tracking ($7E2xxx)
- ✅ Staging buffer 2 tracking ($7F8xxx)
- ✅ FE52 table hook for staged graphics
- ✅ FE52 session priority over DP sessions
- ✅ Direct ROM→VRAM DMA attribution
- ✅ DMA callbacks registered at frame 0
- ✅ `vram_words` populated in all code paths
- ✅ Click handler checks `file_offset`

### Expected Results
| Sprite Type | Attribution Method | Confirmed FILE Offset |
|-------------|-------------------|----------------------|
| Waddle Dee (Level 1) | FE52 table → staging | `0x25AD84` (bank E5) - **CONFIRMED** |
| Poppy Bros Jr/Sr | Direct ROM DMA | **NEEDS VERIFICATION** |
| Kirby | FE52 table → staging | **NEEDS VERIFICATION** |

**Note:** Graphics are NOT limited to bank E9. Different sprites use different ROM banks.

---

## Technical Reference

### Two Data Paths for Sprites

**Path A: Staged/Compressed (FE52 Table)**
```
FE52 Table Read → idx known
       ↓
DP Pointer Load → ptr known (E9:xxxx)
       ↓
Decompress to Staging ($7E2xxx or $7F8xxx)
       ↓
DMA Staging → VRAM
       ↓
Attribution: idx + ptr + file_offset
```

**Path B: Direct ROM (No Staging)**
```
DMA ROM → VRAM directly
       ↓
Source address IS the file pointer (ED/EE/EF:xxxx)
       ↓
Attribution: file_offset only (no idx)
```

### Address Conversion (SA-1 Default Mapping)

For banks E0-EF with default EXB=0x02:
```
File offset = (bank_reg * 0x100000) + ((bank - bank_base) * 0x10000) + addr
           = (0x02 * 0x100000) + ((bank - 0xE0) * 0x10000) + addr
           = 0x200000 + ((bank - 0xE0) * 0x10000) + addr
```

Examples:
- `E5:AD84` → `0x200000 + 0x50000 + 0xAD84` = `0x25AD84` (Waddle Dee - **CONFIRMED**)
- `EE:9D00` → `0x200000 + 0xE0000 + 0x9D00` = `0x2E9D00`
- `ED:5DC0` → `0x200000 + 0xD0000 + 0x5DC0` = `0x2D5DC0`

### Key Parameters (v38)

```lua
SESSION_MATCH_WINDOW = 1000   -- Frames to look back for session attribution
RECENT_SESSIONS_MAX = 128     -- Max sessions to keep in history
CLICK_SESSION_WINDOW = 1000   -- Override window for click attribution
```

---

## Log File Location

`mesen2_exchange/sprite_rom_finder.log`

**Key patterns to grep:**
```bash
grep "DIRECT_ROM" sprite_rom_finder.log   # Direct ROM DMAs (v38)
grep "FE52" sprite_rom_finder.log         # FE52 table reads
grep "staging_map" sprite_rom_finder.log  # Staging attribution
grep "idx=" sprite_rom_finder.log         # Session idx values
grep "Selected:" sprite_rom_finder.log    # Click results
```

---

## v43 FIX: Callback Double-Registration + Byte-Compare Verification (2026-01-15)

**Issue 1: Callback Double-Registration**

Callbacks were being registered TWICE:
1. At script start (frame 0) - correct location
2. In `activate_tracking()` (frame 2800) - duplicate!

This caused every DMA, VRAM write, FE52 read, etc. to be processed twice, pushing duplicate entries into maps and making attribution noisier and harder to trust.

**The bug:** Multiple `emu.addMemoryCallback()` calls for the same handlers:
- FE52 table reads: registered with `"snes_early"`/`"sa1_early"` AND `"snes"`/`"sa1"`
- DMA enable, VRAM addr, VMAIN, DMA regs: registered with `"_early"` suffix AND without

**The fix:**
- Consolidated ALL callback registrations at script start (frame 0)
- Removed duplicate registrations from `activate_tracking()`
- Added DP writes and OBSEL to script start (previously only in activate_tracking)

**Issue 2: No Verification Step**

Attribution logic was "plausible" but never proven. The user asked: "If I click Poppy Bros and get offset 0x2E9D00, how do I KNOW that's correct?"

**The fix:** Added `verify_tile_bytes()` function that:
1. Reads 32 bytes from VRAM at the clicked tile address
2. Reads 32 bytes from ROM at the reported file offset
3. Compares them byte-by-byte
4. Reports match percentage and first mismatch location

This provides **deterministic proof** rather than inference from logs.

---

## v42 FIX: Aggressive Staging Attribution Clear (2026-01-15)

**ROOT CAUSE:** The v40 fix's SESSION_MATCH_WINDOW (1000 frames) was too permissive. Attributions 470 frames old were still being applied.

**The bug:**
```lua
-- v40: Only cleared if older than 1000 frames
if existing and (frame_count - existing.frame) > SESSION_MATCH_WINDOW then
    staging_owner_map[chunk_idx] = nil
end
```

In the log, idx=43 attribution from frame 2605 was applied at frame 3075 (470 frames later) because 470 < 1000.

**The fix (v42):**
```lua
-- v42: ALWAYS clear when no session matches - data has changed regardless of age
if existing then
    staging_owner_map[chunk_idx] = nil
end
```

**Rationale:** If new data is being written to a staging chunk and no FE52/DP session matches, the old attribution is invalid. The fact that there's a write means the chunk's contents are changing, so any previous attribution is stale by definition.

---

## v41 FIX: Stale Attribution During DMA Read (2026-01-15)

**ADDITIONAL ROOT CAUSE:** The v40 fix only cleared stale attributions during staging buffer WRITES. But during DMA READS from staging to VRAM, stale attributions were still applied.

**The bug timeline:**
1. Frame 2605: idx=43 session, staging chunk attributed with `staging_owner_map[chunk] = {idx=43, frame=2605}`
2. Frame 2700+: No new WRITE to that staging chunk, so v40 fix never clears it
3. Frame 3076: DMA reads from staging to VRAM $7xxx
4. DMA handler checks `staging_owner_map[chunk]` - finds stale idx=43 entry (471 frames old!)
5. Stale attribution applied to VRAM $7xxx → Poppy Bros wrongly gets idx=43

**Why v40 was incomplete:**
- v40 cleared stale entries only when `track_staging_write()` was called with no matching session
- But if no WRITE happens to a staging chunk, the stale entry persists indefinitely
- During DMA READ, the old entry was used without checking its age

**The fix (v41):**
```lua
-- In DMA handler, BEFORE using staging attribution:
if owner and (frame_count - owner.frame) > SESSION_MATCH_WINDOW then
    owner = nil  -- Treat as no attribution
    staging_owner_map[chunk_idx] = nil  -- Also clear the stale entry
end
```

**Effect:** DMAs from staging buffer now reject attributions older than SESSION_MATCH_WINDOW (1000 frames), falling back to direct ROM attribution or "unresolved" instead of applying ancient idx values.

---

## v40 FIX: Stale Staging Attribution Bug (2026-01-15)

**ROOT CAUSE IDENTIFIED:** The `staging_owner_map` was retaining old attributions indefinitely, even when the staging buffer was reused for different sprite data.

**The bug timeline:**
1. Frame 2605: FE52 table read for idx=43 (Kirby sprites), staging chunk attributed
2. Staging buffer fills with idx=43 data, DMAs to VRAM $4xxx-$5xxx
3. Frame 3076: Different sprite data written to SAME staging chunk
4. No matching session found → OLD idx=43 attribution persists!
5. DMA from staging buffer to VRAM $7xxx gets attributed to idx=43 (WRONG)

**The bug code:**
```lua
local sess = match_recent_session()
if sess then
    staging_owner_map[chunk_idx] = { idx = sess.idx, ... }
end
-- BUG: If sess is nil, OLD attribution from frame 2605 persists!
```

**The fix (v40):**
```lua
if sess then
    staging_owner_map[chunk_idx] = { ... }
else
    -- Clear stale attributions when no session matches
    if existing and (frame_count - existing.frame) > SESSION_MATCH_WINDOW then
        staging_owner_map[chunk_idx] = nil
    end
end
```

**Why this caused "Poppy Bros → Kirby" misattribution:**
- Kirby sprites (idx=43) were loaded at level start
- Staging buffer chunks were attributed to idx=43
- Poppy Bros data reused the same staging buffer regions later
- Without a matching session, the old idx=43 attribution persisted
- Poppy Bros VRAM got attributed to idx=43 (Kirby's ROM offset)

---

## v39 FIX: Tile Address Calculation Bug (2026-01-15)

**ROOT CAUSE IDENTIFIED:** The tile address calculation in `get_sprite_vram_word_at_point()` had a bug where column overflow didn't carry into the row.

**The bug:**
```lua
-- BUGGY (v38 and earlier):
local base_row = (spr.tile_index >> 4) & 0x0F
local base_col = spr.tile_index & 0x0F
local row = (base_row + tile_y) & 0x0F
local col = (base_col + tile_x) & 0x0F  -- BUG: wraps independently!
local tile_index = row * 16 + col
```

**Example of failure:**
- Base tile 0x1F (row=1, col=15)
- Click one tile to the right (tile_x=1)
- **Buggy result:** col = (15 + 1) & 0x0F = 0, tile_index = 1*16 + 0 = **0x10** (WRONG)
- **Correct result:** tile_index = 0x1F + 1 = **0x20**

This made the script sample from completely wrong VRAM addresses, often landing on Kirby/HUD data instead of the clicked enemy sprite.

**The fix (v39):**
```lua
-- FIXED: Linear 16-wide addition with proper carry
local tile_index = (spr.tile_index + tile_y * 16 + tile_x) & 0xFF
```

**Why the old explanations were wrong:**
- "VRAM sharing" - If Kirby's data overwrote Poppy's VRAM, Poppy would *look* like Kirby on screen
- "Timing issue" - The per-word `vram_owner_map` tracking would still give correct attribution
- "ENEMY SCORE" extraction - This was sampling the wrong tile address, not evidence of VRAM mixing

**Expected behavior after fix:**
- Clicking Poppy Bros should now sample the correct VRAM words
- DMA attribution should point to either:
  - Staging buffer (7F8xxx) → Poppy uses FE52 table path (like Waddle Dee)
  - ROM banks ED/EE/EF → Direct ROM path, and offsets should decode as Poppy sprites

---

## Lessons Learned

1. **Not all sprites use the same data path** - Compressed sprites go through staging, pre-rendered sprites DMA directly from ROM
2. **Callback registration timing matters** - Register at script start, not after delayed activation
3. **Fast-paths can introduce bugs** - Optimized code paths must maintain the same invariants
4. **Check all attribution fields** - `idx` and `file_offset` serve different purposes; both are valid attribution
5. **Debug logging is essential** - The `DBG DIRECT_ROM:` logging revealed the working code path that wasn't persisting data
6. **Don't assume ROM bank layout** - Graphics are spread across multiple banks (E5, ED, EE, EF, etc.), not concentrated in one "graphics bank"
7. **Verify with known-good values** - Always cross-check against confirmed working offsets (e.g., Waddle Dee at 0x25AD84)
8. **Tile address math must handle overflow** - Column overflow into row is critical for multi-tile sprites
9. **Bootstrap offsets are seeds, not truth** - The 0x1A0000 "enemy sprites" in docs is just a database seed; Waddle Dee at 0x25AD84 (E5:AD84) proves sprites are spread across ROM
