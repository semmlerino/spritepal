# Initialization Trace Findings and Recommendations

## Scope
- Based on static analysis from `launch_spritepal.py` through steady state (event loop start).
- Qt/stdlib internals are not expanded; only project-defined methods are tracked.

## Findings (Repeated Initialization or Resource Allocation)
- `core/hal_compression.py` `HALCompressor.__init__()` runs 3x (via `ROMExtractor` and two `ROMInjector` instances).
  - Triggers `HALProcessPool.initialize()` on each call; only the first call does heavy work due to singleton guard.
- `core/rom_injector.py` `ROMInjector.__init__()` runs 2x (from `ROMExtractor` and `InjectionController`), duplicating
  `HALCompressor` and `SpriteConfigLoader` setup.
- `core/sprite_config_loader.py` `SpriteConfigLoader.__init__()` runs 3x (same config file reloaded).
- `core/default_palette_loader.py` `DefaultPaletteLoader.__init__()` runs 2x (same palettes reloaded).
- `QApplication.setStyleSheet()` runs twice (theme, then accessibility) by design.
- Log/cache directories are created in both `ConfigurationService.ensure_directories_exist()` and `setup_logging()`;
  operations are idempotent.
- `AppContext.rom_extractor` is accessed twice during `MainWindow` argument evaluation but returns the same instance.
- High fan-out UI construction is intentional (palette widgets, toolbar actions, etc.), but is a sizable startup cost.

## Recommendations
- Consider sharing a single `HALCompressor` instance across `ROMExtractor` and `ROMInjector` to avoid redundant
  tool path probing and pool init checks.
- Consider reusing a single `ROMInjector` instance or injecting a shared instance to reduce duplicate setup.
- Cache or singleton `SpriteConfigLoader` and `DefaultPaletteLoader` instances to avoid re-reading files.
- If intentional duplication is required, add explicit comments/doc notes to prevent future confusion.
- If startup time becomes a concern, defer heavy file loads (palettes/config) until first use via lazy loading.

## Notes
- `ROMExtractionPanel.load_last_rom_deferred()` only triggers `_load_rom_file()` if the last ROM path exists on disk.
- Some duplication is acceptable for isolation in tests, but production startup could benefit from shared services.
