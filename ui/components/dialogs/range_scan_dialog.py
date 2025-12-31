"""
Range Scan Configuration Dialog

Dialog for selecting range scanning parameters for ROM sprite exploration.
"""

from __future__ import annotations

from typing import override

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.dialog_base import DialogBase
from ui.styles.theme import COLORS


class RangeScanDialog(DialogBase):
    """Dialog for selecting range scanning parameters"""

    def __init__(self, rom_size: int, current_offset: int = 0, parent: QWidget | None = None):
        # Step 1: Declare instance variables BEFORE super().__init__()
        self.current_offset = current_offset
        self.rom_size = rom_size
        self.range_combo: QComboBox | None = None
        self.range_label: QLabel | None = None

        # Step 2: Call parent init (this calls _setup_ui)
        super().__init__(
            parent,
            title="Range Scan Configuration",
            modal=True,
            size=(400, 200),
        )

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout()

        # Form layout for parameters
        form_layout = QFormLayout()

        # Range size selection
        self.range_combo = QComboBox()
        self.range_combo.addItems(
            ["±1 KB (±0x400)", "±4 KB (±0x1000)", "±16 KB (±0x4000)", "±64 KB (±0x10000)", "±256 KB (±0x40000)"]
        )
        self.range_combo.setCurrentIndex(2)  # Default to ±16KB
        form_layout.addRow("Scan Range:", self.range_combo)

        # Current offset display
        offset_label = QLabel(f"0x{self.current_offset:06X}")
        offset_label.setStyleSheet("font-family: monospace; font-weight: bold;")
        form_layout.addRow("Center Offset:", offset_label)

        # Range preview
        self.range_label = QLabel()
        self.range_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-family: monospace;")
        form_layout.addRow("Scan Range:", self.range_label)

        layout.addLayout(form_layout)

        # Update range display when selection changes
        self.range_combo.currentIndexChanged.connect(self._update_range_display)
        self._update_range_display()

        # Set layout on content widget
        self.content_widget.setLayout(layout)

    @override
    def accept(self) -> None:
        """Override to validate scan parameters before accepting."""
        if self._validate_parameters():
            super().accept()

    def _update_range_display(self) -> None:
        """Update the range display based on current selection."""
        if self.range_combo is None:
            return  # Not yet initialized
        range_sizes = [0x400, 0x1000, 0x4000, 0x10000, 0x40000]
        range_size = range_sizes[self.range_combo.currentIndex()]

        start_offset = max(0, self.current_offset - range_size)
        end_offset = min(self.rom_size - 1, self.current_offset + range_size)

        # Calculate actual range size for display
        actual_range = end_offset - start_offset + 1
        range_mb = actual_range / (1024 * 1024)

        if range_mb >= 1.0:
            size_text = f" ({range_mb:.1f} MB)"
        else:
            size_kb = actual_range / 1024
            size_text = f" ({size_kb:.0f} KB)"

        if self.range_label:
            self.range_label.setText(f"0x{start_offset:06X} - 0x{end_offset:06X}{size_text}")

    def _validate_parameters(self) -> bool:
        """Validate scan parameters before accepting.

        Returns:
            True if all validations pass, False otherwise.
        """
        start_offset, end_offset = self._calculate_range()

        # Validation constants
        MIN_SCAN_SIZE = 0x100  # 256 bytes minimum
        MAX_SCAN_SIZE = 0x1000000  # 16MB maximum for reasonable performance

        # Calculate actual scan size
        scan_size = end_offset - start_offset + 1

        # Validate scan size
        if scan_size < MIN_SCAN_SIZE:
            _ = QMessageBox.warning(
                self,
                "Invalid Range",
                f"Scan range too small ({scan_size} bytes).\n\nMinimum range is {MIN_SCAN_SIZE} bytes.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        if scan_size > MAX_SCAN_SIZE:
            result = _ = QMessageBox.question(
                self,
                "Large Range Warning",
                f"Scan range is very large ({scan_size / (1024 * 1024):.1f} MB).\n\n"
                f"This may take a long time and use significant memory.\n"
                f"Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return False

        # Validate offset bounds
        if start_offset < 0 or end_offset >= self.rom_size:
            _ = QMessageBox.warning(
                self,
                "Invalid Range",
                f"Scan range extends outside ROM bounds.\n\n"
                f"ROM size: 0x{self.rom_size:06X}\n"
                f"Range: 0x{start_offset:06X} - 0x{end_offset:06X}",
                QMessageBox.StandardButton.Ok,
            )
            return False

        if start_offset >= end_offset:
            _ = QMessageBox.warning(
                self, "Invalid Range", "Start offset must be less than end offset.", QMessageBox.StandardButton.Ok
            )
            return False

        # All validations passed
        return True

    def _calculate_range(self) -> tuple[int, int]:
        """Calculate the scan range without bounds checking."""
        range_sizes = [0x400, 0x1000, 0x4000, 0x10000, 0x40000]
        # Default to middle option (16KB) if combo not yet initialized
        combo_index = self.range_combo.currentIndex() if self.range_combo else 2
        range_size = range_sizes[combo_index]

        start_offset = max(0, self.current_offset - range_size)
        end_offset = min(self.rom_size - 1, self.current_offset + range_size)

        return start_offset, end_offset

    def get_range(self) -> tuple[int, int]:
        """Get the validated scan range"""
        return self._calculate_range()
