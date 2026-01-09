# Lua Script Display Readability Improvements

## Problem

The ROM offset display in the Mesen2 Lua scripts was difficult to read against colorful game backgrounds due to:
- Poor color contrast (bright yellow text on purple background)
- Small border thickness
- Semi-transparent backgrounds causing text to blend

## Improvements Made

### Enhanced Color Scheme
- **Text**: Changed from bright yellow (`0xFFFFFF00`) to pure white (`0xFFFFFFFF`) for maximum contrast
- **Background**: Changed from semi-transparent purple (`0xFF880088`) to nearly opaque black (`0xF0000000`)
- **Border**: Changed from yellow (`0xFFFFFF00`) to bright green (`0xFF00FF00`) for high visibility
- **Connection Lines**: Updated to bright green (`0xFF00FF00`) to match border

### Enhanced Visual Design
- **Thicker Borders**: Increased from 3px to 4px thick borders for better visibility
- **Text Shadow**: Added black text shadow offset by 1 pixel for extra contrast
- **Larger Padding**: Increased background padding for better readability
- **More Opaque HUD**: Made main HUD background more opaque (`0xE0000000`)

### Results
- **Much Better Contrast**: White text on black background is universally readable
- **Clear Boundaries**: Thick green borders make offset labels stand out against any background
- **Enhanced Legibility**: Text shadows provide extra definition against complex backgrounds
- **Consistent Visibility**: Works well on both light and dark game areas

## Files Updated
- `mesen2_sprite_finder_fixed_offsets.lua` - Base offset tracking script
- `mesen2_sprite_finder_precise.lua` - Precise tile-level offset calculation script

## Usage
Simply reload the Lua script in Mesen2 and the improved display will be active immediately. The offset labels should now be much easier to read against any game background.