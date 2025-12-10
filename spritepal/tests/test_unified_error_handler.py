"""
Tests for the UnifiedErrorHandler service.

This module tests the comprehensive error handling capabilities including
categorization, context management, recovery suggestions, and integration
with existing patterns.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.managers.exceptions import (
    # Systematic pytest markers applied based on test content analysis
    ExtractionError,
    ValidationError,
)
from utils.unified_error_handler import (
    ErrorCategory,
    ErrorContext,
    ErrorResult,
    ErrorSeverity,
    UnifiedErrorHandler,
)

pytestmark = [
    pytest.mark.headless,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.parallel_safe,
    pytest.mark.rom_data,
    pytest.mark.unit,
    pytest.mark.widget,
    pytest.mark.ci_safe,
    pytest.mark.file_io,
]
@pytest.fixture
def error_handler():
    """Create a fresh error handler for testing without Qt dependencies"""
    # Create mock error display to avoid Qt dependencies
    mock_error_display = MagicMock()
    mock_error_display.handle_critical_error = MagicMock()
    mock_error_display.handle_warning = MagicMock()
    mock_error_display.handle_info = MagicMock()

    return UnifiedErrorHandler(error_display=mock_error_display)

@pytest.fixture
def mock_widget():
    """Create a mock widget for testing"""
    return MagicMock()

class TestUnifiedErrorHandler:
    """Test the core UnifiedErrorHandler functionality"""

    def test_error_categorization(self, error_handler):
        """Test automatic error categorization"""
        test_cases = [
            (FileNotFoundError("file.txt"), ErrorCategory.FILE_IO),
            (ValidationError("invalid"), ErrorCategory.VALIDATION),
            (ExtractionError("failed"), ErrorCategory.EXTRACTION),
            (ValueError("bad value"), ErrorCategory.VALIDATION),
            (RuntimeError("runtime"), ErrorCategory.SYSTEM),
            (InterruptedError(), ErrorCategory.WORKER_THREAD),
            (Exception("unknown"), ErrorCategory.UNKNOWN),
        ]

        for error, expected_category in test_cases:
            category = error_handler._categorize_exception(error)
            assert category == expected_category

    def test_severity_determination(self, error_handler):
        """Test error severity determination"""
        context = ErrorContext(operation="test")

        # Critical errors
        assert error_handler._determine_severity(
            MemoryError(), ErrorCategory.SYSTEM, context
        ) == ErrorSeverity.CRITICAL

        # High severity
        assert error_handler._determine_severity(
            ExtractionError("failed"), ErrorCategory.EXTRACTION, context
        ) == ErrorSeverity.HIGH

        # Medium severity
        assert error_handler._determine_severity(
            FileNotFoundError(), ErrorCategory.FILE_IO, context
        ) == ErrorSeverity.MEDIUM

        # Low severity
        assert error_handler._determine_severity(
            ValidationError("invalid"), ErrorCategory.VALIDATION, context
        ) == ErrorSeverity.LOW

    def test_context_manager(self, error_handler):
        """Test error context manager"""
        with error_handler.error_context("test operation", file_path="test.txt") as context:
            assert context.operation == "test operation"
            assert context.file_path == "test.txt"
            assert len(error_handler._context_stack) == 1

        # Context should be removed after exiting
        assert len(error_handler._context_stack) == 0

    def test_context_manager_with_exception(self, error_handler):
        """Test context manager handles exceptions"""
        with pytest.raises(ValueError), error_handler.error_context("failing operation"):
            raise ValueError("test error")

        # Context should be cleaned up even after exception
        assert len(error_handler._context_stack) == 0

    def test_file_error_handling(self, error_handler):
        """Test file error handling"""
        error = FileNotFoundError("test.txt not found")
        result = error_handler.handle_file_error(
            error, "test.txt", "reading configuration"
        )

        assert isinstance(result, ErrorResult)
        assert result.category == ErrorCategory.FILE_IO
        assert "test.txt" in result.message
        assert "reading configuration" in result.message
        assert len(result.recovery_suggestions) > 0

    def test_validation_error_handling(self, error_handler):
        """Test validation error handling"""
        error = ValidationError("Invalid input format")
        result = error_handler.handle_validation_error(
            error, "validating user input", user_input="bad_data"
        )

        assert result.category == ErrorCategory.VALIDATION
        assert result.severity == ErrorSeverity.LOW
        assert "validating user input" in result.message
        assert len(result.recovery_suggestions) > 0

    def test_worker_error_handling(self, error_handler):
        """Test worker error handling"""
        error = ExtractionError("Extraction failed")
        result = error_handler.handle_worker_error(
            error, "SpriteExtractor", "extracting sprites"
        )

        assert result.category == ErrorCategory.EXTRACTION
        assert result.severity == ErrorSeverity.HIGH
        assert "extracting sprites" in result.message
        assert "SpriteExtractor" in result.technical_details

    def test_recovery_suggestions(self, error_handler):
        """Test recovery suggestion generation"""
        # File not found error
        error = FileNotFoundError("missing.txt")
        context = ErrorContext(operation="reading", file_path="missing.txt")
        suggestions = error_handler._generate_recovery_suggestions(
            error, ErrorCategory.FILE_IO, context
        )

        assert any("file" in s.lower() and "exists" in s.lower() for s in suggestions)

        # Permission error
        error = PermissionError("Access denied")
        suggestions = error_handler._generate_recovery_suggestions(
            error, ErrorCategory.FILE_IO, context
        )

        assert any("permission" in s.lower() for s in suggestions)

    def test_error_history(self, error_handler):
        """Test error history tracking"""
        initial_count = error_handler._error_count

        # Generate some errors
        for i in range(3):
            try:
                raise ValueError(f"test error {i}")
            except Exception as e:
                error_handler.handle_exception(e)

        assert error_handler._error_count == initial_count + 3
        assert len(error_handler._error_history) == 3

    def test_error_statistics(self, error_handler):
        """Test error statistics generation"""
        # Generate different types of errors
        errors = [
            FileNotFoundError("file1"),
            ValidationError("invalid1"),
            ExtractionError("extract1"),
            FileNotFoundError("file2"),
        ]

        for error in errors:
            try:
                raise error
            except Exception as e:
                error_handler.handle_exception(e)

        stats = error_handler.get_error_statistics()

        assert stats["total_errors"] == len(errors)
        assert "file_io" in stats["categories"]
        assert "validation" in stats["categories"]
        assert "extraction" in stats["categories"]
        assert stats["categories"]["file_io"] == 2  # Two file errors

class TestErrorIntegration:
    """Test error integration utilities"""

    def test_error_decorator_creation(self, error_handler):
        """Test error decorator creation functionality"""

        # Test creating a decorator
        decorator = error_handler.create_error_decorator(
            "test operation",
            category=ErrorCategory.VALIDATION
        )

        assert callable(decorator)

        # Test applying decorator to a function
        @decorator
        def test_function():
            raise ValueError("test error")

        # Function should not raise when decorated
        result = test_function()
        assert result is None

    def test_decorator_with_successful_function(self, error_handler):
        """Test decorator with function that doesn't raise"""

        decorator = error_handler.create_error_decorator("test operation")

        @decorator
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

