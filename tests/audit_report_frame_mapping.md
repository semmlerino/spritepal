# Frame Mapping Tests Audit

I have audited the tests for the Frame Mapping subsystem, focusing on `core` data models and the `FrameMappingController`.

## 1. Test: `test_create_mapping_accepts_valid_ids`
**File:** `tests/unit/core/data_models/test_frame_mapping_project.py`

### Intended Behavior
Verify that `FrameMappingProject.create_mapping` creates a `FrameMapping` object when provided with valid non-empty string IDs for an AI frame and a Game frame.

### Observable Outcomes
- Returns a `FrameMapping` object.
- `mapping.ai_frame_id` matches input.
- `mapping.game_frame_id` matches input.

### Sufficiency Judgment
**Insufficient.** The test only checks that the method accepts strings. It fails to verify the most critical constraint of the domain model: **Referential Integrity**.
- It does **not** assert that the `ai_frame_id` corresponds to an existing `AIFrame` in the project.
- It does **not** assert that the `game_frame_id` corresponds to an existing `GameFrame`.
- It allows creating "ghost mappings" to non-existent frames, which causes runtime errors later in the UI (e.g., when generating previews).

### Weaknesses
- **Ghost Mappings:** Passable with `create_mapping("ghost.png", "ghost_game")` even if the project is empty.
- **Missing Side Effects:** Does not check if the internal lookup indices (`_mapping_index_by_ai`, etc.) are updated (though `create_mapping` does call `_invalidate_mapping_index`, the test doesn't verify the result of that side effect).

### Improved Assertion Strategy
```python
def test_create_mapping_enforces_referential_integrity(self) -> None:
    """create_mapping should verify frames exist in the project."""
    project = FrameMappingProject(name="test")
    # Don't add frames to project

    # Should fail because frames don't exist
    with pytest.raises(ValueError, match="AI frame.*not found"):
        project.create_mapping("ghost.png", "G001")
```
*Note: This requires updating the `FrameMappingProject.create_mapping` implementation to actually enforce this, moving the check from Controller to Model.*

---

## 2. Test: `test_create_mapping_without_parent`
**File:** `tests/unit/ui/controllers/test_frame_mapping_controller.py`

### Intended Behavior
Verify that the Controller can create a mapping using its `create_mapping` facade method, even when running in "headless" mode (no Qt parent).

### Observable Outcomes
- `success` is `True`.
- `len(controller.project.mappings) == 1`.

### Sufficiency Judgment
**Partial.** It verifies the "happy path" modification of the underlying project, but ignores the Controller's primary responsibilities: **Signal Emission** and **Undo Stack Management**.
- The controller is an orchestration layer. Its value is notifying the UI (`mapping_created` signal) and enabling rollback (`undo_stack`).
- This test verifies the *Model* behavior (which is already tested in the model tests) rather than the *Controller* behavior.

### Weaknesses
- **Missing Signal Check:** Passes even if `mapping_created` or `save_requested` are never emitted.
- **Implicit Undo:** Assumes undo works because `create_mapping` usually pushes a command, but doesn't explicitly check `_undo_stack.count()`.

### Improved Assertion Strategy
```python
def test_create_mapping_emits_signals(self, qtbot) -> None:
    # ... setup ...
    with qtbot.waitSignals([controller.mapping_created, controller.save_requested]):
        success = controller.create_mapping("frame_001.png", "G001")
    
    assert success
    assert controller._undo_stack.canUndo()
```

---

## 3. Test: `test_inject_mapping_uses_selected_entry_ids_not_rom_offset`
**File:** `tests/unit/ui/controllers/test_frame_mapping_controller.py`

### Intended Behavior
Verify that injection logic filters sprite entries based on the explicit `selected_entry_ids` list rather than broadly matching all entries sharing a ROM offset (which causes "bloated" injection regions).

### Observable Outcomes
- `mock_injector.injected_images` has length 1.
- `img.width <= 16`. (The fail condition is a much wider image, ~100px).

### Sufficiency Judgment
**High.** This is a strong, specific regression test.
- It constructs a specific data scenario (`capture_data`) where the naive logic (ROM offset matching) produces a clearly distinguishable incorrect result (wide image) vs the correct result (narrow image).
- It mocks the expensive/complex dependency (`ROMInjector`) but captures the *data sent to it*, acting as a spy.

### Weaknesses
- **Mock Drift:** It relies on `InjectingMockROMInjector`. If the real `ROMInjector` interface changes (e.g., argument order), this test might pass but the code fail.
- **Indirect Assertion:** Checking `img.width <= 16` is a proxy for "did we filter entries?". A more direct assertion would be inspecting the *intermediate* list of tiles passed to the generation logic, but that might require exposing private methods. The current outcome-based assertion is acceptable and less brittle.

### Improved Assertion Strategy
The current assertion is good. To make it more robust against "naive implementation" (e.g. always returning a small image), one could add a counter-case:
```python
# Add a second test ensuring ALL entries are included if selected_entry_ids matches ALL
project.game_frames[0].selected_entry_ids = [10, 20]
# ... perform injection ...
assert img.width > 100  # Verify it expands when requested
```

---

## 4. General Observations & Naive Implementation Risks

- **Missing "Oracle":** Many tests construct data manually (`create_test_capture`). If the Mesen 2 capture format changes, these tests will still pass but the app will break on real files. **Suggestion:** Add a contract test that parses a *real* (checked-in) Mesen 2 capture file to verify the `create_test_capture` fixture matches reality.
- **Naive Implementations:**
    - `FrameMappingProject.create_mapping`: A naive implementation could just append to the list without checking for existing mappings (breaking 1:1 rule). The tests *do* cover this in `FrameMappingProject` tests (checking list length/uniqueness), so that is covered.
    - `FrameMappingController.create_mapping`: A naive implementation could just call `project.create_mapping` without emitting signals. `test_create_mapping_without_parent` would PASS, but the UI would fail to update.

## 5. Summary
The core logic tests are decent but permissive (allowing ghost mappings). The controller tests are heavy on "integration" logic (injection) but light on "controller" logic (signals/undo) in some places. The injection tests are the strongest part of the suite.
