
from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.dialog,
    pytest.mark.gui,
    pytest.mark.requires_display,
    pytest.mark.rom_data,
    pytest.mark.skip(reason="Manual test script - requires dialog fixture setup"),
]
#!/usr/bin/env python3
"""
Test next/prev navigation in manual offset dialog.
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
    datefmt='%H:%M:%S'
)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.managers.registry import get_extraction_manager, initialize_managers
from ui.dialogs.manual_offset_unified_integrated import UnifiedManualOffsetDialog


def test_navigation(dialog):
    """Test next/prev navigation."""
    if not dialog.browse_tab:
        print("ERROR: No browse tab!")
        return

    # Get current offset
    current = dialog.browse_tab.get_current_offset()
    print(f"\nCurrent offset: 0x{current:06X}")

    # Test next button
    print("\n========== TESTING NEXT BUTTON ==========")
    dialog.browse_tab.next_button.click()
    print("Next button clicked, waiting for search...")

    # Wait for search to complete
    QTimer.singleShot(3000, lambda: check_navigation_result(dialog, "next"))

def check_navigation_result(dialog, direction):
    """Check if navigation worked."""
    new_offset = dialog.browse_tab.get_current_offset()
    print(f"\nNew offset after {direction}: 0x{new_offset:06X}")

    if direction == "next":
        # Now test prev button
        print("\n========== TESTING PREV BUTTON ==========")
        dialog.browse_tab.prev_button.click()
        print("Prev button clicked, waiting for search...")
        QTimer.singleShot(3000, lambda: check_navigation_result(dialog, "prev"))
    else:
        print("\n========== NAVIGATION TEST COMPLETE ==========")
        # Close after a short delay
        QTimer.singleShot(1000, QApplication.instance().quit)

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

        # Set initial offset to a known location
        dialog.browse_tab.set_offset(0x200000)
    else:
        print("ERROR: Test ROM not found!")
        return 1

    # Show dialog
    dialog.show()

    # Test navigation after a short delay
    QTimer.singleShot(1000, lambda: test_navigation(dialog))

    # Auto-close after 10 seconds as safety
    QTimer.singleShot(10000, app.quit)

    # Run the application
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
