# Mesen2 Sprite Extraction Pipeline: Action Plan

> **Purpose:** Actionable guidance for implementing fixes and improvements to the Kirby Super Star sprite extraction pipeline.
> **Context:** Based on critical review of documentation identifying contradictions, gaps, and unverified assumptions.

---

## Critical Context

The pipeline assumes SA-1 character conversion explains why ROM bytes don't match VRAM bytes (1.5% hash match rate). **This hypothesis is unverified.** All work depends on confirming or falsifying this assumption first.

**Do not proceed to later phases until Phase 1 is complete and signed off.**

---

## Phase 1: Confirm or Falsify SA-1 Hypothesis

**Status:** BLOCKING  
**Priority:** Must complete before any other work

### Why This Matters

If SA-1 conversion is NOT active, Strategy A (VRAM-based DB with timing correlation) may be fundamentally wrong. Alternative causes for the 1.5% match rate include:
- Post-decompression palette remapping
- Runtime tile composition from multiple sources
- Different compression variant than assumed HAL format
- Interlaced plane storage

### Task 1.1: Create $2230/$2231 Register Logger

Create a Lua script that logs SA-1 character conversion control registers.

```lua
-- File: scripts/sa1_conversion_logger.lua
-- Purpose: Log $2230 (DCNT) and $2231 (CDMA) every frame during gameplay

local log_file = io.open("sa1_conversion_log.txt", "w")
local frame_count = 0

function log_sa1_registers()
    frame_count = frame_count + 1
    
    -- Read SA-1 control registers
    -- $2230 = DCNT (DMA control)
    -- $2231 = CDMA (Character conversion DMA)
    local dcnt = emu.read(0x2230, emu.memType.cpuMemory)
    local cdma = emu.read(0x2231, emu.memType.cpuMemory)
    
    -- Check character conversion mode bit
    local conversion_active = (cdma & 0x80) ~= 0
    
    log_file:write(string.format(
        "Frame %d: DCNT=0x%02X CDMA=0x%02X Conversion=%s\n",
        frame_count, dcnt, cdma, conversion_active and "ACTIVE" or "inactive"
    ))
    
    -- Flush periodically
    if frame_count % 60 == 0 then
        log_file:flush()
    end
end

emu.addEventCallback(log_sa1_registers, emu.eventType.endFrame)

-- Cleanup on script end
emu.addEventCallback(function()
    log_file:close()
end, emu.eventType.scriptEnded)
```

**Expected output:** Log file showing register state during sprite-heavy gameplay scenes.

**Success criteria:**
- If conversion bit consistently SET during sprite loads → Hypothesis CONFIRMED
- If conversion bit consistently NOT SET → Hypothesis FALSIFIED
- If conversion bit toggles → PARTIAL conversion, document which sprite types trigger it

### Task 1.2: Log SA-1 DMA Parameters (If API Allows)

Extend the logger to capture DMA source/destination/length at conversion start.

```lua
-- Additional logging for DMA parameters
-- SDAL/SDAH/SDAB = Source address
-- DDL/DDH/DDB = Destination address

function log_dma_parameters()
    -- Source address (24-bit)
    local sdal = emu.read(0x2232, emu.memType.cpuMemory)
    local sdah = emu.read(0x2233, emu.memType.cpuMemory)
    local sdab = emu.read(0x2234, emu.memType.cpuMemory)
    local source_addr = sdal | (sdah << 8) | (sdab << 16)
    
    -- Destination address
    local ddl = emu.read(0x2235, emu.memType.cpuMemory)
    local ddh = emu.read(0x2236, emu.memType.cpuMemory)
    local ddb = emu.read(0x2237, emu.memType.cpuMemory)
    local dest_addr = ddl | (ddh << 8) | (ddb << 16)
    
    return source_addr, dest_addr
end
```

**Contingency:** If these registers aren't readable via Lua API, document the limitation and use timing correlation between $2230/$2231 state changes and ROM trace buckets.

### Task 1.3: Run Capture Sessions

1. Load Kirby Super Star
2. Start the register logger
3. Play through sprite-heavy scenes:
   - Title screen
   - Character select
   - Gameplay with multiple enemies
   - Boss fights
