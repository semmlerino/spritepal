"""UI components for SpritePal."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_ui_factories() -> None:
    """
    Register UI factories with the DI container.

    This function must be called AFTER configure_container() but BEFORE
    any code tries to inject UI factory protocols. It keeps UI dependencies
    out of core/ by having the UI layer register its own factories.

    Called from: core/managers/registry.py after configure_container()
    """
    from core.di_container import inject, register_factory
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.protocols.dialog_protocols import (
        DialogFactoryProtocol,
        ManualOffsetDialogFactoryProtocol,
    )
    from core.protocols.manager_protocols import (
        ROMCacheProtocol,
        ROMExtractorProtocol,
    )

    def _create_manual_offset_dialog_factory():
        from ui.dialogs.dialog_factories import ManualOffsetDialogFactory

        return ManualOffsetDialogFactory(
            rom_cache=inject(ROMCacheProtocol),
            settings_manager=inject(ApplicationStateManager),
            extraction_manager=inject(CoreOperationsManager),
            rom_extractor=inject(ROMExtractorProtocol),
        )

    register_factory(ManualOffsetDialogFactoryProtocol, _create_manual_offset_dialog_factory)

    def _create_controller_dialog_factory():
        from ui.dialogs.controller_dialog_factory import ControllerDialogFactory

        return ControllerDialogFactory()

    register_factory(DialogFactoryProtocol, _create_controller_dialog_factory)

    logger.debug("UI factories registered with DI container")
