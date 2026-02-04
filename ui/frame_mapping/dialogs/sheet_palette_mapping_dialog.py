"""Dialog for editing sheet-level palette and color mappings."""

from __future__ import annotations

import math
from pathlib import Path
from typing import override

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.frame_mapping_project import SheetPalette
from core.palette_utils import (
    PALETTE_CLUSTER_THRESHOLD_SQ,
    PALETTE_DIVERSITY_MIN_DISTANCE,
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    find_nearest_palette_index,
    quantize_colors_to_palette,
    quantize_with_mappings,
)
from ui.components.base.dialog_base import DialogBase
from ui.frame_mapping.services.palette_service import GamePaletteInfo
from utils.color_distance import detect_rare_important_colors, perceptual_distance
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PaletteSlotWidget(QWidget):
    """Clickable palette slot showing color and index."""

    clicked = Signal(int)  # Emits slot index when clicked

    def __init__(
        self,
        index: int,
        color: tuple[int, int, int],
        size: int = 28,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self._color = color
        self._selected = False
        self.setFixedSize(size, size)
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        """Update tooltip with color info."""
        label = "(transparent)" if self._index == 0 else ""
        self.setToolTip(f"[{self._index}] RGB({self._color[0]}, {self._color[1]}, {self._color[2]}) {label}")

    def set_color(self, color: tuple[int, int, int]) -> None:
        """Update the displayed color."""
        self._color = color
        self._update_tooltip()
        self.update()

    def get_color(self) -> tuple[int, int, int]:
        """Get the current color."""
        return self._color

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self._selected = selected
        self.update()

    @override
    def paintEvent(self, event: object) -> None:
        """Draw the color slot."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(*self._color))

        # Draw border (highlighted if selected)
        if self._selected:
            painter.setPen(Qt.GlobalColor.blue)
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
            painter.drawRect(1, 1, self.width() - 3, self.height() - 3)
        else:
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Draw index number
        painter.setPen(Qt.GlobalColor.white if sum(self._color) < 384 else Qt.GlobalColor.black)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._index))

        # Draw X for transparency slot
        if self._index == 0:
            painter.setPen(Qt.GlobalColor.red)
            painter.drawLine(2, 2, self.width() - 3, self.height() - 3)

        painter.end()

    @override
    def mousePressEvent(self, event: object) -> None:
        """Handle click."""
        self.clicked.emit(self._index)


class ColorMappingRowWidget(QWidget):
    """A row showing: AI color swatch -> palette index dropdown."""

    mapping_changed = Signal(tuple, int)  # (rgb_color, new_palette_index)

    def __init__(
        self,
        rgb_color: tuple[int, int, int],
        pixel_count: int,
        palette: list[tuple[int, int, int]],
        initial_index: int,
        is_rare_important: bool = False,
        distinctness: float = 0.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rgb_color = rgb_color
        self._palette = palette
        self._is_rare_important = is_rare_important
        self._distinctness = distinctness
        self._protected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Protection indicator (★ for rare important colors)
        self._protect_label = QLabel("")
        self._protect_label.setFixedWidth(16)
        self._protect_label.setStyleSheet("font-size: 12px; color: #f0a030;")
        layout.addWidget(self._protect_label)

        # AI color swatch
        self._color_swatch = QWidget()
        self._color_swatch.setFixedSize(24, 24)
        self._color_swatch.setStyleSheet(
            f"background-color: rgb({rgb_color[0]}, {rgb_color[1]}, {rgb_color[2]}); border: 1px solid #888;"
        )
        layout.addWidget(self._color_swatch)

        # Color info label
        info_text = f"RGB({rgb_color[0]}, {rgb_color[1]}, {rgb_color[2]})  [{pixel_count} px]"
        if is_rare_important:
            info_text += f"  ⚠ rare (ΔE={distinctness:.1f})"
        info_label = QLabel(info_text)
        info_label.setMinimumWidth(220)
        info_label.setStyleSheet("font-size: 11px;")
        if is_rare_important:
            info_label.setStyleSheet("font-size: 11px; color: #e08030;")
        layout.addWidget(info_label)

        # Arrow
        arrow = QLabel("\u2192")  # →
        arrow.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(arrow)

        # Palette dropdown
        self._combo = QComboBox()
        self._combo.setMinimumWidth(180)
        self._populate_combo(initial_index)
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo)

        # Target color swatch
        self._target_swatch = QWidget()
        self._target_swatch.setFixedSize(24, 24)
        self._update_target_swatch(initial_index)
        layout.addWidget(self._target_swatch)

        layout.addStretch()

        # Show initial protection status if rare
        if is_rare_important:
            self._update_protection_indicator()

    def _populate_combo(self, selected_index: int) -> None:
        """Populate the palette dropdown."""
        for idx, color in enumerate(self._palette):
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(*color))
            label = f"[{idx}] RGB({color[0]}, {color[1]}, {color[2]})"
            if idx == 0:
                label += " (transparent)"
            self._combo.addItem(label)
            self._combo.setItemIcon(idx, pixmap)
        self._combo.setCurrentIndex(selected_index)

    def _update_target_swatch(self, index: int) -> None:
        """Update target color swatch."""
        if 0 <= index < len(self._palette):
            color = self._palette[index]
            self._target_swatch.setStyleSheet(
                f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); border: 1px solid #888;"
            )

    def _on_combo_changed(self, index: int) -> None:
        """Handle palette selection change."""
        self._update_target_swatch(index)
        self._update_protection_indicator()
        self.mapping_changed.emit(self._rgb_color, index)

    def _update_protection_indicator(self) -> None:
        """Update the protection indicator based on mapping quality."""
        if not self._is_rare_important:
            self._protect_label.setText("")
            return

        # Check if current mapping is good (low perceptual distance to target)
        current_idx = self._combo.currentIndex()
        if 0 <= current_idx < len(self._palette):
            target_color = self._palette[current_idx]
            distance = perceptual_distance(self._rgb_color, target_color)
            # Good mapping if distance < 15 (reasonable threshold)
            if distance < 15:
                self._protect_label.setText("★")
                self._protect_label.setToolTip(f"Protected: good match (ΔE={distance:.1f})")
                self._protected = True
            else:
                self._protect_label.setText("⚠")
                self._protect_label.setToolTip(f"Warning: poor match (ΔE={distance:.1f}), consider adjusting")
                self._protected = False
        else:
            self._protect_label.setText("⚠")
            self._protected = False

    def set_protected(self, protected: bool) -> None:
        """Manually set protection status."""
        self._protected = protected
        if protected:
            self._protect_label.setText("★")
            self._protect_label.setToolTip("Manually protected")
        elif self._is_rare_important:
            self._update_protection_indicator()
        else:
            self._protect_label.setText("")

    def is_protected(self) -> bool:
        """Check if this mapping is protected."""
        return self._protected

    def is_rare_important(self) -> bool:
        """Check if this is a rare important color."""
        return self._is_rare_important

    def get_mapping(self) -> tuple[tuple[int, int, int], int]:
        """Get current mapping."""
        return (self._rgb_color, self._combo.currentIndex())


class SheetPaletteMappingDialog(DialogBase):
    """Dialog for editing sheet palette and color mappings.

    Provides:
    - 16-slot palette editor with clickable slots
    - Scrollable list of extracted AI colors with palette index dropdowns
    - Auto-Map (nearest color), Extract Palette, Copy Game Palette buttons
    """

    def __init__(
        self,
        sheet_colors: dict[tuple[int, int, int], int],  # RGB -> pixel count
        current_palette: SheetPalette | None,
        game_palettes: dict[str, GamePaletteInfo],  # game_frame_id -> palette info
        parent: QWidget | None = None,
        *,
        sample_ai_frame_path: Path | None = None,
    ) -> None:
        """Initialize the dialog.

        Args:
            sheet_colors: Dict of unique RGB colors from AI sheet to pixel counts
            current_palette: Current SheetPalette or None
            game_palettes: Available game palettes to copy from (id -> GamePaletteInfo)
            parent: Parent widget
            sample_ai_frame_path: Optional path to an AI frame image for live preview
        """
        # Store before super().__init__ (DialogBase pattern)
        self._sheet_colors = sheet_colors
        self._game_palettes = game_palettes

        # Load sample image for preview (if provided)
        self._sample_image: Image.Image | None = None
        if sample_ai_frame_path is not None and sample_ai_frame_path.exists():
            try:
                self._sample_image = Image.open(sample_ai_frame_path).convert("RGBA")
            except Exception:
                logger.debug("Could not load sample image for preview: %s", sample_ai_frame_path)

        # Initialize palette (copy current or create default)
        if current_palette is not None:
            self._palette_colors = list(current_palette.colors)
            self._color_mappings = dict(current_palette.color_mappings)
        else:
            self._palette_colors = [(0, 0, 0)] * 16
            self._color_mappings: dict[tuple[int, int, int], int] = {}

        # Track background removal settings
        if current_palette is not None:
            self._background_color = current_palette.background_color
            self._background_tolerance = current_palette.background_tolerance
            self._alpha_threshold = getattr(current_palette, "alpha_threshold", QUANTIZATION_TRANSPARENCY_THRESHOLD)
            self._dither_mode = getattr(current_palette, "dither_mode", "none")
            self._dither_strength = float(getattr(current_palette, "dither_strength", 0.0))
        else:
            self._background_color: tuple[int, int, int] | None = None
            self._background_tolerance = 30
            self._alpha_threshold = QUANTIZATION_TRANSPARENCY_THRESHOLD
            self._dither_mode = "none"
            self._dither_strength = 0.0

        # Extraction tuning defaults
        self._cluster_threshold = math.sqrt(PALETTE_CLUSTER_THRESHOLD_SQ)
        self._diversity_min_distance = PALETTE_DIVERSITY_MIN_DISTANCE

        # Preview zoom + base pixmaps
        self._preview_zoom_percent = 200
        self._original_preview_pixmap: QPixmap | None = None
        self._quantized_preview_pixmap: QPixmap | None = None

        # Detect rare important colors (e.g., eye whites, small highlights)
        self._rare_important_colors = detect_rare_important_colors(
            sheet_colors,
            rarity_threshold=0.01,  # < 1% of pixels
            distinctness_threshold=20.0,  # LAB delta > 20
            max_candidates=10,
        )
        # Create lookup: color -> distinctness
        self._rare_color_lookup: dict[tuple[int, int, int], float] = {
            color: dist for color, _count, dist in self._rare_important_colors
        }

        # Compute initial mappings for unmapped colors
        for color in sheet_colors:
            if color not in self._color_mappings:
                self._color_mappings[color] = find_nearest_palette_index(color, self._palette_colors)

        # UI state
        self._palette_slots: list[PaletteSlotWidget] = []
        self._mapping_rows: list[ColorMappingRowWidget] = []
        self._selected_slot_index: int | None = None
        self._protect_rare_enabled = True  # Default: protect rare colors

        super().__init__(
            parent,
            title="Edit Sheet Palette",
            min_size=(900, 700) if self._sample_image else (650, 550),
            with_button_box=True,
        )

        # Debounced preview update timer
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(100)
        self._preview_timer.timeout.connect(self._update_preview)

        self._extract_timer = QTimer(self)
        self._extract_timer.setSingleShot(True)
        self._extract_timer.setInterval(150)
        self._extract_timer.timeout.connect(self._apply_extraction_settings)

        # Initial preview
        if self._sample_image:
            self._update_preview()

        # Customize button box
        if self.button_box:
            ok_button = self.button_box.button(self.button_box.StandardButton.Ok)
            if ok_button:
                ok_button.setText("Apply")

    def get_result(self) -> SheetPalette:
        """Get the resulting SheetPalette."""
        return SheetPalette(
            colors=list(self._palette_colors),
            color_mappings=dict(self._color_mappings),
            background_color=self._background_color,
            background_tolerance=self._background_tolerance,
            alpha_threshold=self._alpha_threshold,
            dither_mode=self._dither_mode,
            dither_strength=self._dither_strength,
        )

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        content_layout = QVBoxLayout()
        content_layout.setSpacing(8)

        # Header
        header = QLabel(
            "<b>Sheet Palette Editor</b><br>"
            "Define a consistent palette for all AI frames. "
            "Map AI colors to palette slots below."
        )
        header.setWordWrap(True)
        content_layout.addWidget(header)

        # Rare color warning (if any detected)
        if self._rare_important_colors:
            warning_frame = QFrame()
            warning_frame.setStyleSheet(
                "QFrame { background-color: #fff8e0; border: 1px solid #f0a030; border-radius: 4px; }"
            )
            warning_layout = QHBoxLayout(warning_frame)
            warning_layout.setContentsMargins(8, 4, 8, 4)

            warning_icon = QLabel("⚠")
            warning_icon.setStyleSheet("font-size: 16px; color: #e08030;")
            warning_layout.addWidget(warning_icon)

            rare_count = len(self._rare_important_colors)
            warning_text = QLabel(
                f"<b>{rare_count} rare important color(s) detected</b> (e.g., eye whites, highlights). "
                "These are marked below with ⚠. Review their mappings carefully."
            )
            warning_text.setWordWrap(True)
            warning_text.setStyleSheet("color: #604000;")
            warning_layout.addWidget(warning_text, 1)

            content_layout.addWidget(warning_frame)

        # Palette slots section
        palette_group = QWidget()
        palette_layout = QVBoxLayout(palette_group)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(4)

        palette_label = QLabel("Palette (16 colors):")
        palette_label.setStyleSheet("font-weight: bold;")
        palette_layout.addWidget(palette_label)

        # Palette slots row
        slots_layout = QHBoxLayout()
        slots_layout.setSpacing(2)
        for i in range(16):
            slot = PaletteSlotWidget(i, self._palette_colors[i])
            slot.clicked.connect(self._on_slot_clicked)
            self._palette_slots.append(slot)
            slots_layout.addWidget(slot)
        slots_layout.addStretch()
        palette_layout.addLayout(slots_layout)

        content_layout.addWidget(palette_group)

        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        extract_btn = QPushButton("Extract Palette")
        extract_btn.setToolTip("Generate 16-color palette from AI sheet colors")
        extract_btn.clicked.connect(self._on_extract_palette)
        actions_layout.addWidget(extract_btn)

        auto_map_btn = QPushButton("Auto-Map Colors")
        auto_map_btn.setToolTip("Map all AI colors to nearest palette colors (perceptual distance)")
        auto_map_btn.clicked.connect(self._on_auto_map)
        actions_layout.addWidget(auto_map_btn)

        # Protect rare colors checkbox
        self._protect_checkbox = QCheckBox("Protect Rare")
        self._protect_checkbox.setChecked(self._protect_rare_enabled)
        self._protect_checkbox.setToolTip("When enabled, rare important colors (★) are preserved during Auto-Map")
        self._protect_checkbox.stateChanged.connect(self._on_protect_toggle)
        actions_layout.addWidget(self._protect_checkbox)

        # Game palette dropdown (if available)
        if self._game_palettes:
            copy_label = QLabel("Copy from:")
            actions_layout.addWidget(copy_label)

            self._game_palette_combo = QComboBox()
            self._game_palette_combo.setMinimumWidth(160)
            for frame_id in sorted(self._game_palettes.keys()):
                info = self._game_palettes[frame_id]
                # Show display name (falls back to ID if no display name set)
                display_text = info.display_name
                self._game_palette_combo.addItem(display_text, frame_id)  # Store ID as item data
            actions_layout.addWidget(self._game_palette_combo)

            copy_btn = QPushButton("Copy")
            copy_btn.setToolTip("Copy palette from selected game frame")
            copy_btn.clicked.connect(self._on_copy_game_palette)
            actions_layout.addWidget(copy_btn)

        actions_layout.addStretch()
        content_layout.addLayout(actions_layout)

        # Extraction tuning controls
        tuning_group = QGroupBox("Extraction Tuning")
        tuning_layout = QHBoxLayout(tuning_group)
        tuning_layout.setSpacing(8)

        cluster_label = QLabel("Group Similar (ΔE):")
        tuning_layout.addWidget(cluster_label)

        self._cluster_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self._cluster_threshold_slider.setRange(0, 250)
        self._cluster_threshold_slider.setValue(int(round(self._cluster_threshold * 10)))
        self._cluster_threshold_slider.setToolTip(
            "Merge nearby colors before quantization. Higher values group more similar colors."
        )
        tuning_layout.addWidget(self._cluster_threshold_slider, 1)

        self._cluster_threshold_value = QLabel(f"{self._cluster_threshold:.1f}")
        self._cluster_threshold_value.setMinimumWidth(36)
        self._cluster_threshold_value.setStyleSheet("font-size: 11px;")
        tuning_layout.addWidget(self._cluster_threshold_value)

        diversity_label = QLabel("Min Palette ΔE:")
        tuning_layout.addWidget(diversity_label)

        self._diversity_distance_slider = QSlider(Qt.Orientation.Horizontal)
        self._diversity_distance_slider.setRange(0, 300)
        self._diversity_distance_slider.setValue(int(round(self._diversity_min_distance * 10)))
        self._diversity_distance_slider.setToolTip(
            "Minimum perceptual distance between palette colors. Higher values enforce distinct hues."
        )
        tuning_layout.addWidget(self._diversity_distance_slider, 1)

        self._diversity_distance_value = QLabel(f"{self._diversity_min_distance:.1f}")
        self._diversity_distance_value.setMinimumWidth(36)
        self._diversity_distance_value.setStyleSheet("font-size: 11px;")
        tuning_layout.addWidget(self._diversity_distance_value)

        tuning_layout.addStretch()
        content_layout.addWidget(tuning_group)

        self._cluster_threshold_slider.valueChanged.connect(self._on_extraction_settings_changed)
        self._diversity_distance_slider.valueChanged.connect(self._on_extraction_settings_changed)

        # Background removal section
        bg_group = QGroupBox("Background Removal")
        bg_layout = QHBoxLayout(bg_group)
        bg_layout.setSpacing(8)

        # Background color label
        bg_label = QLabel("Background color:")
        bg_layout.addWidget(bg_label)

        # Color swatch
        self._bg_swatch = QWidget()
        self._bg_swatch.setFixedSize(32, 32)
        self._update_bg_swatch()
        bg_layout.addWidget(self._bg_swatch)

        # Pick button
        pick_btn = QPushButton("Pick...")
        pick_btn.setToolTip("Choose background color to remove")
        pick_btn.clicked.connect(self._on_pick_background)
        bg_layout.addWidget(pick_btn)

        # Auto button
        auto_btn = QPushButton("Auto")
        auto_btn.setToolTip("Auto-detect background color from image corners")
        auto_btn.clicked.connect(self._on_auto_detect_background)
        bg_layout.addWidget(auto_btn)

        # Tolerance
        tol_label = QLabel("Tolerance:")
        bg_layout.addWidget(tol_label)

        self._tolerance_spin = QSpinBox()
        self._tolerance_spin.setRange(0, 100)
        self._tolerance_spin.setValue(self._background_tolerance)
        self._tolerance_spin.setToolTip("RGB distance threshold (0-100)")
        self._tolerance_spin.valueChanged.connect(self._on_tolerance_changed)
        bg_layout.addWidget(self._tolerance_spin)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Disable background removal")
        clear_btn.clicked.connect(self._on_clear_background)
        bg_layout.addWidget(clear_btn)

        bg_layout.addStretch()
        content_layout.addWidget(bg_group)

        # Quantization detail controls
        quant_group = QGroupBox("Quantization")
        quant_layout = QHBoxLayout(quant_group)
        quant_layout.setSpacing(8)

        dither_label = QLabel("Dither:")
        quant_layout.addWidget(dither_label)

        self._dither_combo = QComboBox()
        self._dither_combo.addItem("Off", "none")
        self._dither_combo.addItem("Ordered (Bayer)", "bayer")
        self._dither_combo.setToolTip("Ordered dithering can preserve fine detail but adds texture")
        if self._dither_mode == "bayer":
            self._dither_combo.setCurrentIndex(1)
        else:
            self._dither_combo.setCurrentIndex(0)
        self._dither_combo.currentIndexChanged.connect(self._on_dither_mode_changed)
        quant_layout.addWidget(self._dither_combo)

        strength_label = QLabel("Strength:")
        quant_layout.addWidget(strength_label)

        self._dither_strength_slider = QSlider(Qt.Orientation.Horizontal)
        self._dither_strength_slider.setRange(0, 100)
        self._dither_strength_slider.setValue(int(self._dither_strength * 100))
        self._dither_strength_slider.setMaximumWidth(80)
        self._dither_strength_slider.setToolTip("Ordered dither strength (0-100%)")
        self._dither_strength_slider.valueChanged.connect(self._on_dither_strength_changed)
        quant_layout.addWidget(self._dither_strength_slider)

        self._dither_strength_value = QLabel(f"{int(self._dither_strength * 100)}%")
        self._dither_strength_value.setStyleSheet("font-size: 11px;")
        self._dither_strength_value.setMinimumWidth(40)
        quant_layout.addWidget(self._dither_strength_value)

        dither_enabled = self._dither_mode == "bayer"
        self._dither_strength_slider.setEnabled(dither_enabled)
        self._dither_strength_value.setEnabled(dither_enabled)

        quant_sep = QFrame()
        quant_sep.setFrameShape(QFrame.Shape.VLine)
        quant_sep.setFrameShadow(QFrame.Shadow.Sunken)
        quant_layout.addWidget(quant_sep)

        alpha_label = QLabel("Alpha threshold:")
        quant_layout.addWidget(alpha_label)

        self._alpha_threshold_spin = QSpinBox()
        self._alpha_threshold_spin.setRange(0, 255)
        self._alpha_threshold_spin.setValue(self._alpha_threshold)
        self._alpha_threshold_spin.setToolTip("Pixels with alpha below this are transparent")
        self._alpha_threshold_spin.valueChanged.connect(self._on_alpha_threshold_changed)
        quant_layout.addWidget(self._alpha_threshold_spin)

        quant_layout.addStretch()
        content_layout.addWidget(quant_group)

        # Live preview section (only if sample image provided)
        if self._sample_image is not None:
            preview_group = QGroupBox("Live Preview")
            preview_group_layout = QVBoxLayout(preview_group)
            preview_group_layout.setSpacing(8)

            zoom_layout = QHBoxLayout()
            zoom_label = QLabel("Zoom:")
            zoom_layout.addWidget(zoom_label)

            self._preview_zoom_slider = QSlider(Qt.Orientation.Horizontal)
            self._preview_zoom_slider.setRange(50, 800)
            self._preview_zoom_slider.setValue(self._preview_zoom_percent)
            self._preview_zoom_slider.setToolTip("Zoom both previews")
            zoom_layout.addWidget(self._preview_zoom_slider, 1)

            self._preview_zoom_value = QLabel(f"{self._preview_zoom_percent}%")
            self._preview_zoom_value.setMinimumWidth(48)
            self._preview_zoom_value.setStyleSheet("font-size: 11px;")
            zoom_layout.addWidget(self._preview_zoom_value)
            preview_group_layout.addLayout(zoom_layout)

            previews_layout = QHBoxLayout()
            previews_layout.setSpacing(16)

            # Original preview
            original_frame = QVBoxLayout()
            original_label = QLabel("Original")
            original_label.setStyleSheet("font-size: 10px; color: #666;")
            original_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            original_frame.addWidget(original_label)

            self._original_preview_label = QLabel()
            self._original_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._original_preview_label.setStyleSheet("background-color: #2a2a2a;")

            original_scroll = QScrollArea()
            original_scroll.setWidget(self._original_preview_label)
            original_scroll.setWidgetResizable(False)
            original_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
            original_scroll.setMinimumSize(260, 260)
            original_scroll.setStyleSheet("background-color: #1e1e1e; border: 1px solid #888;")
            original_frame.addWidget(original_scroll, 1)
            previews_layout.addLayout(original_frame, 1)

            # Quantized preview
            quantized_frame = QVBoxLayout()
            quantized_label = QLabel("Quantized")
            quantized_label.setStyleSheet("font-size: 10px; color: #666;")
            quantized_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            quantized_frame.addWidget(quantized_label)

            self._quantized_preview_label = QLabel()
            self._quantized_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._quantized_preview_label.setStyleSheet("background-color: #2a2a2a;")

            quantized_scroll = QScrollArea()
            quantized_scroll.setWidget(self._quantized_preview_label)
            quantized_scroll.setWidgetResizable(False)
            quantized_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
            quantized_scroll.setMinimumSize(260, 260)
            quantized_scroll.setStyleSheet("background-color: #1e1e1e; border: 1px solid #888;")
            quantized_frame.addWidget(quantized_scroll, 1)
            previews_layout.addLayout(quantized_frame, 1)

            preview_group_layout.addLayout(previews_layout)
            content_layout.addWidget(preview_group)

            self._preview_zoom_slider.valueChanged.connect(self._on_preview_zoom_changed)
            self._set_original_preview()

        # Color mappings section
        mappings_header_layout = QHBoxLayout()
        mappings_label = QLabel("Color Mappings:")
        mappings_label.setStyleSheet("font-weight: bold;")
        mappings_header_layout.addWidget(mappings_label)

        legend_label = QLabel("★ = protected  ⚠ = needs review")
        legend_label.setStyleSheet("font-size: 10px; color: #808080;")
        mappings_header_layout.addWidget(legend_label)
        mappings_header_layout.addStretch()
        content_layout.addLayout(mappings_header_layout)

        # Scrollable mapping rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(2)

        # Sort colors: rare important colors first, then by pixel count
        sorted_colors = sorted(
            self._sheet_colors.items(),
            key=lambda x: (x[0] not in self._rare_color_lookup, -x[1]),  # rare first, then by count
        )

        # Limit displayed colors
        max_displayed = 50
        displayed_colors = sorted_colors[:max_displayed]
        hidden_count = len(sorted_colors) - len(displayed_colors)

        for color, pixel_count in displayed_colors:
            initial_idx = self._color_mappings.get(color, 1)
            is_rare = color in self._rare_color_lookup
            distinctness = self._rare_color_lookup.get(color, 0.0)
            row = ColorMappingRowWidget(
                color,
                pixel_count,
                self._palette_colors,
                initial_idx,
                is_rare_important=is_rare,
                distinctness=distinctness,
            )
            row.mapping_changed.connect(self._on_mapping_changed)
            self._mapping_rows.append(row)
            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        content_layout.addWidget(scroll, 1)

        # Summary
        total_colors = len(self._sheet_colors)
        total_pixels = sum(self._sheet_colors.values())
        rare_count = len(self._rare_important_colors)
        if hidden_count > 0:
            summary = QLabel(
                f"Showing top {max_displayed} of {total_colors} unique colors "
                f"({total_pixels} total pixels, {rare_count} rare)\n"
                f"Note: {hidden_count} minor colors will use nearest-color matching."
            )
        else:
            summary = QLabel(f"Total: {total_colors} unique colors, {total_pixels} pixels, {rare_count} rare important")
        content_layout.addWidget(summary)

        self.set_content_layout(content_layout)

    def _on_slot_clicked(self, index: int) -> None:
        """Handle palette slot click."""
        # Deselect previous
        if self._selected_slot_index is not None:
            self._palette_slots[self._selected_slot_index].set_selected(False)

        # Select new (or deselect if same)
        if self._selected_slot_index == index:
            self._selected_slot_index = None
        else:
            self._selected_slot_index = index
            self._palette_slots[index].set_selected(True)

    def _on_extract_palette(self) -> None:
        """Extract 16-color palette from AI sheet colors."""
        self._extract_palette(log=True)

    def _apply_extraction_settings(self) -> None:
        """Apply extraction tuning (debounced)."""
        self._extract_palette(log=False)

    def _extract_palette(self, *, log: bool) -> None:
        """Extract a 16-color palette using current tuning options."""
        extracted = quantize_colors_to_palette(
            self._sheet_colors,
            max_colors=16,
            snap_to_snes=True,
            background_color=self._background_color,
            background_tolerance=self._background_tolerance,
            cluster_threshold=self._cluster_threshold,
            diversity_min_distance=self._diversity_min_distance,
        )

        self._palette_colors = extracted
        for i, slot in enumerate(self._palette_slots):
            slot.set_color(extracted[i])

        # Re-map all colors to new palette
        self._on_auto_map()

        if log:
            logger.info("Extracted 16-color palette from %d sheet colors", len(self._sheet_colors))

    def _on_extraction_settings_changed(self, _value: float) -> None:
        """Handle extraction tuning changes."""
        self._cluster_threshold = self._cluster_threshold_slider.value() / 10.0
        self._diversity_min_distance = self._diversity_distance_slider.value() / 10.0
        if hasattr(self, "_cluster_threshold_value"):
            self._cluster_threshold_value.setText(f"{self._cluster_threshold:.1f}")
        if hasattr(self, "_diversity_distance_value"):
            self._diversity_distance_value.setText(f"{self._diversity_min_distance:.1f}")
        self._request_extract_update()

    def _request_extract_update(self) -> None:
        """Request a debounced palette extraction update."""
        self._extract_timer.start()

    def _on_protect_toggle(self, state: int) -> None:
        """Handle protect checkbox toggle."""
        self._protect_rare_enabled = state == Qt.CheckState.Checked.value
        logger.debug("Protect rare colors: %s", self._protect_rare_enabled)

    def _on_auto_map(self) -> None:
        """Auto-map all colors to nearest palette colors (perceptual distance).

        If "Protect Rare" is enabled, protected mappings are preserved.
        """
        protected_count = 0

        for color in self._sheet_colors:
            # Skip protected colors if protection is enabled
            if self._protect_rare_enabled and color in self._rare_color_lookup:
                # Check if current mapping is good enough to protect
                current_idx = self._color_mappings.get(color, 1)
                if 0 <= current_idx < len(self._palette_colors):
                    target_color = self._palette_colors[current_idx]
                    distance = perceptual_distance(color, target_color)
                    if distance < 15:  # Good match - keep it
                        protected_count += 1
                        continue

            # Auto-map to nearest perceptual match
            nearest_idx = find_nearest_palette_index(color, self._palette_colors)
            self._color_mappings[color] = nearest_idx

        # Update UI rows
        for row in self._mapping_rows:
            rgb, _ = row.get_mapping()
            new_idx = self._color_mappings.get(rgb, 1)
            row._combo.blockSignals(True)
            row._combo.setCurrentIndex(new_idx)
            row._update_target_swatch(new_idx)
            row._combo.blockSignals(False)
            # Update protection indicator
            if row.is_rare_important():
                row._update_protection_indicator()

        if protected_count > 0:
            logger.info(
                "Auto-mapped %d colors (perceptual LAB), preserved %d protected mappings",
                len(self._sheet_colors) - protected_count,
                protected_count,
            )
        else:
            logger.info("Auto-mapped %d colors to nearest palette colors (perceptual LAB)", len(self._sheet_colors))

        # Update preview
        self._request_preview_update()

    def _on_copy_game_palette(self) -> None:
        """Copy palette from selected game frame."""
        if not hasattr(self, "_game_palette_combo"):
            return

        # Use item data (frame ID) instead of display text
        frame_id = self._game_palette_combo.currentData()
        if frame_id is None or frame_id not in self._game_palettes:
            return

        palette_info = self._game_palettes[frame_id]

        # Copy colors (ensure 16 colors)
        self._palette_colors = list(palette_info.colors[:16])
        while len(self._palette_colors) < 16:
            self._palette_colors.append((0, 0, 0))

        # Update slots
        for i, slot in enumerate(self._palette_slots):
            slot.set_color(self._palette_colors[i])

        # Re-map to new palette
        self._on_auto_map()

        logger.info("Copied palette from game frame %s (%s)", frame_id, palette_info.display_name)

    def _on_mapping_changed(self, rgb_color: tuple[int, int, int], palette_index: int) -> None:
        """Handle mapping change from a row."""
        self._color_mappings[rgb_color] = palette_index
        self._request_preview_update()

    def _update_bg_swatch(self) -> None:
        """Update the background color swatch display."""
        if self._background_color is not None:
            r, g, b = self._background_color
            self._bg_swatch.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border: 1px solid #888;")
        else:
            # Checkerboard pattern for "no color"
            self._bg_swatch.setStyleSheet("background-color: #ccc; border: 1px solid #888;")

    def _on_pick_background(self) -> None:
        """Open color picker for background color."""
        initial = QColor(*self._background_color) if self._background_color else QColor(255, 255, 255)
        color = QColorDialog.getColor(initial, self, "Select Background Color")
        if color.isValid():
            self._background_color = (color.red(), color.green(), color.blue())
            self._update_bg_swatch()
            self._request_preview_update()
            logger.info("Background color set to RGB(%d, %d, %d)", *self._background_color)

    def _on_auto_detect_background(self) -> None:
        """Auto-detect background color from sheet colors."""
        # Try to find a consistent corner color from the source images
        # For now, use the most common light color (likely background)
        # In practice, we'd need access to an actual image file
        # This is a simplified heuristic using sheet colors

        # Find the lightest colors that are likely backgrounds
        light_colors = [
            (rgb, count)
            for rgb, count in self._sheet_colors.items()
            if sum(rgb) > 600  # Light colors (R+G+B > 600)
        ]

        if light_colors:
            # Use the most common light color
            light_colors.sort(key=lambda x: -x[1])
            self._background_color = light_colors[0][0]
            self._update_bg_swatch()
            logger.info(
                "Auto-detected background color: RGB(%d, %d, %d)",
                *self._background_color,
            )
        else:
            logger.warning("Could not auto-detect background color (no light colors found)")

    def _on_tolerance_changed(self, value: int) -> None:
        """Handle tolerance spinbox change."""
        self._background_tolerance = value
        self._request_preview_update()

    def _on_dither_mode_changed(self, _index: int) -> None:
        """Handle dither mode change."""
        if not hasattr(self, "_dither_combo"):
            return
        self._dither_mode = self._dither_combo.currentData() or "none"
        dither_enabled = self._dither_mode == "bayer"
        if hasattr(self, "_dither_strength_slider"):
            self._dither_strength_slider.setEnabled(dither_enabled)
        if hasattr(self, "_dither_strength_value"):
            self._dither_strength_value.setEnabled(dither_enabled)
        self._request_preview_update()

    def _on_dither_strength_changed(self, value: int) -> None:
        """Handle dither strength change."""
        self._dither_strength = max(0.0, min(1.0, value / 100.0))
        if hasattr(self, "_dither_strength_value"):
            self._dither_strength_value.setText(f"{int(self._dither_strength * 100)}%")
        self._request_preview_update()

    def _on_alpha_threshold_changed(self, value: int) -> None:
        """Handle alpha threshold change."""
        self._alpha_threshold = max(0, min(255, value))
        self._request_preview_update()

    def _on_clear_background(self) -> None:
        """Clear background color (disable removal)."""
        self._background_color = None
        self._update_bg_swatch()
        self._request_preview_update()
        logger.info("Background removal disabled")

    # ===== Live Preview Methods =====

    def _request_preview_update(self) -> None:
        """Request a debounced preview update."""
        if self._sample_image is not None:
            self._preview_timer.start()

    def _on_preview_zoom_changed(self, value: int) -> None:
        """Handle zoom slider changes."""
        self._preview_zoom_percent = max(10, value)
        if hasattr(self, "_preview_zoom_value"):
            self._preview_zoom_value.setText(f"{self._preview_zoom_percent}%")
        self._refresh_preview_labels()

    def _set_original_preview(self) -> None:
        """Set the original preview image."""
        if self._sample_image is None:
            return

        img = self._sample_image.copy()
        qimage = QImage(
            img.tobytes("raw", "RGBA"),
            img.width,
            img.height,
            img.width * 4,
            QImage.Format.Format_RGBA8888,
        )
        self._original_preview_pixmap = QPixmap.fromImage(qimage)
        self._refresh_preview_labels()

    def _update_preview(self) -> None:
        """Update the quantized preview image."""
        if self._sample_image is None:
            return

        if not hasattr(self, "_quantized_preview_label"):
            return

        # Quantize with current mappings
        quantized_indexed = quantize_with_mappings(
            self._sample_image,
            self._palette_colors,
            self._color_mappings,
            transparency_threshold=self._alpha_threshold,
            dither_mode=self._dither_mode,
            dither_strength=self._dither_strength,
        )

        # Convert indexed image back to RGBA for display
        quantized_rgba = quantized_indexed.convert("RGBA")

        # Apply background removal (make background transparent) for preview
        if self._background_color is not None:
            # Get the palette index that background should map to (usually 0)
            bg_idx = self._color_mappings.get(self._background_color, 0)
            if bg_idx == 0:
                # Set pixels with index 0 to transparent in the RGBA version
                # This is already handled by quantize_with_mappings for transparent pixels
                pass

        qimage = QImage(
            quantized_rgba.tobytes("raw", "RGBA"),
            quantized_rgba.width,
            quantized_rgba.height,
            quantized_rgba.width * 4,
            QImage.Format.Format_RGBA8888,
        )
        self._quantized_preview_pixmap = QPixmap.fromImage(qimage)
        self._refresh_preview_labels()

    def _refresh_preview_labels(self) -> None:
        """Apply current zoom to preview pixmaps."""
        if self._sample_image is None:
            return

        zoom = max(0.1, self._preview_zoom_percent / 100.0)

        if hasattr(self, "_original_preview_label") and self._original_preview_pixmap is not None:
            scaled = self._scale_preview_pixmap(self._original_preview_pixmap, zoom)
            self._original_preview_label.setPixmap(scaled)
            self._original_preview_label.resize(scaled.size())

        if hasattr(self, "_quantized_preview_label") and self._quantized_preview_pixmap is not None:
            scaled = self._scale_preview_pixmap(self._quantized_preview_pixmap, zoom)
            self._quantized_preview_label.setPixmap(scaled)
            self._quantized_preview_label.resize(scaled.size())

    @staticmethod
    def _scale_preview_pixmap(pixmap: QPixmap, zoom: float) -> QPixmap:
        """Scale a pixmap using nearest-neighbor for crisp pixel art."""
        width = max(1, int(pixmap.width() * zoom))
        height = max(1, int(pixmap.height() * zoom))
        return pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
