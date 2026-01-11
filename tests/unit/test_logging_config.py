"""
Test logging configuration functionality - essential smoke tests only.

Most tests removed as they just verify Python's logging module API.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.logging_config import get_logger, setup_logging

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_manager_setup,
]


class TestSetupLogging:
    """Test setup_logging function - essential tests only."""

    def test_setup_logging_default_directory(self):
        """Test setup_logging creates log file in default directory (project-relative)."""
        # Default log directory is now relative to the project, not user home
        logger = setup_logging()

        assert logger.name == "spritepal"
        assert logger.level == logging.INFO

        # The default log directory is the 'logs' folder in the project root
        # This is 3 levels up from this test file: tests/unit/test_logging_config.py
        expected_log_dir = Path(__file__).parent.parent.parent / "logs"
        assert expected_log_dir.exists()

        log_file = expected_log_dir / "spritepal.log"
        assert log_file.exists()

    def test_setup_logging_custom_directory(self):
        """Test setup_logging with custom directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_log_dir = Path(temp_dir) / "custom_logs"

            logger = setup_logging(log_dir=custom_log_dir)

            assert logger.name == "spritepal"
            assert custom_log_dir.exists()

            log_file = custom_log_dir / "spritepal.log"
            assert log_file.exists()


class TestGetLogger:
    """Test get_logger function - essential tests only."""

    def test_get_logger_returns_child_logger(self):
        """Test get_logger returns child of spritepal logger."""
        logger = get_logger("test_module")

        assert logger.name == "spritepal.test_module"
        assert isinstance(logger, logging.Logger)

    def test_get_logger_same_module_returns_same_logger(self):
        """Test get_logger returns same instance for same module."""
        logger1 = get_logger("test_module")
        logger2 = get_logger("test_module")

        assert logger1 is logger2


class TestLoggingIntegration:
    """Integration test for the logging workflow."""

    def test_logging_integration_workflow(self):
        """Test complete workflow: setup_logging + get_logger + logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            setup_logging(log_dir=log_dir, log_level="DEBUG")

            module_logger = get_logger("extractor")
            module_logger.info("Test message from module")

            log_file = log_dir / "spritepal.log"
            with log_file.open() as f:
                content = f.read()
                assert "Test message from module" in content
                assert "spritepal.extractor" in content
