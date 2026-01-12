-- Dump 32 bytes from VRAM for tile comparison with SpritePal
-- Run this when Waddle Dee is visible on screen
--
-- Mesen shows: Tile Index $6C, Tile Address $66C0
-- $66C0 is a WORD address, so byte address = $66C0 * 2 = $CD80

local OUTPUT = "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\vram_tile_dump.txt"

-- Tile address from Mesen sprite viewer (WORD address)
local TILE_WORD_ADDR = 0x66C0
local TILE_BYTE_ADDR = TILE_WORD_ADDR * 2  -- = 0xCD80

-- Also dump a few nearby tiles for context
local TILES_TO_DUMP = {
    {name = "Tile $6C (from Mesen)", word_addr = 0x66C0},
    {name = "Tile $6D", word_addr = 0x66D0},
    {name = "Tile $7C (bottom-left if 16x16)", word_addr = 0x67C0},  -- +16 tiles
    {name = "Tile $7D (bottom-right if 16x16)", word_addr = 0x67D0},
}

local function dump_tile(f, name, word_addr)
    local byte_addr = word_addr * 2
    f:write(string.format("\n%s (VRAM word $%04X, byte $%05X):\n", name, word_addr, byte_addr))

    -- Read 32 bytes
    local bytes = {}
    for i = 0, 31 do
        bytes[i] = emu.read(byte_addr + i, emu.memType.snesVideoRam)
    end

    -- Format like SpritePal output
    f:write("  Bitplanes 0-1 (bytes 0-15):\n")
    f:write("    ")
    for i = 0, 7 do f:write(string.format("%02X ", bytes[i])) end
    f:write("\n    ")
    for i = 8, 15 do f:write(string.format("%02X ", bytes[i])) end
    f:write("\n")

    f:write("  Bitplanes 2-3 (bytes 16-31):\n")
    f:write("    ")
    for i = 16, 23 do f:write(string.format("%02X ", bytes[i])) end
    f:write("\n    ")
    for i = 24, 31 do f:write(string.format("%02X ", bytes[i])) end
    f:write("\n")

    f:write("  All 32 bytes (one line):\n")
    f:write("    ")
    for i = 0, 31 do f:write(string.format("%02X ", bytes[i])) end
    f:write("\n")
end

local captured = false
local fr = 0

emu.addEventCallback(function()
    fr = fr + 1

    -- Wait for gameplay (skip boot/menu)
    -- Adjust timing based on when Waddle Dee is visible
    if fr == 1500 and not captured then
        captured = true

        local f = io.open(OUTPUT, "w")
        f:write("VRAM TILE DUMP - For comparison with SpritePal\n")
        f:write("==============================================\n")
        f:write(string.format("Frame: %d\n", fr))

        -- Read OBSEL to confirm sprite base
        local obsel = emu.read(0x2101, emu.memType.snesRegister) or 0
        local name_base = obsel & 0x07
        f:write(string.format("\nOBSEL: $%02X (OBJ name base: $%04X)\n", obsel, name_base * 0x4000))

        -- Dump tiles
        for _, tile in ipairs(TILES_TO_DUMP) do
            dump_tile(f, tile.name, tile.word_addr)
        end

        -- Also dump what SpritePal has for comparison header
        f:write("\n\n-- SPRITEPAL OUTPUT (from HAL decompression at ROM 0x25AD84) --\n")
        f:write("Tile 0: 02 0F C1 FF 7F 1F 63 BD 52 1E 33 DF 02 FD 15 55 09 05 00 FF 3B 80 03 78 7F B0 7E EA 7D 00 64 05\n")
        f:write("Tile 1: 00 0F C1 FF 7F 3E 43 3E 5A 1E 42 7B 49 F8 50 90 50 05 00 FF 3B 80 03 78 7F B0 7E EA 7D 00 64 00\n")

        f:close()
        emu.displayMessage("Info", "VRAM tile dump saved to vram_tile_dump.txt")

        -- Don't stop - let user continue or stop manually
        -- emu.stop()
    end
end, emu.eventType.endFrame)

emu.displayMessage("Info", "Will dump VRAM tiles at frame 1500. Navigate to gameplay with Waddle Dee visible.")
