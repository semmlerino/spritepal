#!/usr/bin/env python3
from __future__ import annotations

"""
Standalone launcher for the Detached Sprite Gallery.
Run this script to open the gallery window independently for testing or demonstration.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Check if we're in the virtual environment
def check_virtual_env():
    """Check if we're running in the virtual environment."""
    return bool(hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))

# If not in venv, try to activate it
if not check_virtual_env():
    print("⚠️  Not running in virtual environment. Checking for venv...")

    # Look for venv in parent directory
    venv_path = Path(__file__).parent.parent / "venv"
    if venv_path.exists():
        print(f"📦 Found virtual environment at: {venv_path}")

        # Try to use the venv Python directly
        if os.name == 'nt':  # Windows
            python_exe = venv_path / "Scripts" / "python.exe"
        else:  # Unix/Linux/Mac
            python_exe = venv_path / "bin" / "python"

        if python_exe.exists():
            print(f"🚀 Restarting with venv Python: {python_exe}")
            import subprocess
            # Re-run this script with the venv Python
            result = subprocess.run([str(python_exe), str(Path(__file__)), *sys.argv[1:]], check=False)
            sys.exit(result.returncode)

    print("❌ Virtual environment not found. Please run from venv or install dependencies.")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from ui.windows.detached_gallery_window import DetachedGalleryWindow
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    print("❌ Qt not available. Please install PySide6.")
    sys.exit(1)

def create_sample_sprites():
    """Create sample sprite data for demonstration."""
    sprite_names = [
        "Kirby Walking", "Kirby Running", "Kirby Jumping", "Kirby Flying",
        "Kirby Inhaling", "Meta Knight", "King Dedede", "Waddle Dee",
        "Waddle Doo", "Gordo", "Bronto Burt", "Cappy", "Scarfy",
        "Hot Head", "Sparky", "Blade Knight", "Sir Kibble", "Poppy Bros",
        "Shotzo", "Laser Ball", "UFO", "Wheelie", "Rocky", "Mr. Shine",
        "Mr. Bright", "Heavy Lobster", "Computer Virus", "Marx"
    ]

    sprites = []
    for i in range(len(sprite_names)):
        sprites.append({
            'offset': 0x200000 + (i * 0x2000),
            'decompressed_size': 1024 + (i * 128),
            'tile_count': 16 + (i * 2),
            'compressed': i % 3 == 0,  # Every 3rd sprite is HAL compressed
            'name': sprite_names[i],
        })

    return sprites

def create_colorful_thumbnails(gallery_window, sprites):
    """Create colorful mock thumbnails for the sprites."""
    colors = [
        Qt.GlobalColor.red, Qt.GlobalColor.green, Qt.GlobalColor.blue,
        Qt.GlobalColor.yellow, Qt.GlobalColor.cyan, Qt.GlobalColor.magenta,
        Qt.GlobalColor.darkRed, Qt.GlobalColor.darkGreen, Qt.GlobalColor.darkBlue,
        Qt.GlobalColor.darkYellow, Qt.GlobalColor.darkCyan, Qt.GlobalColor.darkMagenta,
        QColor(255, 165, 0),  # Orange
        QColor(128, 0, 128),  # Purple
        QColor(255, 192, 203), # Pink
        QColor(165, 42, 42),   # Brown
        QColor(0, 128, 128),   # Teal
        QColor(128, 128, 0),   # Olive
        QColor(255, 20, 147),  # Deep pink
        QColor(72, 61, 139),   # Dark slate blue
        QColor(255, 69, 0),    # Red orange
        QColor(50, 205, 50),   # Lime green
        QColor(186, 85, 211),  # Medium orchid
        QColor(255, 215, 0),   # Gold
        QColor(30, 144, 255),  # Dodger blue
        QColor(220, 20, 60),   # Crimson
        QColor(0, 206, 209),   # Dark turquoise
        QColor(138, 43, 226),  # Blue violet
    ]

    gallery = gallery_window.gallery_widget

    for i, sprite in enumerate(sprites):
        offset = sprite['offset']

        # Create unique thumbnail
        pixmap = QPixmap(128, 128)
        pixmap.fill(Qt.GlobalColor.black)

        painter = QPainter(pixmap)

        # Main sprite color
        main_color = colors[i % len(colors)]
        painter.fillRect(8, 8, 112, 112, main_color)

        # Add border
        painter.setPen(Qt.GlobalColor.white)
        painter.drawRect(8, 8, 112, 112)

        # Add sprite info
        painter.setPen(Qt.GlobalColor.white)
        font = QFont("Arial", 8, QFont.Weight.Bold)
        painter.setFont(font)

        # Sprite number
        painter.drawText(12, 25, f"#{i+1}")

        # Sprite name (truncated)
        name = sprite['name'][:10] + "..." if len(sprite['name']) > 10 else sprite['name']
        painter.drawText(12, 40, name)

        # Offset
        painter.drawText(12, 55, f"0x{offset:06X}")

        # Size info
        size_kb = sprite['decompressed_size'] // 1024
        painter.drawText(12, 70, f"{size_kb}KB")

        # Tile count
        painter.drawText(12, 85, f"{sprite['tile_count']} tiles")

        # HAL compression indicator
        if sprite['compressed']:
            painter.fillRect(90, 95, 30, 20, Qt.GlobalColor.yellow)
            painter.setPen(Qt.GlobalColor.black)
            font_small = QFont("Arial", 7, QFont.Weight.Bold)
            painter.setFont(font_small)
            painter.drawText(94, 107, "HAL")

        painter.end()

        # Set the thumbnail using the gallery widget's method
        gallery.set_thumbnail(offset, pixmap)

