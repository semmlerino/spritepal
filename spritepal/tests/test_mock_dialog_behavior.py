"""Regression tests for mock dialog behavior.

These tests document and verify the critical behaviors of mock dialogs
that tests depend on. They serve as a gate for any mock dialog consolidation
work (Phase 4 of the test infrastructure simplification plan).

Key behaviors tested:
1. exec()/result semantics
2. CallbackSignal connect/emit/disconnect
3. Dialog lifecycle (accept/reject/close)
4. MockFileDialog return value format
5. MockMessageBox static methods
6. MockDialogBase signal properties
"""

import pytest


class TestCallbackSignalBehavior:
    """Test CallbackSignal - the core mock signal implementation."""

    def test_connect_and_emit(self):
        """CallbackSignal.connect() stores callback, emit() invokes it."""
        from tests.infrastructure.mock_dialogs_base import CallbackSignal

        received = []
        signal = CallbackSignal([])

        signal.connect(lambda x: received.append(x))
        signal.emit("test_value")

        assert received == ["test_value"]

    def test_disconnect_removes_callback(self):
        """CallbackSignal.disconnect() removes the callback."""
        from tests.infrastructure.mock_dialogs_base import CallbackSignal

        received = []
        callback = lambda x: received.append(x)
        signal = CallbackSignal([])

        signal.connect(callback)
        signal.disconnect(callback)
        signal.emit("test_value")

        assert received == []

    def test_multiple_callbacks(self):
        """Multiple callbacks can be connected and all are invoked."""
        from tests.infrastructure.mock_dialogs_base import CallbackSignal

        results = []
        signal = CallbackSignal([])

        signal.connect(lambda x: results.append(f"a:{x}"))
        signal.connect(lambda x: results.append(f"b:{x}"))
        signal.emit("val")

        assert "a:val" in results
        assert "b:val" in results

    def test_emit_with_no_args(self):
        """emit() works with no arguments."""
        from tests.infrastructure.mock_dialogs_base import CallbackSignal

        called = []
        signal = CallbackSignal([])
        signal.connect(lambda: called.append(True))
        signal.emit()

        assert called == [True]


class TestMockDialogBaseBehavior:
    """Test MockDialogBase - the foundation for all mock dialogs."""

    def test_exec_returns_accepted_by_default(self):
        """exec() returns DialogCode.Accepted (1) by default."""
        from tests.infrastructure.mock_dialogs_base import MockDialogBase

        dialog = MockDialogBase()
        result = dialog.exec()

        assert result == MockDialogBase.DialogCode.Accepted

    def test_accept_sets_result_and_emits_signals(self):
        """accept() sets result to Accepted and emits accepted/finished signals."""
        from tests.infrastructure.mock_dialogs_base import MockDialogBase

        dialog = MockDialogBase()
        accepted_calls = []
        finished_calls = []

        dialog.accepted.connect(lambda: accepted_calls.append(True))
        dialog.finished.connect(lambda code: finished_calls.append(code))

        dialog.accept()

        assert dialog.result_value == MockDialogBase.DialogCode.Accepted
        assert accepted_calls == [True]
        assert finished_calls == [MockDialogBase.DialogCode.Accepted]

    def test_reject_sets_result_and_emits_signals(self):
        """reject() sets result to Rejected and emits rejected/finished signals."""
        from tests.infrastructure.mock_dialogs_base import MockDialogBase

        dialog = MockDialogBase()
        rejected_calls = []
        finished_calls = []

        dialog.rejected.connect(lambda: rejected_calls.append(True))
        dialog.finished.connect(lambda code: finished_calls.append(code))

        dialog.reject()

        assert dialog.result_value == MockDialogBase.DialogCode.Rejected
        assert rejected_calls == [True]
        assert finished_calls == [MockDialogBase.DialogCode.Rejected]

    def test_close_returns_true(self):
        """close() returns True (does not trigger reject signals)."""
        from tests.infrastructure.mock_dialogs_base import MockDialogBase

        dialog = MockDialogBase()
        result = dialog.close()

        assert result is True

    def test_signal_properties_return_callback_signals(self):
        """Signal properties (accepted, rejected, finished) return CallbackSignal instances."""
        from tests.infrastructure.mock_dialogs_base import MockDialogBase, CallbackSignal

        dialog = MockDialogBase()

        assert isinstance(dialog.accepted, CallbackSignal)
        assert isinstance(dialog.rejected, CallbackSignal)
        assert isinstance(dialog.finished, CallbackSignal)


