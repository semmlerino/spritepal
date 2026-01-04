"""
Enhanced Sprite Navigator Widget

The main navigation interface that provides intuitive sprite discovery with visual feedback.
Features:
- Interactive ROM map with sprite density heatmap
- Quick navigation controls (next/prev sprite)
- Region-aware jumping
- Thumbnail previews for nearby sprites
- Keyboard-friendly navigation
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.services.rom_cache import ROMCache

from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common import WorkerManager
from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.spacing_constants import ROM_MAP_HEIGHT_MIN, SPACING_SMALL, SPACING_TINY
from ui.components.navigation.region_jump_widget import RegionJumpWidget
from ui.components.visualization.rom_map_widget import ROMMapWidget
from ui.rom_extraction.workers import SpritePreviewWorker
from ui.styles.theme import COLORS
from ui.widgets.sprite_preview_widget import SpritePreviewWidget
from utils.constants import ROM_SIZE_2MB, ROM_SIZE_4MB
from utils.logging_config import get_logger
from utils.sprite_regions import SpriteRegion, SpriteRegionDetector

logger = get_logger(__name__)

# Navigation constants
THUMBNAIL_SIZE = 64
MAX_THUMBNAILS = 5
NAVIGATION_STEP_SMALL = 0x100
NAVIGATION_STEP_MEDIUM = 0x1000
NAVIGATION_STEP_LARGE = 0x10000


class SpriteThumbnail(QWidget):
    """A small preview widget for nearby sprites"""

    clicked = Signal(int)  # Emitted when thumbnail is clicked

    def __init__(self, offset: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.offset = offset
        self.quality = 0.0

        # UI components
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        # Don't use setScaledContents - preserve aspect ratio
        self.preview_label.setScaledContents(False)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(f"""
            QLabel {{
                background: {COLORS["input_background"]};
                border: 2px solid {COLORS["border"]};
                border-radius: 4px;
                padding: 2px;
            }}
            QLabel:hover {{
                border: 2px solid {COLORS["highlight"]};
                background: {COLORS["panel_background"]};
            }}
        """)

        self.offset_label = QLabel(f"0x{offset:06X}")
        self.offset_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        self.offset_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Layout - very tight spacing for compact thumbnails
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_TINY // 2)
        layout.setContentsMargins(SPACING_TINY // 2, SPACING_TINY // 2, SPACING_TINY // 2, SPACING_TINY // 2)
        layout.addWidget(self.preview_label)
        layout.addWidget(self.offset_label)

        # Make clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_label.mousePressEvent = lambda e: self.clicked.emit(self.offset)

    def set_sprite(self, pixmap: QPixmap, offset: int, quality: float = 1.0):
        """Update thumbnail with sprite data"""
        self.offset = offset
        self.quality = quality
        # Scale pixmap to fit while preserving aspect ratio
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled)
        else:
            self.preview_label.setPixmap(pixmap)
        self.offset_label.setText(f"0x{offset:06X}")

        # Update border color based on quality
        if quality > 0.8:
            border_color = COLORS["success"]  # Green for high quality
        elif quality > 0.5:
            border_color = COLORS["warning"]  # Yellow for medium
        else:
            border_color = COLORS["danger"]  # Red for low quality

        self.preview_label.setStyleSheet(f"""
            QLabel {{
                background: {COLORS["input_background"]};
                border: 2px solid {border_color};
                border-radius: 4px;
                padding: 2px;
            }}
            QLabel:hover {{
                border: 2px solid {COLORS["highlight"]};
                background: {COLORS["panel_background"]};
            }}
        """)

    def clear(self):
        """Clear thumbnail display"""
        self.preview_label.clear()
        self.preview_label.setText("Empty")
        self.preview_label.setStyleSheet(f"""
            QLabel {{
                background: {COLORS["preview_background"]};
                border: 2px solid {COLORS["panel_background"]};
                border-radius: 4px;
                padding: 2px;
                color: {COLORS["border"]};
            }}
        """)
        self.offset_label.setText("--")


class SpriteNavigator(QWidget):
    """
    Enhanced sprite navigation widget providing intuitive ROM exploration.

    Features:
    - Visual ROM map with sprite density heatmap
    - Smart navigation between sprites
    - Region-based jumping
    - Thumbnail previews of nearby sprites
    - Keyboard navigation support
    """

    # Signals
    offset_changed = Signal(int)  # Emitted when navigation changes offset
    sprite_selected = Signal(int, str)  # offset, name when sprite is selected
    region_changed = Signal(int)  # Emitted when region selection changes
    navigation_mode_changed = Signal(str)  # "manual" or "smart"

    def __init__(self, parent: QWidget | None = None, *, rom_cache: ROMCache):
        super().__init__(parent)

        # State
        self.current_offset = ROM_SIZE_2MB
        self.rom_path = ""
        self.rom_size = ROM_SIZE_4MB
        self.extraction_manager: CoreOperationsManager | None = None
        self.found_sprites: list[tuple[int, float]] = []
        self.sprite_regions: list[SpriteRegion] = []
        self.navigation_mode = "manual"  # "manual" or "smart"

        # Cache and performance
        self.rom_cache = rom_cache
        self.thumbnail_cache: dict[int, QPixmap] = {}
        self._last_thumbnail_update = 0

        # Workers
        self.preview_workers: list[SpritePreviewWorker] = []

        # Navigation history for back/forward
        self.navigation_history: list[int] = []
        self.history_index = -1
        self.max_history = 50

        # UI Components
        self.rom_map: ROMMapWidget | None = None
        self.region_jump: RegionJumpWidget | None = None
        self.position_label: QLabel | None = None
        self.context_label: QLabel | None = None
        self.prev_button: QPushButton | None = None
        self.next_button: QPushButton | None = None
        self.thumbnail_container: QWidget | None = None
        self.thumbnails: list[SpriteThumbnail] = []
        self.main_preview: SpritePreviewWidget | None = None

        self._setup_ui()
        self._connect_signals()

        # Enable keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_ui(self) -> None:
        """Create the UI layout"""
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_SMALL)
        layout.setContentsMargins(0, 0, 0, 0)

        # Main navigation frame
        nav_frame = QFrame()
        nav_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        nav_frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        nav_layout = QVBoxLayout(nav_frame)

        # Title bar with position info
        title_bar = QHBoxLayout()

        title = QLabel("Sprite Navigator")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {COLORS['highlight']};")
        title_bar.addWidget(title)

        title_bar.addStretch()

        # Position and context display
        position_container = QWidget()
        position_layout = QVBoxLayout(position_container)
        position_layout.setSpacing(0)
        position_layout.setContentsMargins(0, 0, 0, 0)

        self.position_label = QLabel("0x200000")
        self.position_label.setStyleSheet(f"""
            font-family: monospace;
            font-size: 14px;
            font-weight: bold;
            color: {COLORS["text_primary"]};
        """)
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.context_label = QLabel("High ROM - Common sprite area")
        self.context_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        self.context_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        position_layout.addWidget(self.position_label)
        position_layout.addWidget(self.context_label)
        title_bar.addWidget(position_container)

        nav_layout.addLayout(title_bar)

        # ROM Map with density visualization
        map_section = CollapsibleGroupBox("ROM Map", collapsed=False)

        # Create a container widget for the map layout
        map_container = QWidget()
        map_layout = QVBoxLayout(map_container)

        self.rom_map = ROMMapWidget()
        self.rom_map.setMinimumHeight(ROM_MAP_HEIGHT_MIN)  # Compact height
        self.rom_map.setMaximumHeight(50)  # Compact height
        map_layout.addWidget(self.rom_map)

        # Map controls
        map_controls = QHBoxLayout()
        map_controls.setSpacing(SPACING_TINY)

        density_label = QLabel("Sprite Density:")
        density_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        map_controls.addWidget(density_label)

        # Density legend
        for color, text in [(COLORS["success"], "High"), (COLORS["warning"], "Medium"), (COLORS["danger"], "Low")]:
            legend_item = QLabel("■")
            legend_item.setStyleSheet(f"color: {color}; font-size: 14px;")
            map_controls.addWidget(legend_item)
            legend_label = QLabel(text)
            legend_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']}; margin-right: 10px;")
            map_controls.addWidget(legend_label)

        map_controls.addStretch()
        map_layout.addLayout(map_controls)

        map_section.add_widget(map_container)
        nav_layout.addWidget(map_section)

        # Navigation Controls
        nav_controls = CollapsibleGroupBox("Navigation", collapsed=False)

        # Create a container widget for the controls layout
        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)

        # Quick navigation buttons
        button_row = QHBoxLayout()
        button_row.setSpacing(SPACING_TINY)

        self.prev_button = QPushButton("◀ Previous Sprite")
        self.prev_button.setMinimumHeight(32)
        self.prev_button.setToolTip("Navigate to previous sprite (PageUp)")
        button_row.addWidget(self.prev_button)

        self.next_button = QPushButton("Next Sprite ▶")
        self.next_button.setMinimumHeight(32)
        self.next_button.setToolTip("Navigate to next sprite (PageDown)")
        button_row.addWidget(self.next_button)

        controls_layout.addLayout(button_row)

        # Region jump widget
        self.region_jump = RegionJumpWidget()
        controls_layout.addWidget(self.region_jump)

        # Mode selector
        mode_row = QHBoxLayout()
        mode_label = QLabel("Navigation Mode:")
        mode_label.setStyleSheet("font-size: 11px;")
        mode_row.addWidget(mode_label)

        manual_btn = QPushButton("Manual")
        manual_btn.setCheckable(True)
        manual_btn.setChecked(True)
        manual_btn.setMaximumWidth(80)
        manual_btn.clicked.connect(lambda: self._set_navigation_mode("manual"))
        mode_row.addWidget(manual_btn)

        smart_btn = QPushButton("Smart")
        smart_btn.setCheckable(True)
        smart_btn.setMaximumWidth(80)
        smart_btn.clicked.connect(lambda: self._set_navigation_mode("smart"))
        mode_row.addWidget(smart_btn)

        self.mode_buttons = [manual_btn, smart_btn]

        mode_row.addStretch()
        controls_layout.addLayout(mode_row)

        nav_controls.add_widget(controls_container)
        nav_layout.addWidget(nav_controls)

        # Nearby Sprites Preview
        preview_section = CollapsibleGroupBox("Nearby Sprites", collapsed=False)

        # Create a container widget for the preview layout
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)

        # Thumbnail container
        self.thumbnail_container = QWidget()
        thumbnail_layout = QHBoxLayout(self.thumbnail_container)
        thumbnail_layout.setSpacing(SPACING_TINY)

        # Create thumbnail widgets
        for _i in range(MAX_THUMBNAILS):
            thumbnail = SpriteThumbnail()
            thumbnail.clicked.connect(self._on_thumbnail_clicked)
            self.thumbnails.append(thumbnail)
            thumbnail_layout.addWidget(thumbnail)

        preview_layout.addWidget(self.thumbnail_container)

        # Selected sprite preview
        self.main_preview = SpritePreviewWidget("Selected Sprite")
        self.main_preview.setMaximumHeight(200)
        preview_layout.addWidget(self.main_preview)

        preview_section.add_widget(preview_container)
        nav_layout.addWidget(preview_section)

        layout.addWidget(nav_frame)

        # Keyboard shortcuts help
        help_text = QLabel("Keyboard: ← → (fine), PageUp/Down (sprites), Ctrl+G (go to), Ctrl+B (bookmarks)")
        help_text.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']}; padding: 4px;")
        help_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(help_text)

    def _connect_signals(self):
        """Connect internal signals"""
        # ROM map interaction
        if self.rom_map is not None:
            self.rom_map.offset_clicked.connect(self._on_map_clicked)

        # Navigation buttons
        if self.prev_button is not None:
            self.prev_button.clicked.connect(self._navigate_prev_sprite)
        if self.next_button is not None:
            self.next_button.clicked.connect(self._navigate_next_sprite)

        # Region jump
        if self.region_jump is not None:
            self.region_jump.region_selected.connect(self._on_region_selected)
            self.region_jump.offset_requested.connect(self._navigate_to_offset)

    def _set_navigation_mode(self, mode: str):
        """Switch between manual and smart navigation modes"""
        self.navigation_mode = mode

        # Update button states
        for btn in self.mode_buttons:
            btn.setChecked(btn.text().lower() == mode)

        # Update UI based on mode
        if mode == "smart" and self.region_jump:
            self.region_jump.set_smart_mode(True)
            if self.sprite_regions:
                self._update_navigation_for_smart_mode()
        elif self.region_jump is not None:
            self.region_jump.set_smart_mode(False)

        self.navigation_mode_changed.emit(mode)

    def _on_map_clicked(self, offset: int):
        """Handle click on ROM map"""
        self._navigate_to_offset(offset)

    def _on_thumbnail_clicked(self, offset: int):
        """Handle thumbnail click"""
        self._navigate_to_offset(offset)

    def _on_region_selected(self, region_index: int):
        """Handle region selection"""
        if 0 <= region_index < len(self.sprite_regions):
            region = self.sprite_regions[region_index]
            # Navigate to center of region
            self._navigate_to_offset(region.center_offset)
            self.region_changed.emit(region_index)

    def _navigate_to_offset(self, offset: int):
        """Navigate to specific offset with history tracking"""
        if offset == self.current_offset:
            return

        # Clamp to ROM bounds
        offset = max(0, min(offset, self.rom_size - 1))

        # Add to navigation history
        self._add_to_history(offset)

        # Update current offset
        self.current_offset = offset

        # Update displays
        self._update_position_display()
        self._update_rom_map()
        self._update_nearby_thumbnails()

        # Emit signal
        self.offset_changed.emit(offset)

    def _navigate_next_sprite(self):
        """Navigate to next sprite based on mode"""
        if self.navigation_mode == "smart":
            self._navigate_smart_next()
        else:
            self._navigate_manual_next()

    def _navigate_prev_sprite(self):
        """Navigate to previous sprite based on mode"""
        if self.navigation_mode == "smart":
            self._navigate_smart_prev()
        else:
            self._navigate_manual_prev()

    def _navigate_manual_next(self):
        """Find next sprite in manual mode"""
        # Look for next sprite after current offset
        next_offset = None
        for offset, _ in sorted(self.found_sprites):
            if offset > self.current_offset:
                next_offset = offset
                break

        if next_offset:
            self._navigate_to_offset(next_offset)
        else:
            # No sprite found, step forward
            self._navigate_to_offset(self.current_offset + NAVIGATION_STEP_MEDIUM)

    def _navigate_manual_prev(self):
        """Find previous sprite in manual mode"""
        # Look for previous sprite before current offset
        prev_offset = None
        for offset, _ in sorted(self.found_sprites, reverse=True):
            if offset < self.current_offset:
                prev_offset = offset
                break

        if prev_offset:
            self._navigate_to_offset(prev_offset)
        else:
            # No sprite found, step backward
            self._navigate_to_offset(self.current_offset - NAVIGATION_STEP_MEDIUM)

    def _navigate_smart_next(self):
        """Navigate to next region in smart mode"""
        if not self.sprite_regions or not self.region_jump:
            return

        current_region = self.region_jump.get_current_region_index()
        if current_region < len(self.sprite_regions) - 1:
            self.region_jump.set_current_region(current_region + 1)
            self._on_region_selected(current_region + 1)

    def _navigate_smart_prev(self):
        """Navigate to previous region in smart mode"""
        if not self.sprite_regions or not self.region_jump:
            return

        current_region = self.region_jump.get_current_region_index()
        if current_region > 0:
            self.region_jump.set_current_region(current_region - 1)
            self._on_region_selected(current_region - 1)

    def _update_position_display(self):
        """Update position and context labels"""
        if self.position_label is not None:
            self.position_label.setText(f"0x{self.current_offset:06X}")

        if self.context_label is not None:
            # Determine context based on offset
            mb_position = self.current_offset / (1024 * 1024)

            if self.current_offset < 0x100000:
                context = "Low ROM - System area"
            elif self.current_offset < 0x200000:
                context = "Mid ROM - Program code"
            elif self.current_offset < 0x300000:
                context = "High ROM - Common sprite area"
            else:
                context = "Extended ROM - Additional data"

            # Add region info if in smart mode
            if self.navigation_mode == "smart":
                for i, region in enumerate(self.sprite_regions):
                    if region.start_offset <= self.current_offset <= region.end_offset:
                        context = f"Region {i + 1}: {region.description}"
                        break

            context += f" ({mb_position:.1f}MB)"
            if self.context_label:
                self.context_label.setText(context)

    def _update_rom_map(self):
        """Update ROM map visualization"""
        if self.rom_map is not None:
            self.rom_map.set_current_offset(self.current_offset)

            # Update region highlighting in smart mode
            if self.navigation_mode == "smart":
                for i, region in enumerate(self.sprite_regions):
                    if region.start_offset <= self.current_offset <= region.end_offset:
                        self.rom_map.set_current_region(i)
                        break

    def _update_nearby_thumbnails(self):
        """Update thumbnail previews of nearby sprites"""
        # Throttle updates
        current_time = time.time()
        if current_time - self._last_thumbnail_update < 0.5:  # 500ms throttle
            return
        self._last_thumbnail_update = current_time

        # Find nearby sprites
        nearby_sprites = []
        search_range = 0x10000  # 64KB range

        for offset, quality in self.found_sprites:
            if abs(offset - self.current_offset) <= search_range and offset != self.current_offset:
                nearby_sprites.append((offset, quality))

        # Sort by distance from current offset
        nearby_sprites.sort(key=lambda x: abs(x[0] - self.current_offset))

        # Update thumbnails
        for i, thumbnail in enumerate(self.thumbnails):
            if i < len(nearby_sprites):
                offset, quality = nearby_sprites[i]

                # Check cache first
                if offset in self.thumbnail_cache:
                    thumbnail.set_sprite(self.thumbnail_cache[offset], offset, quality)
                else:
                    # Request preview generation
                    thumbnail.clear()
                    self._request_thumbnail_preview(offset, quality, i)
            else:
                thumbnail.clear()

    def _request_thumbnail_preview(self, offset: int, quality: float, thumbnail_index: int):
        """Request preview generation for a thumbnail"""
        if not self.extraction_manager or not self.rom_path:
            return

        try:
            # Clean up old workers
            self._cleanup_preview_workers()

            # Create preview worker
            rom_extractor = self.extraction_manager.get_rom_extractor()
            sprite_name = f"thumb_0x{offset:X}"

            worker = SpritePreviewWorker(self.rom_path, offset, sprite_name, rom_extractor, None, parent=self)

            # Connect completion signal
            worker.preview_ready.connect(
                lambda data, w, h, name: self._on_thumbnail_ready(offset, quality, thumbnail_index, data, w, h)
            )

            # Track and start worker
            self.preview_workers.append(worker)
            worker.start()

        except Exception as e:
            logger.warning(f"Failed to request thumbnail preview: {e}")

    def _on_thumbnail_ready(self, offset: int, quality: float, index: int, tile_data: bytes, width: int, height: int):
        """Handle thumbnail preview ready"""
        try:
            # Convert to QPixmap
            from ui.widgets.sprite_preview_widget import SpritePreviewWidget

            # Create temporary preview widget to convert data
            temp_widget = SpritePreviewWidget()
            temp_widget.load_sprite_from_4bpp(tile_data, width, height, f"thumb_0x{offset:X}")

            if temp_widget.sprite_pixmap:
                # Scale to thumbnail size
                pixmap = temp_widget.sprite_pixmap.scaled(
                    THUMBNAIL_SIZE,
                    THUMBNAIL_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                # Cache it
                self.thumbnail_cache[offset] = pixmap

                # Update thumbnail if still in range
                if index < len(self.thumbnails):
                    self.thumbnails[index].set_sprite(pixmap, offset, quality)

        except Exception as e:
            logger.warning(f"Failed to process thumbnail: {e}")

    def _update_navigation_for_smart_mode(self):
        """Update navigation UI for smart mode"""
        if self.rom_map is not None:
            self.rom_map.set_sprite_regions(self.sprite_regions)
            self.rom_map.toggle_region_highlight(True)

        if self.region_jump is not None:
            self.region_jump.set_regions(self.sprite_regions)

    def _add_to_history(self, offset: int):
        """Add offset to navigation history"""
        # Remove any forward history if we're not at the end
        if self.history_index < len(self.navigation_history) - 1:
            self.navigation_history = self.navigation_history[: self.history_index + 1]

        # Add new offset
        self.navigation_history.append(offset)

        # Limit history size
        if len(self.navigation_history) > self.max_history:
            self.navigation_history.pop(0)
        else:
            self.history_index += 1

    def _cleanup_preview_workers(self):
        """Clean up completed preview workers"""
        active_workers = []
        for worker in self.preview_workers:
            if worker.isRunning():
                active_workers.append(worker)
            else:
                WorkerManager.cleanup_worker(worker)
        self.preview_workers = active_workers

    # Public API

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: CoreOperationsManager):
        """Set ROM data for navigation"""
        self.rom_path = rom_path
        self.rom_size = rom_size
        self.extraction_manager = extraction_manager

        # Update ROM map
        if self.rom_map is not None:
            self.rom_map.set_rom_size(rom_size)

        # Clear caches
        if self.thumbnail_cache:
            self.thumbnail_cache.clear()

        # Load sprite data from cache if available
        self._load_cached_sprites()

    def set_found_sprites(self, sprites: list[tuple[int, float]]):
        """Set found sprite locations"""
        self.found_sprites = sprites

        # Update ROM map
        if self.rom_map is not None:
            self.rom_map.clear_sprites()
            self.rom_map.add_found_sprites_batch(sprites)

        # Detect regions
        detector = SpriteRegionDetector()
        self.sprite_regions = detector.detect_regions(sprites)

        # Update region jump widget
        if self.region_jump is not None:
            self.region_jump.set_regions(self.sprite_regions)

        # Update thumbnails
        self._update_nearby_thumbnails()

    def add_found_sprite(self, offset: int, quality: float = 1.0):
        """Add a single found sprite"""
        self.found_sprites.append((offset, quality))

        if self.rom_map is not None:
            self.rom_map.add_found_sprite(offset, quality)

        # Re-detect regions if significant changes
        if len(self.found_sprites) % 10 == 0:  # Every 10 sprites
            detector = SpriteRegionDetector()
            self.sprite_regions = detector.detect_regions(self.found_sprites)
            if self.region_jump is not None:
                self.region_jump.set_regions(self.sprite_regions)

    def get_current_offset(self) -> int:
        """Get current navigation offset"""
        return self.current_offset

    def set_current_offset(self, offset: int):
        """Set current offset programmatically"""
        self._navigate_to_offset(offset)

    def _load_cached_sprites(self):
        """Load sprite locations from cache"""
        if not self.rom_path or not self.rom_cache:
            return

        try:
            cached_locations = self.rom_cache.get_sprite_locations(self.rom_path)
            if cached_locations:
                sprites = []
                for info in cached_locations.values():
                    if isinstance(info, dict) and "offset" in info:
                        offset = info["offset"]
                        quality = info.get("quality", 1.0)
                        sprites.append((offset, quality))

                if sprites:
                    self.set_found_sprites(sprites)
                    logger.info(f"Loaded {len(sprites)} cached sprite locations")

        except Exception as e:
            logger.warning(f"Failed to load cached sprites: {e}")

    # Keyboard navigation

    @override
    def keyPressEvent(self, event: QKeyEvent | None):
        """Handle keyboard navigation"""
        if not event:
            return

        key = event.key()
        modifiers = event.modifiers()

        # Fine navigation with arrow keys
        if key == Qt.Key.Key_Left:
            step = NAVIGATION_STEP_LARGE if modifiers & Qt.KeyboardModifier.ShiftModifier else NAVIGATION_STEP_SMALL
            self._navigate_to_offset(self.current_offset - step)
            event.accept()
        elif key == Qt.Key.Key_Right:
            step = NAVIGATION_STEP_LARGE if modifiers & Qt.KeyboardModifier.ShiftModifier else NAVIGATION_STEP_SMALL
            self._navigate_to_offset(self.current_offset + step)
            event.accept()

        # Sprite navigation with Page Up/Down
        elif key == Qt.Key.Key_PageUp:
            self._navigate_prev_sprite()
            event.accept()
        elif key == Qt.Key.Key_PageDown:
            self._navigate_next_sprite()
            event.accept()

        # Go to offset with Ctrl+G
        elif key == Qt.Key.Key_G and modifiers & Qt.KeyboardModifier.ControlModifier:
            # This would open a dialog - not implemented here for brevity
            event.accept()

        # Navigation history with Alt+Left/Right
        elif key == Qt.Key.Key_Left and modifiers & Qt.KeyboardModifier.AltModifier:
            self._navigate_back()
            event.accept()
        elif key == Qt.Key.Key_Right and modifiers & Qt.KeyboardModifier.AltModifier:
            self._navigate_forward()
            event.accept()

        else:
            super().keyPressEvent(event)

    def _navigate_back(self):
        """Navigate back in history"""
        if self.history_index > 0:
            self.history_index -= 1
            offset = self.navigation_history[self.history_index]
            self.current_offset = offset
            self._update_position_display()
            self._update_rom_map()
            self._update_nearby_thumbnails()
            self.offset_changed.emit(offset)

    def _navigate_forward(self):
        """Navigate forward in history"""
        if self.history_index < len(self.navigation_history) - 1:
            self.history_index += 1
            offset = self.navigation_history[self.history_index]
            self.current_offset = offset
            self._update_position_display()
            self._update_rom_map()
            self._update_nearby_thumbnails()
            self.offset_changed.emit(offset)

    def cleanup(self):
        """Clean up resources"""
        # Clean up all preview workers
        for worker in self.preview_workers:
            WorkerManager.cleanup_worker(worker)
        if self.preview_workers:
            self.preview_workers.clear()

        # Clear caches
        if self.thumbnail_cache:
            self.thumbnail_cache.clear()
