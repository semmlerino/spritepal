"""
Import/Export Panel for Manual Offset Dialog

Handles importing and exporting sprite offsets to/from JSON files.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_COMPACT_SMALL, SPACING_SMALL, SPACING_TINY
from ui.components.visualization import ROMMapWidget
from ui.styles import get_panel_style


class ImportExportPanel(QWidget):
    """Panel for importing and exporting sprite offset data"""

    # Signals
    sprites_imported = Signal(list)  # List of (offset, quality) tuples
    status_changed = Signal(str)  # Status message

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(get_panel_style())

        # State
        self.rom_path: str = ""
        self.rom_size: int = 0x400000
        self.found_sprites: list[tuple[int, float]] = []

        # ROM map reference (set by parent)
        self.rom_map: ROMMapWidget | None = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialize the import/export panel UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_SMALL, SPACING_COMPACT_SMALL, SPACING_SMALL, SPACING_COMPACT_SMALL)
        layout.setSpacing(SPACING_TINY)

        label = QLabel("Import/Export")
        label.setStyleSheet("font-weight: bold; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(label)

        # Export/Import controls
        io_row = QHBoxLayout()
        self.export_btn = QPushButton("Export Offsets")
        self.export_btn.setToolTip("Export found sprite offsets to file")
        io_row.addWidget(self.export_btn)

        self.import_btn = QPushButton("Import Offsets")
        self.import_btn.setToolTip("Import sprite offsets from file")
        io_row.addWidget(self.import_btn)
        layout.addLayout(io_row)

        self.setLayout(layout)

    def _connect_signals(self):
        """Connect internal signals"""
        _ = self.export_btn.clicked.connect(self._export_offsets)
        _ = self.import_btn.clicked.connect(self._import_offsets)

    def set_rom_data(self, rom_path: str, rom_size: int):
        """Set ROM data for import/export operations"""
        self.rom_path = rom_path
        self.rom_size = rom_size

    def set_rom_map(self, rom_map: ROMMapWidget):
        """Set the ROM map reference for visualization updates"""
        self.rom_map = rom_map

    def set_found_sprites(self, sprites: list[tuple[int, float]]):
        """Update the list of found sprites for export"""
        self.found_sprites = sprites.copy()

    def _export_offsets(self):
        """Export found offsets to file"""
        if not self.found_sprites:
            _ = QMessageBox.information(
                self,
                "No Data to Export",
                "No sprite offsets found. Run a scan first to find sprites.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get save file path
        default_name = f"sprite_offsets_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sprite Offsets",
            default_name,
            "JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return

        def _validate_export_permissions(file_path: str) -> None:
            """Validate export directory write permissions"""
            target_dir = Path(file_path).parent
            if target_dir and not os.access(target_dir, os.W_OK):
                raise PermissionError(f"Cannot write to directory: {target_dir}")

        try:
            # Validate data before export
            if not self.found_sprites:
                _ = QMessageBox.warning(
                    self,
                    "No Data to Export",
                    "No sprite offsets found to export. Scan for sprites first.",
                    QMessageBox.StandardButton.Ok
                )
                return

            # Check directory write permissions
            _validate_export_permissions(file_path)

            # Prepare export data
            export_data = {
                "metadata": {
                    "rom_path": self.rom_path,
                    "rom_size": self.rom_size,
                    "export_timestamp": datetime.now(UTC).isoformat(),
                    "spritepal_version": "1.0.0",
                    "total_sprites": len(self.found_sprites)
                },
                "sprites": [
                    {
                        "offset": f"0x{offset:06X}",
                        "offset_decimal": offset,
                        "quality": round(quality, 3),
                        "name": f"sprite_{i+1:03d}_0x{offset:06X}"
                    }
                    for i, (offset, quality) in enumerate(self.found_sprites)
                ]
            }

            # Write to file with atomic operation
            temp_file = file_path + ".tmp"
            try:
                with Path(temp_file).open("w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                # Atomic move to final location
                Path(temp_file).replace(file_path)
            except Exception:
                # Clean up temp file on failure
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
                raise

            # Success message
            sprite_count = len(self.found_sprites)
            self.status_changed.emit(f"Exported {sprite_count} sprite offsets to {Path(file_path).name}")

            _ = QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {sprite_count} sprite offsets to:\n{file_path}",
                QMessageBox.StandardButton.Ok
            )

        except PermissionError as e:
            error_msg = f"Permission denied: {e}"
            self.status_changed.emit(error_msg)
            _ = QMessageBox.critical(
                self,
                "Export Failed",
                f"Cannot write to file:\n{error_msg}\n\nTry selecting a different location.",
                QMessageBox.StandardButton.Ok
            )
        except OSError as e:
            error_msg = f"File I/O error: {e}"
            self.status_changed.emit(error_msg)
            _ = QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to write file:\n{error_msg}\n\nCheck disk space and try again.",
                QMessageBox.StandardButton.Ok
            )
        except Exception as e:
            error_msg = f"Failed to export offsets: {e}"
            self.status_changed.emit(error_msg)
            _ = QMessageBox.critical(
                self,
                "Export Failed",
                error_msg,
                QMessageBox.StandardButton.Ok
            )

    def _import_offsets(self):
        """Import offsets from file"""
        # Get file path
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Sprite Offsets",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return

        def _validate_import_file_access(file_path: str) -> None:
            """Validate import file accessibility"""
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            if not os.access(file_path, os.R_OK):
                raise PermissionError(f"Cannot read file: {file_path}")

        def _validate_import_file_size(file_path: str) -> None:
            """Validate import file size limits"""
            file_size = Path(file_path).stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                raise ValueError(f"File too large: {file_size / 1024 / 1024:.1f}MB (max 10MB)")

        def _validate_import_format(import_data: dict[str, Any]) -> list[Any]:
            """Validate import data format and return sprites data"""
            if "sprites" not in import_data:
                raise ValueError("Invalid file format: missing 'sprites' key")
            sprites_data = import_data["sprites"]
            if not isinstance(sprites_data, list):
                raise ValueError("Invalid file format: 'sprites' must be a list")
            return sprites_data

        try:
            # Validate file accessibility
            _validate_import_file_access(file_path)

            # Check file size (prevent loading huge files)
            _validate_import_file_size(file_path)

            # Read and parse JSON file
            with Path(file_path).open(encoding="utf-8") as f:
                import_data = json.load(f)

            # Validate file format
            sprites_data = _validate_import_format(import_data)

            # Check ROM compatibility if metadata is present
            if "metadata" in import_data:
                metadata = import_data["metadata"]
                if "rom_size" in metadata and metadata["rom_size"] != self.rom_size:
                    result = _ = QMessageBox.question(
                        self,
                        "ROM Size Mismatch",
                        f"The imported data is from a ROM of size {metadata['rom_size']} bytes,\n"
                        f"but current ROM is {self.rom_size} bytes.\n\n"
                        f"Import anyway? Some offsets may be invalid.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if result != QMessageBox.StandardButton.Yes:
                        return

            # Clear existing sprites
            if self.found_sprites:
                self.found_sprites.clear()
            if self.rom_map is not None:
                self.rom_map.clear_sprites()

            # Import sprites
            imported_count = 0
            skipped_count = 0
            imported_sprites = []

            for sprite_data in sprites_data:
                try:
                    # Parse offset (support both hex string and decimal)
                    if "offset_decimal" in sprite_data:
                        offset = int(sprite_data["offset_decimal"])
                    elif "offset" in sprite_data:
                        offset_str = sprite_data["offset"]
                        if offset_str.startswith("0x"):
                            offset = int(offset_str, 16)
                        else:
                            offset = int(offset_str)
                    else:
                        continue

                    # Validate offset is within ROM bounds
                    if offset < 0 or offset >= self.rom_size:
                        skipped_count += 1
                        continue

                    # Get quality (default to 1.0 if not present)
                    quality = float(sprite_data.get("quality", 1.0))

                    # Add to found sprites
                    self.found_sprites.append((offset, quality))
                    imported_sprites.append((offset, quality))
                    if self.rom_map is not None:
                        self.rom_map.add_found_sprite(offset, quality)
                    imported_count += 1

                except (ValueError, KeyError):
                    skipped_count += 1
                    continue

            # Emit imported sprites signal
            if imported_sprites:
                self.sprites_imported.emit(imported_sprites)

            # Update status
            if imported_count > 0:
                status_msg = f"Imported {imported_count} sprite offsets"
                if skipped_count > 0:
                    status_msg += f" ({skipped_count} skipped)"
                self.status_changed.emit(status_msg)

                _ = QMessageBox.information(
                    self,
                    "Import Successful",
                    f"Successfully imported {imported_count} sprite offsets from:\n{Path(file_path).name}\n\n"
                    f"{skipped_count} entries were skipped due to invalid data or out-of-bounds offsets.",
                    QMessageBox.StandardButton.Ok
                )
            else:
                self.status_changed.emit("No valid sprite offsets found in file")
                _ = QMessageBox.warning(
                    self,
                    "No Data Imported",
                    "No valid sprite offsets were found in the file.",
                    QMessageBox.StandardButton.Ok
                )

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON file: {e}"
            self.status_changed.emit(error_msg)
            _ = QMessageBox.critical(
                self,
                "Import Failed",
                f"Failed to parse JSON file:\n{error_msg}",
                QMessageBox.StandardButton.Ok
            )
        except Exception as e:
            error_msg = f"Failed to import offsets: {e}"
            self.status_changed.emit(error_msg)
            _ = QMessageBox.critical(
                self,
                "Import Failed",
                error_msg,
                QMessageBox.StandardButton.Ok
            )

    def get_found_sprites(self) -> list[tuple[int, float]]:
        """Get the current list of found sprites"""
        return self.found_sprites.copy()
