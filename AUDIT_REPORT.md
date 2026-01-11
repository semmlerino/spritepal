# UI-Logic Desynchronization Audit Report

## Executive Summary
A comprehensive audit of the sprite editor workflow identified one Critical-severity desynchronization issue in the ROM loading process, where external state (Mesen captures) was incorrectly cleared from the UI. This has been fixed and verified with a new regression test. The remainder of the workflow demonstrates robust synchronization patterns, primarily due to the usage of the `ROMWorkflowController` as a central coordinator that explicitly manages view state transitions.

## UI Reflection Contract Inventory

| UI Surface | Observable State | Source of Truth | Sync Mechanism | Public API |
|------------|------------------|-----------------|----------------|------------|
| **Source Bar** | ROM Path, Size, Header Info | `ROMWorkflowController.rom_path` | Signal: `rom_info_updated` | `set_rom_path`, `set_info` |
| **Source Bar** | Current Offset | `ROMWorkflowController.current_offset` | Direct call from `set_offset` | `set_offset` |
| **Asset Browser** | Mesen Captures (Recent) | `LogWatcher.recent_captures` | Signal: `offset_discovered` | `add_mesen_capture` |
| **Asset Browser** | ROM Sprites | `ROMExtractor` (via Worker) | Worker Signal | `add_rom_sprite` |
| **Canvas** | Pixel Data | `EditingController.current_image` | Direct call via `load_image` | `set_image` (internal to EditTab) |
| **Workflow Action** | Button Text (Open/Save) | `ROMWorkflowController.state` | Signal: `workflow_state_changed` | `set_action_text` |
| **Injection Status** | Success/Fail Message | `ROMExtractor.inject_sprite_to_rom` | Method Return + Dialog | `QMessageBox` (Modal) |

## Findings

### 1. Mesen Captures Lost on ROM Load (FIXED)

*   **Source of Truth:** `LogWatcher` (Global singleton-like service). State persists across ROM loads.
*   **Expected UI Reflection:** The "Mesen Captures" section in the Asset Browser should display recent captures regardless of the currently loaded ROM, or at least re-populate them after a ROM load.
*   **Desynchronization Classification:**
    *   **Failure Mode:** Stale UI / Missing Data. The UI (Asset Browser) was explicitly cleared but not re-populated, causing the view to desync from the `LogWatcher` state.
    *   **Impact:** Medium. Users lost their reference to recently found sprites when switching ROMs, breaking the "Find in Mesen -> Load ROM -> Edit" workflow.
*   **Evidence:**
    *   `ROMWorkflowController.load_rom` calls `self._view.clear_asset_browser()`.
    *   `ROMWorkflowController` failed to call `sync_captures_from_log_watcher()` immediately after.
*   **Fix Implemented:**
    *   Modified `ui/sprite_editor/controllers/rom_workflow_controller.py` to call `self.sync_captures_from_log_watcher()` inside `load_rom` after the view is reset.
*   **Test Coverage:**
    *   New Test: `tests/ui/test_sync_captures_repro.py`
    *   Status: **PASS**

## Test Specification (Reproduction Case)

This test demonstrates the bug by simulating a ROM load and asserting that the `add_mesen_capture` method is called on the view to restore the state.

```python
# tests/ui/test_sync_captures_repro.py

from unittest.mock import MagicMock, patch, ANY
import pytest
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
from core.mesen_integration.log_watcher import CapturedOffset
from datetime import datetime

class TestSyncCapturesRepro:
    # ... (fixtures for mock_view, mock_log_watcher, controller) ...

    @patch("core.rom_validator.ROMValidator.validate_rom_file")
    @patch("core.rom_validator.ROMValidator.validate_rom_header")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.stat")
    def test_mesen_captures_lost_on_rom_load(self, mock_stat, mock_exists, mock_validate_header, mock_validate_file, controller, mock_view, mock_log_watcher):
        """
        Observable Contract: Mesen captures must persist in the Asset Browser after loading a new ROM.
        Why it fails (before fix): load_rom() clears the browser but fails to re-add global captures.
        """
        # Setup mocks
        mock_exists.return_value = True
        mock_stat.return_value.st_size = 1024 * 1024
        mock_validate_file.return_value = (True, "")
        mock_header = MagicMock()
        mock_header.title = "Test ROM"
        mock_validate_header.return_value = (mock_header, None)
        
        # 1. Setup State: LogWatcher has 1 capture
        capture = CapturedOffset(
            offset=0x123456, 
            frame=123, 
            timestamp=datetime.now(), 
            raw_line="raw"
        )
        mock_log_watcher.recent_captures = [capture]
        
        # 2. Trigger: Set View (Initial Sync)
        controller.set_view(mock_view)
        
        # 3. Trigger: Load ROM (The destructive action)
        controller.load_rom("test.sfc")
        
        # 4. Assertion: Verify browser was cleared AND re-populated
        mock_view.clear_asset_browser.assert_called()
        # This assertion failed before the fix:
        mock_view.add_mesen_capture.assert_called_with(ANY, 0x123456)
```
