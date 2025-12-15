# SpritePal Development Notes

This file contains background context, research notes, and historical information
about the SpritePal project. For operational development guidelines, see `CLAUDE.md`.

## Mesen2/Sprite Finding (Active Work)

Current focus: Finding and extracting SNES sprites using Mesen2 emulator.

### Key Documentation

- `docs/mesen2/` - Mesen2 integration docs (Lua API, sprite finding guides)
- `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md` - Lua scripting knowledge
- `SPRITE_LEARNINGS_DO_NOT_DELETE.md` - ROM extraction patterns
- `mesen2_integration/` - Lua scripts and automation code

### Mesen2 Integration Files

The `docs/mesen2/` directory contains extensive documentation:
- `AUTOMATED_SPRITE_TRACING.md` - Automated sprite discovery
- `ENHANCED_SPRITE_FINDER_GUIDE.md` - Using the sprite finder
- `LUA_AUTO_CAPTURE_INSTRUCTIONS.md` - Automated capture setup
- `SPRITE_FINDER_USAGE_GUIDE.md` - End-to-end usage
- `SPRITE_VISUALIZATION_GUIDE.md` - Visualizing extracted sprites

## Historical Documentation

Completed phase reports and one-time fix summaries are archived in:
`docs/archive/` (phase_reports/, migration_reports/, fix_summaries/, analysis_docs/)

### Archive Structure

```
docs/archive/
├── phase_reports/          # Development phase summaries
│   └── NEXT_STEPS_PLAN.md  # Historical planning document
├── migration_reports/      # Code migration documentation
├── fix_summaries/          # Bug fix post-mortems
└── analysis_docs/          # Technical analysis documents
```

## Project Background

SpritePal is a SNES sprite extraction and editing tool focused on:
- Extracting sprites from ROM files using HAL compression
- VRAM/CGRAM/OAM data processing
- Mesen2 emulator integration for live sprite discovery
- Real-time preview and editing capabilities

### Key Technical Decisions

1. **PySide6 over PyQt6**: Licensing and API consistency
2. **HAL compression**: Native decompression for SNES ROMs
3. **Mock-by-default HAL**: Performance optimization for tests
4. **Real component testing**: Prefer real objects over mocks

---

*This file is for background context only. See CLAUDE.md for operational guidelines.*
