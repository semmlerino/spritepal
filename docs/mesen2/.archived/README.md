# Archived Mesen2 Documentation

This directory contains **obsolete and superseded** Mesen2 integration documentation. These files document earlier iterations of the sprite discovery and capture process that have been replaced by more robust implementations.

## Why These Files Are Archived

These documents were created during earlier development phases (August 2024 - December 2024) and have been superseded by:

1. **`../00_STABLE_SNES_FACTS.md`** - Consolidated SNES/SA-1 facts (replaces scattered learnings)
2. **`../03_GAME_MAPPING_KIRBY_SA1.md`** - Current Kirby SA-1 ROM mapping (replaces manual tracing guides)
3. **`../04_TROUBLESHOOTING.md`** - Current troubleshooting guide

## Files in This Archive

| File | Reason Archived | Replacement |
|------|-----------------|-------------|
| `AUTOMATED_SPRITE_TRACING.md` | Manual tracing approach superseded | Full automated pipeline with `full_correlation_pipeline.py` |
| `ENHANCED_SPRITE_FINDER_GUIDE.md` | Old Lua script interface | Current `sprite_rom_finder.lua` (v34) |
| `LUA_AUTO_CAPTURE_INSTRUCTIONS.md` | Obsolete capture workflow | Built-in auto-capture via `--testrunner` |
| `MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md` | Ad-hoc API documentation | Consolidated in `STABLE_SNES_FACTS.md` |
| `MESEN2_LUA_DRAWING_FIX.md` | Obsolete rendering workaround | Fixed in current Lua scripts |
| `MESEN_LEARNINGS.md` | Early research notes | Formalized in `STABLE_SNES_FACTS.md` |
| `MESEN_SPRITE_FINDER_README.md` | Old sprite finder UI | Current click-to-find workflow |
| Others | Historical reference | See current documentation above |

## If You Need This Information

- **SNES/SA-1 address mapping?** → `../03_GAME_MAPPING_KIRBY_SA1.md`
- **ROM offset discovery workflow?** → `../README.md` (main Mesen2 guide)
- **Lua scripting reference?** → Check current scripts in `mesen2_integration/lua_scripts/`
- **Troubleshooting capture issues?** → `../04_TROUBLESHOOTING.md`

## Notes

- These files are kept for **historical reference only**
- Do not use these for new development—refer to current documentation
- If implementing new features similar to archived content, consult the current docs first to avoid redundant work

---

*Last updated: January 9, 2026*
