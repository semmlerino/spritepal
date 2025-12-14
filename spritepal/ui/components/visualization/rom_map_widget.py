"""
ROM Map Visualization Widget

Visual representation of ROM with sprite locations for manual offset exploration.
"""

from __future__ import annotations

from typing import Any

try:
    from typing_extensions import override
except ImportError:
    from typing_extensions import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.styles.theme import COLORS
from utils.logging_config import get_logger
from utils.sprite_regions import SpriteRegion

logger = get_logger(__name__)

# Memory management constants
MAX_SPRITES_IN_MAP = 10000  # Maximum sprites to keep in memory
SPRITE_CLEANUP_THRESHOLD = 12000  # Start cleanup when we exceed this
SPRITE_CLEANUP_TARGET = 8000  # Clean down to this many sprites

class ROMMapWidget(QWidget):
    """Visual representation of ROM with sprite locations"""

    offset_clicked: Signal = Signal(int)  # Emitted when user clicks on the ROM map

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rom_size: int = 0x400000  # Default 4MB
        self.current_offset: int = 0
        self.found_sprites: list[tuple[int, float]] = []  # List of (offset, quality) tuples
        self._needs_update: bool = False  # Track if widget needs visual update

        # Smart mode region visualization
        self.sprite_regions: list[SpriteRegion] = []
        self.current_region_index: int = -1
        self.highlight_regions: bool = True

        self.setMinimumHeight(60)
        self.setMaximumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self.hover_offset: int | None = None

    def set_rom_size(self, size: int):
        """Update the ROM size"""
        self.rom_size = size
        self.update()

    def set_current_offset(self, offset: int):
        """Update the current offset position"""
        self.current_offset = offset
        self.update()

    def add_found_sprite(self, offset: int, quality: float = 1.0):
        """Add a found sprite location with memory management"""
        # Check for duplicates (same offset)
        for i, (existing_offset, existing_quality) in enumerate(self.found_sprites):
            if existing_offset == offset:
                # Update quality if new one is better
                if quality > existing_quality:
                    self.found_sprites[i] = (offset, quality)
                    self._schedule_update()
                return

        # Add new sprite
        self.found_sprites.append((offset, quality))

        # Memory management: cleanup if we have too many sprites
        if len(self.found_sprites) > SPRITE_CLEANUP_THRESHOLD:
            self._cleanup_sprites()

        self._schedule_update()

    def add_found_sprites_batch(self, sprites: list[tuple[int, float]]):
        """Add multiple sprites efficiently"""
        # Create a set of existing offsets for quick lookup
        existing_offsets = {offset for offset, _ in self.found_sprites}

        # Filter out duplicates and add new sprites
        new_sprites = [(offset, quality) for offset, quality in sprites
                      if offset not in existing_offsets]

        if new_sprites:
            self.found_sprites.extend(new_sprites)

            # Memory management after batch add
            if len(self.found_sprites) > SPRITE_CLEANUP_THRESHOLD:
                self._cleanup_sprites()

            self._schedule_update()

    def clear_sprites(self):
        """Clear all found sprite markers"""
        if self.found_sprites:  # Only clear if there are sprites
            self.found_sprites = []
            self.update()

    def get_sprite_count(self) -> int:
        """Get the current number of sprites in the map"""
        return len(self.found_sprites)

    def set_sprite_regions(self, regions: list[SpriteRegion]):
        """Set sprite regions for visualization"""
        self.sprite_regions = regions
        self.update()

    def set_current_region(self, region_index: int):
        """Highlight the current region"""
        if self.current_region_index != region_index:
            self.current_region_index = region_index
            self.update()

    def toggle_region_highlight(self, enabled: bool):
        """Toggle region highlighting on/off"""
        self.highlight_regions = enabled
        self.update()

    def _cleanup_sprites(self):
        """Clean up sprites when memory usage gets too high"""
        if len(self.found_sprites) <= SPRITE_CLEANUP_TARGET:
            return

        # Sort sprites by quality (descending) and keep the best ones
        self.found_sprites.sort(key=lambda x: x[1], reverse=True)
        self.found_sprites = self.found_sprites[:SPRITE_CLEANUP_TARGET]

        # Re-sort by offset for consistent visualization
        self.found_sprites.sort(key=lambda x: x[0])

    def _schedule_update(self):
        """Schedule a widget update, optimizing for performance"""
        if self.isVisible():
            self.update()
        else:
            self._needs_update = True

    @override
    def showEvent(self, event: Any):
        """Handle widget becoming visible"""
        super().showEvent(event)
        if self._needs_update:
            self.update()
            self._needs_update = False

    @override
    def paintEvent(self, a0: QPaintEvent | None):
        """Paint the ROM map visualization with error recovery"""
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Get widget dimensions with bounds checking
            width = max(1, self.width())  # Ensure minimum width
            height = max(1, self.height())  # Ensure minimum height

            # Draw background
            painter.fillRect(0, 0, width, height, Qt.GlobalColor.black)

            # Draw ROM regions
            # Common sprite areas (based on typical SNES ROM layout)
            regions = [
                (0x000000, 0x100000, COLORS["input_background"], "Low ROM"),
                (0x100000, 0x200000, COLORS["panel_background"], "Mid ROM"),
                (0x200000, 0x300000, COLORS["border"], "High ROM"),
                (0x300000, 0x400000, COLORS["border"], "Extended ROM"),
            ]

            for start, end, color, _label in regions:
                if start < self.rom_size:
                    x_start = int((start / self.rom_size) * width)
                    x_end = int((min(end, self.rom_size) / self.rom_size) * width)
                    painter.fillRect(x_start, 20, x_end - x_start, height - 40, QColor(color))

            # Draw sprite regions if in smart mode
            if self.sprite_regions and self.highlight_regions:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)

                for i, region in enumerate(self.sprite_regions):
                    if 0 <= region.start_offset < self.rom_size:
                        x_start = int((region.start_offset / self.rom_size) * width)
                        x_end = int((min(region.end_offset, self.rom_size) / self.rom_size) * width)

                        # Different colors for current/other regions
                        if i == self.current_region_index:
                            # Highlighted current region
                            painter.fillRect(x_start, 10, x_end - x_start, height - 20,
                                           QColor(100, 150, 255, 60))  # Highlighted blue
                            painter.setPen(QPen(QColor(100, 150, 255), 2))
                        else:
                            # Other regions
                            painter.fillRect(x_start, 10, x_end - x_start, height - 20,
                                           QColor(80, 80, 80, 40))  # Subtle gray
                            painter.setPen(QPen(QColor(120, 120, 120), 1))

                        # Draw region boundaries
                        painter.drawRect(x_start, 10, x_end - x_start, height - 20)

                        # Draw region number if space permits
                        if x_end - x_start > 20:
                            painter.setPen(Qt.GlobalColor.white)
                            painter.setFont(QFont("Arial", 8))
                            painter.drawText(x_start + 2, 25, f"R{i+1}")

            # Draw found sprites with bounds checking
            painter.setPen(Qt.PenStyle.NoPen)
            for offset, quality in self.found_sprites:
                if 0 <= offset < self.rom_size:  # Enhanced bounds checking
                    try:
                        x = int((offset / max(1, self.rom_size)) * width)  # Prevent division by zero
                        # Ensure x is within widget bounds
                        x = max(0, min(x, width - 1))

                        # Color based on quality (green = high, yellow = medium, red = low)
                        if quality > 0.8:
                            painter.setBrush(Qt.GlobalColor.green)
                        elif quality > 0.5:
                            painter.setBrush(Qt.GlobalColor.yellow)
                        else:
                            painter.setBrush(Qt.GlobalColor.red)

                        # Draw sprite marker with bounds checking
                        rect_height = max(1, height - 30)
                        painter.drawRect(x - 2, 15, 4, rect_height)
                    except (ArithmeticError, ValueError) as e:
                        # Skip this sprite if calculation fails
                        logger.warning(f"Error drawing sprite at offset 0x{offset:06X}: {e}")
                        continue

            # Draw current position indicator with error recovery
            if 0 <= self.current_offset < self.rom_size:
                try:
                    x = int((self.current_offset / max(1, self.rom_size)) * width)
                    x = max(0, min(x, width - 1))  # Ensure x is within bounds

                    painter.setPen(Qt.GlobalColor.cyan)
                    painter.pen().setWidth(2)
                    painter.drawLine(x, 0, x, height)

                    # Draw position label with bounds checking
                    painter.setPen(Qt.GlobalColor.white)
                    offset_text = f"0x{self.current_offset:06X}"
                    text_x = max(5, min(x - 30, width - 65))
                    painter.drawText(text_x, 12, offset_text)
                except (ArithmeticError, ValueError) as e:
                    logger.warning(f"Error drawing current position indicator: {e}")

            # Draw scale markers with error recovery
            painter.setPen(Qt.GlobalColor.gray)
            try:
                for i in range(5):  # 0%, 25%, 50%, 75%, 100%
                    x = int((i / 4) * width)
                    x = max(0, min(x, width - 1))  # Bounds check
                    painter.drawLine(x, height - 10, x, height)

                    # Draw MB labels with bounds checking
                    mb_value = int((i / 4) * (self.rom_size / 0x100000)) if self.rom_size > 0 else 0
                    text_x = max(0, min(x - 15, width - 30))
                    painter.drawText(text_x, height - 12, f"{mb_value}MB")
            except (ArithmeticError, ValueError) as e:
                logger.warning(f"Error drawing scale markers: {e}")

        except (RuntimeError, ValueError, ArithmeticError):
            logger.exception("Paint error in ROM map widget")
            # Draw minimal error state
            try:
                painter = QPainter(self)
                painter.fillRect(self.rect(), Qt.GlobalColor.darkRed)
                painter.setPen(Qt.GlobalColor.white)
                painter.drawText(10, 20, "Visualization Error")
            except Exception:
                pass  # Prevent cascading failures
        except Exception:
            logger.exception("Unexpected error in ROM map paint event")

    @override
    def mousePressEvent(self, a0: QMouseEvent | None):
        """Handle mouse clicks on the ROM map"""
        if a0 and a0.button() == Qt.MouseButton.LeftButton:
            # Calculate offset from click position
            offset = int((a0.position().x() / self.width()) * self.rom_size)
            offset = max(0, min(offset, self.rom_size - 1))
            self.offset_clicked.emit(offset)

    @override
    def mouseMoveEvent(self, a0: QMouseEvent | None):
        """Handle mouse hover to show offset preview"""
        if a0:
            self.hover_offset = int((a0.position().x() / self.width()) * self.rom_size)
            self.setToolTip(f"Click to jump to 0x{self.hover_offset:06X}")
