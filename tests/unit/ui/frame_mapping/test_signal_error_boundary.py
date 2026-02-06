"""Tests for signal_error_boundary decorator."""

from __future__ import annotations

import logging

import pytest

from ui.frame_mapping.signal_error_handling import signal_error_boundary


class TestSignalErrorBoundary:
    """Tests for the @signal_error_boundary() decorator."""

    def test_successful_call_returns_normally(self) -> None:
        """Decorated function returns its value when no exception."""

        @signal_error_boundary()
        def handler() -> str:
            return "ok"

        result = handler()
        assert result == "ok"

    def test_exception_is_caught_and_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Exception in handler is caught, logged, and does not propagate."""

        @signal_error_boundary()
        def exploding_handler() -> None:
            raise ValueError("boom")

        with caplog.at_level(logging.ERROR):
            exploding_handler()  # Should not raise

        assert "exploding_handler" in caplog.text
        assert "boom" in caplog.text

    def test_custom_handler_name_appears_in_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Custom handler_name is used in the log message."""

        @signal_error_boundary(handler_name="custom_name")
        def handler() -> None:
            raise RuntimeError("fail")

        with caplog.at_level(logging.ERROR):
            handler()

        assert "custom_name" in caplog.text

    def test_arguments_are_passed_through(self) -> None:
        """Arguments are correctly forwarded to the wrapped function."""
        received: list[tuple] = []

        @signal_error_boundary()
        def handler(a: int, b: str, *, c: bool = False) -> None:
            received.append((a, b, c))

        handler(1, "two", c=True)
        assert received == [(1, "two", True)]

    def test_returns_none_on_exception(self) -> None:
        """Decorated function returns None when exception occurs."""

        @signal_error_boundary()
        def handler() -> str:
            raise TypeError("oops")

        result = handler()
        assert result is None
