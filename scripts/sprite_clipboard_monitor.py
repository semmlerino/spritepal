#!/usr/bin/env python3
"""
Sprite Clipboard Monitor for SpritePal Integration
Monitors a clipboard file written by Mesen2 Lua script and allows quick navigation.
"""

import json
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from utils.logging_config import get_logger

logger = get_logger(__name__)


class SpriteClipboardHandler(FileSystemEventHandler):
    """Handles clipboard file changes from Mesen2."""

    def __init__(self, callback):
        self.callback = callback
        self.last_offset = None

    def on_modified(self, event):
        if event.src_path.endswith("sprite_clipboard.txt"):
            try:
                with Path(event.src_path).open() as f:
                    offset_str = f.read().strip()

                # Parse offset (handles both 0x and $ prefix)
                if offset_str.startswith("0x"):
                    offset = int(offset_str, 16)
                elif offset_str.startswith("$"):
                    offset = int(offset_str[1:], 16)
                else:
                    offset = int(offset_str, 16)

                # Only trigger if offset changed
                if offset != self.last_offset:
                    self.last_offset = offset
                    logger.info(f"Clipboard offset detected: 0x{offset:06X}")
                    self.callback(offset)

            except (OSError, ValueError) as e:
                logger.error(f"Error reading clipboard file: {e}")


class SpriteSessionLoader:
    """Loads sprite session JSON files from Mesen2."""

    @staticmethod
    def load_session(filepath: Path) -> dict | None:
        """Load a sprite session JSON file."""
        try:
            with filepath.open() as f:
                data = json.load(f)
                logger.info(f"Loaded session with {len(data['sprites_found'])} sprites")
                return data
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Error loading session file: {e}")
            return None

    @staticmethod
    def get_latest_session(directory: Path) -> Path | None:
        """Find the most recent sprite_session*.json file."""
        pattern = "sprite_session*.json"
        files = list(directory.glob(pattern))

        if not files:
            return None

        # Sort by modification time
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files[0]


def monitor_clipboard(output_dir: Path, callback):
    """
    Monitor clipboard file for changes.

    Args:
        output_dir: Directory where Mesen2 writes files
        callback: Function to call with new offset
    """
    clipboard_file = output_dir / "sprite_clipboard.txt"

    # Create file if it doesn't exist
    if not clipboard_file.exists():
        clipboard_file.touch()
        logger.info(f"Created clipboard file: {clipboard_file}")

    # Set up file watcher
    event_handler = SpriteClipboardHandler(callback)
    observer = Observer()
    observer.schedule(event_handler, str(output_dir), recursive=False)
    observer.start()

    logger.info(f"Monitoring clipboard file: {clipboard_file}")
    logger.info("Press Ctrl+C to stop monitoring")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Stopped monitoring")
    observer.join()


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    else:
        # Default Mesen2 output directory
        output_dir = Path.home() / "Mesen2"

    def handle_offset(offset: int):
        print(f"Navigate to offset: 0x{offset:06X}")
        # Here you would trigger SpritePal to navigate to this offset

    monitor_clipboard(output_dir, handle_offset)