4. Collect 5+ minutes of log data
5. Analyze for conversion bit patterns

### Task 1.4: Document Findings

Create a findings document with one of these conclusions:

```markdown
# SA-1 Conversion Hypothesis: [CONFIRMED / FALSIFIED / PARTIAL]

## Evidence

[Paste relevant log excerpts]

## Conclusion

[One of:]
- CONFIRMED: Conversion bit active during sprite loads. Proceed with Strategy A.
- FALSIFIED: Conversion bit NOT active. Investigate alternatives: [list which]
- PARTIAL: Conversion active for [sprite types], inactive for [other types].
  Pipeline must route sprites to appropriate strategy.

## Sign-off

- [ ] Log evidence archived
- [ ] Conclusion documented
- [ ] Approved to proceed to Phase 2
```

---

## Phase 2: Fix Dangerous Assumptions

**Status:** Blocked by Phase 1  
**Priority:** HIGH - Do not skip

### Task 2.1: Resolve Byte-Swap Root Cause

The documentation claims byte-swap is needed but doesn't verify why.

**Step 1: Check write capability**

```lua
-- Test if we can write to VRAM
local function test_vram_write()
    local test_addr = 0x0000
    local success, err = pcall(function()
        emu.write(test_addr, 0xAB, emu.memType.videoRam)
    end)
    return success, err
end

local can_write, write_err = test_vram_write()
print("VRAM write available:", can_write)
if not can_write then
    print("Error:", write_err)
    print("Falling back to known-asset comparison method")
end
```

**Step 2a: If write available - Direct test**

```lua
-- Write known pattern, read back, check behavior
emu.write(0x0000, 0xAB, emu.memType.videoRam)
emu.write(0x0001, 0xCD, emu.memType.videoRam)

local word = emu.readWord(0x0000, emu.memType.videoRam)
print(string.format("Wrote 0xAB, 0xCD. readWord returned: 0x%04X", word))

-- Expected if little-endian: 0xCDAB
-- Expected if big-endian: 0xABCD
```

**Step 2b: If write unavailable - Known-asset comparison**

1. Find a game with documented tile data (e.g., title screen logo)
2. Capture tiles via current pipeline
3. Compare against reference extracted via external tile editor
4. Document whether swap produces match

**Step 3: Update documentation**

Based on results, update `01_BUILD_SPECIFIC_CONTRACT.md`:

```markdown
## Byte-Swap Behavior

**Mesen2 Build:** [version]
**Test Date:** [date]
**Test Method:** [direct write/read OR known-asset comparison]

**Finding:** emu.readWord() returns bytes in [little-endian / big-endian] order.
To reconstruct sequential VRAM bytes, [swap required / no swap needed].

**Test Evidence:**
[Paste test output]
```

### Task 2.2: Add prg_size Fail-Fast

Replace any fallback logic with strict validation:

```lua
-- In capture script initialization
local prg_size = emu.getMemorySize(emu.memType.prgRom)

if not prg_size or prg_size == 0 then
    error([[
PRG ROM size unavailable. Cannot proceed.

Possible causes:
1. ROM not loaded - ensure game is running before starting capture
2. Memory type not exposed - verify Mesen2 build supports prgRom
3. Lua API limitation - check Mesen2 version compatibility

Do not use fallback values. Fix the root cause.
]])
end

print(string.format("PRG ROM size: 0x%X bytes", prg_size))
```

### Task 2.3: Fix VMAIN Remap Formulas

Replace the "rotate" formulas in `00_STABLE_SNES_FACTS.md` with SNESdev canonical definitions:

```markdown
## VMAIN Address Remapping

Reference: https://snes.nesdev.org/wiki/PPU_registers#VMAIN

### Mode 00 (No remapping)
Address bits unchanged.

### Mode 01 (8-bit rotate)
Input:  aaaaaaaaBBBccccc
Output: aaaaaaaacccccBBB

### Mode 10 (9-bit rotate)
Input:  aaaaaaaBBBcccccc
Output: aaaaaaaccccccBBB

### Mode 11 (10-bit rotate)
Input:  aaaaaaBBBccccccc
Output:  aaaaaacccccccBBB

### Worked Example (Mode 01)
Input address:  0x1234 = 0001001000110100
Bits:           rrrrrrrrYYYccccc
                00010010 001 10100

Remap YYY to end:
Output:         00010010 10100 001
                = 0001001010100001
                = 0x12A1
```