class TestErrorRecovery:
    """Test error recovery mechanisms"""

    def test_retry_suggestions(self, error_handler):
        """Test retry suggestion logic"""
        # Should suggest retry for transient errors
        assert error_handler._should_suggest_retry(
            RuntimeError("temporary"), ErrorCategory.WORKER_THREAD
        )

        # Should not suggest retry for validation errors
        assert not error_handler._should_suggest_retry(
            ValidationError("invalid"), ErrorCategory.VALIDATION
        )

        # Should not suggest retry for permission errors
        assert not error_handler._should_suggest_retry(
            PermissionError("denied"), ErrorCategory.FILE_IO
        )

    def test_abort_suggestions(self, error_handler):
        """Test abort suggestion logic"""
        ErrorContext(operation="test")

        # Should suggest abort for critical errors
        assert error_handler._should_suggest_abort(
            MemoryError(), ErrorSeverity.CRITICAL
        )

        # Should not suggest abort for low severity
        assert not error_handler._should_suggest_abort(
            ValidationError("invalid"), ErrorSeverity.LOW
        )

@pytest.mark.integration
class TestErrorHandlerIntegration:
    """Integration tests with existing error handling patterns"""

    def test_backward_compatibility(self, error_handler):
        """Test that new error handler maintains backward compatibility"""
        # Should work with existing ErrorHandler interface
        assert hasattr(error_handler, "_error_display")

        # Should have required methods
        assert hasattr(error_handler, "handle_exception")
        assert hasattr(error_handler, "handle_file_error")
        assert hasattr(error_handler, "handle_validation_error")
        assert hasattr(error_handler, "handle_worker_error")

    @patch("utils.unified_error_handler.logger")
    def test_logging_integration(self, mock_logger, error_handler):
        """Test integration with logging system"""
        try:
            raise ExtractionError("test extraction error")
        except Exception as e:
            error_handler.handle_exception(e)

        # Should have called logger
        assert mock_logger.error.called or mock_logger.warning.called or mock_logger.info.called

    def test_message_formatting_consistency(self, error_handler):
        """Test that error messages are consistently formatted"""
        test_errors = [
            (FileNotFoundError("test.txt"), "reading file", "test.txt"),
            (ValidationError("invalid input"), "validating data", None),
            (ExtractionError("failed"), "extracting sprites", None),
        ]

        for error, operation, file_path in test_errors:
            context = ErrorContext(operation=operation, file_path=file_path)
            result = error_handler._process_error(
                error, context, error_handler._categorize_exception(error)
            )

            # Message should contain operation context
            assert operation in result.message.lower()

            # Should be user-friendly (not just str(exception))
            assert result.message != str(error)

            # Should have technical details for debugging
            assert len(result.technical_details) > len(result.message)
