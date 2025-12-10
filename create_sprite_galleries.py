#!/usr/bin/env python3
"""
Create comprehensive HTML galleries for all extracted sprites
"""

import os
from pathlib import Path
import glob

def create_master_gallery():
    """Create a master gallery with all extracted sprites"""
    
    # Collect all PNG files
    sprite_categories = {
        'Confirmed Kirby Sprites': [
            ('sprite_27D800_spritepal.png', 0x27D800, 'Kirby animations'),
            ('sprite_280000_spritepal.png', 0x280000, 'More Kirby sprites'),
        ],
        'UI and Backgrounds': [
            ('enemy_27F700_spritepal.png', 0x27F700, 'UI elements'),
            ('found_27FD80.png', 0x27FD80, 'Background/stage elements'),
            ('sprite_27F400.png', 0x27F400, 'UI with eyes'),
        ],
        'Small Sprites (Potential Enemies)': [],
        'Enemy Area Sprites ($300000+)': [],
    }
    
    # Collect small sprites from $27F area
    for png in glob.glob('enemy_27F*_spritepal.png'):
        if os.path.exists(png):
            offset_str = png.replace('enemy_', '').replace('_spritepal.png', '')
            try:
                offset = int(offset_str, 16)
                sprite_categories['Small Sprites (Potential Enemies)'].append(
                    (png, offset, f'Small sprite ${offset:06X}')
                )
            except:
                pass
    
    for png in glob.glob('found_27F*.png'):
        if os.path.exists(png) and 'found_27FD80.png' not in png:
            offset_str = png.replace('found_', '').replace('.png', '')
            try:
                offset = int(offset_str, 16)
                sprite_categories['Small Sprites (Potential Enemies)'].append(
                    (png, offset, f'Small sprite ${offset:06X}')
                )
            except:
                pass
    
    # Collect enemy area sprites
    for png in glob.glob('enemy_test_30*.png'):
        if os.path.exists(png):
            offset_str = png.replace('enemy_test_', '').replace('.png', '')
            try:
                offset = int(offset_str, 16)
                sprite_categories['Enemy Area Sprites ($300000+)'].append(
                    (png, offset, f'Enemy ${offset:06X}')
                )
            except:
                pass
    
    # Sort each category by offset
    for category in sprite_categories:
        sprite_categories[category].sort(key=lambda x: x[1])
    
    # Create HTML
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Kirby Super Star - Sprite Gallery</title>
    <style>
        body {
            background: #1a1a1a;
            color: #fff;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
        }
        h1 {
            text-align: center;
            color: #ff69b4;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
        h2 {
            color: #87ceeb;
            border-bottom: 2px solid #87ceeb;
            padding-bottom: 5px;
            margin-top: 40px;
        }
        .gallery {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin: 20px 0;
        }
        .sprite-card {
            background: #2a2a2a;
            border: 2px solid #444;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            transition: all 0.3s;
        }
        .sprite-card:hover {
            border-color: #ff69b4;
            transform: scale(1.05);
            box-shadow: 0 0 20px rgba(255,105,180,0.5);
        }
        .sprite-card img {
            image-rendering: pixelated;
            image-rendering: crisp-edges;
            width: 256px;
            height: 256px;
            object-fit: contain;
            background: white;
            border: 1px solid #666;
            margin-bottom: 10px;
        }
        .sprite-info {
            font-size: 14px;
        }
        .offset {
            color: #ffd700;
            font-family: monospace;
            font-weight: bold;
            font-size: 16px;
        }
        .description {
            color: #aaa;
            font-style: italic;
            margin-top: 5px;
        }
        .mushroom-target {
            background: #003300;
            border: 3px dashed #00ff00;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }
        .mushroom-target img {
            width: 128px;
            height: 128px;
            image-rendering: pixelated;
            background: white;
        }
    </style>
</head>
<body>
    <h1>🍄 Kirby Super Star - Mushroom Enemy Hunt 🍄</h1>
    
    <div class="mushroom-target">
        <h2 style="color: #00ff00; border: none;">Target: Mushroom Enemy</h2>
        <p>We're looking for a small mushroom-shaped enemy sprite.</p>
        <p>It should be around 16x16 or 32x32 pixels (4-32 tiles).</p>
        <p>Check VRAM address $6A00 - the mushroom appears there during gameplay.</p>
    </div>
"""
    
    # Add each category
    for category, sprites in sprite_categories.items():
        if not sprites:
            continue
            
        html += f'\n    <h2>{category}</h2>\n    <div class="gallery">\n'
        
        for png_path, offset, description in sprites:
            if os.path.exists(png_path):
                html += f"""
        <div class="sprite-card">
            <img src="{png_path}" alt="{description}">
            <div class="sprite-info">
                <div class="offset">${offset:06X}</div>
                <div class="description">{description}</div>
                <div style="color: #888; font-size: 12px;">{png_path}</div>
            </div>
        </div>
"""
        
        html += '    </div>\n'
    
    html += """
    <script>
        // Add click to zoom functionality
        document.querySelectorAll('.sprite-card img').forEach(img => {
            img.style.cursor = 'zoom-in';
            img.onclick = function() {
                if (this.style.width === '512px') {
                    this.style.width = '256px';
                    this.style.height = '256px';
                    this.style.cursor = 'zoom-in';
                } else {
                    this.style.width = '512px';
                    this.style.height = '512px';
                    this.style.cursor = 'zoom-out';
                }
            };
        });
    </script>
</body>
</html>"""
    
    # Save the gallery
    with open('SPRITE_GALLERY_MASTER.html', 'w') as f:
        f.write(html)
    
    print("Created SPRITE_GALLERY_MASTER.html")
    
    # Count sprites
    total_sprites = sum(len(sprites) for sprites in sprite_categories.values())
    print(f"Total sprites in gallery: {total_sprites}")
    for category, sprites in sprite_categories.items():
        if sprites:
            print(f"  {category}: {len(sprites)} sprites")

if __name__ == '__main__':
    create_master_gallery()
    print("\nOpen SPRITE_GALLERY_MASTER.html in your browser to search for the mushroom!")
    print("Click on any sprite to zoom in/out for better viewing.")