#!/usr/bin/env python3
"""
Apply different visualization techniques to small enemy sprites to find mushroom
"""

import sys
import os
sys.path.insert(0, '/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal')

from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps
import numpy as np

def visualize_mushroom_candidates():
    """Try different visualizations on small enemy sprites"""
    
    # The small 4-tile sprites from enemy area that could be mushroom
    candidates = [
        'enemy_test_300380.png',
        'enemy_test_300E40.png', 
        'enemy_test_301140.png',
        'enemy_test_300500.png',
        'enemy_test_301100.png'
    ]
    
    print("Applying different visualization techniques to find mushroom sprite...")
    print("=" * 60)
    
    for sprite_path in candidates:
        if not Path(sprite_path).exists():
            print(f"\n{sprite_path} not found, skipping...")
            continue
            
        print(f"\nProcessing {sprite_path}...")
        
        # Load the image
        img = Image.open(sprite_path)
        
        # Get the offset from filename
        offset_str = sprite_path.split('_')[-1].replace('.png', '')
        
        # Create multiple visualizations
        visualizations = []
        
        # 1. Original
        visualizations.append(('original', img))
        
        # 2. Inverted colors
        inverted = ImageOps.invert(img.convert('L'))
        visualizations.append(('inverted', inverted))
        
        # 3. High contrast
        enhancer = ImageEnhance.Contrast(img.convert('L'))
        high_contrast = enhancer.enhance(3.0)
        visualizations.append(('high_contrast', high_contrast))
        
        # 4. Threshold (binary)
        threshold = img.convert('L').point(lambda x: 255 if x > 128 else 0, mode='1')
        visualizations.append(('threshold', threshold))
        
        # 5. Edge detection
        edges = detect_edges(img)
        visualizations.append(('edges', edges))
        
        # 6. Pattern analysis - look for mushroom cap shape
        pattern = analyze_mushroom_pattern(img)
        visualizations.append(('pattern', pattern))
        
        # Save all visualizations
        for viz_name, viz_img in visualizations:
            output_path = f"mushroom_viz_{offset_str}_{viz_name}.png"
            
            # Scale up for better visibility
            viz_img_scaled = viz_img.resize(
                (viz_img.width * 8, viz_img.height * 8),
                Image.NEAREST
            )
            viz_img_scaled.save(output_path)
            print(f"  Saved: {output_path}")
    
    # Create comparison gallery
    create_visualization_gallery(candidates)

def detect_edges(img):
    """Simple edge detection"""
    img_array = np.array(img.convert('L'))
    
    # Simple Sobel-like edge detection
    edges = np.zeros_like(img_array)
    
    for y in range(1, img_array.shape[0] - 1):
        for x in range(1, img_array.shape[1] - 1):
            dx = abs(int(img_array[y, x+1]) - int(img_array[y, x-1]))
            dy = abs(int(img_array[y+1, x]) - int(img_array[y-1, x]))
            edges[y, x] = min(255, dx + dy)
    
    return Image.fromarray(edges.astype(np.uint8), 'L')

def analyze_mushroom_pattern(img):
    """Look for mushroom-like pattern (cap on top, stem below)"""
    img_array = np.array(img.convert('L'))
    height, width = img_array.shape
    
    # Create pattern map
    pattern = np.zeros_like(img_array)
    
    # Look for horizontal density (cap)
    for y in range(height // 3):  # Top third
        row_density = np.sum(img_array[y, :] > 128)
        if row_density > width * 0.3:  # More than 30% filled
            pattern[y, :] = 255
    
    # Look for vertical density (stem)  
    center_x = width // 2
    for y in range(height // 3, height):
        # Check center columns for stem
        for x in range(max(0, center_x - 2), min(width, center_x + 3)):
            if img_array[y, x] > 64:
                pattern[y, x] = 128
    
    return Image.fromarray(pattern.astype(np.uint8), 'L')

def create_visualization_gallery(candidates):
    """Create HTML gallery of all visualizations"""
    
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Mushroom Sprite Visualization Analysis</title>
    <style>
        body { font-family: monospace; background: #1a1a1a; color: #fff; padding: 20px; }
        .container { max-width: 1600px; margin: 0 auto; }
        h1 { color: #4CAF50; }
        h2 { color: #FFA500; margin-top: 40px; }
        .viz-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
        .viz-item { background: #2a2a2a; border: 1px solid #444; padding: 10px; text-align: center; }
        .viz-item img { width: 100%; max-width: 256px; height: auto; 
                        image-rendering: pixelated; border: 1px solid #555; }
        .viz-label { color: #4CAF50; font-size: 12px; margin-top: 5px; }
        .note { background: #333; padding: 10px; margin: 20px 0; border-left: 3px solid #4CAF50; }
        .mushroom-ref { float: right; background: #2a2a2a; padding: 10px; border: 1px solid #444; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍄 Mushroom Sprite Visualization Analysis</h1>
        
        <div class="mushroom-ref">
            <div style="color: #4CAF50; margin-bottom: 10px;">Target Mushroom Shape:</div>
            <div style="text-align: center; font-size: 20px; line-height: 1.2;">
                🍄<br>
                Cap on top<br>
                Stem below
            </div>
        </div>
        
        <div class="note">
            Applying different visualization techniques to reveal the mushroom enemy sprite.<br>
            Looking for: Wide cap on top (3-5 tiles wide), narrow stem below (1-2 tiles wide).<br>
            The mushroom is sprite ID 06 and should be a small enemy (4-8 tiles total).
        </div>
"""
    
    viz_types = ['original', 'inverted', 'high_contrast', 'threshold', 'edges', 'pattern']
    
    for candidate in candidates:
        if not Path(candidate).exists():
            continue
            
        offset_str = candidate.split('_')[-1].replace('.png', '')
        html += f"\n        <h2>Candidate: Offset ${offset_str}</h2>\n"
        html += '        <div class="viz-grid">\n'
        
        for viz_type in viz_types:
            viz_path = f"mushroom_viz_{offset_str}_{viz_type}.png"
            if Path(viz_path).exists():
                html += f"""            <div class="viz-item">
                <img src="{viz_path}" alt="{viz_type}">
                <div class="viz-label">{viz_type.replace('_', ' ').title()}</div>
            </div>
"""
        
        html += '        </div>\n'
    
    html += """    </div>
</body>
</html>
"""
    
    gallery_path = "MUSHROOM_VISUALIZATION.html"
    with open(gallery_path, 'w') as f:
        f.write(html)
    
    print(f"\n✓ Created visualization gallery: {gallery_path}")

if __name__ == '__main__':
    visualize_mushroom_candidates()