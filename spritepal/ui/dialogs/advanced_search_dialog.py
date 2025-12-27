"""
Advanced search dialog for sophisticated sprite searching.

Provides multiple search modes, filters, history, and visual search capabilities.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, override

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.app_context import get_app_context
from core.parallel_sprite_finder import SearchResult
from core.services.preview_generator import PreviewRequest
from core.visual_similarity_search import SimilarityMatch
from ui.common import WorkerManager
from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.file_dialogs import FileDialogHelper
from ui.common.spacing_constants import ADVANCED_SEARCH_MIN_SIZE, INDENT_UNDER_CONTROL
from ui.components.filters import SearchFiltersWidget
from ui.components.filters.search_filters_widget import SearchFilter
from ui.constants.help_text import TOOLTIPS
from ui.dialogs.similarity_results_dialog import show_similarity_results
from ui.styles.theme import COLORS
from ui.workers.advanced_search_worker import AdvancedSearchWorker
from utils.constants import MAX_SPRITE_SIZE

logger = logging.getLogger(__name__)

# SearchFilter is imported from ui.components.filters.search_filters_widget


class SearchTab(IntEnum):
    """Tab indices for the search dialog.

    IMPORTANT: Must match the order in which tabs are added in _setup_ui().
    If you reorder tabs, update these values accordingly.
    """

    PARALLEL = 0  # Parallel search tab
    VISUAL = 1  # Visual similarity search tab
    PATTERN = 2  # Pattern-based search tab
    HISTORY = 3  # Search history tab (not a search mode)


@dataclass
class SearchHistoryEntry:
    """Entry in search history."""

    timestamp: datetime
    search_type: str
    query: str
    filters: SearchFilter
    results_count: int

    def to_display_string(self) -> str:
        """Format for display in history list."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] {self.search_type}: {self.query} ({self.results_count} results)"


# SearchWorker moved to ui/workers/advanced_search_worker.py
# Alias for backwards compatibility
SearchWorker = AdvancedSearchWorker


