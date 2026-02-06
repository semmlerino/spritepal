# Architectural Refactor Evaluation Report
**Date:** 2026-02-06
**Scope:** Action Enablement, State Synchronization, and Cache Management

## Executive Summary
Three architectural refactors were evaluated for the SpritePal codebase. 
1. **Centralized Action Enablement:** Defer. Current complexity does not yet justify the abstraction cost.
2. **Reduce Private Mutation:** Implement (Targeted). Specific Law of Demeter violations in workspace wiring should be resolved, but a full overhaul is unnecessary.
3. **Explicit Cache Invalidation:** **CRITICAL**. The current caching mechanism is fundamentally flawed for writable assets (ROMs/VRAM), leading to stale data presentation. Immediate remediation is required.

---

## 1. Centralize Action Enablement Logic

**Proposal:** Move UI state logic (enabling buttons/menus) from scattered `_configure_*` methods in `MainWindow` to a central state reducer.

**Current Status:**
- Logic is encapsulated in `MainWindow._on_extraction_tab_changed`, which delegates to specific helpers (`_configure_rom_extraction_tab`, etc.).
- `ToolbarManager` handles the actual widget manipulation.
- State is determined implicitly by the active tab index and existence of loaded data.

**Assessment:**
- **Problem:** Adding a new mode requires touching `MainWindow` logic in multiple places. Logic is imperative ("if tab 0, enable X") rather than declarative ("if state is IDLE, enable X").
- **Benefit:** Cleaner state transitions; easier testing of UI states without instantiating widgets.
- **Cost:** Moderate. Requires rewriting `MainWindow` flow and potentially introducing a strict State Machine.
- **Risk:** Low.

**Recommendation: DEFER**
The current complexity is low. The `ToolbarManager` provides sufficient abstraction for now. The "scattered" logic is actually well-contained within `MainWindow`'s configuration methods. Premature abstraction here would add boilerplate without solving a painful problem.

---

## 2. Reduce Cross-Component Private Mutation

**Proposal:** Replace direct view/controller manipulation with event-driven synchronization, specifically for palette/editor interactions.

**Current Status:**
- `SpriteEditorWorkspace` acts as a "God Class" for wiring, reaching deep into child components:
  ```python
  # ui/workspaces/sprite_editor_workspace.py
  self._extraction_controller.set_multi_palette_view(self._vram_page.multi_palette_tab)
  self._vram_page.edit_tab.workspace.exportPngRequested.connect(...) 
  ```
- `ExtractionController` holds direct references to `MultiPaletteTab` to push data (`set_palette_images`), coupling the controller to a specific UI implementation.

**Assessment:**
- **Problem:** `SpriteEditorWorkspace` violates the Law of Demeter. Changing the UI hierarchy of `VRAMEditorPage` breaks the workspace. `ExtractionController` cannot be tested easily without mocking complex Qt widgets.
- **Benefit:** Decoupling controllers from specific view implementations allows for easier UI refactoring and unit testing.
- **Cost:** Low to Moderate.
- **Risk:** Low.

**Recommendation: IMPLEMENT (TARGETED)**
Do not rewrite the entire communication layer. Focus on:
1.  **Signals over Setters:** Instead of `controller.set_view(tab)`, use `controller.data_ready.connect(tab.update_data)`.
2.  **Flatten Hierarchy:** `VRAMEditorPage` should expose signals/slots that facade its internal children (`edit_tab`, `multi_palette_tab`), preventing `SpriteEditorWorkspace` from reaching in.

---

## 3. Explicit Cache Invalidation Contracts

**Proposal:** Establish clear contracts for when and how caches (Preview, Icon, Index Map) are invalidated.

**Current Status:**
- **CRITICAL FLAW:** `PreviewGenerator` caches results based on `(file_path, offset)`.
- **The Bug:** When `InjectionController` modifies a file (e.g., injects a sprite to ROM), the file content changes, but the `file_path` remains the same.
- **Result:** `PreviewGenerator` continues to serve the **stale** preview from cache because it has no way of knowing the file content changed.
- **No Link:** There is currently **zero** connection between `InjectionController.injection_completed` and `PreviewGenerator.clear_cache()`.

**Assessment:**
- **Problem:** Users see old sprites after editing and injecting, leading to confusion and lack of trust in the tool.
- **Benefit:** Correctness. The application currently displays false information after an edit.
- **Cost:** Low.
- **Risk:** None (Fixing a bug).

**Recommendation: IMPLEMENT NOW**
This is not just a refactor; it is a correctness fix.
1.  **Create Event Bus / Signal:** `ApplicationStateManager` or a new `GlobalSignals` singleton should define `file_modified(path: str)`.
2.  **Wire Injection:** `InjectionController` emits `file_modified` upon success.
3.  **Wire Cache:** `PreviewGenerator` connects to `file_modified`. If the modified path matches a cached entry (or strictly, just clear the cache for that path), invalidate it.
4.  **Scope:** Apply this to `PreviewGenerator`, `SpriteLibrary` (icon cache), and `ROMCache`.

---

## Implementation Plan (Prioritized)

1.  **Immediate (Bug Fix):** Wire `InjectionController.injection_completed` to a mechanism that clears `PreviewGenerator` cache.
    *   *Quick Fix:* In `MainWindow`, connect `injection_completed` -> `preview_generator.clear_cache()`.
2.  **Short Term:** Refactor `VRAMEditorPage` to expose necessary signals/slots, removing `edit_tab.workspace...` chains from `SpriteEditorWorkspace`.
3.  **Long Term (Backlog):** Revisit Action Enablement when adding the next major workspace/mode.
