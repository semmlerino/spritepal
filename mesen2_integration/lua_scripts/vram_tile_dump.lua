-- vram_tile_dump.lua
-- Press F11 to dump tile data from a VRAM address
-- Compare output to extracted sprites to find ROM source

local function dump_tile(vram_addr, num_tiles)
    num_tiles = num_tiles or 1

    emu.log("========================================")
    emu.log(string.format("VRAM TILE DUMP @ $%04X (%d tiles)", vram_addr, num_tiles))
    emu.log("========================================")

    local bytes_per_tile = 32  -- 4bpp 8x8 tile
    local total_bytes = num_tiles * bytes_per_tile

    local hex_lines = {}
    local all_bytes = {}

    for i = 0, total_bytes - 1 do
        local byte = emu.read(vram_addr + i, emu.memType.snesVideoRam)
        table.insert(all_bytes, byte)

        if i % 16 == 0 then
            table.insert(hex_lines, string.format("$%04X: ", vram_addr + i))
        end
        hex_lines[#hex_lines] = hex_lines[#hex_lines] .. string.format("%02X ", byte)
    end

    for _, line in ipairs(hex_lines) do
        emu.log(line)
    end

    -- Also show as pattern for searching
    emu.log("")
    emu.log("First 16 bytes (for ROM search):")
    local pattern = ""
    for i = 1, math.min(16, #all_bytes) do
        pattern = pattern .. string.format("%02X ", all_bytes[i])
    end
    emu.log(pattern)

    emu.log("========================================")
    return all_bytes
end

-- Configuration: Set these to the sprite you want to dump
local target_vram_addr = 0x6650  -- From Sprite Viewer "Tile address"
local target_num_tiles = 4       -- Dump 4 tiles (32x8 or 16x16 sprite)

local prev_f11 = false

emu.addEventCallback(function()
    local f11 = emu.isKeyPressed("F11")

    if f11 and not prev_f11 then
        dump_tile(target_vram_addr, target_num_tiles)

        -- Also dump nearby tiles (character might span multiple)
        emu.log("")
        emu.log("Adjacent tiles:")
        for offset = 0x20, 0x60, 0x20 do
            local addr = target_vram_addr + offset
            emu.log(string.format("  $%04X:", addr))
            local line = "    "
            for i = 0, 15 do
                line = line .. string.format("%02X ", emu.read(addr + i, emu.memType.snesVideoRam))
            end
            emu.log(line)
        end
    end

    prev_f11 = f11
end, emu.eventType.endFrame)

emu.log("========================================")
emu.log("VRAM TILE DUMPER")
emu.log("========================================")
emu.log(string.format("Target: VRAM $%04X (%d tiles)", target_vram_addr, target_num_tiles))
emu.log("")
emu.log("Press F11 to dump tile data")
emu.log("Compare output to extracted .bin files")
emu.log("========================================")
