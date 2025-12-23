from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ui.dialogs.manual_offset_dialog import UnifiedManualOffsetDialog

if TYPE_CHECKING:
    from core.protocols.manager_protocols import (
        ApplicationStateManagerProtocol,
        ExtractionManagerProtocol,
        ROMCacheProtocol,
        ROMExtractorProtocol,
    )


class ManualOffsetDialogFactory:
    """
    Factory for creating UnifiedManualOffsetDialog instances with injected dependencies.
    """

    def __init__(self,
                 rom_cache: ROMCacheProtocol,
                 settings_manager: ApplicationStateManagerProtocol,
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
