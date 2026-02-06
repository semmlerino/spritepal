"""Tests for UndoRedoStack."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ui.frame_mapping.undo import UndoRedoStack


@dataclass
class MockCommand:
    """Mock command for testing stack behavior."""

    description: str = "Test command"
    execute_count: int = field(default=0, repr=False)
    undo_count: int = field(default=0, repr=False)

    def execute(self) -> None:
        self.execute_count += 1

    def undo(self) -> None:
        self.undo_count += 1


class TestUndoRedoStack:
    """Tests for UndoRedoStack behavior."""

    def test_initial_state(self, qtbot: object) -> None:
        """Stack starts empty with nothing to undo/redo."""
        stack = UndoRedoStack()
        assert not stack.can_undo()
        assert not stack.can_redo()
        assert stack.undo_description() is None
        assert stack.redo_description() is None

    def test_push_executes_command(self, qtbot: object) -> None:
        """Pushing a command executes it immediately."""
        stack = UndoRedoStack()
        cmd = MockCommand()

        stack.push(cmd)

        assert cmd.execute_count == 1
        assert cmd.undo_count == 0

    def test_push_enables_undo(self, qtbot: object) -> None:
        """After push, undo becomes available."""
        stack = UndoRedoStack()
        cmd = MockCommand(description="Create mapping")

        stack.push(cmd)

        assert stack.can_undo()
        assert stack.undo_description() == "Create mapping"

    def test_undo_reverses_command(self, qtbot: object) -> None:
        """Undo calls the command's undo method."""
        stack = UndoRedoStack()
        cmd = MockCommand(description="Test action")
        stack.push(cmd)

        result = stack.undo()

        assert result == "Test action"
        assert cmd.undo_count == 1

    def test_undo_enables_redo(self, qtbot: object) -> None:
        """After undo, redo becomes available."""
        stack = UndoRedoStack()
        cmd = MockCommand(description="Test action")
        stack.push(cmd)

        stack.undo()

        assert stack.can_redo()
        assert stack.redo_description() == "Test action"
        assert not stack.can_undo()

    def test_redo_reexecutes_command(self, qtbot: object) -> None:
        """Redo calls execute again."""
        stack = UndoRedoStack()
        cmd = MockCommand(description="Test action")
        stack.push(cmd)
        stack.undo()

        result = stack.redo()

        assert result == "Test action"
        assert cmd.execute_count == 2  # Once on push, once on redo
        assert cmd.undo_count == 1

    def test_push_clears_redo_stack(self, qtbot: object) -> None:
        """New command clears redo history."""
        stack = UndoRedoStack()
        cmd1 = MockCommand(description="First")
        cmd2 = MockCommand(description="Second")

        stack.push(cmd1)
        stack.undo()
        assert stack.can_redo()

        stack.push(cmd2)
        assert not stack.can_redo()

    def test_multiple_undo_redo(self, qtbot: object) -> None:
        """Multiple commands can be undone/redone in order."""
        stack = UndoRedoStack()
        cmd1 = MockCommand(description="First")
        cmd2 = MockCommand(description="Second")
        cmd3 = MockCommand(description="Third")

        stack.push(cmd1)
        stack.push(cmd2)
        stack.push(cmd3)

        # Undo all three
        assert stack.undo() == "Third"
        assert stack.undo() == "Second"
        assert stack.undo() == "First"
        assert not stack.can_undo()

        # Redo all three
        assert stack.redo() == "First"
        assert stack.redo() == "Second"
        assert stack.redo() == "Third"
        assert not stack.can_redo()

    def test_clear_resets_stack(self, qtbot: object) -> None:
        """Clear removes all history."""
        stack = UndoRedoStack()
        stack.push(MockCommand())
        stack.push(MockCommand())
        stack.undo()

        stack.clear()

        assert not stack.can_undo()
        assert not stack.can_redo()

    def test_undo_empty_returns_none(self, qtbot: object) -> None:
        """Undo on empty stack returns None."""
        stack = UndoRedoStack()
        assert stack.undo() is None

    def test_redo_empty_returns_none(self, qtbot: object) -> None:
        """Redo on empty redo stack returns None."""
        stack = UndoRedoStack()
        stack.push(MockCommand())
        # No undo yet, so redo stack is empty
        assert stack.redo() is None

    def test_history_limit_enforced(self, qtbot: object) -> None:
        """Stack enforces maximum history size."""
        stack = UndoRedoStack(max_history=3)

        for i in range(5):
            stack.push(MockCommand(description=f"Cmd {i}"))

        # Should only keep last 3
        assert stack.can_undo()
        assert stack.undo() == "Cmd 4"
        assert stack.undo() == "Cmd 3"
        assert stack.undo() == "Cmd 2"
        assert not stack.can_undo()  # Cmd 0, 1 were dropped


class TestUndoRedoStackSignals:
    """Tests for stack signal emissions."""

    def test_push_emits_can_undo_changed(self, qtbot: object) -> None:
        """Push emits can_undo_changed(True)."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        stack = UndoRedoStack()

        with qtbot.waitSignal(stack.can_undo_changed, timeout=1000) as blocker:
            stack.push(MockCommand())

        assert blocker.args == [True]

    def test_undo_emits_can_redo_changed(self, qtbot: object) -> None:
        """Undo emits can_redo_changed(True)."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        stack = UndoRedoStack()
        stack.push(MockCommand())

        with qtbot.waitSignal(stack.can_redo_changed, timeout=1000) as blocker:
            stack.undo()

        assert blocker.args == [True]

    def test_clear_emits_signals(self, qtbot: object) -> None:
        """Clear emits both changed signals with False."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        stack = UndoRedoStack()
        stack.push(MockCommand())

        signals_received: list[tuple[str, bool]] = []
        stack.can_undo_changed.connect(lambda v: signals_received.append(("undo", v)))
        stack.can_redo_changed.connect(lambda v: signals_received.append(("redo", v)))

        stack.clear()

        assert ("undo", False) in signals_received
        assert ("redo", False) in signals_received

    def test_undo_returns_none_on_exception(self, qtbot: object) -> None:
        """Undo returns None when command raises exception."""
        stack = UndoRedoStack()

        class FailingCommand:
            """Command that fails on undo."""

            description = "Failing"

            def execute(self) -> None:
                pass

            def undo(self) -> None:
                raise RuntimeError("undo failed")

        cmd = FailingCommand()
        stack.push(cmd)  # This calls execute(), which succeeds

        result = stack.undo()
        assert result is None

    def test_redo_returns_none_on_exception(self, qtbot: object) -> None:
        """Redo returns None when command raises exception."""
        stack = UndoRedoStack()

        class FailOnRedoCommand:
            """Command that fails on second execute (redo)."""

            description = "FailOnRedo"

            def __init__(self) -> None:
                self._call_count = 0

            def execute(self) -> None:
                self._call_count += 1
                if self._call_count > 1:
                    raise RuntimeError("redo failed")

            def undo(self) -> None:
                pass

        cmd = FailOnRedoCommand()
        stack.push(cmd)  # execute succeeds (call_count=1)
        stack.undo()  # undo succeeds, moves to redo stack

        result = stack.redo()  # execute fails (call_count=2)
        assert result is None
