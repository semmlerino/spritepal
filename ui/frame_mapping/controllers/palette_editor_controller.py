#!/usr/bin/env python3
"""
Controller for the AI Frame Palette Editor.

Manages the editing model, selection, undo/redo, and tool state.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, QTimer, Signal

from core.editing import (
    DrawPixelCommand,
    FloodFillCommand,
    IndexedImageModel,
    SelectionMask,
    SelectionPaintCommand,
    UndoManager,
)
from core.services.rgb_to_indexed import (
    convert_indexed_to_pil_indexed,
    convert_rgb_to_indexed,
)

if TYPE_CHECKING:
    from pathlib import Path

    from core.frame_mapping_project import SheetPalette

logger = logging.getLogger(__name__)


class EditorTool(Enum):
    """Available editing tools."""

    PENCIL = auto()
    ERASER = auto()
    FILL = auto()
    CONTIGUOUS_SELECT = auto()
    GLOBAL_SELECT = auto()


class SelectionMode(Enum):
    """Selection modification modes."""

    REPLACE = auto()  # Replace existing selection
    ADD = auto()  # Add to selection (Shift)
    SUBTRACT = auto()  # Remove from selection (Ctrl)


class PaletteEditorController(QObject):
    """Controller for palette-index editing operations.

    Manages:
    - IndexedImageModel: The pixel data being edited
    - SelectionMask: Current selection state
    - UndoManager: Undo/redo stack
    - Tool state: Active tool and settings
    - Palette index: Currently selected color index

    Signals:
        image_changed: Image data was modified
        selection_changed: Selection mask was modified
        undo_state_changed: (can_undo, can_redo) - Undo availability changed
        pixel_info: (x, y, index) - Pixel info for status bar
        preview_requested: Debounced request to update workspace preview
        dirty_changed: (is_dirty) - Modification state changed
    """

    image_changed = Signal()
    selection_changed = Signal()
    undo_state_changed = Signal(bool, bool)  # can_undo, can_redo
    pixel_info = Signal(int, int, int)  # x, y, palette_index
    preview_requested = Signal(np.ndarray)  # indexed data for preview
    dirty_changed = Signal(bool)  # is_dirty

    PREVIEW_DEBOUNCE_MS = 100

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # Model components
        self._image_model: IndexedImageModel | None = None
        self._selection_mask: SelectionMask | None = None
        self._undo_manager = UndoManager(max_commands=100)
        self._palette: SheetPalette | None = None

        # Tool state
        self._current_tool = EditorTool.PENCIL
        self._active_index = 1  # Default to index 1 (not transparent)
        self._brush_size = 1

        # Modification tracking
        self._is_dirty = False
        self._original_path: Path | None = None

        # Preview debounce timer
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_preview)

    # --- Initialization ---

    def load_image(
        self,
        image_path: Path,
        palette: SheetPalette,
    ) -> bool:
        """Load an RGB image and convert to indexed format.

        Args:
            image_path: Path to the RGB PNG image
            palette: SheetPalette to use for conversion

        Returns:
            True if loaded successfully
        """
        try:
            pil_image = Image.open(image_path)
            indexed_data = convert_rgb_to_indexed(pil_image, palette)

            self._image_model = IndexedImageModel()
            self._image_model.set_data(indexed_data)

            self._palette = palette
            self._original_path = image_path

            # Create matching selection mask
            height, width = indexed_data.shape
            self._selection_mask = SelectionMask(width, height)

            # Reset state
            self._undo_manager.clear()
            self._is_dirty = False
            self._emit_undo_state()

            self.image_changed.emit()
            self.selection_changed.emit()
            self.dirty_changed.emit(False)

            logger.info("Loaded image %s (%dx%d)", image_path, width, height)
            return True

        except Exception:
            logger.exception("Failed to load image: %s", image_path)
            return False

    def load_indexed_data(
        self,
        indexed_data: np.ndarray,
        palette: SheetPalette,
        original_path: Path | None = None,
    ) -> None:
        """Load pre-converted indexed data.

        Args:
            indexed_data: 2D numpy array of palette indices
            palette: SheetPalette for colors
            original_path: Optional source path for reference
        """
        self._image_model = IndexedImageModel()
        self._image_model.set_data(indexed_data.copy())

        self._palette = palette
        self._original_path = original_path

        height, width = indexed_data.shape
        self._selection_mask = SelectionMask(width, height)

        self._undo_manager.clear()
        self._is_dirty = False
        self._emit_undo_state()

        self.image_changed.emit()
        self.selection_changed.emit()
        self.dirty_changed.emit(False)

    # --- Properties ---

    @property
    def image_model(self) -> IndexedImageModel | None:
        """Get the current image model."""
        return self._image_model

    @property
    def selection_mask(self) -> SelectionMask | None:
        """Get the current selection mask."""
        return self._selection_mask

    @property
    def palette(self) -> SheetPalette | None:
        """Get the current palette."""
        return self._palette

    @property
    def current_tool(self) -> EditorTool:
        """Get the current tool."""
        return self._current_tool

    @property
    def active_index(self) -> int:
        """Get the currently selected palette index."""
        return self._active_index

    @property
    def brush_size(self) -> int:
        """Get the current brush size."""
        return self._brush_size

    @property
    def is_dirty(self) -> bool:
        """Check if there are unsaved changes."""
        return self._is_dirty

    @property
    def original_path(self) -> Path | None:
        """Get the original image path."""
        return self._original_path

    # --- Tool Management ---

    def set_tool(self, tool: EditorTool) -> None:
        """Set the active tool."""
        self._current_tool = tool
        logger.debug("Tool changed to %s", tool.name)

    def set_active_index(self, index: int) -> None:
        """Set the active palette index."""
        if 0 <= index <= 15:
            self._active_index = index
            logger.debug("Active index changed to %d", index)

    def set_brush_size(self, size: int) -> None:
        """Set the brush size (1-5)."""
        self._brush_size = max(1, min(5, size))

    def set_palette_color(self, index: int, color: tuple[int, int, int]) -> None:
        """Change a palette color.

        Args:
            index: Palette index (1-15, 0 is always transparent)
            color: RGB tuple (r, g, b)
        """
        if not self._palette:
            return
        if not 0 < index < len(self._palette.colors):
            return

        # Update the palette color
        self._palette.colors[index] = color
        self._mark_dirty()
        # Trigger canvas refresh with new palette colors
        self.image_changed.emit()

    # --- Pixel Operations ---

    def handle_pixel_click(
        self,
        x: int,
        y: int,
        button: int,
        modifiers: int = 0,
    ) -> None:
        """Handle a pixel click event.

        Args:
            x: Pixel x coordinate
            y: Pixel y coordinate
            button: Mouse button (0=left, 1=right)
            modifiers: Keyboard modifiers (Qt flags)
        """
        print(f"[DEBUG] handle_pixel_click({x}, {y}, button={button}, tool={self._current_tool})")  # noqa: T201
        if self._image_model is None:
            print("[DEBUG] No image model!")  # noqa: T201
            return

        # Right-click picks color
        if button == 1:
            picked_index = self._image_model.get_pixel(x, y)
            self.set_active_index(picked_index)
            self.pixel_info.emit(x, y, picked_index)
            return

        # Determine selection mode from modifiers
        from PySide6.QtCore import Qt

        mod_flags = Qt.KeyboardModifier(modifiers)
        if mod_flags & Qt.KeyboardModifier.ShiftModifier:
            sel_mode = SelectionMode.ADD
        elif mod_flags & Qt.KeyboardModifier.ControlModifier:
            sel_mode = SelectionMode.SUBTRACT
        else:
            sel_mode = SelectionMode.REPLACE

        # Dispatch to tool handlers
        if self._current_tool == EditorTool.PENCIL:
            self._handle_pencil(x, y)
        elif self._current_tool == EditorTool.ERASER:
            self._handle_eraser(x, y)
        elif self._current_tool == EditorTool.FILL:
            self._handle_fill(x, y)
        elif self._current_tool == EditorTool.CONTIGUOUS_SELECT:
            self._handle_contiguous_select(x, y, sel_mode)
        elif self._current_tool == EditorTool.GLOBAL_SELECT:
            self._handle_global_select(x, y, sel_mode)

    def handle_pixel_drag(self, x: int, y: int) -> None:
        """Handle pixel drag during drawing.

        Args:
            x: Pixel x coordinate
            y: Pixel y coordinate
        """
        if self._image_model is None:
            return

        # Only pencil and eraser work with drag
        if self._current_tool == EditorTool.PENCIL:
            self._handle_pencil(x, y)
        elif self._current_tool == EditorTool.ERASER:
            self._handle_eraser(x, y)

    def handle_pixel_hover(self, x: int, y: int) -> None:
        """Handle pixel hover for status updates.

        Args:
            x: Pixel x coordinate
            y: Pixel y coordinate
        """
        if self._image_model is None:
            return

        index = self._image_model.get_pixel(x, y)
        self.pixel_info.emit(x, y, index)

    # --- Tool Implementations ---

    def _handle_pencil(self, x: int, y: int) -> None:
        """Handle pencil tool click/drag."""
        print(f"[DEBUG] _handle_pencil({x}, {y}), active_index={self._active_index}")  # noqa: T201
        if self._image_model is None:
            return

        # Get pixels in brush area
        pixels_to_paint = self._get_brush_pixels(x, y)
        print(f"[DEBUG] Painting {len(pixels_to_paint)} pixels")  # noqa: T201

        commands_added = 0
        for px, py in pixels_to_paint:
            old_color = self._image_model.get_pixel(px, py)
            if old_color != self._active_index:
                cmd = DrawPixelCommand(
                    x=px,
                    y=py,
                    old_color=old_color,
                    new_color=self._active_index,
                )
                self._undo_manager.execute_command(cmd, self._image_model)
                commands_added += 1

        print(f"[DEBUG] Added {commands_added} commands, stack_size={len(self._undo_manager.command_stack)}, can_undo={self._undo_manager.can_undo()}")  # noqa: T201
        self._mark_dirty()
        self._emit_undo_state()  # Update undo/redo button state
        print("[DEBUG] Emitting image_changed")  # noqa: T201
        self.image_changed.emit()
        self._schedule_preview()

    def _handle_eraser(self, x: int, y: int) -> None:
        """Handle eraser tool click/drag (sets to index 0)."""
        if self._image_model is None:
            return

        pixels_to_erase = self._get_brush_pixels(x, y)

        for px, py in pixels_to_erase:
            old_color = self._image_model.get_pixel(px, py)
            if old_color != 0:
                cmd = DrawPixelCommand(x=px, y=py, old_color=old_color, new_color=0)
                self._undo_manager.execute_command(cmd, self._image_model)

        self._mark_dirty()
        self.image_changed.emit()
        self._schedule_preview()

    def _handle_fill(self, x: int, y: int) -> None:
        """Handle flood fill tool click."""
        if self._image_model is None:
            return

        old_color = self._image_model.get_pixel(x, y)
        if old_color == self._active_index:
            return

        cmd = FloodFillCommand(
            x=x,
            y=y,
            old_color=old_color,
            new_color=self._active_index,
        )
        self._undo_manager.execute_command(cmd, self._image_model)

        self._mark_dirty()
        self.image_changed.emit()
        self._schedule_preview()

    def _handle_contiguous_select(self, x: int, y: int, mode: SelectionMode) -> None:
        """Handle contiguous (magic wand) selection."""
        if self._image_model is None or self._selection_mask is None:
            return

        region = self._image_model.get_contiguous_region(x, y)

        if mode == SelectionMode.REPLACE:
            self._selection_mask.set_pixels(region)
        elif mode == SelectionMode.ADD:
            self._selection_mask.add_pixels(region)
        elif mode == SelectionMode.SUBTRACT:
            self._selection_mask.remove_pixels(region)

        self.selection_changed.emit()

    def _handle_global_select(self, x: int, y: int, mode: SelectionMode) -> None:
        """Handle global index selection."""
        if self._image_model is None or self._selection_mask is None:
            return

        target_index = self._image_model.get_pixel(x, y)
        pixels = self._image_model.get_global_index_pixels(target_index)

        if mode == SelectionMode.REPLACE:
            self._selection_mask.set_pixels(pixels)
        elif mode == SelectionMode.ADD:
            self._selection_mask.add_pixels(pixels)
        elif mode == SelectionMode.SUBTRACT:
            self._selection_mask.remove_pixels(pixels)

        self.selection_changed.emit()

    def _get_brush_pixels(self, x: int, y: int) -> list[tuple[int, int]]:
        """Get all pixels affected by brush at position."""
        if self._image_model is None:
            return []

        pixels = []
        half = self._brush_size // 2

        for dy in range(-half, half + 1):
            for dx in range(-half, half + 1):
                px, py = x + dx, y + dy
                if 0 <= px < self._image_model.width and 0 <= py < self._image_model.height:
                    pixels.append((px, py))

        return pixels

    # --- Selection Operations ---

    def select_all(self) -> None:
        """Select all pixels."""
        if self._selection_mask is not None:
            self._selection_mask.select_all()
            self.selection_changed.emit()

    def deselect_all(self) -> None:
        """Clear selection."""
        if self._selection_mask is not None:
            self._selection_mask.clear()
            self.selection_changed.emit()

    def invert_selection(self) -> None:
        """Invert the current selection."""
        if self._selection_mask is not None:
            self._selection_mask.invert()
            self.selection_changed.emit()

    def paint_selection(self, index: int | None = None) -> None:
        """Paint all selected pixels with the active (or specified) index.

        Args:
            index: Palette index to use, or None for active index
        """
        if self._image_model is None or self._selection_mask is None:
            return

        if not self._selection_mask.has_selection():
            return

        paint_index = index if index is not None else self._active_index

        cmd = SelectionPaintCommand.from_selection(
            self._selection_mask.get_selected_pixels(),
            paint_index,
            self._image_model,
        )

        if cmd.affected_pixels:
            self._undo_manager.execute_command(cmd, self._image_model)
            self._mark_dirty()
            self.image_changed.emit()
            self._schedule_preview()

    def erase_selection(self) -> None:
        """Erase selected pixels (set to index 0)."""
        self.paint_selection(0)

    # --- Undo/Redo ---

    def undo(self) -> bool:
        """Undo the last operation."""
        print(f"[DEBUG] undo() called, can_undo={self._undo_manager.can_undo()}, stack_size={len(self._undo_manager.command_stack)}, current_index={self._undo_manager.current_index}")  # noqa: T201
        if self._image_model is None:
            print("[DEBUG] No image model for undo")  # noqa: T201
            return False

        result = self._undo_manager.undo(self._image_model)
        print(f"[DEBUG] undo result: {result}")  # noqa: T201
        if result:
            self._emit_undo_state()
            self.image_changed.emit()
            self._schedule_preview()
            # Check if we're back to clean state
            if not self._undo_manager.can_undo():
                self._is_dirty = False
                self.dirty_changed.emit(False)
        return result

    def redo(self) -> bool:
        """Redo the next operation."""
        if self._image_model is None:
            return False

        result = self._undo_manager.redo(self._image_model)
        if result:
            self._mark_dirty()
            self._emit_undo_state()
            self.image_changed.emit()
            self._schedule_preview()
        return result

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self._undo_manager.can_undo()

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self._undo_manager.can_redo()

    # --- Save Operations ---

    def save(self, output_path: Path) -> bool:
        """Save the edited image as an indexed PNG.

        Args:
            output_path: Path to save the PNG file

        Returns:
            True if saved successfully
        """
        if self._image_model is None or self._palette is None:
            return False

        try:
            pil_image = convert_indexed_to_pil_indexed(
                self._image_model.data,
                self._palette,
            )
            pil_image.save(output_path)

            self._is_dirty = False
            self.dirty_changed.emit(False)

            logger.info("Saved edited image to %s", output_path)
            return True

        except Exception:
            logger.exception("Failed to save image: %s", output_path)
            return False

    def get_indexed_data(self) -> np.ndarray | None:
        """Get the current indexed data for external use.

        Returns:
            Copy of the indexed data array, or None if not loaded
        """
        if self._image_model is None:
            return None
        return self._image_model.data.copy()

    # --- Internal Methods ---

    def _mark_dirty(self) -> None:
        """Mark the model as having unsaved changes."""
        if not self._is_dirty:
            self._is_dirty = True
            self.dirty_changed.emit(True)

    def _emit_undo_state(self) -> None:
        """Emit current undo/redo availability."""
        self.undo_state_changed.emit(
            self._undo_manager.can_undo(),
            self._undo_manager.can_redo(),
        )

    def _schedule_preview(self) -> None:
        """Schedule a debounced preview update."""
        self._preview_timer.start(self.PREVIEW_DEBOUNCE_MS)

    def _emit_preview(self) -> None:
        """Emit preview data after debounce."""
        if self._image_model is not None:
            self.preview_requested.emit(self._image_model.data.copy())
