
import os

import pytest
from PIL import Image
from PySide6.QtWidgets import QGraphicsPixmapItem

from ui.grid_arrangement_dialog import GridArrangementDialog


@pytest.fixture
def mock_image(tmp_path):
    img_path = tmp_path / "test_overlay.png"
    img = Image.new("RGBA", (32, 32), color=(255, 0, 0, 128))
    img.save(img_path)
    return str(img_path)

@pytest.mark.skipif(os.environ.get("GITHUB_ACTIONS") == "true", reason="Requires GUI")
def test_overlay_import_renders_on_scene(qtbot, mock_image, tmp_path):
    # Create a real dummy original image for the dialog to load
    dummy_path = str(tmp_path / "dummy_sprite.png")
    dummy_img = Image.new("RGB", (128, 128), color="white")
    dummy_img.save(dummy_path)
    
    dialog = GridArrangementDialog(dummy_path)
    qtbot.add_widget(dialog)
    dialog.show()
    
    # Initially no overlay
    assert not dialog.overlay_layer.has_image()
    
    # Import overlay
    success = dialog.overlay_layer.import_image(mock_image)
    assert success
    assert dialog.overlay_layer.has_image()
    
    # Process events to let signals and render happen
    qtbot.wait_until(lambda: any(isinstance(item, QGraphicsPixmapItem) for item in dialog.arrangement_scene.items()), timeout=1000)
    
    # Check if we have pixmap items in the scene
    items = dialog.arrangement_scene.items()
    pixmap_items = [item for item in items if isinstance(item, QGraphicsPixmapItem)]
    
    # The overlay should be one of the pixmap items.
    # If no tiles are placed, it might be the only one.
    assert len(pixmap_items) >= 1
    
    # Find the overlay item (it should be at the top or we can check its size/pos)
    # Overlay is 32x32
    overlay_items = [item for item in pixmap_items if item.pixmap().width() == 32 and item.pixmap().height() == 32]
    assert len(overlay_items) == 1
    
    # Toggle visibility
    dialog.overlay_layer.set_visible(False)
    # Re-render should happen via signal
    qtbot.wait_until(lambda: len([item for item in dialog.arrangement_scene.items() if isinstance(item, QGraphicsPixmapItem) and item.pixmap().width() == 32]) == 0, timeout=1000)
    
    dialog.close()
