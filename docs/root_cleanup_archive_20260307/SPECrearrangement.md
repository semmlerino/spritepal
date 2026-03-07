Sprite Tile Rearrangement \& Overlay — Spec Sheet

Purpose



Allow users to visually reconstruct how a sprite appears in-game by rearranging its existing tiles, align an external reference/replacement image on top, then bake that image back into the original tile layout without changing tile indices or ROM order.



Core Concepts



Arrangement = view-only composition



Tile order / indices are immutable



Overlay is a sampling source, not a new layout



Apply = resample overlay → write back into original tiles



UI Structure

Main Canvas



Zoom / pan enabled



Pixel-accurate interaction



Checkerboard or solid background



Layers (independent)



Original Tiles (Rearranged)



Draggable tiles



Grid snapping (toggle)



Multi-select + marquee



Opacity slider (0–100%)



Visibility toggle



Imported Overlay Image



Import / replace image



Moveable (pixel-precise)



Nudge with arrow keys (±1px, ±10px)



Opacity slider (0–100%)



Visibility toggle



Tile Rearrangement Behavior



Tiles can be freely repositioned to form the in-game sprite



Rearrangement affects only visual placement



Tile indices, ROM order, and tile dimensions remain unchanged



Unplaced tiles are allowed but tracked



Overlay Behavior



Overlay is a reference or replacement sprite



Used only during Apply



No automatic snapping or rescaling unless explicitly enabled



Overlay transform (position) is persistent per sprite



Apply / Commit Behavior (Critical)

On Apply:



For each original tile:



Read the tile’s current position in the composed canvas



Sample a tile-sized region from the overlay image at that position



Quantize/map pixels to the sprite’s palette



Write pixels back into the tile’s original index



Guarantees:



Tile count unchanged



Tile order unchanged



ROM layout unchanged



Warnings / Validation (No Silent Failures)



Overlay does not fully cover placed tiles → warn + highlight



Palette mismatches → warn (with quantization summary)



Unplaced tiles → warn (tile IDs listed)



User must explicitly confirm Apply if warnings exist



Persistence



Arrangement saved per sprite (content-hash based)



Restores automatically on reopen



Overlay position + visibility restored



One-click “Reset to extracted layout”



Explicit Non-Goals



No implicit tile reordering



No painting or pixel editing in this mode



No automatic ROM mutation outside Apply



Success Criteria



User can reconstruct in-game sprite pose visually



Overlay can be aligned precisely via opacity blending



Applying produces correct sprite output without tile index changes



Reopening sprite restores arrangement and overlay state

