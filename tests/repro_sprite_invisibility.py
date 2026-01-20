import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage
from ui.frame_mapping.views.comparison_panel import InlineOverlayCanvas
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry, OBSELConfig, TileData

def test_sprite_invisibility():
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Mock a sprite at the bottom right of the SNES screen (256x224)
    # Position (200, 200), size 32x32
    entry = OAMEntry(
        id=0, x=200, y=200, tile=0, width=32, height=32,
        flip_h=False, flip_v=False, palette=0, tiles=[]
    )
    
    # Create a 256x224 pixmap with a white square at (200, 200)
    # This simulates what renderer.render_composite() currently produces
    img = QImage(256, 224, QImage.Format_ARGB32)
    img.fill(0) # Transparent
    for y in range(200, 232):
        for x in range(200, 232):
            if 0 <= x < 256 and 0 <= y < 224:
                img.setPixelColor(x, y, "white")
    
    pixmap = QPixmap.fromImage(img)
    
    canvas = InlineOverlayCanvas()
    canvas.resize(350, 350)
    canvas.set_game_frame(pixmap)
    
    # Force a paint event and check where the sprite is drawn
    # center of canvas is (175, 175)
    # scaled_width = 256 * 4 = 1024
    # x_start = 175 - 512 = -337
    # sprite x in scaled canvas = 200 * 4 = 800
    # sprite x relative to canvas = -337 + 800 = 463
    # Canvas width is 350, so 463 is OUTSIDE
    
    # Let's check the logic in paintEvent (we can't easily check the painter output here, 
    # but we can verify our calculation)
    
    canvas_width = 350
    frame_width = 256
    DISPLAY_SCALE = 4
    
    scaled_width = frame_width * DISPLAY_SCALE
    x_start = (canvas_width // 2) - (scaled_width // 2)
    
    sprite_x = 200
    sprite_x_scaled = sprite_x * DISPLAY_SCALE
    
    final_x = x_start + sprite_x_scaled
    
    print(f"Canvas width: {canvas_width}")
    print(f"Sprite screen X: {sprite_x}")
    print(f"Final drawing X: {final_x}")
    
    if final_x >= canvas_width:
        print("SUCCESS: Sprite is OUTSIDE the canvas!")
    else:
        print("FAILURE: Sprite is INSIDE the canvas.")

if __name__ == "__main__":
    test_sprite_invisibility()
