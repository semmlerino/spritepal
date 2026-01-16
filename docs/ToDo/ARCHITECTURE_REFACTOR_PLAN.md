# SpritePal Architecture Refactor Plan (January 2026)

## 1. Truth Map of Runtime Flow

The application follows a heavily signal-driven architecture where `MainWindow` and `ROMWorkflowController` act as primary God-object orchestrators.

### Primary Workflows

| Workflow | Entry Point | Path to "Real Work" | Primary Orchestrator | Side Effects |
| :--- | :--- | :--- | :--- | :--- |
| **ROM/VRAM Extraction** | `MainWindow.on_extract_clicked` | `_start_vram_extraction` → `VRAMExtractionWorker` → `CoreOperationsManager` → `SpriteExtractor` | `MainWindow` | Saves `.png`, `.metadata.json`, and `.pal` files to disk. |
| **Edit Sprite** | Asset Browser Dbl-Click | `ROMWorkflowController.set_offset` → `SmartPreviewCoordinator` → `ROMExtractor` → `EditingController.load_image` | `ROMWorkflowController` | Updates in-memory `ImageModel` and `PaletteModel`. |
| **Inject to ROM** | Workspace "Save to ROM" | `ROMWorkflowController.save_to_rom` → `ROMInjector.inject_sprite_to_rom` | `ROMWorkflowController` | Modifies `.sfc` file (or creates `_modified.sfc`), clears cache. |

### Signal Table (Key Orchestration)

| Emitter | Signal | Subscribers | Payload | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `CoreOperationsManager` | `extraction_completed` | `MainWindow` | `ExtractionResult` | Unified update of UI after disk write. |
| `EditingController` | `imageChanged` | `Canvas`, `MainWindow` | None | Triggers re-render and ROM constraint validation. |
| `LogWatcher` | `offset_discovered` | `ROMWorkflowController` | `CapturedOffset` | Adds new Mesen 2 discoveries to the Asset Browser. |
| `SmartPreviewCoordinator`| `preview_ready` | `ROMWorkflowController` | `tile_data`, `offset` | Triggers editor load after decompression completes. |

---

## 2. Abstraction Smells & Signal Smells

*   **Wrapper Pass-through (`CoreOperationsManager`):** This class exists primarily to wrap `ROMExtractor`, `SpriteExtractor`, and `PaletteManager`. It duplicates their APIs and signals, adding an extra jump for every core operation without providing real variability.
*   **God Object (`MainWindow`):** Recent refactors moved massive amounts of worker orchestration and dialog logic into `MainWindow.py` (now 2000+ lines). It is currently handling everything from UI layout to threading and session persistence.
*   **Half-Finished Refactor (`ExtractionController`):** There is an extraction controller in `ui/sprite_editor/` but most extraction logic was recently "inlined" into `MainWindow`. This creates two different paths for the same "real work."
*   **Ambiguous Signal Payloads:** Many signals use `object` or `list`, making it impossible for strict type checking to verify data flow without manual inspection.
*   **Lazy Loading Circularity (`AppContext`):** Lazy-initialized properties in `AppContext` (like `rom_extractor`) often depend on other lazy properties, creating hidden initialization orders that are hard to trace.

---

## 3. Simplification Plan (Prioritized ROI)

| Order | Refactor Action | Target Files | Risk | Rollback |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Inline `CoreOperationsManager`** | `core/managers/core_operations_manager.py` | Med | Git Revert |
| 2 | **Extract Worker Orchestration** | `MainWindow.py` → `ui/services/worker_orchestrator.py` | Med | Move logic back |
| 3 | **Type Signal Payloads** | Project-wide | Low | None needed |
| 4 | **Decouple Asset Browser** | `ROMWorkflowController.py` | High | Git Revert |
| 5 | **Merge Extraction Controllers** | `ui/sprite_editor/controllers/` | Med | Git Revert |

---

## 4. New Architecture Sketch

The goal is to move from **God Objects** to **Functional Services**.

### Target Module Layout
*   **`core/services/`**: Pure logic (Image processing, HAL compression, ROM parsing).
*   **`ui/orchestrators/`**: Non-UI classes that manage threads/workers.
*   **`ui/views/`**: Passive components that only display data and emit basic signals.
*   **`ui/models/`**: Shared state (e.g., `ImageModel`).

### The "Golden Path" for Extraction
1.  `UI.button_clicked` → `MainWindow` (calls `WorkerOrchestrator`).
2.  `WorkerOrchestrator` starts `ExtractionWorker`.
3.  `ExtractionWorker` calls `ROMExtractor` (Service).
4.  `ROMExtractor` returns `ExtractionResult` (Dataclass).
5.  `MainWindow` receives signal and updates `PreviewPanel`.

### Signal Policy
*   **Rule**: Signals for *notifications* ("Data updated"), not *orchestration* ("Go do X").
*   **Naming**: Must be past-tense (`extractionCompleted`, `offsetChanged`).
*   **Payloads**: Must use Dataclasses/TypedDicts, never raw `object`.
