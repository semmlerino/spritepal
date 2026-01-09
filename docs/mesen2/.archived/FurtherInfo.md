Kirby Super Star packs enemy art into compressed sprite “GFX packs”, and each room tells the game which packs to load. The “mushroom” enemy you see right at the start is Cappy, and its tiles live in one of the sprite packs that the first Green Greens room loads.

Here’s exactly where to look in the (U) v1.0 ROM and how to get to Cappy’s tiles:

Go to the first room’s headers (Green Greens – Spring Breeze)

Music/misc header starts at PC $003020EF. 
Super Famicom Development Wiki

The room’s graphics header starts at PC $00302105 and ends with the four sprite-GFX IDs:

... 55 4E 57 15 03
           ^  ^  ^  ^
         packs A B C D


Those four bytes are the sprite GFX pack indices for this room: 4E, 57, 15, 03. 
Super Famicom Development Wiki

Which pack contains the “mushroom” (Cappy)?

In this game’s object list, the “Mushroom” enemy is Cappy (object ID 06). That enemy belongs to the sprite graphics group “03” (the same “03” you see in the room’s sprite-GFX IDs above). 
The Cutting Room Floor

Find the actual compressed tiles for pack 0x03

Bank $FF (PC $3F0000–$3FFFFF) holds a bunch of pointer tables. At $FF:0002 (PC $3F0002) there’s a pointer to the GFX & level-palette pointer table. From there, entry index 0x03 is the address of the compressed sprite tiles for Cappy’s pack. (Each entry is a SNES/LoROM pointer—convert it to a PC offset, then decompress.) 
Super Famicom Development Wiki

Decompress the data

HAL used several related compression types (“0x”, “2x”, “8x”, “E4”). Use exhal to decompress; it outputs standard 4bpp SNES tiles you can open in YY-CHR/Tile Molester. 
Super Famicom Development Wiki

(Optional) Confirm you’ve got the right art

This first room’s sprite list lives right after the level data. You can see example enemy records beginning around PC $00302238 (that example shows a bird, ID 1A, but look nearby for records where the second byte is 06 for Cappy). The sprites will only look correct if the right GFX pack (03) is loaded. 
Super Famicom Development Wiki

Notes & tips

The pointer-table navigation is the key:
• PC $3F0002 → read pointer to “GFX & (Level) Palette pointer table” → go to that table → jump to entry #0x03 → follow that 24-bit pointer (LoROM mapping) → decompress. 
Super Famicom Development Wiki

LoROM conversion (once you have an address like $bb:aaaa): pc = (bb * 0x8000) + (aaaa & 0x7FFF).

If you prefer not to chase pointers, another way is to run the room in a debugger (bsnes-plus/Mesen-S), set a breakpoint on VRAM writes, and dump the DMA/decompressed blob that fills the sprite pattern table—then search the ROM for that blob to find the source. (Still ends up leading you back to the same pack pointer.)

There’s also a known example of a compressed GFX block called out on TCRF at SNES addr DF14FF (unused tiles), which illustrates that enemy/background art is indeed stored as compressed chunks rather than raw tiles. 
The Cutting Room Floor