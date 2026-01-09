# Tracing Kirby Super Star Sprite Graphics from Screen to ROM in Mesen 2

**Goal:** Identify the exact ROM bytes corresponding to a visible sprite (e.g. *Cappy*) in *Kirby Super Star* (SNES, USA v1.0). Kirby Super Star uses the SA-1 coprocessor and a LoROM mapping with no header[\[1\]](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star#:~:text=Header%20None%20Bank%20LoROM%20Interleaved,ROM%204%20MiB%20Country%20USA), meaning graphics are compressed in the ROM and loaded at runtime. We will start from the on-screen sprite, trace backwards through VRAM, and find the ROM offset of its graphic data. Below is a step-by-step debugging workflow using Mesen 2.

## Step 1: Locate the Sprite’s Tiles in VRAM

1. **Pause the game at the sprite:** Run Kirby Super Star in Mesen 2 and pause at a moment where the target sprite (e.g. Cappy) is visible on screen.

2. **Open the Tile Viewer:** In Mesen 2, go to **Tools \> Tile Viewer** (or the equivalent PPU/graphics viewer). This shows the contents of SNES VRAM as tiles/patterns[\[2\]](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/#:~:text=Happily%2C%20the%20Mesen%202%20emulator,VRAM%20debugger%20render%20for%20us). Ensure you are viewing the sprite graphics (you may need to toggle or distinguish sprite tiles vs background tiles).

3. **Identify the sprite’s tiles:** Find the tile(s) in the viewer that match the sprite’s graphics. You can visually scan for the sprite’s pixels or use an OAM viewer (if available) to pinpoint the tile index. For example, clicking on a tile in Mesen’s tile viewer will highlight it and display its details.

4. **Note the VRAM address(es):** In the tile viewer UI (often at the bottom or status bar), note the VRAM address of the selected tile. For multi-tile sprites, note the range of VRAM addresses covering all its tiles (they are usually contiguous or in a predictable pattern). For instance, you might see an address like $1E00 for the tile – remember that SNES **VRAM addresses are word-oriented** (each address increments by 2 bytes)[\[3\]](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/#:~:text=One%20thing%20that%20will%20become,this%20is%20a%20wacky%20choice). Mesen 2 reports VRAM in these word units, so use the value exactly as given.

## Step 2: Set a Write Breakpoint on the VRAM Tile Data

1. **Open the Debugger:** Go to **Debug \> Debugger** (Ctrl+D). This opens the debugging interface where you can set breakpoints.

2. **Add a VRAM write breakpoint:** In the Breakpoints panel, right-click and choose “Add…”. In the breakpoint dialog:

3. Set **Memory Type** (or **Source**) to **VRAM** (Video RAM).

4. Enter the VRAM address range for the sprite’s tile data. For example, if the tile starts at VRAM $1E00 and is 0x20 bytes long (a typical 4bpp 8×8 tile is 32 bytes), you would specify $1E00-$1E1F. Include all tiles of the sprite (e.g. if the sprite uses 4 tiles, cover all of them).

5. Check **Write** (we want to break on writes to VRAM) and uncheck Read/Execute.

6. Confirm to create the breakpoint.

*Note:* Mesen 2’s tile viewer/debugger displays VRAM in word units (each address is a 16-bit word)[\[3\]](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/#:~:text=One%20thing%20that%20will%20become,this%20is%20a%20wacky%20choice). Use the value exactly as shown when setting breakpoints. For Lua `emu.read(..., snesVideoRam)`, convert to byte addresses (`byte = word * 2`).

1. **Verify the breakpoint:** The breakpoint list should now show an entry for VRAM writes at the specified range. This will cause the emulator to pause whenever the game code writes data into that VRAM region (i.e. when the sprite’s graphics are being loaded).

## Step 3: Trigger the Sprite Graphics Loading

1. **Unpause/Reset the game:** Resume the game or reset to a point *before* the sprite appears, so that the sprite’s graphics will be loaded fresh. For example, if the sprite is loaded when entering a level or when the enemy spawns, go to just before that event.

2. **Run until breakpoint:** Continue the game and allow the sprite to load. As soon as the game tries to write the sprite’s graphic data into VRAM, **Mesen 2 will break (pause) execution** at that moment[\[4\]](https://www.reddit.com/r/romhacking/comments/1jl2s3t/help_with_vegas_stakes_snes_graphics_tilesets/#:~:text=replacement%20www,It%20will). In the debugger, you should see that the VRAM write breakpoint has been hit.

3. **Handling multiple hits:** It’s possible the breakpoint might trigger multiple times (e.g. once per tile or frame). If it breaks repeatedly, you can **disable the breakpoint after the first hit** (uncheck it in the breakpoints list) to avoid repetitive stops. One hit is usually enough to inspect the loading process.

## Step 4: Analyze the Breakpoint to Find the ROM Source

Now the game is paused at the point of writing to VRAM. We need to trace where that data is coming from in the ROM:

1. **Examine the code:** In the debugger’s code view, the current program counter (PC) will be at or just after the instruction that wrote to VRAM. Often, this will be an instruction like STA $2118/$2119 (the SNES PPU registers for VRAM data port) or a DMA transfer setup. Look a few instructions *before* this point to see how data is being obtained.

2. **Identify ROM read operations:** Typically, compressed graphics are read from the ROM and then written to VRAM. Look for instructions that **read from memory** just before the VRAM write. Common patterns:

3. A loop like: LDA \[\<pointer\>\],Y or LDA \<address\>,X – this indicates the game is reading bytes from a source address (possibly in ROM) into the accumulator before storing to VRAM. If you see an indexed addressing mode with a pointer (e.g., (dp),Y or $xx,x), note the pointer or base address.

4. If the game uses **DMA** for VRAM transfer: You might see writes to DMA registers (like $4300-$4305) instead of manual STA $2118. In this case, check the DMA registers: $4302/$4303 hold the source address low/high, $4304 the source bank, and $4305-$4306 the transfer length, etc. Mesen’s *Memory* or *Registers* view will show the values in these registers when paused. The source address in DMA registers is where the data was copied from (which could be a RAM buffer or ROM).

5. **Determine the source address:** From the above, deduce the **24-bit SNES address** of the sprite data:

6. If the code uses a pointer in zero-page (direct page), use Mesen’s Memory Viewer to inspect that pointer. For example, if it uses (0x20),Y, open the memory viewer to $00:0020 (or equivalent DP page) to read the 3-byte little-endian address stored there (that will give you something like a bank:address).

7. If the code uses a direct long address (e.g. LDA $xx:yyyy), that xx:yyyy is the SNES address of the data.

8. If using DMA, the combination of $4304 (bank) and $4302/$4303 (address) gives the SNES source address of the data transfer.

9. **Example:** Suppose you find the game was reading from bank $95 at address $B000 (just as an illustration). That means the sprite’s compressed graphics data starts at SNES address $95:B000. Keep a note of your found address.

10. **Confirm it’s in ROM:** SNES cartridge ROM addresses in LoROM typically fall in the range $00:8000-$7D:FFFF or $80:8000-$FF:FFFF (with some mirroring)[\[5\]](https://snes.nesdev.org/wiki/Memory_map#:~:text=Image)[\[6\]](https://snes.nesdev.org/wiki/Memory_map#:~:text=The%20unused%20lower%20half%20of,FFFF). The address you find should correspond to the ROM area (not Work RAM $7E/$7F or SA-1 IRAM $40-$43, etc.). If your address is in $00-$3F or $80-$BF with an offset ≥$8000, it’s likely in the ROM. (For Kirby’s SA-1, banks $00-$3F and $80-$BF are used for the 4MB ROM data due to LoROM mapping.)

11. **Optional – Follow the call stack:** If it’s not immediately clear, you can also look at the call stack or trace log. Often a subroutine is responsible for decompression. The **JSR** that led here might have loaded the address from a table. Scanning earlier code for how that pointer or address was set can be insightful (e.g., the game might have a table of sprite data offsets).

## Step 5: Determine the ROM File Offset of the Sprite Data

Now that you have the SNES memory address of the sprite’s graphics data, convert it to a file offset in the ROM:

* **LoROM address conversion:** In LoROM mapping, the ROM is divided into 32 KB banks[\[7\]](https://www.smwcentral.net/?p=viewthread&t=124174#:~:text=And%20notably%2C%20it%20even%20integrates,are%20only%20%248000%20bytes%20each). The general formula (for an unheadered ROM) is:

File Offset=Bank & 0x7F0x8000+Address−0x8000

* This assumes the SNES address is $Bank:Address and Address ≥ $8000. In simpler terms, drop the high bit of the bank and multiply by 0x8000, then add the offset within the bank beyond $8000.

* **Example:** If the SNES address of the data is $95:B000, the bank is 0x95. Masking with 0x7F gives 0x15 (bank $15 in zero-based count). The address offset within the bank is $B000 \- $8000 \= $3000. So the file offset \= 0x15 \* 0x8000 \+ 0x3000. Calculate that: 0x15 \* 0x8000 \= 0x0A0000, plus 0x3000 \= **0x0A3000**. So the data would start at file offset 0xA3000 in the ROM file. (This is just an example; use your actual address in the formula.)

* **Use Mesen’s memory viewer as a helper:** Mesen 2 can show both SNES addresses and ROM offsets. In the Memory Viewer, set the source to **S-CPU Bus** (SNES CPU memory). Go to the SNES address you found (e.g., enter 95:B000). Then switch the source to **PRG ROM** – the viewer will show the raw ROM at the corresponding file location[\[8\]](https://www.romhacking.net/forum/index.php?topic=37405.0#:~:text=SNES%2FHex%20question%20,For%20an%20unheadered%20ROM). The address shown in the PRG ROM mode is the file offset (for an unheadered ROM, this should align with the calculation above). This is a good way to double-check your conversion.

At this point, you have the exact **ROM offset** (in the .smc/.sfc file) where the sprite’s compressed graphics data begins.

## Step 6: Verify by Decompressing or Viewing the Data (Optional)

To be sure you’ve got the correct bytes, you can verify the data:

* **Use exhal:** Kirby Super Star’s graphics are compressed with HAL Laboratory’s custom algorithm (not easily viewable in a tile editor until decompressed). The utility **exhal** (by Revenant) can decompress Kirby Super Star’s data[\[9\]](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star#:~:text=Utilities). Use exhal on the ROM with the offset you found to extract the graphics. For example, from a command line:

* exhal \-c kirby\_super\_star.sfc \<offset\_in\_hex\> \<output.bin\>

* (Refer to exhal’s documentation for exact usage and whether you need to specify length or it auto-detects.) The output.bin should contain the decompressed tile data, which you can view in a tile editor to confirm it’s the sprite (look for the Cappy graphics in 4bpp format).

* **Alternative verification:** If exhal is available, it will confirm the compression. Otherwise, if the data was not compressed (rare for this game, but hypothetically), you could open the ROM in a tile viewer at the file offset and check if the graphics appear (likely they won’t until decompressed).

## Conclusion

By using Mesen 2’s debugger and tile viewer, we traced the on-screen sprite through VRAM back to its source in the ROM. The key steps were setting a **VRAM write breakpoint** to catch when the game loads the sprite’s graphics, then examining the debugger to find the **SNES memory address** of the data and converting that to a **ROM file offset**. This workflow can be repeated for any visible sprite or graphic in the game. With the ROM offset known, you can now modify or extract the sprite – for example, edit the graphics (after decompression) or replace them and recompress with inhal (the companion tool) if you are modding the game[\[9\]](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star#:~:text=Utilities). This method provides a precise link from what you see on screen all the way back to the original ROM bytes.

**Sources:**

* Mesen 2 VRAM debugging tools[\[2\]](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/#:~:text=Happily%2C%20the%20Mesen%202%20emulator,VRAM%20debugger%20render%20for%20us)[\[3\]](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/#:~:text=One%20thing%20that%20will%20become,this%20is%20a%20wacky%20choice)

* SNES VRAM and LoROM memory details[\[5\]](https://snes.nesdev.org/wiki/Memory_map#:~:text=Image)[\[7\]](https://www.smwcentral.net/?p=viewthread&t=124174#:~:text=And%20notably%2C%20it%20even%20integrates,are%20only%20%248000%20bytes%20each)

* Breakpoint technique for locating graphics in ROM[\[4\]](https://www.reddit.com/r/romhacking/comments/1jl2s3t/help_with_vegas_stakes_snes_graphics_tilesets/#:~:text=replacement%20www,It%20will)

* Kirby Super Star ROM info and compression tools[\[1\]](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star#:~:text=Header%20None%20Bank%20LoROM%20Interleaved,ROM%204%20MiB%20Country%20USA)[\[9\]](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star#:~:text=Utilities)

---

[\[1\]](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star#:~:text=Header%20None%20Bank%20LoROM%20Interleaved,ROM%204%20MiB%20Country%20USA) [\[9\]](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star#:~:text=Utilities) Kirby Super Star \- Data Crystal

[https://datacrystal.tcrf.net/wiki/Kirby\_Super\_Star](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star)

[\[2\]](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/#:~:text=Happily%2C%20the%20Mesen%202%20emulator,VRAM%20debugger%20render%20for%20us) [\[3\]](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/#:~:text=One%20thing%20that%20will%20become,this%20is%20a%20wacky%20choice) SNES Graphics Data | Bumbershoot Software

[https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/](https://bumbershootsoft.wordpress.com/2023/09/16/snes-graphics-data/)

[\[4\]](https://www.reddit.com/r/romhacking/comments/1jl2s3t/help_with_vegas_stakes_snes_graphics_tilesets/#:~:text=replacement%20www,It%20will) Help with Vegas Stakes (SNES) graphics / tilesets replacement

[https://www.reddit.com/r/romhacking/comments/1jl2s3t/help\_with\_vegas\_stakes\_snes\_graphics\_tilesets/](https://www.reddit.com/r/romhacking/comments/1jl2s3t/help_with_vegas_stakes_snes_graphics_tilesets/)

[\[5\]](https://snes.nesdev.org/wiki/Memory_map#:~:text=Image) [\[6\]](https://snes.nesdev.org/wiki/Memory_map#:~:text=The%20unused%20lower%20half%20of,FFFF) Memory map \- SNESdev Wiki

[https://snes.nesdev.org/wiki/Memory\_map](https://snes.nesdev.org/wiki/Memory_map)

[\[7\]](https://www.smwcentral.net/?p=viewthread&t=124174#:~:text=And%20notably%2C%20it%20even%20integrates,are%20only%20%248000%20bytes%20each) Getting Started with Debugging \- Tutorials \- SMW Central

[https://www.smwcentral.net/?p=viewthread\&t=124174](https://www.smwcentral.net/?p=viewthread&t=124174)

[\[8\]](https://www.romhacking.net/forum/index.php?topic=37405.0#:~:text=SNES%2FHex%20question%20,For%20an%20unheadered%20ROM) SNES/Hex question \- ROMhacking.net

[https://www.romhacking.net/forum/index.php?topic=37405.0](https://www.romhacking.net/forum/index.php?topic=37405.0)
