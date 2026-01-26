"""
Test logging levels configuration.
"""
import logging
from unittest.mock import MagicMock, patch

from utils.logging_config import set_console_debug_mode, setup_logging


def test_console_handler_default_level():
    """Verify console handler defaults to WARNING."""
    with patch("logging.StreamHandler") as mock_stream_handler, \
         patch("logging.handlers.RotatingFileHandler"), \
         patch("logging.getLogger") as mock_get_logger, \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.open", MagicMock()):
        
        mock_console_instance = MagicMock()
        mock_stream_handler.return_value = mock_console_instance
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        # Ensure environment variable is not set
        with patch.dict("os.environ", {}, clear=True):
            setup_logging()
            
            # Verify setLevel was called with WARNING for console
            mock_console_instance.setLevel.assert_any_call(logging.WARNING)

def test_console_handler_debug_mode_level():
    """Verify console handler uses DEBUG when debug mode is enabled."""
    with patch("logging.StreamHandler") as mock_stream_handler, \
         patch("logging.handlers.RotatingFileHandler"), \
         patch("logging.getLogger") as mock_get_logger, \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.open", MagicMock()):
        
        mock_console_instance = MagicMock()
        mock_stream_handler.return_value = mock_console_instance

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        # Ensure environment variable IS set
        with patch.dict("os.environ", {"SPRITEPAL_DEBUG": "1"}, clear=True):
            setup_logging()
            
            # Verify setLevel was called with DEBUG for console
            mock_console_instance.setLevel.assert_any_call(logging.DEBUG)

def test_set_console_debug_mode_toggle():
    """Verify set_console_debug_mode toggles between WARNING and DEBUG."""
    # We need to mock the global _console_handler in logging_config
    with patch("utils.logging_config._console_handler", MagicMock()) as mock_handler:
        # Enable debug
        set_console_debug_mode(True)
        mock_handler.setLevel.assert_called_with(logging.DEBUG)
        
        # Disable debug (should go back to WARNING)
        set_console_debug_mode(False)
        mock_handler.setLevel.assert_called_with(logging.WARNING)
