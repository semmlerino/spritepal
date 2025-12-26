from __future__ import annotations

import pytest

"""
Test suite for ConsoleErrorHandler implementation.

This verifies that the ConsoleErrorHandler properly logs errors instead of
silently swallowing them like the old MockErrorHandler did.
"""

import io
import unittest
from unittest.mock import patch

from core.console_error_handler import ConsoleErrorHandler

# Mark as no_manager_setup - pure unit tests for console error handling
pytestmark = [
    pytest.mark.no_manager_setup,
    pytest.mark.headless,
    pytest.mark.allows_registry_state(reason="Pure unit test, no managers used"),
]


class TestConsoleErrorHandler(unittest.TestCase):
    """Test the ConsoleErrorHandler implementation"""

    def setUp(self):
        """Set up test environment"""
        self.handler = ConsoleErrorHandler()

    def test_handle_exception_logs_to_stderr(self):
        """Test that exceptions are properly logged to stderr"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            test_exception = ValueError("Test exception")
            self.handler.handle_exception(test_exception, "test context")

            stderr_output = mock_stderr.getvalue()
            self.assertIn("ERROR [test context]", stderr_output)
            self.assertIn("Test exception", stderr_output)

    def test_handle_critical_error_logs_prominently(self):
        """Test that critical errors are logged with emphasis"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            self.handler.handle_critical_error("Critical Title", "Critical message")

            stderr_output = mock_stderr.getvalue()
            self.assertIn("CRITICAL ERROR", stderr_output)
            self.assertIn("Critical Title", stderr_output)
            self.assertIn("Critical message", stderr_output)
            self.assertIn("=" * 60, stderr_output)  # Check for emphasis

    def test_handle_warning_logs_to_stderr(self):
        """Test that warnings are logged to stderr"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            self.handler.handle_warning("Warning Title", "Warning message")

            stderr_output = mock_stderr.getvalue()
            self.assertIn("WARNING", stderr_output)
            self.assertIn("Warning Title", stderr_output)
            self.assertIn("Warning message", stderr_output)

    def test_handle_info_logs_to_stdout(self):
        """Test that info messages are logged to stdout"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.handler.handle_info("Info Title", "Info message")

            stdout_output = mock_stdout.getvalue()
            self.assertIn("INFO", stdout_output)
            self.assertIn("Info Title", stdout_output)
            self.assertIn("Info message", stdout_output)

    def test_handle_validation_error_includes_context(self):
        """Test that validation errors include all context information"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            test_error = ValueError("Invalid input")
            self.handler.handle_validation_error(
                test_error, "input validation", user_input="bad_value", field="test_field"
            )

            stderr_output = mock_stderr.getvalue()
            self.assertIn("VALIDATION ERROR", stderr_output)
            self.assertIn("Invalid input", stderr_output)
            self.assertIn("input validation", stderr_output)
            self.assertIn("bad_value", stderr_output)
            self.assertIn("test_field", stderr_output)

    def test_error_count_tracking(self):
        """Test that error counts are properly tracked"""
        self.assertEqual(self.handler.get_error_count(), 0)
        self.assertEqual(self.handler.get_warning_count(), 0)

        # Generate some errors and warnings
        self.handler.handle_exception(Exception("test"), "context")
        self.handler.handle_critical_error("title", "message")
        self.handler.handle_validation_error(Exception("test"), "context")
        self.assertEqual(self.handler.get_error_count(), 3)

        self.handler.handle_warning("title", "message")
        self.handler.handle_warning("title2", "message2")
        self.assertEqual(self.handler.get_warning_count(), 2)

        # Test reset
        self.handler.reset_counts()
        self.assertEqual(self.handler.get_error_count(), 0)
        self.assertEqual(self.handler.get_warning_count(), 0)

    def test_set_show_dialogs_is_noop(self):
        """Test that set_show_dialogs is a no-op for console handler."""
        # Console handler should never show dialogs
        self.assertFalse(self.handler._show_dialogs)

        # Method is a no-op - calling it shouldn't change anything
        self.handler.set_show_dialogs()
        self.assertFalse(self.handler._show_dialogs)

    def test_repr_shows_counts(self):
        """Test that string representation shows error/warning counts"""
        self.handler.handle_exception(Exception("test"), "context")
        self.handler.handle_warning("title", "message")

        repr_str = repr(self.handler)
        self.assertIn("ConsoleErrorHandler", repr_str)
        self.assertIn("errors=1", repr_str)
        self.assertIn("warnings=1", repr_str)

    def test_no_silent_failures(self):
        """Test that errors are not silently swallowed (unlike MockErrorHandler)"""
        # This is the key difference from MockErrorHandler
        # All errors should produce output

        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            # Test various error types
            self.handler.handle_exception(RuntimeError("Runtime error"), "runtime")
            self.handler.handle_critical_error("Critical", "Very bad")
            self.handler.handle_validation_error(ValueError("Bad value"), "validation")

            stderr_output = mock_stderr.getvalue()

            # Verify all errors produced output (not silently swallowed)
            self.assertGreater(len(stderr_output), 0)
            self.assertIn("Runtime error", stderr_output)
            self.assertIn("Very bad", stderr_output)
            self.assertIn("Bad value", stderr_output)


class TestControllerErrorHandlerFallback(unittest.TestCase):
    """Test that the controller properly uses ConsoleErrorHandler as fallback"""

    def test_console_handler_is_proper_replacement(self):
        """Test that ConsoleErrorHandler is a proper replacement for MockErrorHandler"""
        handler = ConsoleErrorHandler()

        # Verify all required methods exist
        self.assertTrue(hasattr(handler, "handle_exception"))
        self.assertTrue(hasattr(handler, "handle_critical_error"))
        self.assertTrue(hasattr(handler, "handle_warning"))
        self.assertTrue(hasattr(handler, "handle_info"))
        self.assertTrue(hasattr(handler, "handle_validation_error"))
        self.assertTrue(hasattr(handler, "set_show_dialogs"))

        # Verify they actually log errors (not silently swallow them)
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            handler.handle_exception(Exception("Test"), "context")
            self.assertIn("Test", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
