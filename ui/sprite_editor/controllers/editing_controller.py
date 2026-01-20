#!/usr/bin/env python3
"""
Editing controller for the pixel editor functionality.
Manages the pixel editing workflow, tools, and undo/redo.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, Signal

from core.default_palette_loader import DefaultPaletteLoader
from utils.logging_config import get_logger

from ..commands.pixel_commands import BatchCommand, DrawPixelCommand, FloodFillCommand
from ..managers import ToolManager, ToolType, UndoManager
from ..models import ImageModel, PaletteModel

logger = get_logger(__name__)

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager

    from ..views.tabs import EditTab


class EditingController(QObject):
    """Controller for pixel editing operations."""

    # SNES hardware constraints for ROM injection
    MAX_SNES_COLORS = 16  # 4bpp = max 16 colors per sprite
    TILE_ALIGNMENT = 8  # SNES tiles are 8x8 pixels

    # Signals
    imageChanged = Signal()
    paletteChanged = Signal()
    toolChanged = Signal(str)
    colorChanged = Signal(int)
    undoStateChanged = Signal(bool, bool)  # can_undo, can_redo
    paletteSourceAdded = Signal(str, str, int, object, bool)  # name, type, index, colors, is_active
    paletteSourceSelected = Signal(str, int)  # source_type, palette_index
    # Signal to clear all palettes of a specific type from views
    paletteSourcesCleared = Signal(str)  # source_type ("rom", "mesen", or "all")
    # Emitted when ROM validation state changes: (is_valid, list of error messages)
    validationChanged = Signal(bool, list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # Create models and managers
        self.image_model = ImageModel()
        self.palette_model = PaletteModel()  # Use model instead of inline list
        self._current_palette_source: tuple[str, int] | None = None

        # Tool manager
        self.tool_manager = ToolManager()

        # Undo/Redo manager
        self.undo_manager = UndoManager()

        # Selected color index
        self._selected_color = 1

        # Palette sources registry: (source_type, index) -> (colors, name)
        self._palette_sources: dict[tuple[str, int], tuple[list[tuple[int, int, int]], str]] = {}

        # View reference
        self._view: EditTab | None = None

        # Current stroke batch for undo (accumulated during press/move/release)
        self._current_stroke: BatchCommand | None = None

        # Last save path for Save operation
        self._last_save_path: str = ""

        # ROM validation state
        self._validation_errors: list[str] = []
        self._is_valid_for_rom: bool = True

        # Connect tool manager signals
        self.tool_manager.tool_changed.connect(self._on_tool_changed)

        # Connect image changes to validation
        self.imageChanged.connect(self._validate_rom_constraints)

        # Lazy palette loader (defer initialization to property access)
        self._palette_loader: DefaultPaletteLoader | None = None

        # Load available presets (uses lazy palette_loader property)
        self.load_presets()

        # Load last used palette if available
        self._load_last_palette()

    @property
    def palette_loader(self) -> DefaultPaletteLoader:
        """Lazy access to DefaultPaletteLoader via AppContext when available."""
        if self._palette_loader is None:
            try:
                from core.app_context import get_app_context

                self._palette_loader = get_app_context().default_palette_loader
            except RuntimeError:
                # AppContext not initialized, create standalone instance
                self._palette_loader = DefaultPaletteLoader()
        return self._palette_loader

    @property
    def state_manager(self) -> "ApplicationStateManager" | None:
        """Lazy access to ApplicationStateManager via AppContext when available."""
        try:
            from core.app_context import get_app_context

            return get_app_context().application_state_manager
        except RuntimeError:
            return None

    def load_presets(self) -> None:
        """Load all available palette presets from configuration."""
        presets = self.palette_loader.get_all_presets()
        for i, preset in enumerate(presets):
            name = preset.get("name", f"Preset {i}")
            colors = preset.get("colors", [])
            if colors:
                # Convert list of lists to list of exact RGB tuples
                rgb_colors = [(int(c[0]), int(c[1]), int(c[2])) for c in colors if len(c) >= 3]
                # Use "preset" as source type and loop index as unique ID
                self.register_palette_source("preset", i, rgb_colors, name)

    def set_view(self, view: "EditTab") -> None:
        """Set the edit tab view."""
        self._view = view
        view.set_controller(self)

    def has_image(self) -> bool:
        """Check if an image is loaded (always true - model has default data)."""
        return True

    def get_image_size(self) -> tuple[int, int]:
        """Get the current image size (width, height)."""
        height, width = self.image_model.data.shape
        return (width, height)

    def get_current_colors(self) -> list[tuple[int, int, int]]:
        """Get the current palette colors."""
        return list(self.palette_model.colors)

    def get_current_tool_name(self) -> str:
        """Get the name of the current tool."""
        tool_type = self.tool_manager.current_tool_type
        return {
            ToolType.PENCIL: "pencil",
            ToolType.FILL: "fill",
            ToolType.PICKER: "picker",
            ToolType.ERASER: "eraser",
        }.get(tool_type, "pencil")

    def get_selected_color(self) -> int:
        """Get the currently selected color index."""
        return self._selected_color

    def set_tool(self, tool_name: str) -> None:
        """Set the current tool by name."""
        tool_map = {
            "pencil": ToolType.PENCIL,
            "fill": ToolType.FILL,
            "picker": ToolType.PICKER,
            "eraser": ToolType.ERASER,
        }
        tool_type = tool_map.get(tool_name, ToolType.PENCIL)
        self.tool_manager.set_tool(tool_type)

    def set_brush_size(self, size: int) -> None:
        """Set the brush size."""
        self.tool_manager.set_brush_size(size)

    def get_brush_size(self) -> int:
        """Get the current brush size."""
        return self.tool_manager.get_brush_size()

    def get_brush_pixels(self, x: int, y: int) -> list[tuple[int, int]]:
        """Get the pixel positions affected by the brush at given coordinates."""
        return self.tool_manager.get_brush_pixels(x, y)

    def set_selected_color(self, index: int) -> None:
        """Set the selected color index."""
        if 0 <= index < 16:
            self._selected_color = index
            self.tool_manager.set_color(index)
            self.colorChanged.emit(index)

    def set_palette(
        self,
        colors: list[tuple[int, int, int]],
        name: str = "",
        *,
        source_type: str = "",
        source_index: int = -1,
    ) -> None:
        """Set the palette colors.

        Args:
            colors: List of RGB colors
            name: Optional name for the palette
            source_type: Optional source type (e.g. 'rom', 'mesen', 'file')
            source_index: Optional source index
        """
        self.palette_model.from_rgb_list(colors)
        if name:
            self.palette_model.name = name

        # Update source tracking
        if source_type:
            self._current_palette_source = (source_type, source_index)
        else:
            self._current_palette_source = None

        self.paletteChanged.emit()
        self.paletteSourceSelected.emit(source_type, source_index)

    def load_image(self, data: np.ndarray, palette: list[tuple[int, int, int]] | None = None) -> None:
        """Load an image into the editor.

        Args:
            data: 2D numpy array of palette indices
            palette: Optional palette colors
        """
        self.image_model.set_data(data)
        if palette:
            self.set_palette(palette)

        # Clear undo history and emit state change so UI updates
        self.undo_manager.clear()
        self._emit_undo_state()

        self.imageChanged.emit()

    def import_image(
        self,
        indexed_data: np.ndarray,
        palette: list[tuple[int, int, int]],
        source_path: str = "",
    ) -> bool:
        """Import an external image with undo support.

        Unlike load_image() which clears undo history, this method supports
        undo/redo for the import operation.

        Args:
            indexed_data: 2D numpy array of palette indices (0-15)
            palette: List of 16 RGB tuples for the palette
            source_path: Optional source file path for reference

        Returns:
            True if import succeeded, False otherwise
        """
        if not self.has_image():
            # No existing image - treat as initial load
            self.load_image(indexed_data, palette)
            return True

        # Get current state for undo
        previous_data = self.image_model.data.copy()
        previous_palette = self.palette_model.colors.copy()

        # Create and execute import command
        from ..commands.import_command import ImportImageCommand

        cmd = ImportImageCommand(
            previous_data=previous_data,
            previous_palette=previous_palette,
            new_data=indexed_data,
            new_palette=palette,
            source_path=source_path,
        )

        self.undo_manager.execute_command(cmd, self.image_model)

        # Update palette
        self.set_palette(palette)

        # Emit signals
        self.imageChanged.emit()
        self.paletteSourceSelected.emit("", -1)
        self._emit_undo_state()

        return True

    def _on_tool_changed(self, tool_type: ToolType) -> None:
        """Handle tool change from manager."""
        tool_name = {
            ToolType.PENCIL: "pencil",
            ToolType.FILL: "fill",
            ToolType.PICKER: "picker",
            ToolType.ERASER: "eraser",
        }.get(tool_type, "pencil")
        self.toolChanged.emit(tool_name)

    # Drawing operations

    def handle_pixel_press(self, x: int, y: int) -> None:
        """Handle pixel press event from canvas."""
        if not self.has_image():
            return

        tool = self.tool_manager.get_tool()
        if tool is None:
            return

        tool_type = self.tool_manager.current_tool_type

        # Handle color picker - no undo needed
        if tool_type == ToolType.PICKER:
            color = self.image_model.get_pixel(x, y)
            if 0 <= color < 16:
                self.set_selected_color(color)
            return

        # Handle fill tool - single command
        # NOTE: We DON'T call tool.on_press() here because FloodFillCommand.execute()
        # handles the fill and populates old_data for proper undo support.
        if tool_type == ToolType.FILL:
            old_color = self.image_model.get_pixel(x, y)
            # Don't fill if clicking same color
            if old_color == self._selected_color:
                return
            # Create command and execute it (this populates old_data for undo)
            cmd = FloodFillCommand(x=x, y=y, old_color=old_color, new_color=self._selected_color)
            cmd.execute(self.image_model)
            # Only record if fill actually changed something
            if cmd.old_data is not None:
                self.undo_manager.record_command(cmd)
                self.imageChanged.emit()
                self._emit_undo_state()
            return

        # Handle pencil tool - start a stroke batch
        old_color = self.image_model.get_pixel(x, y)
        result = tool.on_press(x, y, self._selected_color, self.image_model)

        if result:
            # Start new batch for this stroke
            self._current_stroke = BatchCommand()
            cmd = DrawPixelCommand(x=x, y=y, old_color=old_color, new_color=self._selected_color)
            self._current_stroke.add_command(cmd)
            self.imageChanged.emit()

    def handle_pixel_move(self, x: int, y: int) -> None:
        """Handle pixel move event from canvas."""
        if not self.has_image():
            return

        tool = self.tool_manager.get_tool()
        if tool is None:
            return

        tool_type = self.tool_manager.current_tool_type

        # Only pencil and eraser tools use move for continuous drawing
        if tool_type not in (ToolType.PENCIL, ToolType.ERASER):
            return

        # Determine draw color based on tool
        draw_color = self._selected_color
        if tool_type == ToolType.ERASER:
            draw_color = 0

        # Get line points from tool (for interpolation)
        line_points = tool.on_move(x, y, draw_color, self.image_model)

        if not line_points:
            return

        # Draw each line point with brush size applied
        any_changed = False
        for center_x, center_y in line_points:
            # Get all pixels affected by brush at this point
            brush_pixels = self.tool_manager.get_brush_pixels(center_x, center_y)

            for px, py in brush_pixels:
                # Bounds check
                if not (0 <= px < self.image_model.width and 0 <= py < self.image_model.height):
                    continue

                old_color = self.image_model.get_pixel(px, py)
                if self.image_model.set_pixel(px, py, draw_color):
                    any_changed = True
                    if self._current_stroke is not None:
                        cmd = DrawPixelCommand(x=px, y=py, old_color=old_color, new_color=draw_color)
                        self._current_stroke.add_command(cmd)

        if any_changed:
            self.imageChanged.emit()

    def handle_pixel_release(self, x: int, y: int) -> None:
        """Handle pixel release event from canvas."""
        if not self.has_image():
            return

        tool = self.tool_manager.get_tool()
        if tool is None:
            return

        # Notify tool of release (for state cleanup)
        tool.on_release(x, y, self._selected_color, self.image_model)

        # Finalize stroke batch for undo
        if self._current_stroke is not None and self._current_stroke.commands:
            self.undo_manager.record_command(self._current_stroke)
            self._emit_undo_state()
        self._current_stroke = None

    # Color picker callback

    def pick_color_at(self, x: int, y: int) -> int | None:
        """Pick color at the given position."""
        color = self.image_model.get_pixel(x, y)
        if 0 <= color < 16:
            self.set_selected_color(color)
            return color
        return None

    # Palette Management

    def get_palette_sources(self) -> dict[tuple[str, int], tuple[list[tuple[int, int, int]], str]]:
        """Get all registered palette sources."""
        return self._palette_sources.copy()

    def get_current_palette_source(self) -> tuple[str, int] | None:
        """Get the currently selected palette source (source_type, index)."""
        return self._current_palette_source

    def clear_palette_sources(self, source_type: str | None = None) -> None:
        """Clear registered palette sources.

        Args:
            source_type: If provided, only clear sources of this type.
                         If None, clear all sources.
        """
        if source_type is None:
            self._palette_sources.clear()
            self.paletteSourcesCleared.emit("all")
        else:
            # Create list of keys to remove to avoid mutation during iteration
            to_remove = [k for k in self._palette_sources if k[0] == source_type]
            for k in to_remove:
                del self._palette_sources[k]

            self.paletteSourcesCleared.emit(source_type)

    def register_palette_source(
        self,
        source_type: str,
        index: int,
        colors: list[tuple[int, int, int]],
        name: str,
        is_active: bool = False,
    ) -> None:
        """Register a new palette source.

        Args:
            source_type: Type of source ("default", "mesen", "rom", "preset", "file")
            index: Palette index
            colors: List of 16 RGB tuples
            name: Display name for the source
            is_active: Whether this palette is OAM-active (detected in use)
        """
        key = (source_type, index)
        self._palette_sources[key] = (colors, name)
        self.paletteSourceAdded.emit(name, source_type, index, colors, is_active)

    def handle_palette_source_changed(self, source_type: str, index: int) -> None:
        """Handle palette source selection change."""
        key = (source_type, index)
        try:
            if source_type == "default":
                from ui.sprite_editor import get_default_snes_palette

                colors = get_default_snes_palette()
                self.set_palette(colors, "Default SNES", source_type="default", source_index=0)
            elif source_type in ("mesen", "rom", "preset", "file"):
                if key in self._palette_sources:
                    colors, name = self._palette_sources[key]
                    self.set_palette(colors, name, source_type=source_type, source_index=index)
                else:
                    logger.warning(f"Unknown palette source: {source_type} #{index}")
            else:
                logger.warning(f"Unknown palette source type: {source_type}")
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox

            # Use view if available, otherwise None (desktop)
            parent = self._view if self._view else None
            QMessageBox.critical(parent, "Error", f"Failed to change palette source: {e}")

    def register_rom_palettes(
        self,
        palettes: dict[int, list[tuple[int, int, int]]],
        active_indices: list[int] | None = None,
        descriptions: dict[int, str] | None = None,
    ) -> None:
        """Register multiple ROM palettes as switchable sources.

        Args:
            palettes: Dict mapping palette index (8-15) to list of 16 RGB tuples
            active_indices: Optional list of palette indices detected in OAM (marked as active)
            descriptions: Optional dict of semantic descriptions per palette index
        """
        active_set = set(active_indices) if active_indices else set()
        for index, colors in palettes.items():
            # Build name with optional semantic description
            name = f"ROM Palette {index}"
            if descriptions and index in descriptions:
                name = f"ROM Palette {index} - {descriptions[index]}"

            is_active = index in active_set
            self.register_palette_source("rom", index, colors, name, is_active)

    def set_palette_source(self, source_type: str, palette_index: int) -> None:
        """Programmatically select a palette source.

        This looks up the colors from the registered sources and applies them.
        Also updates the view's palette source selector if available.

        Args:
            source_type: Type of source ("default", "mesen", or "rom")
            palette_index: Palette index
        """
        # Update current source tracker
        self._current_palette_source = (source_type, palette_index)

        # Apply the palette
        self.handle_palette_source_changed(source_type, palette_index)

        # Emit signal for all connected views (e.g., EditWorkspace)
        # Views connect to this signal and update their UI accordingly
        self.paletteSourceSelected.emit(source_type, palette_index)

    def load_palette_from_file(self, file_path: str) -> bool:
        """Load a palette from a file and select it.

        Args:
            file_path: Path to the palette file (.pal or .json)

        Returns:
            True if successful
        """
        try:
            colors = []
            if file_path.endswith(".json"):
                import json

                with open(file_path) as f:
                    data = json.load(f)
                    # Expecting {"colors": [[r,g,b], ...]}
                    if "colors" in data:
                        colors = [tuple(c) for c in data["colors"]]
            else:
                # Assume JASC PAL or raw RGB
                with open(file_path) as f:
                    lines = f.readlines()
                    if lines and "JASC-PAL" in lines[0]:
                        for line in lines[3:]:  # Skip header, version, count
                            parts = line.strip().split()
                            if len(parts) >= 3:
                                colors.append((int(parts[0]), int(parts[1]), int(parts[2])))

            if colors:
                # Ensure we have at least 16 colors, pad if necessary
                while len(colors) < 16:
                    colors.append((0, 0, 0))
                colors = colors[:16]

                # Register as "file" source and select it
                # This updates the dropdown via paletteSourceSelected signal
                filename = Path(file_path).name
                self.register_palette_source("file", 0, colors, f"Loaded: {filename}")
                self.set_palette_source("file", 0)

                # Save to settings
                if self.state_manager:
                    self.state_manager.set("paths", "last_palette_path", file_path)
                    self.state_manager.save_session()

                return True
        except Exception as e:
            logger.error(f"Failed to load palette from {file_path}: {e}")

        return False

    def _load_last_palette(self) -> None:
        """Load the last used palette from settings."""
        if self.state_manager:
            last_path = str(self.state_manager.get("paths", "last_palette_path", ""))
            if last_path and Path(last_path).exists():
                logger.info(f"Auto-loading last used palette: {last_path}")
                self.load_palette_from_file(last_path)

    def handle_load_palette(self) -> None:
        """Handle load palette button click."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        # Use view if available, otherwise None
        parent = self._view if self._view else None

        try:
            file_path, _ = QFileDialog.getOpenFileName(
                parent,
                "Load Palette",
                "",
                "Palette Files (*.pal *.json);;All Files (*)",
            )

            if not file_path:
                return

            if not self.load_palette_from_file(file_path):
                QMessageBox.critical(parent, "Error", f"Failed to load palette from {file_path}")

        except Exception as e:
            QMessageBox.critical(parent, "Error", f"Failed to load palette: {e}")

    def handle_save_palette(self) -> None:
        """Handle save palette button click."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        # Use view if available, otherwise None
        parent = self._view if self._view else None

        try:
            file_path, _ = QFileDialog.getSaveFileName(
                parent,
                "Save Palette",
                "palette.json",
                "JSON Palette (*.json);;JASC Palette (*.pal);;All Files (*)",
            )

            if not file_path:
                return

            colors = self.get_current_colors()

            if file_path.endswith(".json"):
                import json

                data = {"name": self.palette_model.name, "colors": colors}
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
            elif file_path.endswith(".pal"):
                with open(file_path, "w") as f:
                    f.write("JASC-PAL\n0100\n16\n")
                    f.writelines(f"{r} {g} {b}\n" for r, g, b in colors)

        except Exception as e:
            QMessageBox.critical(parent, "Error", f"Failed to save palette: {e}")

    def handle_edit_color(self) -> None:
        """Handle edit color button click."""
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog, QMessageBox

        # Use view if available, otherwise None
        parent = self._view if self._view else None

        try:
            current_color = self.palette_model.get_color(self._selected_color)
            qcolor = QColor(*current_color)

            color = QColorDialog.getColor(qcolor, parent, "Edit Color")
            if color.isValid():
                new_rgb = (color.red(), color.green(), color.blue())
                self.palette_model.set_color(self._selected_color, new_rgb)
                self._current_palette_source = None
                self.paletteChanged.emit()
                self.paletteSourceSelected.emit("", -1)
        except Exception as e:
            QMessageBox.critical(parent, "Error", f"Failed to edit color: {e}")

    # Undo/Redo

    def undo(self) -> None:
        """Undo the last operation."""
        if self.undo_manager.can_undo():
            self.undo_manager.undo(self.image_model)
            self.imageChanged.emit()
            self._emit_undo_state()

    def redo(self) -> None:
        """Redo the last undone operation."""
        if self.undo_manager.can_redo():
            self.undo_manager.redo(self.image_model)
            self.imageChanged.emit()
            self._emit_undo_state()

    def has_unsaved_changes(self) -> bool:
        """Check if there are unsaved changes in the undo stack."""
        return self.undo_manager.can_undo()

    def _emit_undo_state(self) -> None:
        """Emit undo state changed signal."""
        self.undoStateChanged.emit(
            self.undo_manager.can_undo(),
            self.undo_manager.can_redo(),
        )

    def clear_undo_history(self) -> None:
        """Clear undo/redo history and emit state change.

        This is the public API for clearing history. It ensures the
        undoStateChanged signal is emitted so UI can update accordingly.
        """
        self.undo_manager.clear()
        self._emit_undo_state()

    # Image export

    def get_image_data(self) -> np.ndarray | None:
        """Get the current image data."""
        return self.image_model.data

    def get_flat_palette(self) -> list[int]:
        """Get the palette as a flat list for PIL."""
        return self.palette_model.to_flat_list()

    # File operations

    def save_image(self, file_path: str | None = None) -> bool:
        """Save current image to file. Returns True if successful."""
        if file_path is None and not self._last_save_path:
            # No path known - delegate to save_as
            return self.save_image_as() is not None

        path = file_path or self._last_save_path
        data = self.get_image_data()
        if data is None:
            return False

        try:
            from PIL import Image

            # Create PIL image with palette
            img = Image.fromarray(data, mode="P")
            img.putpalette(self.get_flat_palette())
            img.save(path, "PNG")

            self._last_save_path = path
            return True

        except (OSError, ValueError, RuntimeError) as e:
            # Show error to user via view dialog
            if self._view:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(
                    self._view,
                    "Save Error",
                    f"Failed to save image:\n{e}",
                )
            return False

    def save_image_as(self) -> str | None:
        """Show save dialog and save. Returns path if successful, None if cancelled."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self._view,
            "Save Sprite Image",
            "sprite.png",
            "PNG Images (*.png);;All Files (*)",
        )

        if file_path:
            if self.save_image(file_path):
                return file_path
        return None

    # ROM Validation

    def _validate_rom_constraints(self) -> None:
        """
        Validate that current image meets SNES ROM constraints.

        Checks:
        - Dimensions are multiples of 8 (tile alignment)
        - Color count <= 16 (4bpp limit)

        Emits validationChanged signal when state changes.
        """
        if not self.has_image():
            # No image = valid (nothing to save)
            if self._validation_errors or not self._is_valid_for_rom:
                self._validation_errors = []
                self._is_valid_for_rom = True
                self.validationChanged.emit(True, [])
            return

        errors: list[str] = []
        data = self.image_model.data

        # Check dimensions for tile alignment
        width, height = self.get_image_size()
        if width % self.TILE_ALIGNMENT != 0:
            errors.append(f"Width ({width}px) must be a multiple of {self.TILE_ALIGNMENT}")
        if height % self.TILE_ALIGNMENT != 0:
            errors.append(f"Height ({height}px) must be a multiple of {self.TILE_ALIGNMENT}")

        # Check color count (data is guaranteed non-None since has_image() passed)
        unique_colors = len(np.unique(data))
        if unique_colors > self.MAX_SNES_COLORS:
            errors.append(f"Uses {unique_colors} colors (SNES 4bpp max: {self.MAX_SNES_COLORS})")

        # Check palette index range explicitly (unique count alone is insufficient)
        if data.size > 0:
            max_index = int(np.max(data))
            if max_index > 15:
                errors.append(f"Uses palette index {max_index} (SNES 4bpp max: 15)")

        # Emit signal only if validation state changed
        is_valid = len(errors) == 0
        if errors != self._validation_errors or is_valid != self._is_valid_for_rom:
            self._validation_errors = errors
            self._is_valid_for_rom = is_valid
            self.validationChanged.emit(is_valid, errors)
            if not is_valid:
                logger.warning("ROM validation failed: %s", "; ".join(errors))

    def is_valid_for_rom(self) -> bool:
        """Check if current image can be saved to ROM without errors."""
        return self._is_valid_for_rom

    def get_validation_errors(self) -> list[str]:
        """Get list of current validation error messages."""
        return self._validation_errors.copy()

    def force_validation(self) -> None:
        """
        Force re-validation of ROM constraints.

        Call this after loading a new image to ensure validation state is up-to-date.
        """
        self._validate_rom_constraints()
