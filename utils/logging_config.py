"""Logging configuration for SpritePal"""

from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import UTC, datetime
from pathlib import Path

# Global reference to console handler for dynamic updates
_console_handler: logging.Handler | None = None

# Track disabled logging categories (relative to spritepal.*, e.g., "core.rom_extractor")
_disabled_categories: set[str] = {
    "core.rom_extractor",
    "core.tile_renderer",
    "ui.workers.batch_thumbnail_worker",
    "core.mesen_integration.tile_hash_database",
    "core.mesen_integration.rom_tile_matcher",
    "core.hal_compression",
    "core.rom_injector",
    "ui.workers",
}

# Known noisy categories for UI display
NOISY_CATEGORIES: dict[str, str] = {
    "core.rom_extractor": "ROM Extraction",
    "core.tile_renderer": "Tile Rendering",
    "ui.workers.batch_thumbnail_worker": "Thumbnail Worker",
    "core.mesen_integration.tile_hash_database": "Tile Hash Database",
    "core.rom_tile_matcher": "ROM Tile Matcher",
    "core.hal_compression": "HAL Compression",
    "core.rom_injector": "ROM Injection",
    "ui.workers": "All UI Workers",
}


def setup_logging(log_dir: Path | None = None, log_level: str = "INFO") -> logging.Logger:
    """
    Configure application-wide logging.

    Args:
        log_dir: Directory for log files (defaults to current directory)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Check for debug mode from environment
    debug_mode = os.environ.get("SPRITEPAL_DEBUG", "").lower() in ("1", "true", "yes")
    if debug_mode:
        log_level = "DEBUG"

    # Use default directory within the spritepal project
    if log_dir is None:
        log_dir = Path(__file__).parent.parent / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger for spritepal
    logger = logging.getLogger("spritepal")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler - use detailed format if debug mode is enabled
    global _console_handler
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.DEBUG if debug_mode else logging.WARNING)

    if debug_mode:
        # Detailed format for debug mode (matches file format)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
    else:
        # Simplified format for normal mode
        console_formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")

    _console_handler.setFormatter(console_formatter)

    # File handler with detailed format - clear on startup
    log_file = log_dir / "spritepal.log"

    # Clear the log file on startup by opening in write mode first
    try:
        with log_file.open("w") as f:
            _ = f.write("")  # Clear the file
    except Exception:
        # If we can't clear it, that's okay, just continue
        pass

    # File handler with rotating logs
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5_000_000,
            backupCount=3,  # 5MB
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except (FileNotFoundError, OSError):
        # If file handler creation fails, continue with console only
        pass

    logger.addHandler(_console_handler)

    # Log startup banner
    logger.info("=" * 80)
    logger.info(f"SpritePal Session Started - {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"Log Level: {log_level}")
    logger.info(f"Log File: {log_file}")
    logger.info(f"Working Directory: {Path.cwd()}")
    logger.info("=" * 80)

    # Log debug mode status if enabled
    if log_level == "DEBUG":
        logger.debug("Debug mode enabled via SPRITEPAL_DEBUG environment variable")

    # Apply default disabled categories
    for category in _disabled_categories:
        full_name = f"spritepal.{category}"
        logging.getLogger(full_name).setLevel(logging.CRITICAL + 1)

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        module_name: Name of the module requesting the logger

    Returns:
        Logger instance for the module
    """
    logger = logging.getLogger(f"spritepal.{module_name}")

    # CRITICAL FIX: Ensure logging is configured for test environments
    # This prevents FileNotFoundError during threaded operations in tests
    root_spritepal_logger = logging.getLogger("spritepal")

    # If the spritepal logger has no handlers, configure minimal logging
    # This happens in test environments where setup_logging() wasn't called
    if not root_spritepal_logger.handlers:
        # Configure console-only logging for test environment
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)  # Allow all levels for test capture
        console_formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
        console_handler.setFormatter(console_formatter)

        root_spritepal_logger.addHandler(console_handler)
        root_spritepal_logger.setLevel(logging.DEBUG)  # Allow all levels for tests

        # Keep propagation enabled for test logging capture to work
        # This allows pytest's caplog to capture messages
        root_spritepal_logger.propagate = True

    return logger


