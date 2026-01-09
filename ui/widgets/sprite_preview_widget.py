"""
Sprite preview widget for SpritePal
Shows visual preview of sprites with optional palette support
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from PySide6.QtCore import QPoint

    from core.rom_extractor import ROMExtractor
    from core.visual_similarity_search import SimilarityMatch

from PIL import Image
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
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

from core.default_palette_loader import DefaultPaletteLoader
from core.services.image_utils import pil_to_qimage

# ExtractionManager accessed via get_app_context().core_operations_manager
from core.visual_similarity_search import VisualSimilarityEngine
from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.signal_utils import is_valid_qt
from ui.common.spacing_constants import (
    COMPACT_BUTTON_HEIGHT,
    QWIDGETSIZE_MAX,
    SPACING_TINY,
)
from ui.styles import get_muted_text_style
from ui.styles.theme import COLORS
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
            self.preview_label.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)  # Use all available space
            self.preview_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,  # Use ALL available space
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
                color: {COLORS["text_muted"]};
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
            parent=self,
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
                self.info_label.setText(f"Size: {img.size[0]}x{img.size[1]} | Mode: {img.mode}")

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

    def _load_grayscale_sprite(self, img: Image.Image, sprite_name: str | None = None) -> None:
        """Load grayscale sprite and apply palettes"""
        # NOTE: Thread safety is handled by Qt signals with QueuedConnection
        # This method should only be called from main thread via signals

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

        # Apply current palette
        self._update_preview_with_palette(img)

        # Diagnostic check after loading
        self.diagnose_display_issue()

    def _load_indexed_sprite(self, img: Image.Image) -> None:
        """Load indexed sprite with its palette"""
        # Convert to QImage using centralized utility (with alpha for transparency support)
        qimg = pil_to_qimage(img, with_alpha=True)
        pixmap = QPixmap.fromImage(qimg)

        # Scale for preview - adaptive sizing for space efficiency
        scaled = self._scale_pixmap_efficiently(pixmap)

        if self.preview_label:
            self.preview_label.setPixmap(scaled)
        # SPACE EFFICIENCY: When content is loaded, use borderless style
        self._apply_content_style()
        self.sprite_pixmap = pixmap

        # Guarantee the pixmap is displayed
        self._ensure_pixmap_displayed()

        # No palette selection for indexed sprites
        if self.palette_combo:
            self.palette_combo.setEnabled(False)
            self.palette_combo.clear()
            self.palette_combo.addItem("Built-in Palette")

    def _update_preview_with_palette(self, grayscale_img: Image.Image) -> None:
        """Update preview by applying selected palette to grayscale image"""
        # CRITICAL: Prevent concurrent pixmap updates which can crash Qt
        if self._update_in_progress:
            logger.warning("Update already in progress - skipping to prevent crash")
            return

        self._update_in_progress = True
        try:
            # Check if grayscale is selected (None) or palette index is invalid
            if self.current_palette_index is None:
                # Grayscale explicitly selected
                show_grayscale = True
            elif self.palettes and self.current_palette_index >= len(self.palettes):
                # Invalid palette index - reset to grayscale
                self.current_palette_index = None
                show_grayscale = True
            elif not self.palettes or self.current_palette_index >= len(self.palettes):
                # No palettes available or invalid index - show grayscale
                show_grayscale = True
            else:
                show_grayscale = False

            if show_grayscale:
                # Scale 4-bit values (0-15) to 8-bit (0-255)
                import numpy as np

                img_array = np.array(grayscale_img)
                # Detect if values are in 4-bit range and scale them
                if img_array.max() <= 15:
                    img_array = img_array * 17  # Scale 0-15 to 0-255
                    grayscale_img = Image.fromarray(img_array.astype(np.uint8), mode="L")
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

            # Convert to QImage using centralized utility
            qimg = pil_to_qimage(img_rgba, with_alpha=True)
            pixmap = QPixmap.fromImage(qimg)

            # Scale for preview - adaptive sizing for space efficiency
            scaled = self._scale_pixmap_efficiently(pixmap)

            if self.preview_label:
                self.preview_label.setPixmap(scaled)
            # SPACE EFFICIENCY: When content is loaded, use borderless style
            self._apply_content_style()
            self.sprite_pixmap = pixmap

            # Guarantee the pixmap is displayed
            self._ensure_pixmap_displayed()
            self._force_visibility()

        finally:
            # CRITICAL: Always clear the update flag to prevent deadlock
            self._update_in_progress = False

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

        try:
            # Validate tile data
            if not tile_data:
                # Don't clear to prevent flashing - keep last valid preview
                # Just update the info labels
                if self.essential_info_label:
                    self.essential_info_label.setText("No data")
                if self.info_label:
                    self.info_label.setText("No sprite data at this offset")
                return

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
                    else:
                        # Fallback to all palettes - filter out None entries
                        filtered_palette_list: list[list[tuple[int, int, int]]] = [
                            p for p in palette_list if p is not None
                        ]
                        self.palettes = filtered_palette_list if filtered_palette_list else []
                        # Ensure palette index is valid
                        if self.current_palette_index is not None and self.current_palette_index >= len(self.palettes):
                            self.current_palette_index = 0

            bytes_per_tile = 32
            extra_bytes = len(tile_data) % bytes_per_tile
            if extra_bytes > bytes_per_tile // 2:  # More than half a tile of extra data
                logger.warning(f"Possible corrupted data: {extra_bytes} extra bytes")
                # Don't clear() - try to display what we can to prevent flashing
                if self.essential_info_label:
                    self.essential_info_label.setText("Warning: Partial data")
                if self.info_label:
                    self.info_label.setText("Unable to display sprite - data appears corrupted")
                return

            # Try to get ROM extractor - handle case where it's not available
            extractor: ROMExtractor | None
            try:
                from core.app_context import get_app_context

                extraction_manager = get_app_context().core_operations_manager
                extractor = extraction_manager.get_rom_extractor()
            except Exception as e:
                logger.warning(f"ROM extractor not available: {e}")
                extractor = None

            # Create temporary image from 4bpp data
            img = Image.new("L", (width, height), 0)

            # Process tiles (simplified - assumes data is already in correct format)
            tiles_per_row = width // 8
            num_tiles = len(tile_data) // bytes_per_tile

            if num_tiles == 0:
                # Don't call clear() to prevent flashing - just update labels
                if self.essential_info_label:
                    self.essential_info_label.setText("No tiles")
                if self.info_label:
                    self.info_label.setText("No valid sprite tiles found")
                return

            # Track actual pixel data
            pixel_count = 0
            non_zero_pixels = 0

            # Choose decoding method based on extractor availability
            if extractor is not None and hasattr(extractor, "_get_4bpp_pixel"):
                decode_method = "rom_extractor"
            else:
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

            # Verify image has content before displaying
            if non_zero_pixels == 0:
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
            self._ensure_pixmap_displayed()

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

        # Only clear if there's actually content to clear
        # This prevents unnecessary flashing during rapid updates
        preview_pixmap = (
            self.preview_label.pixmap() if self.preview_label is not None and is_valid_qt(self.preview_label) else None
        )
        if self.sprite_pixmap is not None or preview_pixmap is not None:
            if self.preview_label is not None and is_valid_qt(self.preview_label):
                self.preview_label.clear()
            if self.preview_label is not None and is_valid_qt(self.preview_label):
                self.preview_label.setText(
                    "No preview available\n\nLoad a ROM and select an offset\nto view sprite data"
                )
            # Reset to minimum size for visibility when empty
            if self.preview_label is not None and is_valid_qt(self.preview_label):
                self.preview_label.setMinimumSize(100, 100)  # Space-efficient minimum

            # Apply visible empty state style
            self._apply_empty_state_style()

            if self.palette_combo is not None and is_valid_qt(self.palette_combo):
                self.palette_combo.clear()
            if self.palette_combo is not None and is_valid_qt(self.palette_combo):
                self.palette_combo.setEnabled(False)
            # Reset both info labels to cleared state
            if self.essential_info_label is not None and is_valid_qt(self.essential_info_label):
                self.essential_info_label.setText("No sprite loaded")
            if self.info_label is not None and is_valid_qt(self.info_label):
                self.info_label.setText("No sprite loaded")
            self.sprite_pixmap = None
            self.sprite_data = None
            self.palettes = []

    def _apply_empty_state_style(self) -> None:
        """Apply dark theme styling for empty state that's clearly visible"""
        if self.preview_label:
            try:
                from shiboken6 import isValid

                if not isValid(self.preview_label):
                    return
            except Exception:
                pass
            self.preview_label.setStyleSheet(f"""
            QLabel {{
                border: 2px dashed {COLORS["text_muted"]};
                background-color: {COLORS["preview_background"]};
                color: {COLORS["text_secondary"]};
                margin: 0px;
                padding: 20px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: normal;
            }}
        """)

    def _apply_content_style(self) -> None:
        """Apply style for actual content display with checkerboard background"""
        # Use dark background for better sprite visibility on dark theme
        if self.preview_label:
            self.preview_label.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS["preview_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                padding: 4px;
            }}
        """)

    def set_sprite(self, pixmap: QPixmap | None) -> None:
        """Set the sprite preview from a QPixmap.

        This method is called by the manual offset dialog to update the preview.

        Args:
            pixmap: The QPixmap to display, or None to clear
        """
        try:
            # Handle None or invalid pixmap by clearing
            if pixmap is None or pixmap.isNull():
                # Don't clear - keep previous preview visible
                return

            # Store the original pixmap
            self.sprite_pixmap = pixmap

            # Scale the pixmap efficiently for display
            scaled_pixmap = self._scale_pixmap_efficiently(pixmap)

            # Update the preview label
            if self.preview_label:
                self.preview_label.setPixmap(scaled_pixmap)

            # Apply content styling with checkerboard background
            self._apply_content_style()

            # Guarantee the pixmap is displayed
            self._ensure_pixmap_displayed()

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
                self.palette_combo.setEnabled(False)
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

    def _show_context_menu(self, position: QPoint) -> None:
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
            QMessageBox.information(self, "No Sprite", "Please load a sprite first before searching for similar ones.")
            return

        try:
            # Convert QPixmap to PIL Image for similarity search
            image = self._qpixmap_to_pil_image(self.sprite_pixmap)
            if image is None:
                QMessageBox.warning(self, "Conversion Error", "Could not convert sprite image for similarity search.")
                return

            # Show progress dialog for indexing
            progress_dialog = QProgressDialog(
                "Indexing sprites for similarity search...",
                "Cancel",
                0,
                0,  # Indeterminate progress
                self,
            )
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(500)  # Show after 500ms
            progress_dialog.show()

            # Start similarity search in a separate thread
            self._start_similarity_search_async(image, progress_dialog)

        except Exception as e:
            logger.exception("Error starting similarity search")
            QMessageBox.critical(self, "Search Error", f"Failed to start similarity search: {e!s}")

    def _qpixmap_to_pil_image(self, pixmap: QPixmap) -> Image.Image | None:
        """Convert QPixmap to PIL Image."""
        try:
            # Convert QPixmap to QImage
            qimage = pixmap.toImage()

            # Convert QImage to PIL Image
            width = qimage.width()
            height = qimage.height()

            # Get raw bytes from QImage
            # In PySide6, bits() returns a buffer-compatible object that can be 
            # converted directly to bytes.
            img_data = bytes(qimage.bits())

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
            from core.app_context import get_app_context

            extraction_manager = get_app_context().core_operations_manager
            if not extraction_manager:
                progress_dialog.close()
                QMessageBox.warning(
                    self, "No ROM Data", "ROM extraction manager not available. Please load a ROM first."
                )
                return

            # Create or get similarity engine
            if self.similarity_engine is None:
                self.similarity_engine = VisualSimilarityEngine()

            # Index current sprite
            self.similarity_engine.index_sprite(self.current_offset, target_image, {"source": "preview_widget"})

            # TODO: Index other sprites from ROM
            # This would require accessing sprite data from the ROM
            # For now, show a message that indexing is not fully implemented

            progress_dialog.close()

            # Perform similarity search
            matches = self.similarity_engine.find_similar(target_image, max_results=10, similarity_threshold=0.7)

            # Show results
            self._show_similarity_results(matches)

        except Exception as e:
            progress_dialog.close()
            logger.exception("Error during similarity search")
            QMessageBox.critical(self, "Search Error", f"Similarity search failed: {e!s}")

    def _show_similarity_results(self, matches: list[SimilarityMatch]) -> None:
        """Show similarity search results."""

        if not matches:
            QMessageBox.information(
                self,
                "No Similar Sprites",
                "No similar sprites found.\n\n"
                "Note: Similarity search requires indexing sprites from the ROM, "
                "which is not fully implemented yet. Currently only the current "
                "sprite is indexed for demonstration purposes.",
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
            self.preview_label.update()  # Schedule paint event
            self.preview_label.repaint()  # Force immediate repaint
            # Note: repaint() already forces synchronous paint; processEvents() removed
            # to prevent reentrancy bugs

    def _show_no_data_pattern(self, width: int, height: int) -> None:
        """Show a checkerboard pattern to indicate no sprite data at this offset."""

        # Create a checkerboard pattern to clearly indicate "no data"
        img = Image.new("L", (width, height), 0)

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

        # Convert to QPixmap using centralized utility
        qimg = pil_to_qimage(img, with_alpha=True)
        pixmap = QPixmap.fromImage(qimg)

        # Scale for preview
        scaled = self._scale_pixmap_efficiently(pixmap)

        # Update display
        if self.preview_label:
            self.preview_label.setPixmap(scaled)
        if self.info_label:
            self.info_label.setText("No sprite data at this offset (all zeros)")
            self.info_label.setVisible(True)

        # Ensure it's displayed
        self._ensure_pixmap_displayed()

        # Disable palette selection for empty data
        if self.palette_combo:
            self.palette_combo.setEnabled(False)
            self.palette_combo.clear()
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

    def _show_error_state(self, error_type: str) -> None:
        """Show visual error state with clear feedback."""
        if self.preview_label is not None:
            self.preview_label.setText(f"Error: {error_type}")
            self.preview_label.setStyleSheet(f"""
                QLabel {{
                    border: 1px solid {COLORS["danger"]};
                    background-color: {COLORS["background"]};
                    color: {COLORS["danger"]};
                    margin: 0px;
                    padding: 10px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
            # Force immediate update for error state
            self._force_widget_update()

        if self.essential_info_label is not None:
            self.essential_info_label.setText(error_type)

    def _load_grayscale_sprite_with_validation_and_update(
        self, img: Image.Image, sprite_name: str | None = None
    ) -> None:
        """Load grayscale sprite with validation and guaranteed Qt widget updates."""
        try:
            # Use original method for core functionality
            self._load_grayscale_sprite(img, sprite_name)

            # Then apply Qt-specific update guarantees
            self._ensure_pixmap_displayed()

        except Exception as e:
            logger.warning(f"Error in sprite validation: {e}")
            # Fallback to standard method
            self._load_grayscale_sprite(img, sprite_name)
            self._ensure_pixmap_displayed()

    def _ensure_pixmap_displayed(self, validate: bool = False) -> None:
        """Ensure pixmap is displayed with optional validation logging.

        Consolidates the display guarantee and verification logic into a single method.

        Args:
            validate: If True, log detailed thread/visibility information for debugging.
        """
        if self.preview_label is None:
            return

        pixmap = self.preview_label.pixmap()
        if pixmap.isNull():
            return

        # Optional validation logging for debugging
        if validate:
            self._log_display_validation_info(pixmap)

        # Stage 0: Ensure widget is shown
        if not self.preview_label.isVisible():
            self.preview_label.show()
        if not self.isVisible():
            self.show()

        # Stage 1: Immediate widget update
        self.preview_label.update()

        # Stage 2: Force repaint if widget is visible
        if self.preview_label.isVisible():
            self.preview_label.repaint()

        # Stage 3: Ensure parent layout is updated
        layout = self.layout()
        if layout is not None:
            layout.update()

        # Stage 4: Delayed verification update (ensures display)
        if self._update_timer is not None:
            self._update_timer.start(1)  # 1ms delayed update verification

        # Update info label with size
        if self.essential_info_label is not None:
            self.essential_info_label.setText(f"{pixmap.width()}x{pixmap.height()} - Loaded")

    def _log_display_validation_info(self, pixmap: QPixmap) -> None:
        """Log detailed validation info for debugging display issues.

        Args:
            pixmap: The pixmap being displayed.
        """
        # This method is only called when validate=True, for debugging purposes
        logger.debug(
            f"Pixmap: {pixmap.width()}x{pixmap.height()}, visible={self.preview_label.isVisible() if self.preview_label else False}"
        )

    def diagnose_display_issue(self) -> str:
        """Diagnose why sprites might not be displaying.

        Returns a diagnostic report string for debugging.
        """
        report = ["=== SPRITE DISPLAY DIAGNOSTIC ==="]

        # Check preview label
        if self.preview_label is None:
            report.append("ERROR: preview_label is None")
        else:
            report.append(f"preview_label: visible={self.preview_label.isVisible()}, size={self.preview_label.size()}")

            pixmap = self.preview_label.pixmap()
            if pixmap.isNull():
                report.append("pixmap: Null/empty")
            else:
                report.append(f"pixmap: {pixmap.width()}x{pixmap.height()}")

        # Check stored sprite data
        report.append(f"sprite_data: {len(self.sprite_data) if self.sprite_data else 0} bytes")
        report.append(f"palettes: {len(self.palettes)} loaded")

        return "\n".join(report)

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
