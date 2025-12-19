"""
Test logging configuration functionality
"""
from __future__ import annotations

import logging
import logging.handlers
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.logging_config import get_logger, setup_logging

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_manager_setup,
]

class TestSetupLogging:
    """Test setup_logging function"""

    def test_setup_logging_default_directory(self):
        """Test setup_logging with default directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock Path.home() to return temp directory
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                logger = setup_logging()

                # Check logger configuration
                assert logger.name == "spritepal"
                assert logger.level == logging.INFO
                assert len(logger.handlers) == 2

                # Check default log directory was created
                expected_log_dir = Path(temp_dir) / ".spritepal" / "logs"
                assert expected_log_dir.exists()
                assert expected_log_dir.is_dir()

                # Check log file was created
                log_file = expected_log_dir / "spritepal.log"
                assert log_file.exists()

    def test_setup_logging_custom_directory(self):
        """Test setup_logging with custom directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_log_dir = Path(temp_dir) / "custom_logs"

            logger = setup_logging(log_dir=custom_log_dir)

            # Check logger configuration
            assert logger.name == "spritepal"
            assert logger.level == logging.INFO

            # Check custom directory was created
            assert custom_log_dir.exists()
            assert custom_log_dir.is_dir()

            # Check log file was created in custom directory
            log_file = custom_log_dir / "spritepal.log"
            assert log_file.exists()

    def test_setup_logging_different_levels(self):
        """Test setup_logging with different log levels"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # Test valid log levels
            test_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            expected_levels = [
                logging.DEBUG,
                logging.INFO,
                logging.WARNING,
                logging.ERROR,
                logging.CRITICAL,
            ]

            for level_str, expected_level in zip(test_levels, expected_levels, strict=False):
                logger = setup_logging(log_dir=log_dir, log_level=level_str)
                assert logger.level == expected_level

    def test_setup_logging_invalid_level(self):
        """Test setup_logging with invalid log level defaults to INFO"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            logger = setup_logging(log_dir=log_dir, log_level="INVALID")
            assert logger.level == logging.INFO

    def test_setup_logging_case_insensitive_level(self):
        """Test setup_logging with case insensitive log levels"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # Test lowercase
            logger = setup_logging(log_dir=log_dir, log_level="debug")
            assert logger.level == logging.DEBUG

            # Test mixed case
            logger = setup_logging(log_dir=log_dir, log_level="WaRnInG")
            assert logger.level == logging.WARNING

    def test_setup_logging_handlers_configuration(self):
        """Test that handlers are configured correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            logger = setup_logging(log_dir=log_dir)

            # Should have exactly 2 handlers
            assert len(logger.handlers) == 2

            # Check handler types using isinstance for better robustness
            has_stream_handler = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
            has_rotating_file_handler = any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers)

            assert has_stream_handler, "Should have a StreamHandler"
            assert has_rotating_file_handler, "Should have a RotatingFileHandler (or subclass)"

            # Check console handler configuration
            console_handler = next(
                h for h in logger.handlers if isinstance(h, logging.StreamHandler)
            )
            assert console_handler.level == logging.INFO
            assert console_handler.formatter is not None

            # Check file handler configuration
            file_handler = next(
                h
                for h in logger.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            )
            assert file_handler.level == logging.DEBUG
            assert file_handler.formatter is not None
            assert file_handler.maxBytes == 5_000_000
            assert file_handler.backupCount == 3

    def test_setup_logging_formatters(self):
        """Test that formatters are configured correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            logger = setup_logging(log_dir=log_dir)

            # Get handlers
            console_handler = next(
                h for h in logger.handlers if isinstance(h, logging.StreamHandler)
            )
            file_handler = next(
                h
                for h in logger.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            )

            # Check formatter formats
            console_format = console_handler.formatter._fmt
            file_format = file_handler.formatter._fmt

            # Console format should be simple
            assert console_format == "%(levelname)s - %(name)s - %(message)s"

            # File format should be detailed
            expected_file_format = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            assert expected_file_format == file_format

    def test_setup_logging_removes_existing_handlers(self):
        """Test that existing handlers are removed"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # Get the logger and clear any existing handlers first
            logger = logging.getLogger("spritepal")
            logger.handlers.clear()

            # Add a fake handler
            fake_handler = logging.StreamHandler()
            logger.addHandler(fake_handler)

            # Initial state - should have our fake handler
            assert len(logger.handlers) == 1
            assert fake_handler in logger.handlers

            # Setup logging should remove existing handlers
            setup_logging(log_dir=log_dir)

            # Should have new handlers, not the old one
            assert len(logger.handlers) == 2
            assert fake_handler not in logger.handlers

    def test_setup_logging_creates_directory_recursively(self):
        """Test that log directory is created recursively"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a nested directory path
            nested_log_dir = Path(temp_dir) / "deeply" / "nested" / "log" / "directory"

            # Directory should not exist initially
            assert not nested_log_dir.exists()

            setup_logging(log_dir=nested_log_dir)

            # Directory should be created
            assert nested_log_dir.exists()
            assert nested_log_dir.is_dir()

            # Log file should be created
            log_file = nested_log_dir / "spritepal.log"
            assert log_file.exists()

    def test_setup_logging_handles_existing_directory(self):
        """Test that existing directories are handled correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "existing_logs"

            # Pre-create the directory
            log_dir.mkdir(parents=True, exist_ok=True)
            assert log_dir.exists()

            # Should not raise an error
            setup_logging(log_dir=log_dir)

            # Should still work correctly
            assert log_dir.exists()
            log_file = log_dir / "spritepal.log"
            assert log_file.exists()

    def test_setup_logging_writes_startup_message(self):
        """Test that startup message is logged"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            setup_logging(log_dir=log_dir)

            # Check that log file contains startup message
            log_file = log_dir / "spritepal.log"
            with open(log_file) as f:
                content = f.read()
                assert "SpritePal Session Started" in content
                assert str(log_file) in content

    def test_setup_logging_actual_logging_works(self):
        """Test that actual logging works correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            logger = setup_logging(log_dir=log_dir, log_level="DEBUG")

            # Test logging at different levels
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")

            # Check log file content
            log_file = log_dir / "spritepal.log"
            with open(log_file) as f:
                content = f.read()
                assert "Debug message" in content
                assert "Info message" in content
                assert "Warning message" in content
                assert "Error message" in content
                assert "Critical message" in content

    def test_setup_logging_file_rotation_config(self):
        """Test that file rotation is configured correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            logger = setup_logging(log_dir=log_dir)

            # Get file handler
            file_handler = next(
                h
                for h in logger.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            )

            # Check rotation settings
            assert file_handler.maxBytes == 5_000_000  # 5MB
            assert file_handler.backupCount == 3
            assert file_handler.baseFilename.endswith("spritepal.log")

    def test_setup_logging_return_value(self):
        """Test that setup_logging returns the correct logger"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            logger = setup_logging(log_dir=log_dir)

            # Should return the spritepal logger
            assert logger is logging.getLogger("spritepal")
            assert logger.name == "spritepal"

    def test_setup_logging_multiple_calls(self):
        """Test that multiple calls to setup_logging work correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # First call
            logger1 = setup_logging(log_dir=log_dir, log_level="DEBUG")
            assert logger1.level == logging.DEBUG
            assert len(logger1.handlers) == 2

            # Second call with different level
            logger2 = setup_logging(log_dir=log_dir, log_level="ERROR")
            assert logger2.level == logging.ERROR
            assert len(logger2.handlers) == 2

            # Should be the same logger instance
            assert logger1 is logger2

    def test_setup_logging_with_permissions_error(self):
        """Test handling of permission errors during directory creation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "restricted"

            # Create a file where we want to create a directory
            log_dir.touch()

            # This should raise an exception since we can't create a directory over a file
            # The actual error depends on the system, but it should be a filesystem error
            with pytest.raises((FileExistsError, NotADirectoryError, OSError)):
                setup_logging(log_dir=log_dir)

