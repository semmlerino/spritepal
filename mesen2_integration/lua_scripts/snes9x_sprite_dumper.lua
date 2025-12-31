-- SNES9x-rr Lua Script for Kirby Super Star Sprite Dumping
-- This script helps find sprite data by dumping memory at key points

-- Configuration
local OUTPUT_DIR = "memory_dumps/"
local DUMP_COUNTER = 0
local LAST_FRAME = 0

-- Memory regions
local VRAM_START = 0x7E0000  -- VRAM in SNES memory map
local VRAM_SIZE = 0x10000    -- 64KB
local CGRAM_START = 0x7E0000 -- CGRAM location (need to find exact address)
local CGRAM_SIZE = 0x200     -- 512 bytes

-- Create output directory message
print("Sprite Dumper for Kirby Super Star")
print("Make sure to create 'memory_dumps' folder in snes9x directory")
print("Press P to dump current VRAM/CGRAM")
print("Press S to dump at next sprite load")

-- Helper function to dump memory region
function dump_memory_region(filename, start_addr, size)
    local data = memory.readbyterange(start_addr, size)
    local file = io.open(OUTPUT_DIR .. filename, "wb")
    if file then
        -- Convert byte array to string for writing
        local str = ""
        for i = 0, size - 1 do
            str = str .. string.char(data[i])
        end
        file:write(str)
        file:close()
        return true
    end
    return false
end

-- Dump VRAM and CGRAM
function dump_sprite_memory()
    DUMP_COUNTER = DUMP_COUNTER + 1
    local frame = emu.framecount()
    
    print(string.format("Dumping memory at frame %d...", frame))
    
    -- Dump VRAM
    local vram_file = string.format("vram_%04d_f%06d.bin", DUMP_COUNTER, frame)
    if dump_memory_region(vram_file, VRAM_START, VRAM_SIZE) then
        print("  VRAM saved to " .. vram_file)
    end
    
    -- Try to find and dump CGRAM
    -- CGRAM is typically accessed via PPU registers
    -- We'll need to find the exact location in WRAM
    local cgram_file = string.format("cgram_%04d_f%06d.bin", DUMP_COUNTER, frame)
    -- Note: CGRAM location needs to be determined
    
    -- Also dump some key RAM areas that might contain decompressed sprites
    local ram_file = string.format("wram_%04d_f%06d.bin", DUMP_COUNTER, frame)
    if dump_memory_region(ram_file, 0x7E0000, 0x20000) then  -- First 128KB of WRAM
        print("  WRAM saved to " .. ram_file)
    end
    
    -- Log current game state
    local log_file = io.open(OUTPUT_DIR .. string.format("dump_%04d_info.txt", DUMP_COUNTER), "w")
    if log_file then
        log_file:write(string.format("Frame: %d\n", frame))
        log_file:write(string.format("PC: $%06X\n", memory.getregister("pc")))
        -- Add more game state info as needed
        log_file:close()
    end
end

-- Monitor for sprite decompression routine
function monitor_decompression()
    local pc = memory.getregister("pc")
    
    -- Known decompression routine address (from documentation)
    if pc == 0x00889A then
        print("Decompression routine called!")
        -- Could dump memory here or set a flag
    end
    
    -- Monitor DMA transfers to VRAM (common for sprite uploads)
    local dma_enable = memory.readbyte(0x420B)
    if dma_enable ~= 0 then
        -- Check if DMA is writing to VRAM
        for channel = 0, 7 do
            if bit.band(dma_enable, bit.lshift(1, channel)) ~= 0 then
                local dma_dest = memory.readbyte(0x4301 + channel * 0x10)
                if dma_dest == 0x18 or dma_dest == 0x19 then  -- VRAM data register
                    print(string.format("DMA to VRAM on channel %d", channel))
                    -- Could trigger dump here
                end
            end
        end
    end
end

-- Keyboard input handler
function handle_input()
    local keys = input.get()
    
    -- P key: Manual dump
    if keys["P"] and not LAST_P_STATE then
        dump_sprite_memory()
    end
    LAST_P_STATE = keys["P"]
    
    -- S key: Toggle sprite monitoring
    if keys["S"] and not LAST_S_STATE then
        MONITOR_SPRITES = not MONITOR_SPRITES
        print("Sprite monitoring: " .. (MONITOR_SPRITES and "ON" or "OFF"))
    end
    LAST_S_STATE = keys["S"]
end

-- Frame callback
function on_frame()
    handle_input()
    
    if MONITOR_SPRITES then
        monitor_decompression()
    end
    
    -- Auto-dump every 1000 frames if enabled
    if AUTO_DUMP and emu.framecount() % 1000 == 0 then
        dump_sprite_memory()
    end
end

-- Global state
MONITOR_SPRITES = false
AUTO_DUMP = false
LAST_P_STATE = false
LAST_S_STATE = false

-- Memory access hooks for specific addresses
-- Hook the decompression routine
memory.registerexec(0x00889A, function()
    print(string.format("HAL decompression at frame %d", emu.framecount()))
    -- Could auto-dump here
end)

-- Hook sprite-related memory regions
-- These addresses would need to be determined for Kirby Super Star
--[[
memory.registerwrite(0x2116, function(addr, val)
    -- VRAM address register write
    local vram_addr = val + (memory.readbyte(0x2117) * 256)
    if vram_addr >= 0x6000 and vram_addr < 0x8000 then
        print(string.format("VRAM write to sprite area: $%04X", vram_addr))
    end
end)
]]

-- Register frame callback
emu.registerafter(on_frame)

print("Sprite dumper loaded!")
print("Commands:")
print("  P - Dump current memory")
print("  S - Toggle sprite monitoring")

-- Optional: Create a marker when at specific game states
-- You can add more conditions based on RAM values that indicate
-- specific game modes or sprite test modes
function check_game_state()
    -- Example: Check for sprite test mode
    -- These addresses are examples and need to be found for Kirby
    local game_mode = memory.readbyte(0x7E0100)
    if game_mode == 0x07 then  -- Hypothetical sprite test mode value
        print("Sprite test mode detected!")
        dump_sprite_memory()
    end
end

-- Tips for finding sprite data:
-- 1. Look for DMA transfers to VRAM addresses 0x4000-0x7000 (common sprite areas)
-- 2. Monitor calls to decompression routine at $00889A
-- 3. Check for patterns in WRAM that match known sprite data
-- 4. Use frame advance to catch exact moments when sprites are loaded