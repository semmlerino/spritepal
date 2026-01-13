from unittest.mock import MagicMock

import pytest
from PIL import Image

from core.arrangement_persistence import ArrangementConfig
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition


@pytest.fixture
def mock_sprite_image(tmp_path):
    path = tmp_path / "test_sprite.png"
    Image.new("RGBA", (32, 16)).save(path)
    return str(path)

@pytest.fixture
def sample_config():
    # create a mock ArrangementConfig with some data
    config = MagicMock(spec=ArrangementConfig)
    config.arrangement_order = [
        {"type": "tile", "key": "0,0"},
        {"type": "tile", "key": "0,1"}
    ]
    config.groups = []
    config.grid_dimensions = {"rows": 2, "cols": 4}
    config.logical_width = 16
    config.overlay_path = None
    config.overlay_visible = True
    config.overlay_opacity = 0.5
    config.overlay_x = 0
    config.overlay_y = 0
    # Include grid_mapping for v1.2+ logic
    config.grid_mapping = {
        "0,0": {"type": "tile", "key": "0,0"},
        "0,1": {"type": "tile", "key": "0,1"}
    }
    return config

def test_dialog_accepts_config(qtbot, mock_sprite_image, sample_config):
    """Test that GridArrangementDialog accepts an arrangement_config parameter."""
    try:
        dialog = GridArrangementDialog(mock_sprite_image, arrangement_config=sample_config)
    except TypeError:
        pytest.fail("GridArrangementDialog does not accept arrangement_config")
    
    qtbot.addWidget(dialog)
    
    assert hasattr(dialog, "arrangement_config")
    assert dialog.arrangement_config == sample_config

def test_dialog_restores_state(qtbot, mock_sprite_image, sample_config):
    """Test that dialog restores manager state from config."""
    dialog = GridArrangementDialog(mock_sprite_image, arrangement_config=sample_config)
    qtbot.addWidget(dialog)
    
    # Check if tiles are arranged
    assert dialog.arrangement_manager.is_tile_arranged(TilePosition(0, 0))
    assert dialog.arrangement_manager.is_tile_arranged(TilePosition(0, 1))
    assert dialog.arrangement_manager.get_arranged_count() == 2
