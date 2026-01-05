#!/usr/bin/env python3
"""
Worker threads for async file operations in the pixel editor.
Handles file I/O operations asynchronously.
"""

import json
import logging
import traceback
from pathlib import Path
from typing import Any, override

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal

from .base_worker import BaseWorker

logger = logging.getLogger(__name__)


def _sanitize_for_json(obj: Any) -> Any:
    """Convert non-JSON-serializable objects to JSON-safe types."""
    if isinstance(obj, str | int | float | bool | type(None)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="ignore")
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_sanitize_for_json(item) for item in obj]
    return str(obj)


class FileLoadWorker(BaseWorker):
    """Worker for loading image files asynchronously."""

    result = Signal(object, dict)  # Image array, metadata

    def __init__(self, file_path: str | Path, parent: QObject | None = None) -> None:
        """Initialize the file load worker.

        Args:
            file_path: Path to the image file to load
            parent: Parent QObject
        """
        super().__init__(file_path, parent)

    @override
    def run(self) -> None:
        """Load the image file in background thread."""
        try:
            if not self.validate_file_path(must_exist=True):
                return

            self.emit_progress(0, f"Loading {self.file_path.name if self.file_path else 'file'}...")
            if self.is_cancelled():
                return

            # Open image
            self.emit_progress(20, "Opening image file...")
            image = Image.open(str(self.file_path))

            if self.is_cancelled():
                return

            # Convert to indexed color if necessary
            self.emit_progress(40, "Processing image format...")
            if image.mode != "P":
                image = image.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)

            if self.is_cancelled():
                return

            # Extract image data
            self.emit_progress(60, "Extracting image data...")
            image_array = np.array(image, dtype=np.uint8)

            # Extract palette
            palette_data = image.getpalette()
            if palette_data is None:
                self.emit_error("Image has no palette data")
                return

            if self.is_cancelled():
                return

            # Prepare metadata
            self.emit_progress(80, "Preparing metadata...")
            metadata: dict[str, Any] = {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format,
                "palette": palette_data,
                "file_path": str(self.file_path) if self.file_path else "",
                "file_name": str(self.file_path.name) if self.file_path else "unknown",
            }

            if hasattr(image, "info"):
                metadata["info"] = _sanitize_for_json(image.info)

            metadata = _sanitize_for_json(metadata)

            if self.is_cancelled():
                return

            self.emit_progress(100, "Loading complete!")
            self.result.emit(image_array, metadata)
            self.emit_finished()

        except Exception as e:
            logger.exception("Error loading file")
            self.emit_error(f"Unexpected error loading file: {e}\n{traceback.format_exc()}")