def set_console_debug_mode(enabled: bool) -> None:
    """
    Dynamically update console logging to debug mode.

    This allows toggling detailed console output (with timestamp, filename, line number)
    without restarting the application.

    Args:
        enabled: True for detailed debug format, False for simplified format
    """
    global _console_handler  # noqa: PLW0602

    if _console_handler is None:
        # Logging not initialized yet - this can happen during early startup
        return

    # Update console level
    _console_handler.setLevel(logging.DEBUG if enabled else logging.WARNING)

    # Update console formatter
    if enabled:
        # Detailed format for debug mode (matches file format)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s")
    else:
        # Simplified format for normal mode
        formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")

    _console_handler.setFormatter(formatter)

    # Also update root spritepal logger level to allow DEBUG messages
    spritepal_logger = logging.getLogger("spritepal")
    spritepal_logger.setLevel(logging.DEBUG if enabled else logging.INFO)


def set_category_enabled(category: str, enabled: bool) -> None:
    """
    Enable or disable logging for a specific category.

    The category name is relative to 'spritepal.', e.g., 'core.rom_extractor'
    will control the 'spritepal.core.rom_extractor' logger.

    Disabling a parent category (e.g., 'ui.workers') also silences all children
    (e.g., 'ui.workers.batch_thumbnail_worker').

    Args:
        category: The category name relative to spritepal (e.g., 'core.rom_extractor')
        enabled: True to enable logging, False to disable
    """
    full_name = f"spritepal.{category}"
    logger = logging.getLogger(full_name)

    if enabled:
        _disabled_categories.discard(category)
        # Restore to parent's level (inherit from spritepal)
        logger.setLevel(logging.NOTSET)
    else:
        _disabled_categories.add(category)
        # Set to a level higher than CRITICAL to suppress all output
        logger.setLevel(logging.CRITICAL + 1)


def is_category_enabled(category: str) -> bool:
    """
    Check if a logging category is enabled.

    Args:
        category: The category name relative to spritepal

    Returns:
        True if the category is enabled, False if disabled
    """
    return category not in _disabled_categories


def get_disabled_categories() -> set[str]:
    """
    Get the set of currently disabled logging categories.

    Returns:
        Set of disabled category names (relative to spritepal)
    """
    return _disabled_categories.copy()


def set_disabled_categories(categories: set[str]) -> None:
    """
    Set the disabled categories from a collection (typically from saved settings).

    This replaces the current disabled set and updates all affected loggers.

    Args:
        categories: Set of category names to disable (relative to spritepal)
    """
    global _disabled_categories

    # First, re-enable all currently disabled categories
    for category in _disabled_categories:
        full_name = f"spritepal.{category}"
        logging.getLogger(full_name).setLevel(logging.NOTSET)

    # Then set the new disabled categories
    _disabled_categories = set(categories)

    # Apply the new disabled state
    for category in _disabled_categories:
        full_name = f"spritepal.{category}"
        logging.getLogger(full_name).setLevel(logging.CRITICAL + 1)


def enable_all_categories() -> None:
    """Re-enable all logging categories."""
    set_disabled_categories(set())


def disable_categories(categories: list[str]) -> None:
    """
    Disable multiple logging categories at once.

    Args:
        categories: List of category names to disable
    """
    for category in categories:
        set_category_enabled(category, enabled=False)


def get_noisy_categories() -> dict[str, str]:
    """
    Get the dictionary of known noisy categories for UI display.

    Returns:
        Dict mapping category names to human-readable labels
    """
    return NOISY_CATEGORIES.copy()
