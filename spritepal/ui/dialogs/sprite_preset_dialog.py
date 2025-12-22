"""
Sprite preset management dialog for SpritePal.

Provides a UI for managing user-defined sprite presets with CRUD operations,
import/export, and filtering capabilities.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.managers.sprite_preset_manager import SpritePresetManager
from core.types import SpritePreset, WidgetParent
from ui.common.file_dialogs import browse_for_open_file, browse_for_save_file
from ui.components.base import DialogBase

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ConfigurationServiceProtocol

logger = logging.getLogger(__name__)


class AddEditPresetDialog(DialogBase):
    """Dialog for adding or editing a sprite preset."""

    def __init__(
        self,
        parent: QWidget | None = None,
        preset: SpritePreset | None = None,
        game_title: str = "",
    ) -> None:
        # Instance variables BEFORE super().__init__() - DialogBase pattern
        self._preset = preset
        self._game_title = game_title

        # Widget references (set in _setup_ui)
        self.name_edit: QLineEdit | None = None
        self.game_title_edit: QLineEdit | None = None
        self.offset_spin: QSpinBox | None = None
        self.size_spin: QSpinBox | None = None
        self.compressed_check: QCheckBox | None = None
        self.description_edit: QTextEdit | None = None
        self.tags_edit: QLineEdit | None = None
        self.checksums_edit: QLineEdit | None = None

        super().__init__(
            parent=parent,
            title="Add Preset" if not preset else "Edit Preset",
            modal=True,
            min_size=(400, None),
            with_button_box=True,
        )

        # Load preset data after UI is set up
        if preset:
            self._load_preset(preset)

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout()

        # Form layout for fields
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Kirby Main Sprites")
        form.addRow("Name:", self.name_edit)

        self.game_title_edit = QLineEdit()
        self.game_title_edit.setPlaceholderText("e.g., KIRBY SUPER STAR")
        if self._game_title:
            self.game_title_edit.setText(self._game_title)
        form.addRow("Game Title:", self.game_title_edit)

        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 0xFFFFFF)
        self.offset_spin.setPrefix("0x")
        self.offset_spin.setDisplayIntegerBase(16)
        form.addRow("Offset:", self.offset_spin)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(32, 65536)
        self.size_spin.setValue(8192)
        self.size_spin.setSingleStep(32)
        form.addRow("Est. Size:", self.size_spin)

        self.compressed_check = QCheckBox("Compressed (HAL)")
        self.compressed_check.setChecked(True)
        form.addRow("", self.compressed_check)

        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(60)
        self.description_edit.setPlaceholderText("Optional description...")
        form.addRow("Description:", self.description_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("character, enemy, boss (comma-separated)")
        form.addRow("Tags:", self.tags_edit)

        self.checksums_edit = QLineEdit()
        self.checksums_edit.setPlaceholderText("0x8A5C, 0x7F4C (comma-separated)")
        form.addRow("Checksums:", self.checksums_edit)

        layout.addLayout(form)

        # Set content layout (DialogBase provides button_box automatically)
        self.set_content_layout(layout)

        # Rename Ok button to "Save"
        if self.button_box:
            from PySide6.QtWidgets import QDialogButtonBox
            ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button:
                ok_button.setText("Save")

    def _load_preset(self, preset: SpritePreset) -> None:
        """Load preset data into form fields."""
        # Widgets are guaranteed to be initialized after _setup_ui
        assert self.name_edit is not None
        assert self.game_title_edit is not None
        assert self.offset_spin is not None
        assert self.size_spin is not None
        assert self.compressed_check is not None
        assert self.description_edit is not None
        assert self.tags_edit is not None
        assert self.checksums_edit is not None

        self.name_edit.setText(preset.name)
        self.game_title_edit.setText(preset.game_title)
        self.offset_spin.setValue(preset.offset)
        self.size_spin.setValue(preset.estimated_size)
        self.compressed_check.setChecked(preset.compressed)
        self.description_edit.setText(preset.description)
        self.tags_edit.setText(", ".join(preset.tags))
        checksums_str = ", ".join(f"0x{c:04X}" for c in preset.game_checksums)
        self.checksums_edit.setText(checksums_str)

    @override
    def accept(self) -> None:
        """Validate inputs and accept dialog."""
        if self.name_edit is None or self.game_title_edit is None:
            super().accept()
            return

        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Name is required.")
            return

        game_title = self.game_title_edit.text().strip()
        if not game_title:
            QMessageBox.warning(self, "Validation Error", "Game title is required.")
            return

        super().accept()

    def get_preset(self) -> SpritePreset:
        """Get the preset data from the form."""
        # Widgets are guaranteed to be initialized after _setup_ui
        assert self.name_edit is not None
        assert self.game_title_edit is not None
        assert self.offset_spin is not None
        assert self.size_spin is not None
        assert self.compressed_check is not None
        assert self.description_edit is not None
        assert self.tags_edit is not None
        assert self.checksums_edit is not None

        name = self.name_edit.text().strip()
        game_title = self.game_title_edit.text().strip()
        offset = self.offset_spin.value()
        estimated_size = self.size_spin.value()
        compressed = self.compressed_check.isChecked()
        description = self.description_edit.toPlainText().strip()

        # Parse tags
        tags_text = self.tags_edit.text().strip()
        tags = [t.strip() for t in tags_text.split(",") if t.strip()]

        # Parse checksums
        checksums: list[int] = []
        checksums_text = self.checksums_edit.text().strip()
        if checksums_text:
            for part in checksums_text.split(","):
                part = part.strip()
                try:
                    if part.startswith("0x") or part.startswith("0X"):
                        checksums.append(int(part, 16))
                    else:
                        checksums.append(int(part))
                except ValueError:
                    pass

        source = self._preset.source if self._preset else "user"
        verified = self._preset.verified if self._preset else False

        return SpritePreset(
            name=name,
            offset=offset,
            game_title=game_title,
            game_checksums=checksums,
            description=description,
            compressed=compressed,
            estimated_size=estimated_size,
            tags=tags,
            source=source,
            verified=verified,
        )


class SpritePresetDialog(DialogBase):
    """Dialog for managing sprite presets."""

    # Signals
    preset_selected = Signal(object)  # SpritePreset
    presets_changed = Signal()

    def __init__(
        self,
        parent: WidgetParent = None,
        *,
        config_service: ConfigurationServiceProtocol | None = None,
        current_game_title: str = "",
        current_checksum: int | None = None,
    ) -> None:
        # Initialize preset manager
        self._preset_manager = SpritePresetManager(config_service=config_service)
        self._current_game_title = current_game_title
        self._current_checksum = current_checksum

        super().__init__(
            parent=parent,
            title="Manage Sprite Presets",
            modal=True,
            size=(700, 500),
            min_size=(500, 400),
            with_status_bar=True,
            with_button_box=True,
        )

        self._connect_signals()
        self._refresh_preset_list()

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog content."""
        layout = QHBoxLayout(self.content_widget)

        # Left panel - preset list with filter
        left_panel = QVBoxLayout()

        # Filter controls
        filter_group = QGroupBox("Filter")
        filter_layout = QVBoxLayout()

        filter_row = QHBoxLayout()
        filter_row.addWidget(QWidget())  # Spacer

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Presets", "all")
        self.filter_combo.addItem("Current Game", "game")
        self.filter_combo.addItem("Matching ROM", "checksum")
        self.filter_combo.addItem("User Created", "user")
        self.filter_combo.addItem("Imported", "imported")
        filter_layout.addWidget(self.filter_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name...")
        filter_layout.addWidget(self.search_edit)

        filter_group.setLayout(filter_layout)
        left_panel.addWidget(filter_group)

        # Preset list
        self.preset_list = QListWidget()
        left_panel.addWidget(self.preset_list, 1)

        layout.addLayout(left_panel)

        # Right panel - actions and details
        right_panel = QVBoxLayout()

        # Actions group
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()

        self.add_btn = QPushButton("Add Preset...")
        actions_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit...")
        self.edit_btn.setEnabled(False)
        actions_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        actions_layout.addWidget(self.delete_btn)

        actions_layout.addSpacing(10)

        self.use_btn = QPushButton("Use Selected")
        self.use_btn.setEnabled(False)
        actions_layout.addWidget(self.use_btn)

        actions_group.setLayout(actions_layout)
        right_panel.addWidget(actions_group)

        # Import/Export group
        io_group = QGroupBox("Import / Export")
        io_layout = QVBoxLayout()

        self.import_btn = QPushButton("Import Presets...")
        io_layout.addWidget(self.import_btn)

        self.export_btn = QPushButton("Export All...")
        io_layout.addWidget(self.export_btn)

        self.export_selected_btn = QPushButton("Export Selected...")
        self.export_selected_btn.setEnabled(False)
        io_layout.addWidget(self.export_selected_btn)

        io_group.setLayout(io_layout)
        right_panel.addWidget(io_group)

        # Details group
        details_group = QGroupBox("Preset Details")
        self.details_label = QTextEdit()
        self.details_label.setReadOnly(True)
        self.details_label.setMaximumHeight(150)
        details_layout = QVBoxLayout()
        details_layout.addWidget(self.details_label)
        details_group.setLayout(details_layout)
        right_panel.addWidget(details_group)

        right_panel.addStretch()

        layout.addLayout(right_panel)

    def _connect_signals(self) -> None:
        """Connect UI signals."""
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.preset_list.currentItemChanged.connect(self._on_selection_changed)
        self.preset_list.itemDoubleClicked.connect(self._on_use_preset)

        self.add_btn.clicked.connect(self._on_add_preset)
        self.edit_btn.clicked.connect(self._on_edit_preset)
        self.delete_btn.clicked.connect(self._on_delete_preset)
        self.use_btn.clicked.connect(self._on_use_preset)

        self.import_btn.clicked.connect(self._on_import)
        self.export_btn.clicked.connect(self._on_export_all)
        self.export_selected_btn.clicked.connect(self._on_export_selected)

    def _refresh_preset_list(self) -> None:
        """Refresh the preset list based on current filter."""
        self.preset_list.clear()

        filter_mode = self.filter_combo.currentData()
        search_text = self.search_edit.text().strip().lower()

        presets = self._preset_manager.get_all_presets()

        # Apply filter
        if filter_mode == "game" and self._current_game_title:
            presets = [
                p for p in presets
                if p.game_title.upper() == self._current_game_title.upper()
            ]
        elif filter_mode == "checksum" and self._current_checksum is not None:
            presets = [
                p for p in presets
                if self._current_checksum in p.game_checksums
            ]
        elif filter_mode == "user":
            presets = [p for p in presets if p.source == "user"]
        elif filter_mode == "imported":
            presets = [p for p in presets if p.source == "imported"]

        # Apply search
        if search_text:
            presets = [
                p for p in presets
                if search_text in p.name.lower()
                or search_text in p.game_title.lower()
                or any(search_text in t.lower() for t in p.tags)
            ]

        # Sort by game title, then name
        presets.sort(key=lambda p: (p.game_title.upper(), p.name.upper()))

        # Populate list
        for preset in presets:
            item = QListWidgetItem(f"{preset.name} ({preset.game_title})")
            item.setData(Qt.ItemDataRole.UserRole, preset)
            self.preset_list.addItem(item)

        self._update_status()

    def _on_filter_changed(self) -> None:
        """Handle filter combo change."""
        self._refresh_preset_list()

    def _on_search_changed(self) -> None:
        """Handle search text change."""
        self._refresh_preset_list()

    def _on_selection_changed(self) -> None:
        """Handle preset selection change."""
        # currentItem() returns None when no item is selected (stub incorrectly says non-None)
        item = cast("QListWidgetItem | None", self.preset_list.currentItem())
        has_selection = item is not None

        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.use_btn.setEnabled(has_selection)
        self.export_selected_btn.setEnabled(has_selection)

        if item is not None:
            preset: SpritePreset = item.data(Qt.ItemDataRole.UserRole)
            self._show_preset_details(preset)
        else:
            self.details_label.clear()

    def _show_preset_details(self, preset: SpritePreset) -> None:
        """Display preset details."""
        details = f"""<b>{preset.name}</b><br>
Game: {preset.game_title}<br>
Offset: 0x{preset.offset:06X}<br>
Size: {preset.estimated_size} bytes<br>
Compressed: {"Yes" if preset.compressed else "No"}<br>
Source: {preset.source}<br>
"""
        if preset.description:
            details += f"<br>{preset.description}<br>"
        if preset.tags:
            details += f"<br>Tags: {', '.join(preset.tags)}"
        if preset.game_checksums:
            checksums = ", ".join(f"0x{c:04X}" for c in preset.game_checksums)
            details += f"<br>Checksums: {checksums}"

        self.details_label.setHtml(details)

    def _on_add_preset(self) -> None:
        """Add a new preset."""
        dialog = AddEditPresetDialog(
            self, game_title=self._current_game_title
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            preset = dialog.get_preset()
            if self._preset_manager.add_preset(preset):
                self._refresh_preset_list()
                self.presets_changed.emit()
                self.update_status(f"Added preset: {preset.name}")
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"A preset named '{preset.name}' already exists.",
                )

    def _on_edit_preset(self) -> None:
        """Edit the selected preset."""
        item = self.preset_list.currentItem()
        if not item:
            return

        preset: SpritePreset = item.data(Qt.ItemDataRole.UserRole)
        dialog = AddEditPresetDialog(self, preset=preset)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_preset = dialog.get_preset()
            if self._preset_manager.update_preset(updated_preset):
                self._refresh_preset_list()
                self.presets_changed.emit()
                self.update_status(f"Updated preset: {updated_preset.name}")

    def _on_delete_preset(self) -> None:
        """Delete the selected preset."""
        item = self.preset_list.currentItem()
        if not item:
            return

        preset: SpritePreset = item.data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete preset '{preset.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self._preset_manager.remove_preset(preset.name):
                self._refresh_preset_list()
                self.presets_changed.emit()
                self.update_status(f"Deleted preset: {preset.name}")

    def _on_use_preset(self) -> None:
        """Use the selected preset."""
        item = self.preset_list.currentItem()
        if not item:
            return

        preset: SpritePreset = item.data(Qt.ItemDataRole.UserRole)
        self.preset_selected.emit(preset)
        self.accept()

    def _on_import(self) -> None:
        """Import presets from file."""
        path = browse_for_open_file(
            self,
            title="Import Sprite Presets",
            file_filter="SpritePal Presets (*.spritepal-presets.json);;All Files (*)",
        )

        if path:
            count = self._preset_manager.import_presets(Path(path))
            if count > 0:
                self._refresh_preset_list()
                self.presets_changed.emit()
                self.update_status(f"Imported {count} presets")
            else:
                QMessageBox.warning(
                    self, "Import Failed", "No presets were imported."
                )

    def _on_export_all(self) -> None:
        """Export all presets to file."""
        path = browse_for_save_file(
            self,
            title="Export All Presets",
            file_filter="SpritePal Presets (*.spritepal-presets.json)",
        )

        if path:
            if not path.endswith(".spritepal-presets.json"):
                path += ".spritepal-presets.json"
            count = self._preset_manager.export_presets(Path(path))
            if count > 0:
                self.update_status(f"Exported {count} presets to {path}")
            else:
                QMessageBox.warning(
                    self, "Export Failed", "No presets were exported."
                )

    def _on_export_selected(self) -> None:
        """Export selected preset to file."""
        item = self.preset_list.currentItem()
        if not item:
            return

        preset: SpritePreset = item.data(Qt.ItemDataRole.UserRole)

        path = browse_for_save_file(
            self,
            title="Export Preset",
            file_filter="SpritePal Presets (*.spritepal-presets.json)",
        )

        if path:
            if not path.endswith(".spritepal-presets.json"):
                path += ".spritepal-presets.json"
            count = self._preset_manager.export_presets(
                Path(path), preset_names=[preset.name]
            )
            if count > 0:
                self.update_status(f"Exported preset: {preset.name}")

    def _update_status(self) -> None:
        """Update status bar with count."""
        count = self.preset_list.count()
        total = self._preset_manager.get_preset_count()
        if count == total:
            self.update_status(f"{count} preset(s)")
        else:
            self.update_status(f"Showing {count} of {total} preset(s)")

    def get_preset_manager(self) -> SpritePresetManager:
        """Get the preset manager instance."""
        return self._preset_manager