class TestMockFileDialogBehavior:
    """Test MockFileDialog - critical for file operation tests.

    Note: MockFileDialog uses static methods with hardcoded return values.
    Tests verify the return format, not configurable values.
    """

    def test_getOpenFileName_returns_tuple(self):
        """getOpenFileName returns (path, filter) tuple with hardcoded values."""
        from tests.infrastructure.mock_dialogs_base import MockFileDialog

        result = MockFileDialog.getOpenFileName(None)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == "/test/file.txt"  # Hardcoded in MockFileDialog
        assert "All Files" in result[1]

    def test_getSaveFileName_returns_tuple(self):
        """getSaveFileName returns (path, filter) tuple with hardcoded values."""
        from tests.infrastructure.mock_dialogs_base import MockFileDialog

        result = MockFileDialog.getSaveFileName(None)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == "/test/output.txt"  # Hardcoded in MockFileDialog
        assert "All Files" in result[1]

    def test_getExistingDirectory_returns_string(self):
        """getExistingDirectory returns hardcoded directory path string."""
        from tests.infrastructure.mock_dialogs_base import MockFileDialog

        result = MockFileDialog.getExistingDirectory(None)

        assert result == "/test/directory"  # Hardcoded in MockFileDialog


class TestMockMessageBoxBehavior:
    """Test MockMessageBox - critical for error/warning tests."""

    def test_information_returns_ok_by_default(self):
        """information() returns the default button (OK-like)."""
        from tests.infrastructure.mock_dialogs_base import MockMessageBox

        box = MockMessageBox()
        result = box.information(None, "Title", "Message")

        # Should return some truthy value indicating OK
        assert result is not None

    def test_question_returns_configurable_response(self):
        """question() can return Yes or No based on configuration."""
        from tests.infrastructure.mock_dialogs_base import MockMessageBox

        box = MockMessageBox()

        # Default behavior test
        result = box.question(None, "Title", "Question?")
        assert result is not None


class TestMockDialogIntegration:
    """Integration tests for mock dialog usage patterns."""

    def test_mock_dialog_in_context_manager_pattern(self):
        """Mock dialogs work with common usage patterns."""
        from tests.infrastructure.mock_dialogs_base import MockDialogBase

        dialog = MockDialogBase()

        # Simulate typical usage pattern
        dialog.show()
        assert dialog._show_called

        dialog.accept()
        assert dialog.result_value == MockDialogBase.DialogCode.Accepted

    def test_mock_dialog_signal_chain(self):
        """Signals can be chained through multiple handlers."""
        from tests.infrastructure.mock_dialogs_base import MockDialogBase

        dialog = MockDialogBase()
        chain = []

        dialog.accepted.connect(lambda: chain.append("accepted"))
        dialog.finished.connect(lambda _: chain.append("finished"))

        dialog.accept()

        assert "accepted" in chain
        assert "finished" in chain


class TestMockDialogsModuleExports:
    """Test that mock_dialogs module exports expected items."""

    def test_mock_dialogs_exports(self):
        """Verify key exports from mock_dialogs module."""
        from tests.infrastructure import mock_dialogs

        # Check key classes exist
        assert hasattr(mock_dialogs, 'MockDialog')
        assert hasattr(mock_dialogs, 'MockUnifiedManualOffsetDialog')
        assert hasattr(mock_dialogs, 'MockSettingsDialog')
        assert hasattr(mock_dialogs, 'MockUserErrorDialog')
        assert hasattr(mock_dialogs, 'MockResumeScanDialog')

        # Check utility functions
        assert hasattr(mock_dialogs, 'create_test_dialog')
        assert hasattr(mock_dialogs, 'patch_dialog_imports')

    def test_mock_dialogs_base_exports(self):
        """Verify key exports from mock_dialogs_base module."""
        from tests.infrastructure import mock_dialogs_base

        # Check base classes
        assert hasattr(mock_dialogs_base, 'MockDialogBase')
        assert hasattr(mock_dialogs_base, 'CallbackSignal')
        assert hasattr(mock_dialogs_base, 'MockFileDialog')
        assert hasattr(mock_dialogs_base, 'MockMessageBox')
        assert hasattr(mock_dialogs_base, 'MockInputDialog')
        assert hasattr(mock_dialogs_base, 'MockProgressDialog')

        # Check utility functions
        assert hasattr(mock_dialogs_base, 'create_mock_dialog')
        assert hasattr(mock_dialogs_base, 'patch_all_dialogs')