class FileSaveWorker(BaseWorker):
    """Worker for saving image files asynchronously."""

    saved = Signal(str)  # Saved file path

    def __init__(
        self,
        image_array: np.ndarray,
        palette: list[int],
        file_path: str | Path,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the file save worker.

        Args:
            image_array: Indexed image data to save
            palette: Color palette (768 RGB values)
            file_path: Path where to save the image
            parent: Parent QObject
        """
        super().__init__(file_path, parent)
        self.image_array = image_array
        self.palette = palette

    @override
    def run(self) -> None:
        """Save the image file in background thread."""
        try:
            if not self.validate_file_path(must_exist=False):
                return

            self.emit_progress(0, "Preparing to save...")

            if len(self.image_array) == 0:
                self.emit_error("No image data to save")
                return

            if len(self.palette) != 768:
                self.emit_error("Invalid palette data")
                return

            if self.is_cancelled():
                return

            self.emit_progress(20, "Validating image data...")

            # Create PIL image from array
            image = Image.fromarray(self.image_array, mode="P")

            if self.is_cancelled():
                return

            self.emit_progress(40, "Creating indexed image...")

            # Apply palette
            image.putpalette(self.palette)

            if self.is_cancelled():
                return

            self.emit_progress(60, "Applying color palette...")

            # Ensure parent directory exists
            if self.file_path:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Determine format from extension
            format_map = {
                ".png": "PNG",
                ".gif": "GIF",
                ".bmp": "BMP",
                ".tiff": "TIFF",
                ".tif": "TIFF",
            }

            file_format = format_map.get(self.file_path.suffix.lower() if self.file_path else ".png", "PNG")

            # Save with appropriate options
            save_kwargs: dict[str, Any] = {}
            if file_format == "PNG":
                save_kwargs["optimize"] = True
                save_kwargs["transparency"] = 0

            self.emit_progress(80, f"Writing {file_format} to disk...")
            image.save(str(self.file_path), format=file_format, **save_kwargs)

            if self.is_cancelled():
                return

            self.emit_progress(100, "Save complete!")
            self.saved.emit(str(self.file_path))
            self.emit_finished()

        except Exception as e:
            logger.exception("Error saving file")
            self.emit_error(f"Unexpected error saving file: {e}\n{traceback.format_exc()}")


class PaletteLoadWorker(BaseWorker):
    """Worker for loading palette files asynchronously."""

    result = Signal(dict)  # Palette data dictionary

    def __init__(self, file_path: str | Path, parent: QObject | None = None) -> None:
        """Initialize the palette load worker.

        Args:
            file_path: Path to the palette file to load
            parent: Parent QObject
        """
        super().__init__(file_path, parent)

    @override
    def run(self) -> None:
        """Load the palette file in background thread."""
        try:
            if not self.validate_file_path(must_exist=True):
                return

            if not self.file_path:
                return

            self.emit_progress(0, f"Loading palette from {self.file_path.name}...")
            if self.is_cancelled():
                return

            self.emit_progress(30, "Reading palette file...")

            suffix = self.file_path.suffix.lower()
            palette_data: dict[str, Any] | None = None

            if suffix == ".json":
                palette_data = self._load_json_palette()
            elif suffix == ".pal":
                palette_data = self._load_binary_palette()
            elif suffix == ".gpl":
                palette_data = self._load_gimp_palette()
            else:
                self.emit_error(f"Unsupported palette format: {suffix}")
                return

            if palette_data is None:
                return
            if self.is_cancelled():
                return

            self.emit_progress(90, "Validating palette colors...")

            # Add file metadata
            palette_data["file_path"] = str(self.file_path)
            palette_data["file_name"] = self.file_path.name

            self.emit_progress(100, "Palette loaded successfully!")
            self.result.emit(palette_data)
            self.emit_finished()

        except Exception as e:
            logger.exception("Error loading palette")
            self.emit_error(f"Unexpected error loading palette: {e}\n{traceback.format_exc()}")

    def _load_json_palette(self) -> dict[str, Any] | None:
        """Load JSON palette file."""
        try:
            if not self.file_path:
                return None
            with self.file_path.open() as f:
                data = json.load(f)

            if self.is_cancelled():
                return None

            self.emit_progress(60, "Parsing JSON palette data...")

            if "colors" not in data:
                self.emit_error("Invalid palette JSON: missing 'colors' field")
                return None

            return data

        except json.JSONDecodeError as e:
            self.emit_error(f"Invalid JSON format: {e}")
            return None
        except Exception as e:
            self.emit_error(f"Failed to load JSON palette: {e}")
            return None

    def _load_binary_palette(self) -> dict[str, Any] | None:
        """Load ACT/PAL palette file (raw RGB data)."""
        try:
            if not self.file_path:
                return None
            with self.file_path.open("rb") as f:
                raw_data = f.read()

            if self.is_cancelled():
                return None

            self.emit_progress(60, "Converting binary palette data...")

            if len(raw_data) < 768:
                self.emit_error(f"Invalid palette file: expected 768 bytes, got {len(raw_data)}")
                return None

            colors = []
            for i in range(0, min(768, len(raw_data)), 3):
                r = raw_data[i]
                g = raw_data[i + 1]
                b = raw_data[i + 2]
                colors.append([r, g, b])

            return {
                "name": self.file_path.stem,
                "colors": colors,
                "format": "ACT",
            }

        except Exception as e:
            self.emit_error(f"Failed to load PAL/ACT palette: {e}")
            return None

    def _load_gimp_palette(self) -> dict[str, Any] | None:
        """Load GIMP palette file (.gpl format)."""
        try:
            if not self.file_path:
                return None
            colors: list[list[int]] = []
            name = self.file_path.stem

            with self.file_path.open() as f:
                lines = f.readlines()

            if self.is_cancelled():
                return None

            self.emit_progress(60, "Parsing GIMP palette format...")

            if not lines or not lines[0].strip().startswith("GIMP Palette"):
                self.emit_error("Invalid GIMP palette file")
                return None

            for line in lines[1:]:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if line.startswith("Name:"):
                    name = line[5:].strip()
                    continue

                parts = line.split()
                if len(parts) >= 3:
                    try:
                        r = int(parts[0])
                        g = int(parts[1])
                        b = int(parts[2])
                        colors.append([r, g, b])
                    except ValueError:
                        continue

            return {"name": name, "colors": colors, "format": "GIMP"}

        except Exception as e:
            self.emit_error(f"Failed to load GIMP palette: {e}")
            return None
