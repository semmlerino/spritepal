"""
Centralized help text for SpritePal UI components.

Provides consistent tooltips and detailed help for technical terms
that may be unfamiliar to users.
"""

from __future__ import annotations

# Short tooltips for common controls
TOOLTIPS = {
    # Offset-related
    "offset": "Memory location in the ROM file (hexadecimal format)",
    "start_offset": "Where to begin searching in the ROM",
    "end_offset": "Where to stop searching (leave empty for end of ROM)",
    "step_size": "How far to jump between search positions",
    # Size and tile filters
    "min_size": "Minimum sprite data size in bytes",
    "max_size": "Maximum sprite data size in bytes",
    "size_range": "Filter by sprite data size. 16x16 sprites are typically 128-512 bytes",
    "tile_count": "SNES sprites are made of 8x8 tiles. A 16x16 sprite uses 4 tiles",
    "min_tiles": "Minimum number of 8x8 tiles",
    "max_tiles": "Maximum number of 8x8 tiles",
    # Compression
    "compressed": "Include HAL-compressed sprite data",
    "uncompressed": "Include raw uncompressed sprite data",
    # Alignment
    "alignment": "Required offset alignment. 0x100 means offset ends in 00",
    "alignment_detail": "Some ROMs store sprites at aligned addresses for faster access",
    # Performance
    "worker_threads": "Number of parallel search threads (more = faster, but uses more CPU)",
    "adaptive_stepping": "Automatically adjust step size based on search results",
    # Visual search
    "similarity_threshold": "How closely sprites must match the reference (0-100%)",
    "search_scope": "Which sprites to compare against",
    # Extraction
    "extract_button": "Extract sprites for editing (Ctrl+E)",
    "output_name": "Name for the extracted sprite file",
    # CGRAM
    "cgram": "Color Graphics RAM - contains the sprite palette colors",
    "cgram_file": "A .cgram file containing palette data from Mesen2",
    # ROM navigation
    "scan_rom": "Automatically find sprite offsets in the ROM",
    "manual_offset": "Manually specify a hex offset to extract from",
    "preset_offsets": "Jump to known sprite locations in this game",
}

# Detailed help text for "?" buttons and What's This dialogs
HELP_TEXT = {
    "offset": """
<h3>Hex Offset</h3>
<p>A <b>hex offset</b> is a position (address) in the ROM file, written in hexadecimal.</p>
<p>For example: <code>0x1A2B3</code> means "byte number 107,187 in the file".</p>
<p>Sprites are stored at specific offsets. Finding the right offset is key to extracting sprites.</p>
""",
    "compression": """
<h3>Sprite Compression</h3>
<p>Many SNES games use <b>HAL compression</b> to save space.</p>
<p><b>Compressed sprites:</b> Stored efficiently, need decompression to view. Most common.</p>
<p><b>Uncompressed sprites:</b> Raw tile data, less common. Try this if compressed search fails.</p>
""",
    "tiles": """
<h3>Tiles and Sprite Size</h3>
<p>SNES sprites are built from <b>8x8 pixel tiles</b>.</p>
<ul>
<li>8x8 sprite = 1 tile = 32 bytes</li>
<li>16x16 sprite = 4 tiles = 128 bytes</li>
<li>32x32 sprite = 16 tiles = 512 bytes</li>
</ul>
<p>Larger sprites use more tiles.</p>
""",
    "alignment": """
<h3>Offset Alignment</h3>
<p>Some ROMs store sprites at <b>aligned addresses</b> (multiples of 0x10, 0x100, etc.).</p>
<p>Using alignment filters can speed up searches by skipping unlikely positions.</p>
<ul>
<li><b>Any</b>: Check every position (slowest, most thorough)</li>
<li><b>0x10</b>: Only check offsets ending in 0 (like 0x1230, 0x4560)</li>
<li><b>0x100</b>: Only check offsets ending in 00 (like 0x1200, 0x4500)</li>
</ul>
""",
    "visual_search": """
<h3>Visual Similarity Search</h3>
<p>Find sprites that <b>look similar</b> to a reference sprite.</p>
<p>Useful for finding variations of characters, animation frames, or related graphics.</p>
<p>The <b>similarity threshold</b> controls how close the match must be:</p>
<ul>
<li>90-100%: Nearly identical sprites</li>
<li>70-90%: Similar sprites (color variations, slight changes)</li>
<li>50-70%: Related sprites (same character, different pose)</li>
</ul>
""",
    "cgram": """
<h3>CGRAM (Palette Data)</h3>
<p><b>CGRAM</b> (Color Graphics RAM) contains the color palette used to display sprites.</p>
<p>Without the correct palette, sprites will have wrong or missing colors.</p>
<p><b>To get a CGRAM file:</b></p>
<ol>
<li>Open the ROM in Mesen2 emulator</li>
<li>Navigate to the screen showing the sprite</li>
<li>Use Tools → Export → CGRAM to save the palette</li>
</ol>
""",
    "parallel_search": """
<h3>Parallel ROM Search</h3>
<p>Scans the ROM file to find all valid sprites.</p>
<p><b>How it works:</b></p>
<ol>
<li>Starts at the beginning of the ROM (or specified offset)</li>
<li>Tries to decompress data at each position</li>
<li>Valid sprites are added to the results</li>
</ol>
<p><b>Tips:</b></p>
<ul>
<li>Use alignment filters to speed up the search</li>
<li>Start with a small range to test</li>
<li>More worker threads = faster search</li>
</ul>
""",
}
