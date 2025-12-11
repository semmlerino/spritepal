"""
Sprite preview widget for SpritePal
Shows visual preview of sprites with optional palette support
"""
from __future__ import annotations

from typing import Any

from PIL import Image
from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from typing_extensions import override

from core.default_palette_loader import DefaultPaletteLoader
# ExtractionManager accessed via DI: inject(ExtractionManagerProtocol)
from core.visual_similarity_search import VisualSimilarityEngine
from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.spacing_constants import (
    COLOR_MUTED,
    COMPACT_BUTTON_HEIGHT,
    SPACING_TINY,
)
from ui.styles import get_muted_text_style
from utils.logging_config import get_logger

logger = get_logger(__name__)

class SpritePreviewWidget(QWidget):
    """Widget for displaying sprite previews with palette selection"""

    palette_changed = Signal(int)  # Emitted when palette selection changes
    similarity_search_requested = Signal(int)  # Emitted when user wants to search for similar sprites

    def __init__(self, title: str = "Sprite Preview", parent: QWidget | None = None) -> None:
        # Step 1: Declare instance variables with type hints
        self.title = title
        self.sprite_pixmap: QPixmap | None = None
        self.palettes: list[list[tuple[int, int, int]]] = []
        self.current_palette_index: int | None = None  # Default to grayscale (None = grayscale)
        self.sprite_data: bytes | None = None
        self._update_in_progress = False  # Guard against concurrent updates
        self.default_palette_loader = DefaultPaletteLoader()

        # Similarity search related
        self.current_offset: int = 0  # Current sprite offset for similarity search
        self.similarity_engine: VisualSimilarityEngine | None = None

        # UI components (initialized in _setup_ui)
        self.preview_label: QLabel | None = None
        self.controls_group: CollapsibleGroupBox | None = None
        self.palette_combo: QComboBox | None = None
        self.info_label: QLabel | None = None
        self.essential_info_label: QLabel | None = None

        # Update timer for guaranteed Qt refresh
        self._update_timer: QTimer | None = None

        # Step 2: Initialize parent
        super().__init__(parent)

        # Step 3: Setup UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the user interface - space-efficient with progressive disclosure"""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_TINY, SPACING_TINY, SPACING_TINY, SPACING_TINY)  # 4px minimum for focus
        layout.setSpacing(SPACING_TINY)  # 4px spacing

        # Preview label - maximum space usage with 100x100 minimum
        self.preview_label = QLabel(self)
        if self.preview_label:
            self.preview_label.setMinimumSize(100, 100)  # UX-validated minimum
            self.preview_label.setMaximumSize(16777215, 16777215)  # Use all available space
            self.preview_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding  # Use ALL available space
            )
            self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Enable context menu for similarity search
            self.preview_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.preview_label.customContextMenuRequested.connect(self._show_context_menu)

        # Start with visible empty state style
        self._apply_empty_state_style()
        layout.addWidget(self.preview_label)

        # Essential info (always visible) - single line for collapsed state
        self.essential_info_label = QLabel("No sprite loaded")
        if self.essential_info_label:
            self.essential_info_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_MUTED};
                font-size: 11px;
                padding: 2px;
                margin: 0px;
            }}
        """)
        if self.essential_info_label:
            self.essential_info_label.setFixedHeight(COMPACT_BUTTON_HEIGHT // 2)  # 16px height
        layout.addWidget(self.essential_info_label)

        # Collapsible controls group - starts collapsed for space efficiency
        self.controls_group = CollapsibleGroupBox(
            title="Controls",
            collapsed=True,  # Default to collapsed for maximum preview space
            parent=self
        )

        # Palette selector in horizontal layout for space efficiency
        palette_widget = QWidget(self)
        palette_layout = QHBoxLayout(palette_widget)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(SPACING_TINY)

        palette_label = QLabel("Palette:")
        palette_label.setFixedHeight(COMPACT_BUTTON_HEIGHT)
        palette_layout.addWidget(palette_label)

        self.palette_combo = QComboBox(self)
        if self.palette_combo:
            self.palette_combo.setMinimumWidth(120)  # Compact width
            self.palette_combo.setFixedHeight(COMPACT_BUTTON_HEIGHT)  # 32px for accessibility
            self.palette_combo.currentIndexChanged.connect(self._on_palette_changed)
        palette_layout.addWidget(self.palette_combo)

        palette_layout.addStretch()  # Push everything left

        # Detailed info label (only visible when expanded)
        self.info_label = QLabel("No sprite loaded")
        if self.info_label:
            self.info_label.setStyleSheet(get_muted_text_style(color_level="dark"))
        if self.info_label:
            self.info_label.setWordWrap(True)

        # Add to collapsible group
        self.controls_group.add_widget(palette_widget)
        self.controls_group.add_widget(self.info_label)

        layout.addWidget(self.controls_group)

        # Set widget to use maximum available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setLayout(layout)

        # Initialize update timer for guaranteed Qt refresh
        self._setup_update_timer()

    def _scale_pixmap_efficiently(self, pixmap: QPixmap) -> QPixmap:
        """Scale pixmap to make best use of available preview space"""
        original_width = pixmap.width()
        original_height = pixmap.height()

        # Guard against zero-dimension pixmaps (corrupted or empty images)
        if original_width <= 0 or original_height <= 0:
            return pixmap

        # Get available space in the preview label
        max_width = self.preview_label.maximumWidth() if self.preview_label else 400
        max_height = self.preview_label.maximumHeight() if self.preview_label else 400

        # Determine scale size based on available space and sprite size
        if original_width <= 32 and original_height <= 32:
            # Very small sprites: scale up significantly for visibility
            scale_factor = min(6, max_width // original_width, max_height // original_height)
            scale_width, scale_height = original_width * scale_factor, original_height * scale_factor
        elif original_width <= 64 and original_height <= 64:
            # Small sprites: scale up moderately
            scale_factor = min(4, max_width // original_width, max_height // original_height)
            scale_width, scale_height = original_width * scale_factor, original_height * scale_factor
        elif original_width <= 128 and original_height <= 128:
            # Medium sprites: scale up to use available space
            scale_factor = min(3, max_width // original_width, max_height // original_height)
            scale_width, scale_height = original_width * scale_factor, original_height * scale_factor
        else:
            # Large sprites: fit to available space
            scale_factor_x = max_width / original_width
            scale_factor_y = max_height / original_height
            scale_factor = min(scale_factor_x, scale_factor_y, 2.0)  # Cap at 2x for very large sprites
            scale_width, scale_height = int(original_width * scale_factor), int(original_height * scale_factor)

        # Apply scaling with smooth transformation for better quality at larger sizes
        return pixmap.scaled(
            scale_width,
            scale_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,  # Better quality for larger previews
        )

    def load_sprite_from_png(self, png_path: str, sprite_name: str | None = None) -> None:
        """Load sprite from PNG file"""
        try:
            # Load image
            img = Image.open(png_path)

            # Check if grayscale or indexed
            if img.mode == "L":
                # Grayscale - need palettes for color
                self._load_grayscale_sprite(img, sprite_name)
            elif img.mode == "P":
                # Indexed - has built-in palette
                self._load_indexed_sprite(img)
            else:
                # Convert to indexed
                img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
                self._load_indexed_sprite(img)

            # Update info
            if self.info_label:
                self.info_label.setText(
                f"Size: {img.size[0]}x{img.size[1]} | Mode: {img.mode}"
            )

        except (OSError, PermissionError) as e:
            logger.exception("File I/O error loading sprite preview")
            if self.info_label:
                self.info_label.setText(f"Cannot access sprite file: {e}")
        except (ValueError, TypeError) as e:
            logger.exception("Image format error loading sprite preview")
            if self.info_label:
                self.info_label.setText(f"Invalid sprite format: {e}")
        except Exception as e:
            logger.exception("Failed to load sprite preview")
            if self.info_label:
                self.info_label.setText(f"Error loading sprite: {e}")

    def _load_grayscale_sprite(
        self, img: Image.Image, sprite_name: str | None = None
    ) -> None:
        """Load grayscale sprite and apply palettes"""
        logger.debug(f"[DEBUG_SPRITE] _load_grayscale_sprite called: size={img.size}, mode={img.mode}, name={sprite_name}")

        # NOTE: Thread safety is handled by Qt signals with QueuedConnection
        # This method should only be called from main thread via signals

        # Sample pixel values to verify image has content
        try:
            pixel_samples = []
            for y in range(min(5, img.height)):
                for x in range(min(5, img.width)):
                    pixel_samples.append(img.getpixel((x, y)))
            logger.debug(f"[DEBUG_SPRITE] First 25 pixel values: {pixel_samples}")
            logger.debug(f"[DEBUG_SPRITE] Unique values: {sorted(set(pixel_samples))}")
        except Exception as e:
            logger.error(f"[DEBUG_SPRITE] Failed to sample pixels: {e}")

        # Convert to QImage
        width, height = img.size
        logger.debug(f"[DEBUG_SPRITE] PIL Image properties: {width}x{height}, mode={img.mode}")

        # Get default palettes if available
        if sprite_name:
            default_palettes = self.default_palette_loader.get_all_kirby_palettes()
            if default_palettes:
                # Convert dict values to list maintaining type compatibility
                palette_list = []
                for palette in default_palettes.values():
                    palette_list.append(palette)
                self.palettes = palette_list

                # Update combo box
                if self.palette_combo:
                    self.palette_combo.clear()
                # Add grayscale as first option
                if self.palette_combo:
                    self.palette_combo.addItem("Grayscale", None)
                # Add color palettes
                for idx in default_palettes:
                    if self.palette_combo:
                        self.palette_combo.addItem(f"Palette {idx}", idx)

                # Select grayscale by default (index 0)
                if self.palette_combo:
                    self.palette_combo.setCurrentIndex(0)
                self.current_palette_index = None  # Grayscale

        # Store grayscale data for palette swapping
        self.sprite_data = img.tobytes()
        logger.debug(f"[DEBUG_SPRITE] Stored sprite_data: {len(self.sprite_data)} bytes")

        # Apply current palette
        logger.debug(f"[DEBUG_SPRITE] About to call _update_preview_with_palette with {len(self.palettes)} palettes")
        self._update_preview_with_palette(img)

        # Diagnostic check after loading
        logger.debug("[DEBUG_SPRITE] Calling diagnostic check after loading")
        self._diagnose_preview_state()

        # Additional diagnostic
        self.diagnose_display_issue()

    def _load_indexed_sprite(self, img: Image.Image) -> None:
        """Load indexed sprite with its palette"""
        # Convert to RGBA for display
        img_rgba = img.convert("RGBA")

        # Convert to QPixmap
        logger.debug(f"[DEBUG_SPRITE] Converting PIL Image to QImage: {img_rgba.width}x{img_rgba.height}")

        # Get byte data and verify
        img_bytes = img_rgba.tobytes()
        logger.debug(f"[DEBUG_SPRITE] Image byte data: {len(img_bytes)} bytes")
        logger.debug(f"[DEBUG_SPRITE] First 100 bytes (hex): {img_bytes[:100].hex() if len(img_bytes) > 0 else 'EMPTY'}")

        qimg = QImage(
            img_bytes,
            img_rgba.width,
            img_rgba.height,
            img_rgba.width * 4,
            QImage.Format.Format_RGBA8888,
        )

        logger.debug(f"[DEBUG_SPRITE] QImage created: {qimg.width()}x{qimg.height()}, null={qimg.isNull()}")

        pixmap = QPixmap.fromImage(qimg)
        logger.debug(f"[DEBUG_SPRITE] QPixmap created: {pixmap.width()}x{pixmap.height()}, null={pixmap.isNull()}")

        # Scale for preview - adaptive sizing for space efficiency
        scaled = self._scale_pixmap_efficiently(pixmap)

        if self.preview_label:
            self.preview_label.setPixmap(scaled)
        # SPACE EFFICIENCY: When content is loaded, use borderless style
        self._apply_content_style()
        self.sprite_pixmap = pixmap

        # Guarantee the pixmap is displayed
        self._guarantee_pixmap_display()

        # No palette selection for indexed sprites
        if self.palette_combo:
            self.palette_combo.setEnabled(False)
        if self.palette_combo:
            self.palette_combo.clear()
        if self.palette_combo:
            self.palette_combo.addItem("Built-in Palette")

    def _update_preview_with_palette(self, grayscale_img: Image.Image) -> None:
        """Update preview by applying selected palette to grayscale image"""
        import threading

        thread_id = threading.get_ident()
        logger.debug(f"[DEBUG_SPRITE] _update_preview_with_palette START - Thread {thread_id}")
        logger.debug(f"[DEBUG_SPRITE] palette_idx={self.current_palette_index}, has_palettes={bool(self.palettes)}, num_palettes={len(self.palettes)}")

        # CRITICAL: Prevent concurrent pixmap updates which can crash Qt
        if self._update_in_progress:
            logger.warning(f"[DEBUG_SPRITE] Update already in progress - skipping to prevent crash (Thread {thread_id})")
            return

        self._update_in_progress = True
        try:
            # Check if grayscale is selected (None) or palette index is invalid
            if self.current_palette_index is None:
                # Grayscale explicitly selected
                logger.debug("[DEBUG_SPRITE] Grayscale selected, showing without palette")
                show_grayscale = True
            elif self.palettes and self.current_palette_index >= len(self.palettes):
                # Invalid palette index - reset to grayscale
                self.current_palette_index = None
                logger.debug("[DEBUG_SPRITE] Invalid palette index, reverting to grayscale")
                show_grayscale = True
            elif not self.palettes or self.current_palette_index >= len(self.palettes):
                # No palettes available or invalid index - show grayscale
                logger.debug("[DEBUG_SPRITE] No palette available, showing grayscale")
                show_grayscale = True
            else:
                show_grayscale = False

            if show_grayscale:
                # Show grayscale with proper scaling
                logger.debug("[DEBUG_SPRITE] Showing grayscale with scaling")
                # Scale 4-bit values (0-15) to 8-bit (0-255)
                import numpy as np
                img_array = np.array(grayscale_img)
                # Detect if values are in 4-bit range and scale them
                if img_array.max() <= 15:
                    img_array = img_array * 17  # Scale 0-15 to 0-255
                    grayscale_img = Image.fromarray(img_array.astype(np.uint8), mode='L')
                img_rgba = grayscale_img.convert("RGBA")
            else:
                # Apply palette
                if self.current_palette_index is not None and 0 <= self.current_palette_index < len(self.palettes):
                    palette_colors = self.palettes[self.current_palette_index]
                else:
                    # Fallback to first palette if index is out of bounds
                    palette_colors = self.palettes[0] if self.palettes else []

                # Create indexed image
                indexed = Image.new("P", grayscale_img.size)
                # Scale grayscale values (0-255) back to palette indices (0-15)
                indexed.putdata([p // 17 for p in grayscale_img.getdata()])

                # Create palette (16 colors -> 256 color palette)
                full_palette = []
                for i in range(256):
                    if i < len(palette_colors):
                        full_palette.extend(palette_colors[i])
                    else:
                        full_palette.extend([0, 0, 0])

                indexed.putpalette(full_palette)

                # Convert to RGBA for display
                img_rgba = indexed.convert("RGBA")

            # Convert to QPixmap
            logger.debug(f"[DEBUG_SPRITE] Converting PIL Image to QImage: {img_rgba.width}x{img_rgba.height}")

            # Get byte data and verify
            img_bytes = img_rgba.tobytes()
            logger.debug(f"[DEBUG_SPRITE] Image byte data: {len(img_bytes)} bytes")
            logger.debug(f"[DEBUG_SPRITE] First 100 bytes (hex): {img_bytes[:100].hex() if len(img_bytes) > 0 else 'EMPTY'}")

            qimg = QImage(
                img_bytes,
                img_rgba.width,
                img_rgba.height,
                img_rgba.width * 4,
                QImage.Format.Format_RGBA8888,
            )

            logger.debug(f"[DEBUG_SPRITE] QImage created: {qimg.width()}x{qimg.height()}, null={qimg.isNull()}")

            pixmap = QPixmap.fromImage(qimg)
            logger.debug(f"[DEBUG_SPRITE] QPixmap created: {pixmap.width()}x{pixmap.height()}, null={pixmap.isNull()}")

            # Scale for preview - adaptive sizing for space efficiency
            scaled = self._scale_pixmap_efficiently(pixmap)
            logger.debug(f"[DEBUG_SPRITE] Scaled pixmap: {scaled.width()}x{scaled.height()}, null={scaled.isNull()}")

            logger.info(f"[DEBUG_SPRITE] Setting pixmap on preview_label: original={pixmap.width()}x{pixmap.height()}, scaled={scaled.width()}x{scaled.height()}")
            logger.info(f"[DEBUG_SPRITE] Widget visibility state: widget={self.isVisible()}, label={self.preview_label.isVisible() if self.preview_label else 'N/A'}")

            # Check label state before setting pixmap
            logger.debug("[DEBUG_SPRITE] preview_label state BEFORE setPixmap:")
            logger.debug(f"  - exists: {self.preview_label is not None}")
            if self.preview_label:
                logger.debug(f"  - visible: {self.preview_label.isVisible()}")
                logger.debug(f"  - size: {self.preview_label.size()}")
                logger.debug(f"  - enabled: {self.preview_label.isEnabled()}")
                logger.debug(f"  - parent: {self.preview_label.parent()}")
                logger.debug(f"  - current pixmap: {self.preview_label.pixmap()}")
                logger.debug(f"  - current text: '{self.preview_label.text()}'")

            if self.preview_label:
                self.preview_label.setPixmap(scaled)
            # SPACE EFFICIENCY: When content is loaded, use borderless style
            self._apply_content_style()
            self.sprite_pixmap = pixmap

            # Verify pixmap was actually set
            actual_pixmap = self.preview_label.pixmap() if self.preview_label else None
            if actual_pixmap is None:
                logger.error("[DEBUG_SPRITE] CRITICAL: Pixmap was NOT set on preview_label!")
                logger.error(f"[DEBUG_SPRITE] Label text after failed setPixmap: '{self.preview_label.text() if self.preview_label else 'N/A'}'")
                logger.error(f"[DEBUG_SPRITE] Label stylesheet: {self.preview_label.styleSheet()[:200] if self.preview_label and self.preview_label.styleSheet() else '[DEBUG_SPRITE] No stylesheet'}...")
                # Try to understand why
                logger.error(f"[DEBUG_SPRITE] QApplication instance: {QApplication.instance()}")
                logger.error(f"[DEBUG_SPRITE] Current thread: {QThread.currentThread()}")
                app = QApplication.instance()
                logger.error(f"[DEBUG_SPRITE] Main thread: {app.thread() if app else 'NO APP'}")
            else:
                logger.info(f"[DEBUG_SPRITE] Pixmap successfully set: {actual_pixmap.width()}x{actual_pixmap.height()}")
                logger.info(f"[DEBUG_SPRITE] Label size after setting pixmap: {self.preview_label.size() if self.preview_label else 'N/A'}")
                logger.debug("[DEBUG_SPRITE] Actual pixmap properties:")
                logger.debug(f"  - size: {actual_pixmap.size()}")
                logger.debug(f"  - depth: {actual_pixmap.depth()}")
                logger.debug(f"  - has alpha: {actual_pixmap.hasAlpha()}")

            # Guarantee the pixmap is displayed with validation
            logger.debug("[DEBUG_SPRITE] Calling _guarantee_pixmap_display_with_validation")
            self._guarantee_pixmap_display_with_validation()

            # Force visibility as last resort
            logger.debug("[DEBUG_SPRITE] Calling _force_visibility as last resort")
            self._force_visibility()

            # Final check
            final_pixmap = self.preview_label.pixmap() if self.preview_label else None
            if final_pixmap and not final_pixmap.isNull():
                logger.info(f"[DEBUG_SPRITE] SUCCESS: Final pixmap is displayed: {final_pixmap.width()}x{final_pixmap.height()}")
            else:
                logger.error("[DEBUG_SPRITE] FAILURE: No pixmap displayed after all attempts")
                self.diagnose_display_issue()

        finally:
            # CRITICAL: Always clear the update flag to prevent deadlock
            self._update_in_progress = False
            logger.debug(f"[DEBUG_SPRITE] _update_preview_with_palette END - Thread {thread_id}")

    def _on_palette_changed(self, index: int) -> None:
        """Handle palette selection change"""
        if index >= 0 and self.sprite_data:
            # Get the actual palette index from combo box data (could be None for grayscale)
            palette_data = self.palette_combo.itemData(index) if self.palette_combo else None
            self.current_palette_index = palette_data
            # Recreate image from grayscale data
            # Assume square sprite for now
            size = int(len(self.sprite_data) ** 0.5)
            img = Image.frombytes("L", (size, size), self.sprite_data)
            self._update_preview_with_palette(img)
            # Emit -1 for grayscale, otherwise the palette index
            emit_value = -1 if self.current_palette_index is None else self.current_palette_index
            self.palette_changed.emit(emit_value)

    def load_sprite_from_4bpp(
        self,
        tile_data: bytes,
        width: int = 128,
        height: int = 128,
        sprite_name: str | None = None,
    ) -> None:
        """Load sprite from 4bpp tile data with guaranteed Qt widget updates"""
        # NOTE: This method is called via Qt signals with QueuedConnection,
        # so it's guaranteed to run on the main thread. No additional thread
        # safety checks needed here.

        logger.debug(f"[SPRITE_DISPLAY] load_sprite_from_4bpp called: data_len={len(tile_data) if tile_data else 0}, {width}x{height}, name={sprite_name}")
        try:
            # Don't show loading state during rapid updates to prevent flashing
            # self._show_loading_state()  # REMOVED - causes flashing

            # Validate tile data with detailed logging
            if not tile_data:
                logger.debug("[SPRITE_DISPLAY] No tile data")
                # Don't clear to prevent flashing - keep last valid preview
                # Just update the info labels
                if self.essential_info_label:
                    self.essential_info_label.setText("No data")
                if self.info_label:
                    self.info_label.setText("No sprite data at this offset")
                return

            logger.debug(f"[SPRITE_DISPLAY] Tile data validation: {len(tile_data)} bytes received")

            # Load default palettes early to ensure they're available
            if not self.palettes:
                default_palettes = self.default_palette_loader.get_all_kirby_palettes()
                if default_palettes:
                    # The palettes dict has keys like 8, 9, etc. We need to preserve these indices
                    # Create a list with enough slots to hold the highest index
                    max_index = max(default_palettes.keys()) if default_palettes else 0
                    palette_list: list[list[tuple[int, int, int]] | None] = [None] * (max_index + 1)

                    # Place each palette at its correct index
                    for idx, palette in default_palettes.items():
                        if 0 <= idx < len(palette_list):
                            palette_list[idx] = palette

                    # Remove None entries and use a simple list if indices are sparse
                    # But keep track of the actual palette we want (index 8)
                    if 8 in default_palettes:
                        # Use the Kirby Pink palette directly
                        self.palettes = [default_palettes[8]]  # Just use the main palette
                        self.current_palette_index = 0  # It's now at position 0 in our list
                        logger.debug("[SPRITE_DISPLAY] Loaded Kirby Pink palette (was index 8)")
                    else:
                        # Fallback to all palettes - filter out None entries
                        filtered_palette_list: list[list[tuple[int, int, int]]] = [p for p in palette_list if p is not None]
                        self.palettes = filtered_palette_list if filtered_palette_list else []
                        logger.debug(f"[SPRITE_DISPLAY] Loaded {len(self.palettes)} default palettes")
                        # Ensure palette index is valid
                        if self.current_palette_index is not None and self.current_palette_index >= len(self.palettes):
                            self.current_palette_index = 0

            bytes_per_tile = 32
            extra_bytes = len(tile_data) % bytes_per_tile
            if extra_bytes > bytes_per_tile // 2:  # More than half a tile of extra data
                logger.warning(f"[SPRITE_DISPLAY] Possible corrupted data: {extra_bytes} extra bytes (>{bytes_per_tile//2})")
                # Don't clear() - try to display what we can to prevent flashing
                if self.essential_info_label:
                    self.essential_info_label.setText("Warning: Partial data")
                if self.info_label:
                    self.info_label.setText(
                    "Unable to display sprite - data appears corrupted"
                )
                return

            # Try to get ROM extractor - handle case where it's not available
            try:
                from core.di_container import inject
                from core.protocols.manager_protocols import ExtractionManagerProtocol
                extraction_manager = inject(ExtractionManagerProtocol)
                extractor = extraction_manager.get_rom_extractor()
                logger.debug(f"[SPRITE_DISPLAY] Got extractor: {bool(extractor)}")
            except Exception as e:
                logger.warning(f"[SPRITE_DISPLAY] ROM extractor not available: {e}")
                extractor = None

            # Create temporary image from 4bpp data
            img = Image.new("L", (width, height), 0)
            logger.debug(f"[SPRITE_DISPLAY] Created PIL image: {width}x{height}")

            # Log first 200 bytes of tile data for debugging
            logger.debug(f"[DEBUG_SPRITE] First 200 bytes of tile_data (hex): {tile_data[:200].hex() if len(tile_data) >= 200 else tile_data.hex()}")

            # Process tiles (simplified - assumes data is already in correct format)
            tiles_per_row = width // 8
            num_tiles = len(tile_data) // bytes_per_tile
            logger.debug(f"[DEBUG_SPRITE] Processing {num_tiles} tiles ({tiles_per_row} per row)")

            if num_tiles == 0:
                logger.warning("[SPRITE_DISPLAY] No valid tiles found")
                # Don't call clear() to prevent flashing - just update labels
                if self.essential_info_label:
                    self.essential_info_label.setText("No tiles")
                if self.info_label:
                    self.info_label.setText("No valid sprite tiles found")
                return

            # Track actual pixel data for debugging
            pixel_count = 0
            non_zero_pixels = 0

            # Choose decoding method based on extractor availability
            if extractor is not None and hasattr(extractor, '_get_4bpp_pixel'):
                logger.debug("[SPRITE_DISPLAY] Using ROM extractor for 4bpp decoding")
                decode_method = "rom_extractor"
            else:
                logger.debug("[SPRITE_DISPLAY] Using fallback 4bpp decoding (ROM extractor not available)")
                decode_method = "fallback"

            for tile_idx in range(num_tiles):
                tile_x = (tile_idx % tiles_per_row) * 8
                tile_y = (tile_idx // tiles_per_row) * 8

                if tile_y >= height:
                    break

                tile_offset = tile_idx * bytes_per_tile
                tile_bytes = tile_data[tile_offset : tile_offset + bytes_per_tile]

                # Decode 4bpp tile using available method
                for y in range(8):
                    for x in range(8):
                        if decode_method == "rom_extractor":
                            pixel = extractor._get_4bpp_pixel(tile_bytes, x, y) if extractor else 0
                        else:
                            # Fallback 4bpp decoding method
                            pixel = self._decode_4bpp_pixel_fallback(tile_bytes, x, y)

                        gray_value = pixel * 17  # Convert to grayscale
                        pixel_count += 1
                        if gray_value > 0:
                            non_zero_pixels += 1
                        if tile_x + x < width and tile_y + y < height:
                            img.putpixel((tile_x + x, tile_y + y), gray_value)

            percent = (non_zero_pixels/pixel_count)*100 if pixel_count > 0 else 0
            logger.debug(f"[DEBUG_SPRITE] Pixel analysis: {non_zero_pixels}/{pixel_count} non-zero pixels ({percent:.1f}%)")

            # Sample unique pixel values to verify sprite data (debug only)
            if pixel_count > 0 and img:
                unique_pixels = set()
                for y in range(min(height, 16)):  # Sample first 16 rows
                    for x in range(min(width, 16)):  # Sample first 16 columns
                        try:
                            pixel_val = img.getpixel((x, y))
                            unique_pixels.add(pixel_val)
                        except (IndexError, ValueError):
                            pass
                logger.debug(f"[DEBUG_SPRITE] Unique pixel values in 16x16 sample: {sorted(unique_pixels)[:20]}")
                if len(unique_pixels) <= 1:
                    logger.debug("[DEBUG_SPRITE] Note: Sprite appears to be monochrome")

            # Check PIL image directly
            logger.debug("[DEBUG_SPRITE] PIL Image stats:")
            logger.debug(f"  - size: {img.size}")
            logger.debug(f"  - mode: {img.mode}")
            logger.debug(f"  - extrema: {img.getextrema()}")

            # Verify image has content before displaying
            if non_zero_pixels == 0:
                logger.warning("[SPRITE_DISPLAY] Image appears to be completely black - showing no data pattern")
                self._show_no_data_pattern(width, height)
                return

            # Load as grayscale sprite with forced update and validation
            self._load_grayscale_sprite_with_validation_and_update(img, sprite_name)

            info_text = f"Size: {width}x{height} | Tiles: {num_tiles} | Pixels: {non_zero_pixels}/{pixel_count}"
            if extra_bytes > 0:
                info_text += f" | Warning: {extra_bytes} extra bytes"
            if self.info_label:
                self.info_label.setText(info_text)

            # Final verification that pixmap was created and set
            self._verify_pixmap_display()

        except (OSError, PermissionError):
            logger.exception("File I/O error loading 4bpp sprite")
            self._show_error_state("I/O error")
        except (ValueError, TypeError):
            logger.exception("Data format error loading 4bpp sprite")
            self._show_error_state("Data error")
        except Exception as e:
            logger.exception("Failed to load 4bpp sprite")
            self._show_error_state("Load error")
            if self.info_label:
                self.info_label.setText(f"Error loading sprite: {e}")

    # _load_sprite_from_4bpp_main_thread method removed - no longer needed
    # Signals already ensure main thread execution with QueuedConnection

    def clear(self) -> None:
        """Clear the preview and show visible placeholder"""
        logger.debug("[DEBUG] SpritePreviewWidget.clear() called")
        # Only clear if there's actually content to clear
        # This prevents unnecessary flashing during rapid updates
        preview_pixmap = self.preview_label.pixmap() if self.preview_label else None
        if self.sprite_pixmap is not None or preview_pixmap is not None:
            if self.preview_label:
                self.preview_label.clear()
            if self.preview_label:
                self.preview_label.setText("No preview available\n\nLoad a ROM and select an offset\nto view sprite data")
            # Reset to minimum size for visibility when empty
            if self.preview_label:
                self.preview_label.setMinimumSize(100, 100)  # Space-efficient minimum

            # Apply visible empty state style
            self._apply_empty_state_style()

            if self.palette_combo:
                self.palette_combo.clear()
            if self.palette_combo:
                self.palette_combo.setEnabled(False)
            # Reset both info labels to cleared state
            if self.essential_info_label:
                self.essential_info_label.setText("No sprite loaded")
            if self.info_label:
                self.info_label.setText("No sprite loaded")
            self.sprite_pixmap = None
            self.sprite_data = None
            self.palettes = []

    def _apply_empty_state_style(self) -> None:
        """Apply dark theme styling for empty state that's clearly visible"""
        if self.preview_label:
            self.preview_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #666;
                background-color: #1e1e1e;
                color: #ccc;
                margin: 0px;
                padding: 20px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: normal;
            }
        """)

    def _apply_content_style(self) -> None:
        """Apply style for actual content display with checkerboard background"""
        # Use dark background for better sprite visibility on dark theme
        if self.preview_label:
            self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
        """)

    def set_sprite(self, pixmap: QPixmap | None) -> None:
        """Set the sprite preview from a QPixmap.

        This method is called by the manual offset dialog to update the preview.

        Args:
            pixmap: The QPixmap to display, or None to clear
        """
        logger.debug(f"[SPRITE_DISPLAY] set_sprite called with pixmap: {pixmap is not None}")
        try:
            # Handle None or invalid pixmap by clearing
            if pixmap is None or pixmap.isNull():
                logger.debug("[SPRITE_DISPLAY] Invalid pixmap, not updating display")
                # Don't clear - keep previous preview visible
                return

            # At this point, pixmap is guaranteed to be not None and not null
            logger.debug(f"[SPRITE_DISPLAY] Setting pixmap: {pixmap.width()}x{pixmap.height()}")
            # Store the original pixmap
            self.sprite_pixmap = pixmap

            # Scale the pixmap efficiently for display
            scaled_pixmap = self._scale_pixmap_efficiently(pixmap)
            logger.debug(f"[SPRITE_DISPLAY] Scaled pixmap: {scaled_pixmap.width()}x{scaled_pixmap.height()}")

            # Update the preview label
            if self.preview_label:
                self.preview_label.setPixmap(scaled_pixmap)
            logger.debug("[SPRITE_DISPLAY] Pixmap set on label")

            # Apply content styling with checkerboard background
            self._apply_content_style()

            # Guarantee the pixmap is displayed
            self._guarantee_pixmap_display()

            # Update sprite info with dimensions
            width = pixmap.width()
            height = pixmap.height()
            if self.essential_info_label:
                self.essential_info_label.setText(f"{width}x{height} - Direct")
            if self.info_label:
                self.info_label.setText(f"Size: {width}x{height} | Source: QPixmap")

            # Disable palette combo for direct pixmap display
            # (since pixmaps are already rendered with colors)
            if self.palette_combo:
                self.palette_combo.clear()
            if self.palette_combo:
                self.palette_combo.setEnabled(False)
            if self.palette_combo:
                self.palette_combo.addItem("Direct Display")

            # Clear sprite data since this is a direct pixmap
            self.sprite_data = None
            self.palettes = []

        except Exception as e:
            logger.exception("Failed to set sprite pixmap")
            # Don't clear on error - keep previous preview visible
            if self.essential_info_label:
                self.essential_info_label.setText("Display error")
            if self.info_label:
                self.info_label.setText(f"Error displaying sprite: {e}")

    def get_current_pixmap(self) -> QPixmap | None:
        """Get the current preview pixmap"""
        return self.sprite_pixmap

    def expand_controls(self) -> None:
        """Expand the controls group for better access"""
        if self.controls_group is not None:
            self.controls_group.set_collapsed(False)

    def collapse_controls(self) -> None:
        """Collapse the controls group for maximum preview space"""
        if self.controls_group is not None:
            self.controls_group.set_collapsed(True)

    def is_controls_collapsed(self) -> bool:
        """Check if controls are currently collapsed"""
        return self.controls_group.is_collapsed() if self.controls_group is not None else True

    @override
    def sizeHint(self) -> QSize:
        """Provide optimal size hint for layout negotiations - space-efficient"""

        # If we have a sprite loaded, base size on the preview content
        if self.sprite_pixmap is not None and not self.sprite_pixmap.isNull():
            # Use the scaled pixmap size as the hint, with minimal space for controls
            preview_pixmap = self.preview_label.pixmap() if self.preview_label is not None else None
            if preview_pixmap is not None:
                preview_size = preview_pixmap.size()
            else:
                preview_size = QSize(100, 100)  # Fallback

            # Collapsed controls take minimal space: essential info (16px) + collapsible header (32px)
            controls_height = 48

            width = max(preview_size.width(), 150)  # Smaller minimum
            height = preview_size.height() + controls_height

            # More aggressive space usage - allow larger sizes
            width = min(max(width, 120), 1200)
            height = min(max(height, 148), 900)  # Match minimumSizeHint

            return QSize(width, height)

        # No sprite loaded - compact default for empty state
        return QSize(150, 148)  # Match minimumSizeHint for consistency

    @override
    def minimumSizeHint(self) -> QSize:
        """Provide minimum size hint to prevent overly small widgets"""

        # Minimum size should accommodate the empty state message and basic controls
        # Match preview_label minimum (100x100) plus controls
        return QSize(150, 150)  # Consistent minimum size

    @override
    def hasHeightForWidth(self) -> bool:
        """Indicate that widget can adapt height based on width"""
        return True

    @override
    def heightForWidth(self, width: int) -> int:
        """Calculate optimal height for given width"""
        if self.sprite_pixmap is not None and not self.sprite_pixmap.isNull():
            # Calculate height based on aspect ratio of current sprite
            preview_pixmap = self.preview_label.pixmap() if self.preview_label else None
            if preview_pixmap:
                preview_size = preview_pixmap.size()
                if preview_size.width() > 0:
                    aspect_ratio = preview_size.height() / preview_size.width()
                    preview_height = int((width - 20) * aspect_ratio)  # 20px margin
                    controls_height = 60  # For palette controls and info
                    return preview_height + controls_height

        # Default calculation for empty state
        return int(width * 0.6)  # Reasonable aspect ratio

    def set_current_offset(self, offset: int) -> None:
        """Set the current sprite offset for similarity search."""
        self.current_offset = offset

    def _show_context_menu(self, position: Any) -> None:
        """Show context menu with similarity search option."""
        # Only show context menu if we have a sprite loaded
        if self.sprite_pixmap is None or self.sprite_pixmap.isNull():
            return

        menu = QMenu(self)

        # Find Similar Sprites action
        similar_action = QAction("Find Similar Sprites...", self)
        similar_action.setToolTip("Search for visually similar sprites in the ROM")
        similar_action.triggered.connect(self._find_similar_sprites)
        menu.addAction(similar_action)

        # Show menu at cursor position
        global_pos = self.preview_label.mapToGlobal(position) if self.preview_label else self.mapToGlobal(position)
        menu.exec(global_pos)

    def _find_similar_sprites(self) -> None:
        """Handle similarity search request."""
        if self.sprite_pixmap is None or self.sprite_pixmap.isNull():
            QMessageBox.information(
                self,
                "No Sprite",
                "Please load a sprite first before searching for similar ones."
            )
            return

        try:
            # Convert QPixmap to PIL Image for similarity search
            image = self._qpixmap_to_pil_image(self.sprite_pixmap)
            if image is None:
                QMessageBox.warning(
                    self,
                    "Conversion Error",
                    "Could not convert sprite image for similarity search."
                )
                return

            # Show progress dialog for indexing
            progress_dialog = QProgressDialog(
                "Indexing sprites for similarity search...",
                "Cancel",
                0, 0,  # Indeterminate progress
                self
            )
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(500)  # Show after 500ms
            progress_dialog.show()

            # Start similarity search in a separate thread
            self._start_similarity_search_async(image, progress_dialog)

        except Exception as e:
            logger.exception("Error starting similarity search")
            QMessageBox.critical(
                self,
                "Search Error",
                f"Failed to start similarity search: {e!s}"
            )

    def _qpixmap_to_pil_image(self, pixmap: QPixmap) -> Image.Image | None:
        """Convert QPixmap to PIL Image."""
        try:
            # Convert QPixmap to QImage
            qimage = pixmap.toImage()

            # Convert QImage to PIL Image
            width = qimage.width()
            height = qimage.height()

            # Get raw bytes from QImage
            ptr = qimage.bits()
            ptr.setsize(height * width * 4)  # type: ignore[attr-defined] # Qt-specific memoryview method
            img_data = bytes(ptr)

            # Create PIL image
            pil_image = Image.frombytes("RGBA", (width, height), img_data, "raw", "BGRA")
            return pil_image.convert("RGB")  # Convert to RGB for similarity search

        except Exception:
            logger.exception("Error converting QPixmap to PIL Image")
            return None

    def _start_similarity_search_async(self, target_image: Image.Image, progress_dialog: QProgressDialog) -> None:
        """Start similarity search in background thread."""
        # For now, implement synchronous search
        # In a real implementation, this should be moved to a worker thread

        try:
            # Get extraction manager for ROM access
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            extraction_manager = inject(ExtractionManagerProtocol)
            if not extraction_manager:
                progress_dialog.close()
                QMessageBox.warning(
                    self,
                    "No ROM Data",
                    "ROM extraction manager not available. Please load a ROM first."
                )
                return

            # Create or get similarity engine
            if self.similarity_engine is None:
                self.similarity_engine = VisualSimilarityEngine()

            # Index current sprite
            self.similarity_engine.index_sprite(
                self.current_offset,
                target_image,
                {"source": "preview_widget"}
            )

            # TODO: Index other sprites from ROM
            # This would require accessing sprite data from the ROM
            # For now, show a message that indexing is not fully implemented

            progress_dialog.close()

            # Perform similarity search
            matches = self.similarity_engine.find_similar(
                target_image,
                max_results=10,
                similarity_threshold=0.7
            )

            # Show results
            self._show_similarity_results(matches)

        except Exception as e:
            progress_dialog.close()
            logger.exception("Error during similarity search")
            QMessageBox.critical(
                self,
                "Search Error",
                f"Similarity search failed: {e!s}"
            )

    def _show_similarity_results(self, matches: Any) -> None:
        """Show similarity search results."""

        if not matches:
            QMessageBox.information(
                self,
                "No Similar Sprites",
                "No similar sprites found.\n\n"
                "Note: Similarity search requires indexing sprites from the ROM, "
                "which is not fully implemented yet. Currently only the current "
                "sprite is indexed for demonstration purposes."
            )
            return

        # Show results dialog (lazy import to avoid circular dependency)
        from ui.dialogs.similarity_results_dialog import (
            show_similarity_results,
        )

        dialog = show_similarity_results(matches, self.current_offset, self)
        dialog.sprite_selected.connect(self.similarity_search_requested.emit)
        dialog.exec()

    # === Qt-Specific Widget Update Methods ===

    def _setup_update_timer(self) -> None:
        """Setup timer for guaranteed Qt widget updates."""
        self._update_timer = QTimer(self)
        if self._update_timer:
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._force_widget_update)

    def _force_widget_update(self) -> None:
        """Force complete widget update using Qt-specific methods."""
        if self.preview_label is not None:
            # Progressive Qt update strategy for guaranteed visibility
            self.preview_label.update()           # Schedule paint event
            self.preview_label.repaint()          # Force immediate repaint
            # Note: repaint() already forces synchronous paint; processEvents() removed
            # to prevent reentrancy bugs

    def _diagnose_preview_state(self) -> None:
        """Diagnostic method to check preview widget state."""
        logger.info("[DIAGNOSIS] === Preview Widget State ===")
        logger.info(f"  preview_label exists: {self.preview_label is not None}")
        if self.preview_label is not None:
            logger.info(f"  preview_label visible: {self.preview_label.isVisible()}")
            logger.info(f"  preview_label size: {self.preview_label.size()}")
            pixmap = self.preview_label.pixmap()
            # QLabel.pixmap() always returns QPixmap, check if it's null
            logger.info(f"  pixmap size: {pixmap.width()}x{pixmap.height()}")
            logger.info(f"  pixmap null: {pixmap.isNull()}")
            logger.info(f"  label text: '{self.preview_label.text()}'")
        logger.info(f"  sprite_pixmap exists: {self.sprite_pixmap is not None}")
        logger.info(f"  sprite_data exists: {self.sprite_data is not None}")
        logger.info("====================================")

    def _show_no_data_pattern(self, width: int, height: int) -> None:
        """Show a checkerboard pattern to indicate no sprite data at this offset."""
        logger.debug(f"[SPRITE_DISPLAY] Showing no data pattern for {width}x{height}")

        # Create a checkerboard pattern to clearly indicate "no data"
        img = Image.new('L', (width, height), 0)

        # Draw checkerboard pattern
        square_size = 8
        for y in range(0, height, square_size):
            for x in range(0, width, square_size):
                # Alternate between dark and light squares
                if ((x // square_size) + (y // square_size)) % 2 == 0:
                    for dy in range(min(square_size, height - y)):
                        for dx in range(min(square_size, width - x)):
                            img.putpixel((x + dx, y + dy), 64)  # Dark gray
                else:
                    for dy in range(min(square_size, height - y)):
                        for dx in range(min(square_size, width - x)):
                            img.putpixel((x + dx, y + dy), 128)  # Light gray

        # Convert to RGBA for display
        img_rgba = img.convert("RGBA")

        # Convert to QPixmap
        img_bytes = img_rgba.tobytes()
        qimg = QImage(
            img_bytes,
            img_rgba.width,
            img_rgba.height,
            img_rgba.width * 4,
            QImage.Format.Format_RGBA8888,
        )

        pixmap = QPixmap.fromImage(qimg)

        # Scale for preview
        scaled = self._scale_pixmap_efficiently(pixmap)

        # Update display
        if self.preview_label:
            self.preview_label.setPixmap(scaled)
        if self.info_label:
            self.info_label.setText("No sprite data at this offset (all zeros)")
        if self.info_label:
            self.info_label.setVisible(True)

        # Ensure it's displayed
        self._guarantee_pixmap_display()

        # Disable palette selection for empty data
        if self.palette_combo:
            self.palette_combo.setEnabled(False)
        if self.palette_combo:
            self.palette_combo.clear()
        if self.palette_combo:
            self.palette_combo.addItem("No Data")

    def _force_visibility(self) -> None:
        """Force the preview widget and its contents to be visible."""
        if self.preview_label is None:
            return

        # Make sure widget is shown
        self.preview_label.show()
        self.show()

        # Force size recalculation
        self.preview_label.adjustSize()

        # Raise to top
        self.preview_label.raise_()

        # Note: processEvents() removed to prevent reentrancy bugs;
        # show() already queues necessary paint events

        logger.debug("[TRACE] Forced visibility update complete")

    def _show_loading_state(self) -> None:
        """Show visual loading state for immediate user feedback."""
        if self.preview_label is not None:
            self.preview_label.setText("Loading...")
            if self.preview_label:
                self.preview_label.setStyleSheet("""
                QLabel {
                    border: 1px solid #87ceeb;
                    background-color: #2d2d30;
                    color: #87ceeb;
                    margin: 0px;
                    padding: 10px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
            # Force immediate update for loading state
            self._force_widget_update()

    def _show_error_state(self, error_type: str) -> None:
        """Show visual error state with clear feedback."""
        if self.preview_label is not None:
            self.preview_label.setText(f"Error: {error_type}")
            if self.preview_label:
                self.preview_label.setStyleSheet("""
                QLabel {
                    border: 1px solid #ff6347;
                    background-color: #2d2d30;
                    color: #ff6347;
                    margin: 0px;
                    padding: 10px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
            # Force immediate update for error state
            self._force_widget_update()

        if self.essential_info_label is not None:
            self.essential_info_label.setText(error_type)

    def _load_grayscale_sprite_with_update(
        self, img: Image.Image, sprite_name: str | None = None
    ) -> None:
        """Load grayscale sprite with guaranteed Qt widget updates."""
        # Use original method for core functionality
        self._load_grayscale_sprite(img, sprite_name)

        # Then apply Qt-specific update guarantees
        self._guarantee_pixmap_display()

    def _load_grayscale_sprite_with_validation_and_update(
        self, img: Image.Image, sprite_name: str | None = None
    ) -> None:
        """Load grayscale sprite with validation and guaranteed Qt widget updates."""
        logger.debug("[SPRITE_DISPLAY] _load_grayscale_sprite_with_validation_and_update called")

        # Verify image has actual data
        try:
            # Quick sampling to verify image content
            sample_pixels = []
            sample_size = min(10, img.width, img.height)
            for i in range(sample_size):
                for j in range(sample_size):
                    pixel_value = img.getpixel((i, j))
                    sample_pixels.append(pixel_value)

            unique_values = set(sample_pixels)
            logger.debug(f"[SPRITE_DISPLAY] Image sample: {len(unique_values)} unique pixel values: {sorted(unique_values)[:10]}")

            # Use original method for core functionality
            self._load_grayscale_sprite(img, sprite_name)

            # Then apply Qt-specific update guarantees with validation
            self._guarantee_pixmap_display_with_validation()

        except Exception as e:
            logger.warning(f"[SPRITE_DISPLAY] Error in validation: {e}")
            # Fallback to standard method
            self._load_grayscale_sprite(img, sprite_name)
            self._guarantee_pixmap_display()

    def _guarantee_pixmap_display(self) -> None:
        """Guarantee pixmap is displayed using Qt-specific update pattern."""
        if self.preview_label is None:
            logger.warning("[TRACE] Cannot guarantee display - preview_label is None")
            return

        pixmap = self.preview_label.pixmap()
        # QLabel.pixmap() always returns QPixmap, check if it's null
        if pixmap.isNull():
            logger.warning("[TRACE] Cannot guarantee display - no pixmap set")
            return

        logger.debug(f"[TRACE] Guaranteeing pixmap display: {pixmap.width()}x{pixmap.height()}")

        # Multi-stage Qt update pattern for maximum reliability

        # Stage 0: Ensure widget is shown
        if not self.preview_label.isVisible():
            self.preview_label.show()
        if not self.isVisible():
            self.show()

        # Stage 1: Immediate widget update
        if self.preview_label:
            self.preview_label.update()

        # Stage 2: Force repaint if widget is visible
        if self.preview_label.isVisible():
            self.preview_label.repaint()

        # Stage 3: Ensure parent layout is updated
        layout = self.layout()
        if layout is not None:
            layout.update()

        # Stage 4: Delayed verification update (ensures display)
        # Note: processEvents() removed to prevent reentrancy bugs;
        # the timer-based verification handles deferred updates safely
        if self._update_timer is not None:
            self._update_timer.start(1)  # 1ms delayed update verification

        logger.debug("[TRACE] Pixmap display guarantee complete")

    def _guarantee_pixmap_display_with_validation(self) -> None:
        """Guarantee pixmap is displayed with comprehensive validation."""
        logger.debug("[DEBUG_SPRITE] _guarantee_pixmap_display_with_validation called")

        if self.preview_label is None:
            logger.error("[DEBUG_SPRITE] preview_label is None!")
            return

        pixmap = self.preview_label.pixmap()
        # QLabel.pixmap() always returns a QPixmap, check if it's null instead
        if pixmap.isNull():
            logger.error("[DEBUG_SPRITE] No pixmap set on preview_label!")
            logger.error(f"[DEBUG_SPRITE] Label has text instead: '{self.preview_label.text()}'")
            return

        logger.debug(f"[DEBUG_SPRITE] Pixmap validation passed: {pixmap.width()}x{pixmap.height()}, visible={self.preview_label.isVisible()}")

        # Check Qt thread context
        app = QApplication.instance()
        if app:
            logger.debug(f"[DEBUG_SPRITE] QApplication thread: {app.thread()}")
            logger.debug(f"[DEBUG_SPRITE] Current thread: {QThread.currentThread()}")
            logger.debug(f"[DEBUG_SPRITE] Label thread: {self.preview_label.thread()}")
        parent = self.parent()
        parent_visible = parent.isVisible() if parent and hasattr(parent, 'isVisible') else 'N/A'  # type: ignore[attr-defined]
        logger.debug(f"[SPRITE_DISPLAY] Widget hierarchy visibility: widget={self.isVisible()}, parent={parent_visible}")

        # Apply the standard guarantee method
        self._guarantee_pixmap_display()

        # Additional validation checks
        if not self.preview_label.isVisible():
            logger.warning("[DEBUG_SPRITE] preview_label is not visible!")
            logger.debug("[DEBUG_SPRITE] Trying to show label...")
            self.preview_label.show()
            logger.debug(f"[DEBUG_SPRITE] After show(): visible={self.preview_label.isVisible()}")

        # Verify parent widget visibility chain
        parent = self.preview_label.parent()
        parent_chain = []
        while parent:
            parent_info = {
                'class': parent.__class__.__name__,
                'visible': parent.isVisible() if hasattr(parent, 'isVisible') else 'N/A',  # type: ignore[attr-defined]
                'enabled': parent.isEnabled() if hasattr(parent, 'isEnabled') else 'N/A'  # type: ignore[attr-defined]
            }
            parent_chain.append(parent_info)
            if hasattr(parent, 'isVisible') and not parent.isVisible():  # type: ignore[attr-defined]
                logger.warning(f"[DEBUG_SPRITE] Parent widget not visible: {parent.__class__.__name__}")
            parent = parent.parent() if hasattr(parent, 'parent') else None

        if parent_chain:
            logger.debug(f"[DEBUG_SPRITE] Parent widget chain: {parent_chain}")

    def _verify_pixmap_display(self) -> None:
        """Final verification that pixmap is properly displayed."""
        logger.debug("[SPRITE_DISPLAY] _verify_pixmap_display called")

        if self.preview_label is None:
            logger.error("[SPRITE_DISPLAY] VERIFICATION FAILED: preview_label is None")
            return

        pixmap = self.preview_label.pixmap()
        # QLabel.pixmap() always returns a QPixmap, check if it's null
        if pixmap.isNull():
            logger.error("[SPRITE_DISPLAY] VERIFICATION FAILED: No valid pixmap")
            return

        # Check widget visibility
        if not self.preview_label.isVisible():
            logger.warning("[SPRITE_DISPLAY] VERIFICATION WARNING: preview_label not visible")

        # Check if widget has proper size
        widget_size = self.preview_label.size()
        pixmap_size = pixmap.size()

        logger.debug(f"[SPRITE_DISPLAY] VERIFICATION SUCCESS: pixmap={pixmap_size.width()}x{pixmap_size.height()}, widget={widget_size.width()}x{widget_size.height()}")

        # Force final display update
        # Note: processEvents() removed to prevent reentrancy bugs;
        # update() schedules paint event that will be processed by event loop
        self.preview_label.update()

        # Set essential info to show successful display
        if self.essential_info_label is not None:
            self.essential_info_label.setText(f"{pixmap_size.width()}x{pixmap_size.height()} - Loaded")

    def diagnose_display_issue(self) -> str:
        """Diagnose why sprites might not be displaying."""
        report = ["=== SPRITE DISPLAY DIAGNOSTIC ==="]

        # Check preview label
        if self.preview_label is None:
            report.append("ERROR: preview_label is None")
            logger.error("[DEBUG_SPRITE] " + report[-1])
        else:
            report.append(f"preview_label exists: {self.preview_label}")
            report.append(f"  - visible: {self.preview_label.isVisible()}")
            report.append(f"  - enabled: {self.preview_label.isEnabled()}")
            report.append(f"  - size: {self.preview_label.size()}")
            report.append(f"  - minimumSize: {self.preview_label.minimumSize()}")
            report.append(f"  - maximumSize: {self.preview_label.maximumSize()}")
            report.append(f"  - sizePolicy: {self.preview_label.sizePolicy()}")
            report.append(f"  - text: '{self.preview_label.text()}'")
            report.append(f"  - stylesheet: '{self.preview_label.styleSheet()[:100]}...'" if self.preview_label.styleSheet() else "  - stylesheet: None")

            pixmap = self.preview_label.pixmap()
            # QLabel.pixmap() always returns a QPixmap, check if it's null
            if pixmap.isNull():
                report.append("  - pixmap: Null/empty (THIS IS THE PROBLEM!)")
                logger.error("[DEBUG_SPRITE] Null pixmap!")
            else:
                report.append(f"  - pixmap: {pixmap.width()}x{pixmap.height()}")
                report.append(f"    - depth: {pixmap.depth()}")
                report.append(f"    - hasAlpha: {pixmap.hasAlpha()}")

        # Check stored sprite data
        report.append(f"\nsprite_pixmap: {self.sprite_pixmap}")
        if self.sprite_pixmap:
            report.append(f"  - size: {self.sprite_pixmap.width()}x{self.sprite_pixmap.height()}")
            report.append(f"  - null: {self.sprite_pixmap.isNull()}")

        report.append(f"sprite_data: {len(self.sprite_data) if self.sprite_data else 0} bytes")
        report.append(f"palettes: {len(self.palettes)} palettes loaded")
        report.append(f"current_palette_index: {self.current_palette_index}")

        # Check widget hierarchy
        report.append("\nWidget hierarchy:")
        parent = self.parent()
        level = 1
        while parent and level < 10:  # Limit depth to prevent infinite loops
            report.append(f"  {'  ' * level}Parent {level}: {parent.__class__.__name__}")
            if hasattr(parent, 'isVisible'):
                report.append(f"  {'  ' * level}  - visible: {parent.isVisible()}")  # type: ignore[attr-defined]
            parent = parent.parent() if hasattr(parent, 'parent') else None
            level += 1

        # Check Qt application
        app = QApplication.instance()
        if app:
            report.append(f"\nQApplication exists: {app}")
            report.append(f"  - thread: {app.thread()}")
            report.append(f"  - widget thread: {self.thread()}")
            report.append(f"  - current thread: {QThread.currentThread()}")
        else:
            report.append("\nERROR: No QApplication instance!")

        # Layout information
        layout = self.layout()
        if layout:
            report.append(f"\nLayout: {layout.__class__.__name__}")
            report.append(f"  - count: {layout.count()}")
            report.append(f"  - spacing: {layout.spacing()}")

        diagnostic_str = "\n".join(report)
        logger.info(f"[DEBUG_SPRITE]\n{diagnostic_str}")
        return diagnostic_str

    def _decode_4bpp_pixel_fallback(self, tile_bytes: bytes, x: int, y: int) -> int:
        """
        Fallback 4bpp pixel decoder when ROM extractor is not available.

        4bpp format: Each pixel is 4 bits, stored in a specific pattern within the tile.
        Based on typical SNES/Game Boy 4bpp tile format.
        """
        if len(tile_bytes) < 32:
            return 0

        # SNES 4bpp tile format:
        # - 8x8 tile = 32 bytes
        # - Each row is represented by 4 bytes (2 bitplanes of 2 bytes each)
        # - Pixel = bit from bp0_low | (bit from bp0_high << 1) | (bit from bp1_low << 2) | (bit from bp1_high << 3)

        # Calculate byte positions for this pixel
        row_offset = y * 2  # Each row uses 2 bytes for bitplane 0
        bitplane1_offset = 16  # Bitplane 1 starts at byte 16

        # Get the bit position within the byte (MSB = leftmost pixel)
        bit_pos = 7 - x

        try:
            # Get bitplane 0 (bytes 0-15)
            bp0_low = tile_bytes[row_offset]
            bp0_high = tile_bytes[row_offset + 1]

            # Get bitplane 1 (bytes 16-31)
            bp1_low = tile_bytes[bitplane1_offset + row_offset]
            bp1_high = tile_bytes[bitplane1_offset + row_offset + 1]

            # Extract bits for this pixel position
            bit0 = (bp0_low >> bit_pos) & 1
            bit1 = (bp0_high >> bit_pos) & 1
            bit2 = (bp1_low >> bit_pos) & 1
            bit3 = (bp1_high >> bit_pos) & 1

            # Combine bits to form 4-bit pixel value
            pixel_value = bit0 | (bit1 << 1) | (bit2 << 2) | (bit3 << 3)

            return pixel_value

        except IndexError:
            # If we can't access the required bytes, return 0
            return 0