### Task 2.4: Add WRAM Staging Warning

Add to `04_TROUBLESHOOTING.md`:

```markdown
## WARNING: WRAM Staging Analysis Limitations

WRAM staging analysis (`analyze_wram_staging.py`) is ONLY valid for:
- Static assets (UI elements, fonts)
- Non-converted tile data

When tile conversion/transformation is active:
- WRAM contains SOURCE data (bitmap or compressed format)
- VRAM contains OUTPUT data (converted bitplane format)
- Hash comparison will show ZERO OVERLAP

**This is expected behavior, not a bug.**

If you see zero overlap between WRAM and VRAM dumps:
1. Check if conversion is active (see Phase 1 logs)
2. If active: zero overlap is correct
3. If not active: investigate other causes (compression, format mismatch)
```

---

## Phase 3: Fix Naming and Schema

**Status:** Blocked by Phase 2  
**Priority:** MEDIUM

### Task 3.1: Schema Migration

**Old names → New names:**
| Old | New | Reason |
|-----|-----|--------|
| `oam_base_addr` | `obj_tile_base_word` | VRAM address, not OAM |
| `oam_addr_offset` | `obj_tile_offset_word` | VRAM address, not OAM |
| `confidence` | `observation_count` | Avoid statistics confusion |

**Migration script:**

```python
#!/usr/bin/env python3
"""Migrate schema v1 to v2."""

import json
import sys
from pathlib import Path

FIELD_RENAMES = {
    "oam_base_addr": "obj_tile_base_word",
    "oam_addr_offset": "obj_tile_offset_word",
    "confidence": "observation_count",
}

def migrate_file(input_path: Path) -> dict:
    with open(input_path) as f:
        data = json.load(f)
    
    # Check version
    version = data.get("schema_version", 1)
    if version >= 2:
        print(f"SKIP: {input_path} already v{version}")
        return None
    
    # Rename fields recursively
    def rename_fields(obj):
        if isinstance(obj, dict):
            return {
                FIELD_RENAMES.get(k, k): rename_fields(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [rename_fields(item) for item in obj]
        else:
            return obj
    
    migrated = rename_fields(data)
    migrated["schema_version"] = 2
    
    return migrated

def main():
    if len(sys.argv) < 2:
        print("Usage: migrate_v1_to_v2.py <file_or_directory>")
        sys.exit(1)
    
    target = Path(sys.argv[1])
    files = list(target.glob("**/*.json")) if target.is_dir() else [target]
    
    for f in files:
        result = migrate_file(f)
        if result:
            output_path = f.with_suffix(".v2.json")
            with open(output_path, "w") as out:
                json.dump(result, out, indent=2)
            print(f"MIGRATED: {f} -> {output_path}")

if __name__ == "__main__":
    main()
```

**Validation:**

```lua
-- Add to capture script
local function validate_schema_version(data)
    local version = data.schema_version or 1
    if version < 2 then
        error(string.format(
            "Schema v%d detected. Run: python migrate_v1_to_v2.py %s",
            version, data.source_file or "database.json"
        ))
    end
end
```

### Task 3.2: Enforce Address Unit Suffixes

Add validation that all address fields end in `_word` or `_byte`:

```lua
local function validate_address_field_name(name)
    if name:match("addr") or name:match("offset") then
        if not (name:match("_word$") or name:match("_byte$")) then
            error("Address field '" .. name .. "' must end with _word or _byte")
        end
    end
end
```

### Task 3.3: Fix 128KB VRAM Claim

Update `00_STABLE_SNES_FACTS.md`:

```markdown
## OBJSEL name_base Field (bits 0-2)

- Values 0-3: Valid. Address within 64KB VRAM.
- Values 4-7: **UNDEFINED BEHAVIOR.**
  - Hardware: Wraps/mirrors within 64KB (unverified)
  - Emulators: Behavior varies
  - Pipeline: Reject with warning

SNES VRAM is fixed at 64KB. Claims about "128KB expansion" are unverified speculation.
```

