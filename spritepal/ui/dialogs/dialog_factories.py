from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from core.di_container import inject
from ui.dialogs.manual_offset_unified_integrated import UnifiedManualOffsetDialog

if TYPE_CHECKING:
    from core.protocols.manager_protocols import (
        ExtractionManagerProtocol,
        ROMCacheProtocol,
        ROMExtractorProtocol,
        SettingsManagerProtocol,
    )


class ManualOffsetDialogFactory:
    """
    Factory for creating UnifiedManualOffsetDialog instances with injected dependencies.
    """

    def __init__(self,
                 rom_cache: ROMCacheProtocol,
                 settings_manager: SettingsManagerProtocol,
                 extraction_manager: ExtractionManagerProtocol,
                 rom_extractor: ROMExtractorProtocol):
        self._rom_cache = rom_cache
        self._settings_manager = settings_manager
        self._extraction_manager = extraction_manager
        self._rom_extractor = rom_extractor

    def create(self, parent: QWidget | None = None) -> UnifiedManualOffsetDialog:
        """
        Creates a new instance of UnifiedManualOffsetDialog with its dependencies.
        """
        return UnifiedManualOffsetDialog(
            parent=parent,
            rom_cache=self._rom_cache,
            settings_manager=self._settings_manager,
            extraction_manager=self._extraction_manager,
            rom_extractor=self._rom_extractor
        )

# Optional: A global accessor for the factory, if needed in some non-DI contexts
_manual_offset_dialog_factory: ManualOffsetDialogFactory | None = None

def get_manual_offset_dialog_factory() -> ManualOffsetDialogFactory:
    """
    Provides a global accessor for the ManualOffsetDialogFactory.
    This should primarily be used in legacy code or if injection is not feasible.
    """
    global _manual_offset_dialog_factory
    if _manual_offset_dialog_factory is None:
        _manual_offset_dialog_factory = inject(ManualOffsetDialogFactory)
    return _manual_offset_dialog_factory
