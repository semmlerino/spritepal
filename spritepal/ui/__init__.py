"""UI components for SpritePal."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_ui_factories() -> None:
    """
    Legacy no-op function, kept for backwards compatibility.

    Previously registered DialogFactoryProtocol with the DI container,
    but this is no longer needed since ExtractionController now directly
    imports and instantiates dialogs.

    This function can be safely removed once all call sites are updated.
    """
    logger.debug("register_ui_factories() is now a no-op (dialog factory removed)")