---

## Phase 4: Documentation Improvements

**Status:** Blocked by Phase 3  
**Priority:** LOW

### Task 4.1: Document Tile Hash Byte Order

Add to `02_DATA_CONTRACTS.md`:

```markdown
## Tile Hash Database Format

Tiles are stored as 32 bytes in sequential VRAM order (after byte-swap correction).

### Reconstruction from readWord()

| Word Read | Returns | After Swap | DB Position |
|-----------|---------|------------|-------------|
| addr+0    | 0xCDAB  | CD, AB     | [0], [1]    |
| addr+2    | 0x1234  | 12, 34     | [2], [3]    |
| ...       | ...     | ...        | ...         |
| addr+30   | 0xFFEE  | FF, EE     | [30], [31]  |
```

### Task 4.2: Add Success Criteria

Add provisional thresholds (adjust based on empirical data):

```markdown
## Success Criteria (Provisional)

| Metric | Non-SA1 Expected | SA1+Conversion Expected |
|--------|------------------|-------------------------|
| Tile hash hit rate | >70% | <10% |
| Low-info tile % | 10-30% | 10-30% |
| Top bucket concentration | >50% | Variable |

These are heuristics, not diagnostics. Cross-reference with register logs.
```

### Task 4.3: Document Failure Modes

Add timing correlation failure table:

```markdown
## Timing Correlation Failures

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Low top-bucket count, buckets tied | Multi-region frame | Use per-burst bucketing |
| High confidence, wrong region | Hash collision | Cross-ref with timing |
| Correlation off by 1-2 frames | Double buffering | Widen window to ±2 |
| Hot bucket has no graphics | Pointer table reads | Filter by 32-byte alignment |
```

### Task 4.4: Add Golden Test SHA256

Calculate and add the actual ROM hash:

```bash
sha256sum "Kirby Super Star (USA).sfc"
```

Update `03_GAME_MAPPING_KIRBY_SA1.md` with result.

---

## Phase Checklist

### Phase 1 Exit Criteria
- [ ] Register logger script created and tested
- [ ] 5+ minutes of gameplay logged
- [ ] Hypothesis outcome documented (CONFIRMED / FALSIFIED / PARTIAL)
- [ ] Log evidence archived
- [ ] Sign-off to proceed

### Phase 2 Exit Criteria
- [ ] Byte-swap test completed
- [ ] Byte-swap behavior documented with build version
- [ ] prg_size fail-fast implemented (no fallback)
- [ ] VMAIN formulas match SNESdev
- [ ] WRAM warning added

### Phase 3 Exit Criteria
- [ ] Migration script created and tested
- [ ] Schema v2 validation in place
- [ ] Address suffix convention enforced
- [ ] 128KB VRAM claim corrected

### Phase 4 Exit Criteria
- [ ] Byte order documented with example
- [ ] Success criteria added (labeled provisional)
- [ ] Failure modes documented
- [ ] Golden test SHA256 filled in

---

## Quick Commands

```bash
# Run SA-1 register logger
mesen -script scripts/sa1_conversion_logger.lua "Kirby Super Star (USA).sfc"

# Migrate database to v2
python scripts/migrate_v1_to_v2.py ./databases/

# Calculate ROM SHA256
sha256sum "Kirby Super Star (USA).sfc"

# Run capture with validation
mesen -script scripts/capture_v2.lua "Kirby Super Star (USA).sfc"
```

---

## If Things Go Wrong

### SA-1 hypothesis falsified
Stop. Do not proceed with Strategy A. Investigate alternatives:
1. Palette remapping → Compare tiles with palette swap applied
2. Runtime composition → Trace tile assembly in disassembly
3. Compression variant → Try alternate decompressors
4. Interlaced planes → Test alternate bitplane ordering

### Byte-swap test shows inconsistent behavior
**Blocking issue.** Do not proceed. Possible causes:
- Race condition in Lua API
- VRAM state changes between write and read
- Mesen2 bug

Escalate to Mesen2 debugging.

### Migration corrupts data
Restore from backup:
```bash
rm -rf ./databases
mv ./databases.backup.YYYYMMDD ./databases
```
Investigate failure before re-attempting.