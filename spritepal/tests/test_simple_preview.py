from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.dialog,
    pytest.mark.gui,
    pytest.mark.requires_display,
    pytest.mark.rom_data,
]
#!/usr/bin/env python3
"""
Test the simplified preview coordinator.
"""

import logging
import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout  # Force stdout to see everything
)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.managers.registry import get_extraction_manager, initialize_managers
from ui.dialogs.manual_offset_unified_integrated import UnifiedManualOffsetDialog


def test_preview(dialog):
    """Test moving the slider once."""
    if not dialog.browse_tab:
        print("ERROR: No browse tab!")
        return

    slider = dialog.browse_tab.position_slider
    print(f"\nSlider range: {slider.minimum()} to {slider.maximum()}")
    print(f"Current value: 0x{slider:06X}")

    # Move to a specific offset
    new_value = 0x250000
    print(f"\n========== SETTING SLIDER TO 0x{new_value:06X} ==========")
    slider.setValue(new_value)
    print("Slider value set, waiting for preview...")

    # Wait a bit for preview to generate
    QTimer.singleShot(2000, lambda: print("\n========== TEST COMPLETE =========="))

def main():
    app = QApplication(sys.argv)

    # Initialize managers
    print("Initializing managers...")
    initialize_managers()

    # Create dialog
    print("Creating dialog...")
    dialog = UnifiedManualOffsetDialog()

    # Set a test ROM path if available
    test_rom = "Kirby Super Star (USA).sfc"
    if os.path.exists(test_rom):
        print(f"Loading ROM: {test_rom}")
        rom_size = os.path.getsize(test_rom)
        extraction_manager = get_extraction_manager()
        dialog.set_rom_data(test_rom, rom_size, extraction_manager)
    else:
        print("ERROR: Test ROM not found!")
        return 1

    # Show dialog
    dialog.show()

    # Test preview after a short delay
    QTimer.singleShot(1000, lambda: test_preview(dialog))

    # Auto-close after 5 seconds
    QTimer.singleShot(5000, app.quit)

    # Run the application
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
