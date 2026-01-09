# Automating Mesen2 to Find Sprite Offsets in Kirby Super Star

## Running Mesen2 via Command-Line with Lua Scripts

**Mesen2’s Test Runner Mode:** Mesen2 (the multi-system emulator) supports a special *“test runner”* mode that lets you launch a game ROM along with a Lua script from the command line. In this mode, Mesen2 runs headlessly (no GUI) at max speed and executes the provided Lua script for automation[\[1\]](https://www.mesen.ca/docs/apireference.html#test-runner-mode#:~:text=To%20start%20Mesen%20in%20headless,a%20Lua%20script%20to%20run). For example, you can start Mesen2 with a Kirby Super Star ROM and a custom script by running a command (from WSL or a terminal) like:

mesen.exe \--testrunner "C:\\path\\to\\KirbySuperStar.sfc" "C:\\path\\to\\script.lua"

This will load the SNES ROM and immediately run the Lua script. The script can then drive the emulation, set breakpoints, and even terminate Mesen when finished (using emu.stop())[\[1\]](https://www.mesen.ca/docs/apireference.html#test-runner-mode#:~:text=To%20start%20Mesen%20in%20headless,a%20Lua%20script%20to%20run). Using this method, **Claude’s code assistant** (via WSL) can programmatically launch the emulator and control it, rather than you having to manually use the GUI.

**Linux vs Windows:** Mesen2 is available on Windows and Linux[\[2\]](https://www.mesen.ca/#:~:text=Mesen%20is%20a%20multi,It%20supports%20the%20following%20consoles)[\[3\]](https://www.mesen.ca/#:~:text=Latest%20version%3A%202,2025). If you’re using WSL on a Windows machine, you have two options: either compile/run the Linux version of Mesen2 under WSL, or invoke the Windows Mesen2 .exe from WSL (providing Windows-style file paths for the ROM and script). Both approaches work – the key is that the \--testrunner option lets the emulator be controlled purely via scripts and command-line, which is ideal for automation.

## Leveraging Mesen2’s Lua Debugger Capabilities

**Embedded Lua Scripting:** Mesen2 has a built-in Lua scripting interface that gives you access to powerful debugging tools[\[4\]](https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833#:~:text=,scripts%20included%20within%20the%20emulation). Through Lua, you can read or write memory, set breakpoints on memory access, run code when certain events occur, and even simulate controller input. In essence, **any action you could do in the GUI debugger (and more)** can be automated with a Lua script[\[4\]](https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833#:~:text=,scripts%20included%20within%20the%20emulation). We will use these capabilities to find where sprite graphics are stored in the ROM.

**Simulating Controller Input:** To get to the part of the game where certain sprites load, your script can simulate button presses. Mesen’s Lua API allows injecting controller input on any frame. For example, you can register a callback that runs every frame (or every time input is polled) and at specific frame counts have it press the **Start** button or other keys. In code, this looks like:

emu.addEventCallback(function()  
    local frame \= emu.getState().ppu.frameCount  
    if frame \== 60 then   
        emu.setInput(0, { start \= true })  \-- press Start after \~60 frames  
    elseif frame \== 120 then   
        emu.setInput(0, { A \= true })      \-- press A at frame 120 (for menu selection, etc.)  
    end   
end, emu.eventType.inputPolled)

In the above snippet, the script waits 60 frames (1–2 seconds) then sends a Start button press, and sends an A button at 120 frames. This is just an example – you would adjust the timing and buttons according to Kirby Super Star’s menus. For instance, you might press Start to skip the title screen, then navigate the game select menu (with D-pad or A), and press Start again to begin a level. Using a technique like this, you can automate entering **Spring Breeze** (or whichever sub-game) and starting a stage so that Kirby and other sprites appear. The key is that **Claude’s code** can generate and adjust these Lua callbacks for input to ensure the game reaches the point where the target sprites are loaded (as shown in a similar scripting approach on NES[\[5\]](https://forums.nesdev.org/viewtopic.php?t=23598&start=15#:~:text=,start%20%3D%20true)).

**Memory Breakpoints via Lua:** Mesen’s Lua API also lets us set breakpoints or hooks on memory accesses[\[4\]](https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833#:~:text=,scripts%20included%20within%20the%20emulation). Specifically, we can register a **memory callback** that triggers when the SNES CPU reads or writes certain addresses. By leveraging this, we can catch the moment when Kirby Super Star loads sprite graphics data from the ROM. There are two main strategies:

* **Break on ROM Reads:** We could watch for CPU **read** access from the ROM address range. However, many code instructions also reside in ROM, so triggering on *all* ROM reads would be noisy. We’d have to narrow it down to specific ranges or patterns (e.g. if we know roughly where graphics data might be, or during a certain time window).

* **Break on VRAM Writes (via DMA):** A more efficient method is to catch when the game *writes sprite graphics into VRAM*. On SNES, graphics (tiles for sprites) are typically transferred from ROM into VRAM (Video RAM) using DMA. By intercepting the DMA transfer that uploads sprite tiles, we can identify the source ROM address of the graphics. This method is precise and doesn’t trigger for unrelated ROM usage.

We will use the **DMA approach**, as it’s commonly used for bulk graphics transfers on SNES.

## Setting Breakpoints to Locate Sprite Graphics in the ROM

To find the exact ROM offset of Kirby Super Star’s sprite data, we can script the following steps:

1. **Hook the DMA Register:** In SNES, writing to address $420B initiates a DMA transfer. We add a memory write callback on $420B (the DMA trigger register). For example:

emu.addMemoryCallback(function(address, value)  
    \-- This function runs whenever the CPU writes to $420B  
    \-- (The 'value' contains which DMA channels are triggered)  
    \-- We will inspect the DMA parameters here...  
end, emu.callbackType.write, 0x420B, 0x420B)

The emu.addMemoryCallback registers our function to be called on every **write** to the specified address range (here just 0x420B)[\[6\]](https://pastebin.com/z9w7Dj5Q#:~:text=891.%20read%20,called%20when%20data%20is%20read). This means as soon as the game triggers any DMA, our Lua code will execute.

1. **Identify VRAM DMA Transfers:** Inside the callback, we need to check if the DMA is transferring sprite graphics to VRAM. Kirby Super Star might use multiple DMA channels for various purposes (graphics, audio, etc.), but sprite tile transfers can be recognized by their target address. In SNES DMA registers:

2. $4301 (for channel 0\) holds the **destination register** on the PPU’s bus. For VRAM transfers, this is usually 0x18 (which corresponds to writing to PPU register $2118, the VRAM data port)[\[7\]](https://www.smwcentral.net/?p=viewthread&t=84388#:~:text=LDA%20,and).

3. $4302,$4303,$4304 form the 24-bit **source address** in SNES memory (bank: $4304, low 16-bit: $4302/$4303).

4. $4305,$4306 give the transfer length (number of bytes, typically a multiple of 32 bytes for tile data).

In the callback, we can loop through all DMA channels indicated by the bitmask in value (e.g. if value & 0x01 is set, channel 0 is used; if 0x02, channel 1, etc.). For each active channel, read these registers via the Lua memory read functions. For example:

\-- Inside the DMA callback:  
for channel=0,7 do  
    if bit.band(value, 1\<\<channel) \~= 0 then  
        local base \= 0x4300 \+ channel\*0x10  \-- base address for this channel’s regs  
        local destReg \= emu.read(base \+ 1, emu.memType.cpuDebug)    \-- $4301  
        local ctrl    \= emu.read(base \+ 0, emu.memType.cpuDebug)    \-- $4300 (control)  
        \-- Check if this is DMA to PPU (bit7 of ctrl \= 0 means CPU-\>PPU) and dest \= $2118  
        if destReg \== 0x18 and bit.band(ctrl, 0x80) \== 0 then   
            \-- It's a VRAM graphics DMA\! Now get source address:  
            local srcLo   \= emu.read(base \+ 2, emu.memType.cpuDebug)  \-- $4302  
            local srcHi   \= emu.read(base \+ 3, emu.memType.cpuDebug)  \-- $4303  
            local srcBank \= emu.read(base \+ 4, emu.memType.cpuDebug)  \-- $4304  
            local srcAddr \= srcBank \* 0x10000 \+ srcHi \* 0x100 \+ srcLo  \-- 24-bit SNES address  
            \-- (Now we’ll convert this to a ROM file offset below)  
        end  
    end  
end

The above pseudo-code checks each DMA channel triggered, and if it finds one whose destination is $2118 (VRAM data port) and direction is from CPU memory to PPU, we assume this is a graphics upload. We then compute the 24-bit SNES source address of the data.

1. **Convert SNES Address to ROM Offset:** SNES uses a mapped address space, so we need to convert the 24-bit CPU address (srcAddr) into a byte offset in the actual ROM file. Mesen2 provides helper functions for this. We can use emu.getPrgRomOffset(address) which returns the corresponding offset in the ROM’s PRG data (or \-1 if the address isn’t in ROM)[\[8\]](https://www.mesen.ca/docs/apireference/memoryaccess.html#:~:text=Syntax). For example:

local offset \= emu.getPrgRomOffset(srcAddr)  
if offset and offset \>= 0 then   
    emu.displayMessage("SpriteGFX", string.format(  
        "Sprite data DMA from ROM offset $%06X", offset))  
    \-- Optionally log to file:  
    local f \= io.open("sprite\_offset.txt", "w")  
    f:write(string.format("Sprite graphics found at ROM offset 0x%06X\\n", offset))  
    f:close()  
    emu.stop(0)  \-- stop emulation (exit) once found  
end

Here we check that the source address maps to ROM (not RAM). If it does, we format the offset as a hex string and output it. We used emu.displayMessage("SpriteGFX", "...") to show a message in the emulator’s HUD[\[9\]](https://www.mesen.ca/docs/apireference/logging.html#:~:text=Description%20Displays%20a%20message%20on,category%5D%20text%E2%80%9D) – in headless mode this may not be visible, so we also write it to a text file. The script then calls emu.stop(0) to terminate Mesen after capturing the info (so the \--testrunner process will exit)[\[10\]](https://www.mesen.ca/docs/apireference.html#test-runner-mode#:~:text=Mesen.exe%20).

**Note:** If the game’s graphics are compressed, the DMA source might be in **WRAM** (RAM) instead of ROM (meaning the game decompressed the sprite into RAM then transferred to VRAM). In that case, getPrgRomOffset will return \-1. To handle this, you could also set a **read breakpoint on the ROM** during the decompression routine – but that requires identifying where the decompression reads from. In practice, many Kirby Super Star sprite graphics are compressed in the ROM[\[11\]](https://www.reddit.com/r/romhacking/comments/1kuianz/where_to_start_on_rom_hacking/#:~:text=Also%2C%20from%20some%20experience%20digging,typically%20for). You might need to let the game decompress them first. One approach is to let the game run a bit and catch *any* reads from ROM during the time before the DMA (perhaps by setting a temporary callback on a broad ROM range when you detect a specific sprite is about to load). This can reveal the compressed data location if VRAM DMA alone isn’t sufficient. However, for many cases, the above DMA catch is enough to pinpoint the ROM offset of graphics data being transferred.

1. **Run the Script to Find Offsets:** With the script set up to press the necessary buttons and break on the sprite DMA, you can now run Mesen2 via the command line (as described earlier). Claude (or any code assistant) can generate this Lua script for you and even launch the process. Once the script runs, it will output the ROM offset(s) where sprite graphics were pulled from. For example, it might log something like:

\[SpriteGFX\] Sprite data DMA from ROM offset $2A7B20

This tells you the exact location in the ROM file of the sprite graphics in question. You can cross-verify by opening the ROM in a hex editor or using your extraction tool at that offset.

1. **Using the Offset with Your Extraction Tool:** Now that you have the offset, you can feed it into your graphics extraction tool to rip the sprite. Keep in mind you may need to extract a block of data (e.g. a few KB starting at that offset) to get the full sprite graphics, and you’ll need the correct bit depth/format (SNES typically uses 4bpp tiled graphics for sprites). The extraction tool should handle that if pointed to the right location. If the graphics were compressed, the offset will point to compressed data – you’d then have to either decompress it (if you know the algorithm) or find if the game stores uncompressed frames elsewhere.

By following the above approach, you are **leveraging Claude’s coding capabilities and Mesen2’s scripting** to automate what would normally be tedious manual debugging. The code assistant can write the Lua script to set breakpoints and simulate gameplay, run Mesen2 to collect the data, and finally present you with the ROM offsets for the Kirby Super Star sprites you’re interested in. This greatly speeds up the process of locating sprite data in the ROM, allowing you to then use your extraction tool on those exact offsets.

**Summary of Key Points:**

* We use Mesen2’s \--testrunner mode to run the emulator with a Lua script via command line[\[1\]](https://www.mesen.ca/docs/apireference.html#test-runner-mode#:~:text=To%20start%20Mesen%20in%20headless,a%20Lua%20script%20to%20run), which Claude (in WSL) can invoke.

* The Lua script uses Mesen’s debugging API[\[4\]](https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833#:~:text=,scripts%20included%20within%20the%20emulation) to add breakpoints (memory callbacks) on SNES DMA events and to simulate input presses for automating the game flow[\[5\]](https://forums.nesdev.org/viewtopic.php?t=23598&start=15#:~:text=,start%20%3D%20true).

* When a VRAM DMA for sprite graphics occurs, the script captures the source ROM address and converts it to a file offset using Mesen’s API (e.g. emu.getPrgRomOffset)[\[8\]](https://www.mesen.ca/docs/apireference/memoryaccess.html#:~:text=Syntax).

* The script logs or saves the found offset, then stops the emulator. You can then take that offset and plug it into your sprite extraction workflow.

Using this method, you can systematically find **where exactly in the ROM** the Kirby Super Star sprite data resides, without having to manually step through the game or guess the offsets. The combination of Claude’s automation and Mesen2’s debugger scripting is a powerful way to reverse-engineer ROM data and should greatly simplify your sprite-hunting task. Good luck with your Kirby sprite project\!

**Sources:**

* Mesen Emulator Documentation – *Test Runner Mode*[\[1\]](https://www.mesen.ca/docs/apireference.html#test-runner-mode#:~:text=To%20start%20Mesen%20in%20headless,a%20Lua%20script%20to%20run) (automating ROM \+ Lua script via CLI)

* Mesen Emulator Documentation – *Lua API & Debugging Tools*[\[4\]](https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833#:~:text=,scripts%20included%20within%20the%20emulation) (Lua scripting can use all debugger features)

* Nesdev Forums – *Automated Testing with Mesen’s Lua Scripting*[\[5\]](https://forums.nesdev.org/viewtopic.php?t=23598&start=15#:~:text=,start%20%3D%20true)[\[12\]](https://forums.nesdev.org/viewtopic.php?t=23598&start=15#:~:text=Post%20by%20gauauu%20%C2%BB%20Thu,Jan%2006%2C%202022%208%3A53%20am) (example of simulating input and using test runner mode)

* Mesen Emulator Documentation – *Memory Access Functions*[\[8\]](https://www.mesen.ca/docs/apireference/memoryaccess.html#:~:text=Syntax) (converting SNES addresses to ROM file offsets)

---

[\[1\]](https://www.mesen.ca/docs/apireference.html#test-runner-mode#:~:text=To%20start%20Mesen%20in%20headless,a%20Lua%20script%20to%20run) [\[10\]](https://www.mesen.ca/docs/apireference.html#test-runner-mode#:~:text=Mesen.exe%20) Lua API reference :: Mesen Documentation

[https://www.mesen.ca/docs/apireference.html](https://www.mesen.ca/docs/apireference.html)

[\[2\]](https://www.mesen.ca/#:~:text=Mesen%20is%20a%20multi,It%20supports%20the%20following%20consoles) [\[3\]](https://www.mesen.ca/#:~:text=Latest%20version%3A%202,2025) Mesen \- Emulator

[https://www.mesen.ca/](https://www.mesen.ca/)

[\[4\]](https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833#:~:text=,scripts%20included%20within%20the%20emulation) Mesen NES and Famicom Emulator — Hive

[https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833](https://hive.blog/utopian-io/@pinkwonder/mesen-nes-and-famicom-emulator-1549293625833)

[\[5\]](https://forums.nesdev.org/viewtopic.php?t=23598&start=15#:~:text=,start%20%3D%20true) [\[12\]](https://forums.nesdev.org/viewtopic.php?t=23598&start=15#:~:text=Post%20by%20gauauu%20%C2%BB%20Thu,Jan%2006%2C%202022%208%3A53%20am) Is there an assembler that supports unit testing? \- Page 2 \- nesdev.org

[https://forums.nesdev.org/viewtopic.php?t=23598\&start=15](https://forums.nesdev.org/viewtopic.php?t=23598&start=15)

[\[6\]](https://pastebin.com/z9w7Dj5Q#:~:text=891.%20read%20,called%20when%20data%20is%20read) Mesen Lua API reference\_Mesen Lua 函数库 \- Pastebin.com

[https://pastebin.com/z9w7Dj5Q](https://pastebin.com/z9w7Dj5Q)

[\[7\]](https://www.smwcentral.net/?p=viewthread&t=84388#:~:text=LDA%20,and) \[SOLVED\] How to use DMA? \- ASM & Related Topics \- SMW Central

[https://www.smwcentral.net/?p=viewthread\&t=84388](https://www.smwcentral.net/?p=viewthread&t=84388)

[\[8\]](https://www.mesen.ca/docs/apireference/memoryaccess.html#:~:text=Syntax) Memory Access :: Mesen Documentation

[https://www.mesen.ca/docs/apireference/memoryaccess.html](https://www.mesen.ca/docs/apireference/memoryaccess.html)

[\[9\]](https://www.mesen.ca/docs/apireference/logging.html#:~:text=Description%20Displays%20a%20message%20on,category%5D%20text%E2%80%9D) Logging :: Mesen Documentation

[https://www.mesen.ca/docs/apireference/logging.html](https://www.mesen.ca/docs/apireference/logging.html)

[\[11\]](https://www.reddit.com/r/romhacking/comments/1kuianz/where_to_start_on_rom_hacking/#:~:text=Also%2C%20from%20some%20experience%20digging,typically%20for) Where to start on ROM Hacking? : r/romhacking \- Reddit

[https://www.reddit.com/r/romhacking/comments/1kuianz/where\_to\_start\_on\_rom\_hacking/](https://www.reddit.com/r/romhacking/comments/1kuianz/where_to_start_on_rom_hacking/)