---
paths:
  - "core/rom_injector.py"
  - "core/injector.py"
  - "core/hal_compression.py"
  - "core/hal_parser.py"
  - "ui/**/inject*"
---

# Injection — ROM & VRAM Write Paths

## Mental Model

Two injection targets:

- **ROM Injection**: Compress sprite → check slack space → write to ROM → update checksum → verify
- **VRAM Injection**: Validate PNG constraints → convert to 4bpp tiles → write at VRAM offset

## ROM Injection Flow

```
Validate input
  → Copy ROM (atomic: write → fsync → rename)
  → Convert PNG to 4bpp tile data
  → Prepend header_bytes (if any)
  → Compress (HAL or RAW)
  → Detect slack space at target offset
  → Size check (compressed ≤ slack)
  → Inject at offset
  → Preserve padding (for idempotent re-injection)
  → Update ROM checksum
  → Atomic write to final path
```

## VRAM Injection Flow

```
Validate PNG (indexed or grayscale, 8×8 tile grid, ≤16 colors)
  → Convert to SNES 4bpp format
  → Write at VRAM offset
```

## Key Types

- `CompressionType` — HAL, RAW, UNKNOWN
- `ROMHeader` — SMC header detection and offset adjustment
- `HALCompressor` — HAL format compression/decompression

## Invariants

- **Atomic writes**: write → fsync → rename (never partial writes to target)
- Checksum always updated after injection
- Max 256 bytes slack space (compressed data must fit)
- SMC header adjustment: offset + 0 (no header) or + 512 (SMC header present)
- Backup before any ROM modification
- Typical HAL compression ratio: 30-70%
- Padding preservation ensures idempotent re-injection

## Safety

- `force` flag bypasses size check (for advanced users)
- `preserve_existing` for batch injection (don't re-inject already-injected frames)

## Non-Goals

- No multi-ROM injection in single call (caller handles batch iteration)
- No compression auto-detection at injection time (caller specifies type)

## Key Files

- `core/rom_injector.py` — ROM-level injection orchestration
- `core/injector.py` — low-level byte writing, checksum update
- `core/hal_compression.py` — HAL compression algorithm
- `core/hal_parser.py` — HAL format parsing, decompression
- `core/rom_validator.py` — ROM validation, header detection
