# Mesen Integration Subsystem Architecture

The `core/mesen_integration/` package provides tools for **live sprite capture** from the Mesen 2 emulator and **automated ROM offset discovery**. This is a critical subsystem for mapping VRAM tiles back to their source locations in ROM.

## Purpose

The subsystem bridges three domains:

1. **Mesen 2 Lua Scripts** (`mesen2_integration/lua_scripts/`) - Capture sprites at runtime
2. **JSON Exchange** (`mesen2_exchange/`) - Structured capture data
3. **Python Analysis** (`core/mesen_integration/`) - ROM offset discovery

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Mesen 2 Emulator                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ sprite_rom_finder.lua (click on sprite → get ROM offset)    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼ JSON
┌─────────────────────────────────────────────────────────────────────┐
│                  mesen2_exchange/*.json                             │
│  (OAM entries, VRAM tile data, DMA logs, timing info)               │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 core/mesen_integration/                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │         CorrelationPipeline (Orchestrator)                   │   │
│  │  load_dma_log() → load_capture() → build_database() → run() │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                               │                                     │
│         ┌─────────────────────┼─────────────────────┐              │
│         ▼                     ▼                     ▼              │
│  ┌─────────────┐    ┌─────────────────┐    ┌────────────────┐     │
│  │click_extractor│    │timing_correlator│    │address_space   │     │
│  │(parse JSON)  │    │(DMA matching)   │    │_bridge (SA-1)  │     │
│  └─────────────┘    └─────────────────┘    └────────────────┘     │
│         │                     │                     │              │
│         └──────────┬──────────┴─────────────────────┘              │
│                    ▼                                                │
│         ┌─────────────────────┐                                    │
│         │ tile_hash_database  │  Build searchable tile index       │
│         └─────────────────────┘                                    │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────┐                                    │
│         │  rom_tile_matcher   │  Find ROM offsets via hash lookup  │
│         └─────────────────────┘                                    │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────────────────────────────────────┐   │
│         │  capture_to_rom_mapper → CaptureMapResult            │   │
│         │  (confidence scoring, ambiguity detection)           │   │
│         └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                     ROM offset for extraction
```

## Module Responsibilities

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `click_extractor.py` | Parse Mesen JSON captures | `MesenCaptureParser`, `OAMEntry`, `TileData` |
| `address_space_bridge.py` | SA-1 ↔ SNES address conversion | `CanonicalAddress`, `sa1_to_canonical()` |
| `timing_correlator.py` | Match tiles to DMA events | `TimingCorrelator`, `DMAEvent`, `TileCorrelation` |
| `tile_hash_database.py` | Efficient tile similarity search | `TileHashDatabase`, `build_and_save_database()` |
| `rom_tile_matcher.py` | Find ROM offsets via tile hashing | `ROMTileMatcher`, `TileLocation` |
| `capture_to_rom_mapper.py` | Map entire captures to ROM | `CaptureToROMMapper`, `CaptureMapResult` |
| `full_correlation_pipeline.py` | Orchestrate end-to-end workflow | `CorrelationPipeline`, `PipelineResults` |
| `sa1_character_conversion.py` | SA-1 character format handling | `snes_4bpp_to_bitmap()`, `hash_two_planes()` |
| `gfx_pointer_table.py` | Parse GFX pointer tables | `GFXPointerTableParser`, `rom_to_sa1_cpu()` |
| `capture_renderer.py` | Render captures to images | `CaptureRenderer`, `render_capture_to_files()` |
| `sprite_reassembler.py` | Reassemble multi-OAM sprites | (Used internally by pipeline) |

## Import Rules

The mesen_integration package follows standard Core layer rules:

- **CAN import from**: `core/`, `utils/`, Python stdlib
- **CANNOT import from**: `ui/`, `core/managers/` (except via protocols)
- **CANNOT import from**: External emulators (pure Python analysis only)

## Data Flow: Click-to-ROM Pipeline

```
1. User clicks sprite in Mesen 2 emulator
                    ↓
2. Lua script captures: OAM index, VRAM tile, DMA log
                    ↓
3. JSON written to mesen2_exchange/
                    ↓
4. click_extractor.py parses JSON → OAMEntry, TileData
                    ↓
5. timing_correlator.py correlates tile with DMA events
                    ↓
6. address_space_bridge.py converts SA-1 addresses → canonical
                    ↓
7. tile_hash_database.py indexes ROM tiles (with flip variants)
                    ↓
8. rom_tile_matcher.py looks up VRAM tile hash → TileLocation[]
                    ↓
9. capture_to_rom_mapper.py scores candidates, detects ambiguity
                    ↓
10. Return ROM offset with confidence score
```

## SA-1 Address Space

Kirby Super Star uses the SA-1 coprocessor, which has a different memory map than standard SNES. The `address_space_bridge.py` module handles:

- **Canonical addresses**: Unified representation for both SNES and SA-1 addresses
- **Staging buffer detection**: Identify WRAM, IRAM, BWRAM staging areas
- **DMA source normalization**: Convert DMA sources to ROM file offsets

**Example:**
```python
from core.mesen_integration import sa1_to_canonical, CanonicalAddress

# SA-1 CPU address 0xC08000 → ROM file offset 0x000000
canonical = sa1_to_canonical(0xC08000)
# canonical.rom_offset == 0x000000 (bank 0xC0 maps to ROM start)
```

## Key Patterns

### Tile Hash Lookup

Tiles are indexed by their content hash (not position). This allows finding matching tiles anywhere in ROM:

```python
from core.mesen_integration import ROMTileMatcher

matcher = ROMTileMatcher(rom_data)
matcher.build_database()

# Lookup VRAM tile (32 bytes of 4bpp data)
locations = matcher.lookup_vram_tile(tile_bytes)
# Returns list of TileLocation(offset, flip_h, flip_v)
```

### Confidence Scoring

The mapper detects ambiguous matches (multiple ROM locations with same tile):

```python
from core.mesen_integration import CaptureToROMMapper

mapper = CaptureToROMMapper(rom_path)
result = mapper.map_capture(capture_json)

if result.is_confident():
    offset = result.primary_rom_offset
else:
    # Multiple candidates - may need manual verification
    for entry in result.get_entries_for_offset(candidate):
        print(f"  {entry.scored_percentage}% confidence")
```

### Full Pipeline

For end-to-end processing:

```python
from core.mesen_integration import CorrelationPipeline, format_pipeline_report

pipeline = CorrelationPipeline(rom_path)
pipeline.load_dma_log("mesen2_exchange/dma_log.txt")
pipeline.load_captures("mesen2_exchange/sprite_capture_*.json")
pipeline.build_database()

results = pipeline.run()
print(format_pipeline_report(results))
```

## Usage in SpritePal

This subsystem is used by:

1. **Manual Offset Control** (`ui/dialogs/manual_offset_dialog.py`) - For verifying ROM offsets
2. **Automated extraction workflows** - When Mesen 2 captures are available
3. **Development/debugging** - Understanding where sprite data comes from

## Related Documentation

- **Lua Scripts**: See [mesen2_integration/README.md](../../mesen2_integration/README.md) for script usage
- **SNES/SA-1 Hardware**: See [00_STABLE_SNES_FACTS.md](00_STABLE_SNES_FACTS.md)
- **Kirby-Specific Mapping**: See [03_GAME_MAPPING_KIRBY_SA1.md](03_GAME_MAPPING_KIRBY_SA1.md)

---

*Extracted from docs/architecture.md on January 22, 2026*