class AdvancedSearchDialog(QDialog):
    """
    Advanced search dialog with multiple search modes and filters.

    Features:
    - Parallel search with progress
    - Visual similarity search
    - Pattern-based search
    - Search history
    - Advanced filters
    - Keyboard shortcuts
    """

    # Signals
    sprite_selected = Signal(int)  # Offset of selected sprite
    search_started = Signal()
    search_completed = Signal(int)  # Number of results

    def __init__(self, rom_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rom_path = rom_path
        self.search_history = []
        self.current_results = []
        self.search_worker = None

        self._setup_ui()
        self._setup_shortcuts()
        self._load_history()

    def _setup_ui(self) -> None:
        """Setup the user interface."""
        self.setWindowTitle("Advanced Sprite Search")
        self.setMinimumSize(*ADVANCED_SEARCH_MIN_SIZE)

        layout = QVBoxLayout(self)

        # Create tab widget
        self.tabs = QTabWidget()

        # Add search tabs
        self.tabs.addTab(self._create_parallel_search_tab(), "Parallel Search")
        self.tabs.addTab(self._create_visual_search_tab(), "Visual Search")
        self.tabs.addTab(self._create_pattern_search_tab(), "Pattern Search")
        self.tabs.addTab(self._create_history_tab(), "History")

        layout.addWidget(self.tabs)

        # Results section
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout()

        # Results info
        self.results_label = QLabel("No search performed")
        results_layout.addWidget(self.results_label)

        # Results list
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._on_result_selected)
        results_layout.addWidget(self.results_list)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        results_layout.addWidget(self.progress_bar)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._start_search)
        buttons.addButton(self.search_button, QDialogButtonBox.ButtonRole.ActionRole)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_search)
        if self.stop_button:
            self.stop_button.setEnabled(False)
        buttons.addButton(self.stop_button, QDialogButtonBox.ButtonRole.ActionRole)

        layout.addWidget(buttons)

    def _create_parallel_search_tab(self) -> QWidget:
        """Create parallel search tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Search range
        range_group = QGroupBox("Search Range")
        range_layout = QGridLayout()

        # Start offset
        self.start_offset_edit = QLineEdit("0x0")
        self.start_offset_edit.setToolTip(TOOLTIPS["start_offset"])
        range_layout.addWidget(QLabel("Start Offset:"), 0, 0)
        range_layout.addWidget(self.start_offset_edit, 0, 1)

        # End offset
        self.end_offset_edit = QLineEdit("")
        self.end_offset_edit.setPlaceholderText("End of ROM")
        self.end_offset_edit.setToolTip(TOOLTIPS["end_offset"])
        range_layout.addWidget(QLabel("End Offset:"), 1, 0)
        range_layout.addWidget(self.end_offset_edit, 1, 1)

        # Step size
        self.step_size_spin = QSpinBox()
        self.step_size_spin.setRange(0x10, 0x1000)
        self.step_size_spin.setValue(0x100)
        self.step_size_spin.setSingleStep(0x10)
        self.step_size_spin.setPrefix("0x")
        self.step_size_spin.setDisplayIntegerBase(16)
        self.step_size_spin.setToolTip(TOOLTIPS["step_size"])
        range_layout.addWidget(QLabel("Step Size:"), 2, 0)
        range_layout.addWidget(self.step_size_spin, 2, 1)

        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        # Performance settings - collapsible, collapsed by default
        perf_group = CollapsibleGroupBox("Performance", collapsed=True)
        perf_layout = QGridLayout()

        # Worker threads
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(4)
        self.workers_spin.setToolTip(TOOLTIPS["worker_threads"])
        perf_layout.addWidget(QLabel("Worker Threads:"), 0, 0)
        perf_layout.addWidget(self.workers_spin, 0, 1)

        # Adaptive stepping
        self.adaptive_check = QCheckBox("Adaptive Step Sizing")
        self.adaptive_check.setChecked(True)
        self.adaptive_check.setToolTip(TOOLTIPS["adaptive_stepping"])
        perf_layout.addWidget(self.adaptive_check, 1, 0, 1, 2)

        perf_group.setContentLayout(perf_layout)
        layout.addWidget(perf_group)

        # Filters - use shared SearchFiltersWidget
        self.filters_widget = SearchFiltersWidget(collapsible=True, expanded=True)
        layout.addWidget(self.filters_widget)

        layout.addStretch()
        return widget

    def _create_visual_search_tab(self) -> QWidget:
        """Create visual search tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Reference source selection
        ref_group = QGroupBox("Reference Selection")
        ref_layout = QVBoxLayout()

        # Mode selection radio buttons
        self.ref_mode_offset_radio = QRadioButton("Use ROM Sprite Offset")
        self.ref_mode_offset_radio.setChecked(True)
        self.ref_mode_offset_radio.toggled.connect(self._on_ref_mode_changed)
        ref_layout.addWidget(self.ref_mode_offset_radio)

        # ROM offset selection row
        offset_layout = QHBoxLayout()
        offset_layout.setContentsMargins(INDENT_UNDER_CONTROL, 0, 0, 0)  # Indent under radio
        self.ref_offset_edit = QLineEdit()
        self.ref_offset_edit.setPlaceholderText("Sprite offset (e.g. 0x12345)")
        self.ref_offset_edit.setToolTip(TOOLTIPS["offset"])
        self.ref_offset_edit.textChanged.connect(self._on_reference_offset_changed)
        offset_layout.addWidget(self.ref_offset_edit)

        self.ref_browse_button = QPushButton("Browse ROM...")
        self.ref_browse_button.clicked.connect(self._browse_reference_sprite)
        offset_layout.addWidget(self.ref_browse_button)
        ref_layout.addLayout(offset_layout)

        # Image file mode
        self.ref_mode_image_radio = QRadioButton("Use Image File")
        self.ref_mode_image_radio.toggled.connect(self._on_ref_mode_changed)
        ref_layout.addWidget(self.ref_mode_image_radio)

        # Image file selection row
        image_layout = QHBoxLayout()
        image_layout.setContentsMargins(INDENT_UNDER_CONTROL, 0, 0, 0)  # Indent under radio
        self.image_path_edit = QLineEdit()
        self.image_path_edit.setPlaceholderText("Image file path (PNG, BMP, GIF)")
        self.image_path_edit.setToolTip(
            "Upload an image to search for similar sprites.\n"
            "Supported formats: PNG, BMP, GIF, JPEG\n"
            "Recommended size: 8x8 to 256x256 pixels"
        )
        self.image_path_edit.setEnabled(False)  # Disabled until image mode selected
        self.image_path_edit.textChanged.connect(self._on_image_path_changed)
        image_layout.addWidget(self.image_path_edit)

        self.image_browse_button = QPushButton("Browse...")
        self.image_browse_button.setEnabled(False)
        self.image_browse_button.clicked.connect(self._browse_image_file)
        image_layout.addWidget(self.image_browse_button)
        ref_layout.addLayout(image_layout)

        # Reference preview
        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("margin-top: 8px;")
        ref_layout.addWidget(preview_label)

        self.ref_preview_label = QLabel("No reference selected")
        self.ref_preview_label.setMinimumHeight(128)
        self.ref_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ref_preview_label.setStyleSheet(
            f"border: 1px solid {COLORS['border']}; background-color: {COLORS['background']};"
        )
        ref_layout.addWidget(self.ref_preview_label)

        ref_group.setLayout(ref_layout)
        layout.addWidget(ref_group)

        # Similarity settings
        sim_group = QGroupBox("Similarity Settings")
        sim_layout = QGridLayout()

        # Similarity threshold
        self.similarity_slider = QSlider(Qt.Orientation.Horizontal)
        self.similarity_slider.setRange(0, 100)
        self.similarity_slider.setValue(80)
        self.similarity_slider.setToolTip(TOOLTIPS["similarity_threshold"])
        self.similarity_label = QLabel("80%")
        self.similarity_slider.valueChanged.connect(self._update_similarity_label)

        sim_layout.addWidget(QLabel("Similarity Threshold:"), 0, 0)
        sim_layout.addWidget(self.similarity_slider, 0, 1)
        sim_layout.addWidget(self.similarity_label, 0, 2)

        # Search scope
        self.visual_scope_combo = QComboBox()
        self.visual_scope_combo.addItems(["Current ROM", "All Indexed Sprites", "Selected Region"])
        self.visual_scope_combo.setToolTip(TOOLTIPS["search_scope"])
        sim_layout.addWidget(QLabel("Search Scope:"), 1, 0)
        sim_layout.addWidget(self.visual_scope_combo, 1, 1, 1, 2)

        sim_group.setLayout(sim_layout)
        layout.addWidget(sim_group)

        # Store uploaded image
        self._uploaded_image: Image.Image | None = None

        layout.addStretch()
        return widget

    def _create_pattern_search_tab(self) -> QWidget:
        """Create pattern search tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Pattern input
        pattern_group = QGroupBox("Search Pattern")
        pattern_layout = QVBoxLayout()

        # Pattern type
        type_layout = QHBoxLayout()
        self.hex_radio = QRadioButton("Hex Pattern")
        if self.hex_radio:
            self.hex_radio.setChecked(True)
        self.regex_radio = QRadioButton("Regular Expression")
        type_layout.addWidget(self.hex_radio)
        type_layout.addWidget(self.regex_radio)
        type_layout.addStretch()
        pattern_layout.addLayout(type_layout)

        # Pattern input
        self.pattern_edit = QTextEdit()
        self.pattern_edit.setMaximumHeight(100)
        self.pattern_edit.setPlaceholderText("Enter hex pattern (e.g. '00 01 02 ?? ?? FF') or regex")
        pattern_layout.addWidget(self.pattern_edit)

        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)

        # Pattern options
        options_group = QGroupBox("Search Options")
        options_layout = QGridLayout()

        # Pattern-specific options
        self.case_sensitive_check = QCheckBox("Case Sensitive (Regex)")
        self.whole_word_check = QCheckBox("Whole Word Only")
        self.pattern_aligned_check = QCheckBox("Alignment Required (16-byte)")

        options_layout.addWidget(self.case_sensitive_check, 0, 0)
        options_layout.addWidget(self.whole_word_check, 0, 1)
        options_layout.addWidget(self.pattern_aligned_check, 1, 0, 1, 2)

        # Context size
        options_layout.addWidget(QLabel("Context Size:"), 2, 0)
        self.context_size_spin = QSpinBox()
        self.context_size_spin.setRange(0, 256)
        self.context_size_spin.setValue(32)
        self.context_size_spin.setSuffix(" bytes")
        self.context_size_spin.setToolTip("Number of bytes to show around each match")
        options_layout.addWidget(self.context_size_spin, 2, 1)

        # Maximum results
        options_layout.addWidget(QLabel("Max Results:"), 3, 0)
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 10000)
        self.max_results_spin.setValue(1000)
        self.max_results_spin.setToolTip("Maximum number of matches to find")
        options_layout.addWidget(self.max_results_spin, 3, 1)

        # Multiple pattern operation
        options_layout.addWidget(QLabel("Multiple Patterns:"), 4, 0)
        self.pattern_operation_combo = QComboBox()
        self.pattern_operation_combo.addItems(["Single Pattern", "OR (any match)", "AND (all match)"])
        self.pattern_operation_combo.setToolTip("How to handle multiple patterns (one per line)")
        options_layout.addWidget(self.pattern_operation_combo, 4, 1)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Pattern examples (collapsible - hidden by default to reduce clutter)
        examples_group = CollapsibleGroupBox("Pattern Examples", collapsed=True)

        examples_text = (
            "Hex Pattern Examples:\n"
            "• 00 01 02 FF - Exact bytes\n"
            "• 00 ?? ?? FF - Wildcards (any byte)\n"
            "• 10 20 ?? ?? 30 - Mixed exact and wildcards\n\n"
            "Regex Pattern Examples:\n"
            "• SNES - Find ASCII text 'SNES'\n"
            "• [A-Z]{4} - Four uppercase letters\n"
            "• \\x00\\x01.{2}\\xFF - Bytes with any 2-byte gap\n\n"
            "Multiple Patterns (one per line):\n"
            "• OR: Find any matching pattern\n"
            "• AND: Find locations with all patterns nearby"
        )

        examples_label = QLabel(examples_text)
        examples_label.setWordWrap(True)
        examples_label.setStyleSheet(f"QLabel {{ font-size: 9pt; color: {COLORS['text_muted']}; }}")
        examples_group.add_widget(examples_label)

        layout.addWidget(examples_group)

        layout.addStretch()
        return widget

    def _create_history_tab(self) -> QWidget:
        """Create search history tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # History list
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)

        # History actions
        actions_layout = QHBoxLayout()

        self.clear_history_button = QPushButton("Clear History")
        self.clear_history_button.clicked.connect(self._clear_history)
        actions_layout.addWidget(self.clear_history_button)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        return widget

    # NOTE: _create_filters_group has been replaced by SearchFiltersWidget

    def _update_similarity_label(self, value: int):
        """Update similarity label text."""
        if self.similarity_label:
            self.similarity_label.setText(f"{value}%")

    def _focus_search(self):
        """Focus the search input field."""
        self.start_offset_edit.setFocus()

    def _show_history_tab(self):
        """Show the history tab."""
        if self.tabs:
            self.tabs.setCurrentIndex(3)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+F - Focus search
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)

        # Ctrl+Enter - Start search
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._start_search)

        # Escape - Stop search
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._stop_search)

        # Ctrl+H - Show history
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._show_history_tab)

    def _start_search(self):
        """Start the search based on current tab."""
        if self.search_worker is not None and self.search_worker.isRunning():
            return

        current_tab = self.tabs.currentIndex()

        if current_tab == SearchTab.PARALLEL:
            self._start_parallel_search()
        elif current_tab == SearchTab.VISUAL:
            self._start_visual_search()
        elif current_tab == SearchTab.PATTERN:
            self._start_pattern_search()
        # SearchTab.HISTORY doesn't trigger a search

    def _start_parallel_search(self):
        """Start parallel search."""
        # Get parameters
        start_text = self.start_offset_edit.text()
        end_text = self.end_offset_edit.text()

        start = self._parse_hex_offset(start_text) if start_text else 0
        end = self._parse_hex_offset(end_text) if end_text else None

        # Check for invalid offset format
        if start_text and start is None:
            if self.results_label:
                self.results_label.setText("Invalid start offset format")
            return
        if end_text and end is None:
            if self.results_label:
                self.results_label.setText("Invalid end offset format")
            return

        # Ensure start has a value (0 if empty)
        start = start if start is not None else 0

        # Get filters from widget
        filters = self.filters_widget.get_filters()

        # Create worker
        params = {
            "rom_path": self.rom_path,
            "start_offset": start,
            "end_offset": end,
            "num_workers": self.workers_spin.value(),
            "step_size": self.step_size_spin.value(),
            "filters": filters,
        }

        self.search_worker = SearchWorker("parallel", params)
        self._connect_worker_signals()

        # Update UI
        if self.search_button:
            self.search_button.setEnabled(False)
        if self.stop_button:
            self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        if self.results_list:
            self.results_list.clear()
        self.current_results = []
        if self.results_label:
            self.results_label.setText("Searching...")

        # Add to history
        entry = SearchHistoryEntry(
            timestamp=datetime.now(UTC),
            search_type="Parallel",
            query=f"0x{start:X} - {f'0x{end:X}' if end else 'EOF'}",
            filters=filters,
            results_count=0,
        )
        self.search_history.append(entry)

        # Start search
        self.search_started.emit()
        self.search_worker.start()

    def _start_visual_search(self):
        """Start visual similarity search."""
        # Check if similarity index exists first
        if not self._check_similarity_index_exists():
            self._offer_to_build_similarity_index()
            return

        # Determine mode: offset or image file
        use_offset_mode = self.ref_mode_offset_radio.isChecked()
        ref_offset: int | None = None
        image_path: str | None = None
        query_description: str

        if use_offset_mode:
            # Get reference sprite offset
            ref_text = self.ref_offset_edit.text().strip()
            if not ref_text:
                if self.results_label:
                    self.results_label.setText("Please specify a reference sprite offset")
                return

            ref_offset = self._parse_hex_offset(ref_text)
            if ref_offset is None:
                if self.results_label:
                    self.results_label.setText("Invalid offset format. Use hex format like 0x12345")
                return

            query_description = f"Similar to 0x{ref_offset:X}"
        else:
            # Get image file
            image_path = self.image_path_edit.text().strip()
            if not image_path or self._uploaded_image is None:
                if self.results_label:
                    self.results_label.setText("Please select an image file")
                return

            query_description = f"Similar to image: {Path(image_path).name}"

        # Get similarity threshold
        similarity_threshold = self.similarity_slider.value()  # Get percentage value

        # Get search scope
        search_scope = self.visual_scope_combo.currentText()

        # Create worker parameters
        params: dict[str, Any] = {  # pyright: ignore[reportExplicitAny] - Dynamic params
            "rom_path": self.rom_path,
            "similarity_threshold": similarity_threshold,
            "search_scope": search_scope,
            "max_results": 50,
        }

        if use_offset_mode:
            params["reference_offset"] = ref_offset
        else:
            params["image_path"] = image_path

        self.search_worker = SearchWorker("visual", params)
        self._connect_worker_signals()

        # Update UI
        if self.search_button:
            self.search_button.setEnabled(False)
        if self.stop_button:
            self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        if self.results_list:
            self.results_list.clear()
        self.current_results = []
        if self.results_label:
            self.results_label.setText("Searching for similar sprites...")

        # Add to history
        entry = SearchHistoryEntry(
            timestamp=datetime.now(UTC),
            search_type="Visual",
            query=f"{query_description} (threshold: {similarity_threshold}%)",
            filters=SearchFilter(
                min_size=0,
                max_size=MAX_SPRITE_SIZE,
                min_tiles=0,
                max_tiles=1024,
                alignment=1,
                include_compressed=True,
                include_uncompressed=True,
                confidence_threshold=self.similarity_slider.value() / 100.0,
            ),
            results_count=0,
        )
        self.search_history.append(entry)

        # Start search
        self.search_started.emit()
        self.search_worker.start()

    def _start_pattern_search(self):
        """Start pattern search with comprehensive options."""
        # Get pattern input
        pattern_text = self.pattern_edit.toPlainText().strip()
        if not pattern_text:
            if self.results_label:
                self.results_label.setText("Please enter a search pattern")
            return

        # Determine pattern type
        pattern_type = "hex" if self.hex_radio.isChecked() else "regex"

        # Parse multiple patterns (one per line)
        patterns = [p.strip() for p in pattern_text.split("\n") if p.strip()]

        # Validate patterns based on type
        if pattern_type == "hex":
            for i, pattern in enumerate(patterns):
                if not self._validate_hex_pattern(pattern):
                    if self.results_label:
                        self.results_label.setText(
                            f"Invalid hex pattern on line {i + 1}: Use format like: 00 01 02 ?? FF"
                        )
                    return
        else:  # regex
            for i, pattern in enumerate(patterns):
                if not self._validate_regex_pattern(pattern):
                    if self.results_label:
                        self.results_label.setText(f"Invalid regex pattern on line {i + 1}")
                    return

        # Get search options
        case_sensitive = self.case_sensitive_check.isChecked()
        alignment = self._get_pattern_alignment()

        # Create search parameters
        params = {
            "rom_path": self.rom_path,
            "patterns": patterns,
            "pattern_type": pattern_type,
            "case_sensitive": case_sensitive,
            "alignment": alignment,
            "context_bytes": self.context_size_spin.value(),
            "max_results": self.max_results_spin.value(),
            "whole_word": self.whole_word_check.isChecked(),
            "operation": self.pattern_operation_combo.currentText(),
        }

        # Create worker
        self.search_worker = SearchWorker("pattern", params)
        self._connect_worker_signals()

        # Update UI
        if self.search_button:
            self.search_button.setEnabled(False)
        if self.stop_button:
            self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        if self.results_list:
            self.results_list.clear()
        self.current_results = []
        if self.results_label:
            self.results_label.setText("Searching for pattern...")

        # Add to history
        entry = SearchHistoryEntry(
            timestamp=datetime.now(UTC),
            search_type=f"Pattern ({'Hex' if pattern_type == 'hex' else 'Regex'})",
            query=pattern_text[:50] + ("..." if len(pattern_text) > 50 else ""),
            filters=SearchFilter(
                min_size=0,
                max_size=0,
                min_tiles=0,
                max_tiles=0,
                alignment=alignment,
                include_compressed=True,
                include_uncompressed=True,
                confidence_threshold=0.0,
            ),
            results_count=0,
        )
        self.search_history.append(entry)

        # Start search
        self.search_started.emit()
        self.search_worker.start()

    def _validate_hex_pattern(self, pattern: str) -> bool:
        """Validate hex pattern format."""
        try:
            # Clean pattern
            pattern = pattern.strip().upper()
            if not pattern:
                return False

            # Split into tokens
            tokens = re.split(r"[\s,]+", pattern)

            for token in tokens:
                if not token:
                    continue

                # Check for wildcard
                if token in ["??", "?"]:
                    continue

                # Check for valid hex byte
                if len(token) != 2 or not all(c in "0123456789ABCDEF" for c in token):
                    return False

            return len(tokens) > 0

        except Exception:
            return False

    def _validate_regex_pattern(self, pattern: str) -> bool:
        """Validate regex pattern."""
        try:
            re.compile(pattern.encode())
            return True
        except re.error:
            return False

    def _get_pattern_alignment(self) -> int:
        """Get alignment requirement for pattern search."""
        if not self.pattern_aligned_check.isChecked():
            return 1

        # Default to 16-byte alignment for pattern searches
        return 16

    def _connect_worker_signals(self):
        """Connect search worker signals."""
        if self.search_worker:
            self.search_worker.result_found.connect(self._add_result)
            self.search_worker.search_complete.connect(self._search_complete)
            self.search_worker.error.connect(self._search_error)

    def _disconnect_worker_signals(self) -> None:
        """Disconnect search worker signals before cleanup."""
        if self.search_worker:
            from contextlib import suppress

            with suppress(RuntimeError, TypeError):
                self.search_worker.result_found.disconnect(self._add_result)
                self.search_worker.search_complete.disconnect(self._search_complete)
                self.search_worker.error.disconnect(self._search_error)

    def _add_result(self, result: SearchResult):
        """Add result to list with enhanced pattern search support."""
        self.current_results.append(result)

        # Create display text based on result type
        metadata: Any = result.metadata  # pyright: ignore[reportExplicitAny] - SearchResult.metadata is dict[str, Any] at runtime
        if metadata.get("pattern_type") in ["hex", "regex"]:
            # Pattern search result
            pattern_type = str(metadata["pattern_type"]).upper()
            pattern_str = str(metadata.get("pattern", ""))
            pattern = pattern_str[:30] + ("..." if len(pattern_str) > 30 else "")
            match_data_str = str(metadata.get("match_data", ""))
            match_data = match_data_str[:20] + ("..." if len(match_data_str) > 20 else "")

            display_text = (
                f"0x{result.offset:08X} - {pattern_type} Pattern: {pattern} "
                f"(Match: {match_data}, Size: {result.size} bytes)"
            )

            # Add context information for tooltip
            context_data = str(metadata.get("context_data", ""))
            if context_data:
                context_preview = context_data[:32] + ("..." if len(context_data) > 32 else "")
                tooltip_text = (
                    f"Pattern: {metadata.get('pattern', '')}\n"
                    f"Match at: 0x{result.offset:08X}\n"
                    f"Size: {result.size} bytes\n"
                    f"Context: {context_preview}"
                )
                match_text = metadata.get("match_text")
                if match_text:
                    tooltip_text += f"\nText: {str(match_text)[:50]}"
            else:
                tooltip_text = f"Pattern match at 0x{result.offset:08X}"
        else:
            # Regular sprite search result
            display_text = (
                f"0x{result.offset:08X} - "
                f"Size: {result.size:,} bytes, "
                f"Tiles: {result.tile_count}, "
                f"Confidence: {result.confidence:.0%}"
            )
            tooltip_text = f"Sprite at 0x{result.offset:08X}"

        # Create list item
        item = QListWidgetItem(display_text)
        item.setData(Qt.ItemDataRole.UserRole, result)
        item.setToolTip(tooltip_text)
        if self.results_list:
            self.results_list.addItem(item)

        # Update count with appropriate label
        result_type = "patterns" if metadata.get("pattern_type") else "sprites"
        if self.results_label:
            self.results_label.setText(f"Found {len(self.current_results)} {result_type}")

    def _search_complete(self, results: list[Any]):  # pyright: ignore[reportExplicitAny] - SearchResult list from worker
        """Handle search completion."""
        if self.search_button:
            self.search_button.setEnabled(True)
        if self.stop_button:
            self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)

        # Update history
        if self.search_history:
            self.search_history[-1].results_count = len(results)
            self._update_history_display()

        # For visual search, show similarity results dialog
        if self.search_worker is not None and self.search_worker.search_type == "visual" and results:
            self._show_visual_search_results(results)

        # Update results
        if self.results_label:
            self.results_label.setText(f"Search complete: {len(results)} sprites found")
        self.search_completed.emit(len(results))

    def _search_error(self, error_msg: str):
        """Handle search error."""
        if self.search_button:
            self.search_button.setEnabled(True)
        if self.stop_button:
            self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)

        if self.results_label:
            self.results_label.setText(f"Search error: {error_msg}")
        logger.error(f"Search error: {error_msg}")

    def _stop_search(self):
        """Stop current search."""
        if self.search_worker is not None and self.search_worker.isRunning():
            self.search_worker.cancel()
            if self.results_label:
                self.results_label.setText("Search cancelled")

    def _on_result_selected(self, item: QListWidgetItem):
        """Handle result selection."""
        result = item.data(Qt.ItemDataRole.UserRole)
        if result:
            self.sprite_selected.emit(result.offset)

    def _browse_reference_sprite(self):
        """Browse for reference sprite (thread-safe)."""
        # For now, use a simple dialog to input an offset
        # In a full implementation, this could open a sprite browser
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QInputDialog

        # Check if we're in the main thread
        if QThread.currentThread() != self.thread():
            logger.warning("_browse_reference_sprite called from worker thread - operation skipped")
            return

        try:
            offset_text, ok = QInputDialog.getText(
                self, "Reference Sprite Offset", "Enter sprite offset (hex format):", text="0x"
            )

            if ok and offset_text.strip():
                offset = self._parse_hex_offset(offset_text)
                if offset is None:
                    if self.results_label:
                        self.results_label.setText("Invalid offset format")
                    return

                # Set the offset in the edit field
                if self.ref_offset_edit:
                    self.ref_offset_edit.setText(f"0x{offset:X}")

                # Try to generate and show a preview
                self._update_reference_preview(offset)
        except Exception as e:
            logger.exception(f"Error in _browse_reference_sprite: {e}")
            if self.results_label:
                self.results_label.setText(f"Error: {e}")

    def _on_ref_mode_changed(self, checked: bool) -> None:
        """Handle reference mode radio button changes."""
        if not checked:
            return  # Only handle when a button is being selected

        use_offset = self.ref_mode_offset_radio.isChecked()

        # Toggle enabled state of inputs
        self.ref_offset_edit.setEnabled(use_offset)
        self.ref_browse_button.setEnabled(use_offset)
        self.image_path_edit.setEnabled(not use_offset)
        self.image_browse_button.setEnabled(not use_offset)

        # Clear preview when switching modes
        if self.ref_preview_label:
            self.ref_preview_label.setText("No reference selected")
            self.ref_preview_label.setPixmap(QPixmap())

        # Clear stored image when switching to offset mode
        if use_offset:
            self._uploaded_image = None

    def _browse_image_file(self) -> None:
        """Browse for an image file to use as reference."""
        filename = FileDialogHelper.browse_open_file(
            parent=self,
            title="Select Reference Image",
            file_filter="Image Files (*.png *.bmp *.gif *.jpg *.jpeg);;All Files (*.*)",
            settings_key="advanced_search_reference_image",
        )

        if filename:
            self.image_path_edit.setText(filename)

    def _parse_hex_offset(self, text: str) -> int | None:
        """Parse hex offset text, returning None on invalid input.

        Handles both with and without '0x'/'0X' prefix.
        Strips whitespace and handles case-insensitively.
        """
        text = text.strip()
        if not text:
            return None
        if text.lower().startswith(("0x", "0X")):
            text = text[2:]
        try:
            return int(text, 16)
        except ValueError:
            return None

    def _on_image_path_changed(self) -> None:
        """Handle changes to the image path."""
        image_path = self.image_path_edit.text().strip()
        if not image_path:
            if self.ref_preview_label:
                self.ref_preview_label.setText("No image selected")
                self.ref_preview_label.setPixmap(QPixmap())
            self._uploaded_image = None
            return

        self._load_and_validate_image(image_path)

    def _load_and_validate_image(self, path: str) -> bool:
        """Load and validate an image file.

        Args:
            path: Path to the image file

        Returns:
            True if image was loaded successfully
        """
        try:
            # Check if file exists
            image_path = Path(path)
            if not image_path.exists():
                if self.ref_preview_label:
                    self.ref_preview_label.setText("File not found")
                self._uploaded_image = None
                return False

            # Load the image
            image = Image.open(path)

            # Validate dimensions
            width, height = image.size
            if width < 8 or height < 8:
                if self.ref_preview_label:
                    self.ref_preview_label.setText(f"Image too small ({width}x{height}). Minimum: 8x8")
                self._uploaded_image = None
                return False

            # Resize if too large
            max_size = 256
            if width > max_size or height > max_size:
                # Maintain aspect ratio
                if width > height:
                    new_width = max_size
                    new_height = int(height * max_size / width)
                else:
                    new_height = max_size
                    new_width = int(width * max_size / height)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

            # Convert to RGBA for consistent processing
            if image.mode != "RGBA":
                image = image.convert("RGBA")

            # Store the image
            self._uploaded_image = image

            # Show preview
            # Convert PIL image to QPixmap
            from io import BytesIO

            buffer = BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())

            # Scale for display (max 128 pixels)
            if pixmap.width() > 128 or pixmap.height() > 128:
                pixmap = pixmap.scaled(
                    128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )

            if self.ref_preview_label:
                self.ref_preview_label.setPixmap(pixmap)
                self.ref_preview_label.setToolTip(f"Image: {image_path.name}\nSize: {image.size[0]}x{image.size[1]}")

            logger.info(f"Loaded reference image: {path} ({image.size[0]}x{image.size[1]})")
            return True

        except Exception as e:
            logger.exception(f"Error loading image: {e}")
            if self.ref_preview_label:
                self.ref_preview_label.setText(f"Error loading image: {e}")
            self._uploaded_image = None
            return False

    def _on_reference_offset_changed(self):
        """Handle changes to reference offset text."""
        offset_text = self.ref_offset_edit.text().strip()
        if not offset_text:
            if self.ref_preview_label:
                self.ref_preview_label.setText("No reference sprite selected")
                self.ref_preview_label.setPixmap(QPixmap())
            return

        offset = self._parse_hex_offset(offset_text)
        if offset is None:
            if self.ref_preview_label:
                self.ref_preview_label.setText("Invalid offset format")
                self.ref_preview_label.setPixmap(QPixmap())
            return

        # Update preview
        self._update_reference_preview(offset)

    def _update_reference_preview(self, offset: int):
        """Update the reference sprite preview."""
        try:
            # Create a preview request
            request = PreviewRequest(source_type="rom", data_path=self.rom_path, offset=offset, size=(128, 128))

            # Generate preview using the preview service (via AppContext for proper ROM extractor)
            preview_generator = get_app_context().preview_generator
            result = preview_generator.generate_preview(request)

            if result and result.pixmap and not result.pixmap.isNull():
                # Scale preview to fit the label
                scaled_pixmap = result.pixmap.scaled(
                    128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                if self.ref_preview_label:
                    self.ref_preview_label.setPixmap(scaled_pixmap)
                    self.ref_preview_label.setText("")
            elif self.ref_preview_label:
                self.ref_preview_label.setText(f"Could not load sprite at 0x{offset:X}")
                self.ref_preview_label.setPixmap(QPixmap())

        except Exception as e:
            logger.exception(f"Failed to generate reference preview: {e}")
            if self.ref_preview_label:
                self.ref_preview_label.setText(f"Preview error: {str(e)[:50]}...")
                self.ref_preview_label.setPixmap(QPixmap())

    def _show_visual_search_results(self, results: list[Any]):  # pyright: ignore[reportExplicitAny] - SearchResult list from worker
        """Show visual search results in similarity dialog."""
        try:
            # Convert SearchResult objects back to SimilarityMatch for the dialog
            ref_offset_text = self.ref_offset_edit.text().strip()
            ref_offset = self._parse_hex_offset(ref_offset_text)
            if ref_offset is None:
                logger.warning("Could not parse reference offset for results display")
                return

            matches = []
            for result in results:
                # Runtime type is SearchResult, but typed as Any to avoid object issues
                result_typed: Any = result  # pyright: ignore[reportExplicitAny] - worker result list contains SearchResult objects
                metadata = result_typed.metadata if hasattr(result_typed, "metadata") else {}
                match = SimilarityMatch(
                    offset=result_typed.offset,
                    similarity_score=result_typed.confidence,
                    hash_distance=int(metadata.get("hash_distance", 0)) if metadata else 0,
                    metadata=metadata or {},
                )
                matches.append(match)

            # Show similarity results dialog
            dialog = show_similarity_results(matches, ref_offset, self)
            dialog.sprite_selected.connect(self.sprite_selected.emit)
            dialog.exec()

        except Exception as e:
            logger.exception(f"Failed to show visual search results: {e}")
            if self.results_label:
                self.results_label.setText(f"Error displaying results: {e}")

    def _check_similarity_index_exists(self) -> bool:
        """Check if similarity index exists for the current ROM."""
        index_path = Path(self.rom_path).with_suffix(".similarity_index")
        return index_path.exists()

    def _offer_to_build_similarity_index(self):
        """Offer to build similarity index if it doesn't exist (thread-safe)."""
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QMessageBox

        # Check if we're in the main thread
        if QThread.currentThread() != self.thread():
            logger.warning("_offer_to_build_similarity_index called from worker thread - operation skipped")
            return

        try:
            reply = QMessageBox.question(
                self,
                "Build Similarity Index",
                "No similarity index found for this ROM. Visual search requires an index to be built first.\n\n"
                "Building an index will scan the ROM for sprites and create a searchable database. "
                "This may take several minutes but only needs to be done once per ROM.\n\n"
                "Would you like to build the similarity index now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._build_similarity_index()
        except Exception as e:
            logger.exception(f"Error in _offer_to_build_similarity_index: {e}")
            if self.results_label:
                self.results_label.setText(f"Error: {e}")

    def _build_similarity_index(self):
        """Build similarity index for the current ROM (thread-safe)."""
        # This would be implemented to scan the ROM and build the index
        # For now, show a placeholder message
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QMessageBox

        # Check if we're in the main thread
        if QThread.currentThread() != self.thread():
            logger.warning("_build_similarity_index called from worker thread - operation skipped")
            return

        try:
            QMessageBox.information(
                self,
                "Build Index",
                "Index building is not yet implemented. This feature would:\n\n"
                "1. Scan the entire ROM for sprite data\n"
                "2. Extract visual features from each sprite\n"
                "3. Build a searchable similarity index\n"
                "4. Save the index for future searches\n\n"
                "This functionality will be added in a future update.",
            )
        except Exception as e:
            logger.exception(f"Error in _build_similarity_index: {e}")
            if self.results_label:
                self.results_label.setText(f"Error: {e}")

    def _clear_history(self):
        """Clear search history."""
        if self.search_history:
            self.search_history.clear()
        if self.history_list:
            self.history_list.clear()
        self._save_history()

    def _update_history_display(self):
        """Update history list display."""
        if self.history_list:
            self.history_list.clear()
        for entry in reversed(self.search_history[-20:]):  # Show last 20
            item = QListWidgetItem(entry.to_display_string())
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if self.history_list:
                self.history_list.addItem(item)

    def _save_history(self):
        """Save search history to file."""
        history_file = Path.home() / ".spritepal" / "search_history.json"
        history_file.parent.mkdir(exist_ok=True)

        # Convert to serializable format
        data = []
        for entry in self.search_history[-100:]:  # Keep last 100
            data.append(
                {
                    "timestamp": entry.timestamp.isoformat(),
                    "search_type": entry.search_type,
                    "query": entry.query,
                    "results_count": entry.results_count,
                    "filters": {
                        "min_size": entry.filters.min_size,
                        "max_size": entry.filters.max_size,
                        "min_tiles": entry.filters.min_tiles,
                        "max_tiles": entry.filters.max_tiles,
                        "alignment": entry.filters.alignment,
                        "include_compressed": entry.filters.include_compressed,
                        "include_uncompressed": entry.filters.include_uncompressed,
                        "confidence_threshold": entry.filters.confidence_threshold,
                    },
                }
            )

        with Path(history_file).open("w") as f:
            json.dump(data, f, indent=2)

    def _load_history(self):
        """Load search history from file."""
        history_file = Path.home() / ".spritepal" / "search_history.json"
        if not history_file.exists():
            return

        try:
            with Path(history_file).open() as f:
                data = json.load(f)

            for item in data:
                filters = SearchFilter(**item["filters"])
                entry = SearchHistoryEntry(
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    search_type=item["search_type"],
                    query=item["query"],
                    filters=filters,
                    results_count=item["results_count"],
                )
                self.search_history.append(entry)

            self._update_history_display()

        except Exception as e:
            logger.exception(f"Failed to load search history: {e}")

    @override
    def closeEvent(self, event: Any):  # pyright: ignore[reportExplicitAny] - Qt event can be QCloseEvent
        """Handle dialog close event with proper thread cleanup."""
        # Stop any running search worker using safe cleanup (never terminate)
        if self.search_worker and self.search_worker.isRunning():
            logger.debug("Stopping search worker on dialog close")
            # Disconnect signals first to prevent late signal delivery to destroyed dialog
            self._disconnect_worker_signals()
            # Use WorkerManager for safe cleanup - never uses terminate()
            WorkerManager.cleanup_worker_attr(self, "search_worker", timeout=3000)
            logger.debug("Search worker cleanup completed")

        # Save history before closing
        try:
            self._save_history()
        except Exception as e:
            logger.exception(f"Failed to save search history on close: {e}")

        # Accept the close event
        event.accept()
