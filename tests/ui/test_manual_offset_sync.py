from unittest.mock import MagicMock

import pytest

from ui.rom_extraction_panel import ROMExtractionPanel


def test_set_manual_offset_updates_display_label(qtbot):
    """
    Test that calling set_manual_offset on the ROMExtractionPanel
    correctly updates the manual_offset_section display label.
    """
    # Setup mocks
    mock_extraction_manager = MagicMock()
    mock_state_manager = MagicMock()
    mock_rom_cache = MagicMock()
    
    # Instantiate with qtbot to prevent crash
    panel = ROMExtractionPanel(
        extraction_manager=mock_extraction_manager,
        state_manager=mock_state_manager,
        rom_cache=mock_rom_cache
    )
    qtbot.addWidget(panel)
    panel.show() # Ensure widget is shown for isVisible() checks
    
    # Initial state - using public API
    assert panel.manual_offset_section.get_offset_display_text() == ""
    # Might still be False because layout/show events might not have fully processed
    # but setVisible(False) was called in init.
    
    # Action: Set manual offset
    panel.set_manual_offset(0x3C6EF1)
    
    # Verify: Label should be updated and visible
    display_text = panel.manual_offset_section.get_offset_display_text()
    assert "3C6EF1" in display_text
    assert display_text == "Manual offset: 0x3C6EF1"
    
    # Use qtbot.waitUntil to give Qt time to update visibility if needed
    # although setVisible(True) should be immediate for the property
    assert panel.manual_offset_section.is_offset_display_visible()