class TestGetLogger:
    """Test get_logger function"""

    def test_get_logger_basic_functionality(self):
        """Test basic get_logger functionality"""
        logger = get_logger("test_module")

        assert logger.name == "spritepal.test_module"
        assert isinstance(logger, logging.Logger)

    def test_get_logger_different_modules(self):
        """Test get_logger with different module names"""
        test_modules = [
            "extractor",
            "palette_manager",
            "ui.main_window",
            "core.injector",
        ]

        for module_name in test_modules:
            logger = get_logger(module_name)
            assert logger.name == f"spritepal.{module_name}"

    def test_get_logger_same_module_returns_same_logger(self):
        """Test that get_logger returns the same logger instance for the same module"""
        logger1 = get_logger("test_module")
        logger2 = get_logger("test_module")

        assert logger1 is logger2

    def test_get_logger_inherits_from_parent(self):
        """Test that module loggers inherit from parent spritepal logger"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # Set up parent logger
            parent_logger = setup_logging(log_dir=log_dir, log_level="DEBUG")

            # Get module logger
            module_logger = get_logger("test_module")

            # Module logger should inherit settings from parent
            assert module_logger.parent is parent_logger
            assert module_logger.level == logging.NOTSET  # Should inherit from parent

    def test_get_logger_with_empty_module_name(self):
        """Test get_logger with empty module name"""
        logger = get_logger("")
        assert logger.name == "spritepal."

    def test_get_logger_with_dots_in_module_name(self):
        """Test get_logger with dots in module name"""
        logger = get_logger("ui.widgets.palette_panel")
        assert logger.name == "spritepal.ui.widgets.palette_panel"

    def test_get_logger_works_with_actual_logging(self):
        """Test that get_logger works with actual logging"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # Set up parent logger
            setup_logging(log_dir=log_dir, log_level="DEBUG")

            # Get module logger
            module_logger = get_logger("test_module")

            # Log a message
            module_logger.info("Test message from module")

            # Check that message was logged
            log_file = log_dir / "spritepal.log"
            with open(log_file) as f:
                content = f.read()
                assert "Test message from module" in content
                assert "spritepal.test_module" in content

