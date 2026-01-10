"""Tests for multi-palette error routing to correct tab."""

import pytest


def test_multi_palette_missing_inputs_report_in_multi_tab(qtbot, app_context):
    """
    Contract: Multi-palette preview errors appear in MultiPaletteTab output.
    Fails today: error is appended to ExtractTab only.
    """
    from ui.sprite_editor.controllers.extraction_controller import ExtractionController
    from ui.sprite_editor.views.tabs.extract_tab import ExtractTab
    from ui.sprite_editor.views.tabs.multi_palette_tab import MultiPaletteTab

    controller = ExtractionController()
    extract_tab = ExtractTab()
    multi_tab = MultiPaletteTab()
    qtbot.addWidget(extract_tab)
    qtbot.addWidget(multi_tab)

    controller.set_view(extract_tab)
    controller.set_multi_palette_view(multi_tab)

    with qtbot.waitSignal(controller.extraction_failed) as blocker:
        controller.generate_multi_palette_preview(64)

    assert "VRAM and CGRAM files required" in blocker.args[0]  # source-of-truth
    assert "VRAM and CGRAM files required" in multi_tab.output_area.toPlainText()  # UI reflection
