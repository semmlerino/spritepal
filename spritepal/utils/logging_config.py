"""Logging configuration for SpritePal"""
from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import UTC, datetime
from pathlib import Path


def setup_logging(
    log_dir: Path | None = None, log_level: str = "INFO"
) -> logging.Logger:
    """
    Configure application-wide logging.

    Args:
        log_dir: Directory for log files (defaults to current directory)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Check for debug mode from environment
    if os.environ.get("SPRITEPAL_DEBUG", "").lower() in ("1", "true", "yes"):
        log_level = "DEBUG"

    # Use default directory under user's home if not specified
    if log_dir is None:
        log_dir = Path.home() / ".spritepal" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger for spritepal
    logger = logging.getLogger("spritepal")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler with simplified format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
    console_handler.setFormatter(console_formatter)

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
            log_file, maxBytes=5_000_000, backupCount=3  # 5MB
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

    logger.addHandler(console_handler)

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