class TestLoggingIntegration:
    """Test integration between setup_logging and get_logger"""

    def test_logging_integration_workflow(self):
        """Test the typical workflow of setting up logging and getting module loggers"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # Step 1: Set up logging
            main_logger = setup_logging(log_dir=log_dir, log_level="DEBUG")

            # Step 2: Get module loggers
            extractor_logger = get_logger("extractor")
            palette_logger = get_logger("palette_manager")
            ui_logger = get_logger("ui.main_window")

            # Step 3: Use the loggers
            main_logger.info("Application started")
            extractor_logger.debug("Extracting sprites from VRAM")
            palette_logger.warning("Palette data inconsistent")
            ui_logger.error("UI component failed to load")

            # Step 4: Verify all messages are logged
            log_file = log_dir / "spritepal.log"
            with open(log_file) as f:
                content = f.read()
                assert "Application started" in content
                assert "Extracting sprites from VRAM" in content
                assert "Palette data inconsistent" in content
                assert "UI component failed to load" in content
                assert "spritepal.extractor" in content
                assert "spritepal.palette_manager" in content
                assert "spritepal.ui.main_window" in content

    def test_logging_level_inheritance(self):
        """Test that module loggers inherit level from parent"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            # Set up with WARNING level
            setup_logging(log_dir=log_dir, log_level="WARNING")

            # Get module logger
            module_logger = get_logger("test_module")

            # Log at different levels
            module_logger.debug("Debug message")
            module_logger.info("Info message")
            module_logger.warning("Warning message")
            module_logger.error("Error message")

            # Check that only WARNING and above are logged
            log_file = log_dir / "spritepal.log"
            with open(log_file) as f:
                content = f.read()
                assert "Debug message" not in content
                assert "Info message" not in content
                assert "Warning message" in content
                assert "Error message" in content

    def test_logging_with_exception_handling(self):
        """Test logging with exception information"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            setup_logging(log_dir=log_dir, log_level="DEBUG")
            logger = get_logger("test_module")

            # Log exception
            try:
                raise ValueError("Test exception")
            except ValueError:
                logger.exception("An error occurred")

            # Check that exception is logged
            log_file = log_dir / "spritepal.log"
            with open(log_file) as f:
                content = f.read()
                assert "An error occurred" in content
                assert "ValueError: Test exception" in content
                assert "Traceback" in content

if __name__ == "__main__":
    pytest.main([__file__])
