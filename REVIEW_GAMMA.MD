# Code Clarity Review

## 1. Redundant PNG→4bpp Converters
- **Location:** `core/injector.py` (135-219) vs `ui/sprite_editor/services/image_converter.py` (62-140)
- **Problem:** Two different implementations with slightly different validation/padding behaviors. A grayscale PNG can succeed during ROM injection but fail inside the editor, so the abstraction primarily just forwards parse logic without reuse.
- **Suggestion:** Pull the conversion logic into a single `core` helper (e.g., `core/services/png_conversion.py::convert_png_to_4bpp`) and have both modules call it. Ensure shared validation/padding policy so behavior is consistent across flows.
- **Risk:** Medium (touches injection + editor paths).

## 2. Confusing Preview Stack
- **Location:** `core/services/preview_generator.py` vs `ui/common/smart_preview_coordinator.py` + `ui/common/preview_cache.py`
- **Problem:** The UI layer maintains its own `PendingPreviewRequest` and `PreviewCache`, running parallel to the centralized `PreviewGenerator` and its `PreviewCache`. Call chains pass through ~5 layers just to surface the preview, and cache semantics are duplicated/aliased, which obscures intent.
- **Suggestion:** Either route the slider-based preview flow through `PreviewGenerator` (leveraging its cache) or rename the UI-only types to reflect their specialized purpose (e.g., `ManualOffsetPreviewCache`) and keep its usage isolated. Avoid aliasing `SpritePreviewCache` as `PreviewCache` when a different cache already exists.
- **Risk:** High (threading + performance sensitive).

## 3. Thin Worker/Coordinator Layers
- **Location:** `ui/services/extraction_workflow_coordinator.py` (start_rom_extraction) → `core/workers/extraction.py` (ROMExtractionWorker) → `core/managers/core_operations_manager.py` (extract_from_rom)
- **Problem:** `ROMExtractionWorker` simply forwards parameters to `CoreOperationsManager`, yet the coordinator spawns and wires the worker through multiple signal proxies. The added indirection hides what actually happens and adds >5 call levels.
- **Suggestion:** Introduce a `CoreOperationsManager.start_rom_extraction_job(params)` helper that manages threading internally, or collapse the coordinator/worker into a generic worker that takes a callable, reducing the chain depth and improving signal locality.
- **Risk:** Medium.

## 4. Palette Utility Lives Only as Helper
- **Location:** `core/services/palette_utils.py` (26-115)
- **Problem:** This module exists solely to support `CoreOperationsManager.extract_from_rom`, and it duplicates the `core.palette_utils` namespace. It wraps `PaletteManager` without owning state, so it behaves more like an isolated helper than a service.
- **Suggestion:** Merge the helper into `PaletteManager` (e.g., `PaletteManager.extract_palettes(...)`) or move it into `CoreOperationsManager` as `_extract_palettes_and_metadata`. Rename the module to clarify its single consumer.
- **Risk:** Low.

## 5. Misleading Naming / Layer Confusion
- **Location:** `core/extractor.py::SpriteExtractor` vs `core/rom_extractor.py` and `ui/common/preview_cache.py::PreviewCache`
- **Problem:** `SpriteExtractor` only handles VRAM dumps, yet the rest of the code also uses other `extractor` abstractions (`ROMExtractor`), which can mislead contributors. The UI cache alias `PreviewCache` collides with `core.services.preview_generator.PreviewCache`, hiding which cache is being referenced.
- **Suggestion:** Rename `SpriteExtractor` to `VramSpriteExtractor` and avoid aliasing `SpritePreviewCache` as `PreviewCache` (use a more descriptive name like `ManualOffsetPreviewCache`).
- **Risk:** Low.