class StandaloneGalleryLauncher:
    """Standalone launcher for the detached gallery."""

    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setApplicationName("SpritePal - Detached Gallery")
        self.gallery_window = None

        # Initialize SpritePal managers
        self._initialize_managers()

        # Set application icon if available
        try:
            # You could add an icon file here
            pass
        except Exception:
            pass

    def _initialize_managers(self):
        """Initialize SpritePal core managers."""
        try:
            from core.managers import initialize_managers
            initialize_managers()

            print("✅ SpritePal managers initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize managers: {e}")
            raise

    def create_gallery_window(self):
        """Create and setup the gallery window."""
        print("🗖 Creating detached gallery window...")

        # Inject dependencies at app boundary
        from core.di_container import inject
        from core.managers import ApplicationStateManager, CoreOperationsManager
        from core.services.rom_cache import ROMCache
        core_ops_manager = inject(CoreOperationsManager)
        settings_manager = inject(ApplicationStateManager)
        rom_cache = inject(ROMCache)

        # Create the detached gallery window with dependencies
        self.gallery_window = DetachedGalleryWindow(
            extraction_manager=core_ops_manager,
            settings_manager=settings_manager,
            rom_cache=rom_cache,
        )
        self.gallery_window.setWindowTitle("SpritePal - Sprite Gallery (Standalone)")

        # Create sample sprites
        sprites = create_sample_sprites()

        # Set the sprites in the gallery
        self.gallery_window.set_sprites(sprites)

        # Generate colorful thumbnails
        create_colorful_thumbnails(self.gallery_window, sprites)

        # Update the status to show it's a demo
        if self.gallery_window.gallery_widget:
            status_label = self.gallery_window.gallery_widget.status_label
            status_label.setText(f"{len(sprites)} demo sprites loaded")

        print(f"✅ Created gallery with {len(sprites)} colorful demo sprites")

    def run(self):
        """Run the standalone gallery."""
        print("=" * 60)
        print("🚀 LAUNCHING STANDALONE SPRITEGAL GALLERY")
        print("=" * 60)
        print("Full-featured standalone SpritePal gallery with:")
        print("• ROM loading and scanning capabilities")
        print("• Sprite extraction to PNG")
        print("• Progress indicators and caching")
        print("• Fixed empty space stretching issue")
        print()

        # Create and setup the gallery
        self.create_gallery_window()

        # Show the window
        if self.gallery_window:
            self.gallery_window.show()
            self.gallery_window.resize(1200, 800)  # Nice initial size

        # Welcome message removed - direct to functionality

        print("🎉 Gallery window opened!")
        print()
        print("💡 Try these actions:")
        print("  • Load a ROM file (Ctrl+O)")
        print("  • Scan ROM for sprites (Ctrl+S)")
        print("  • Extract selected sprites (Ctrl+E)")
        print("  • Maximize the window (no empty space!)")
        print("  • Adjust thumbnail size with the slider")
        print("  • Filter sprites with 'HAL only' checkbox")
        print("  • Sort by Offset/Size/Tiles")
        print("  • Use F11 for fullscreen")
        print("  • Use Ctrl+W to close")
        print()
        print("Press Ctrl+C in terminal to exit")
        print("=" * 60)

        # Run the application
        return self.app.exec()

def main():
    """Main entry point."""
    if not QT_AVAILABLE:
        return 1

    try:
        launcher = StandaloneGalleryLauncher()
        return launcher.run()
    except KeyboardInterrupt:
        print("\n👋 Gallery closed by user")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
