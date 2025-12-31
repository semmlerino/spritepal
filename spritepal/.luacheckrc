-- Luacheck configuration for Mesen2 Lua scripts

-- Mesen2 API globals (injected by emulator)
-- Plus script-defined globals (callbacks registered with emu.addEventCallback)
globals = {
    -- Mesen2 API
    "emu",
    "snes",
    "ppu",
    "cpu",
    "input",
    "callbacks",
    "memType",
    "cpuType",
    "eventType",
    -- Snes9x API (for snes9x_sprite_dumper.lua)
    "memory",
    -- Script globals (forward-declared functions)
    "on_end_frame",
    "on_start_frame",
    "on_frame",
    "init",
    "cleanup",
    "export_findings",
    "export_json",
}

-- Allow unused arguments (common in callbacks)
unused_args = false

-- Line length (match common Lua style)
max_line_length = 120

-- Ignore certain warnings
ignore = {
    "611",  -- line contains only whitespace
}

-- Ignore archive directory (old/experimental scripts) and snes9x script (different API)
exclude_files = {
    "mesen2_integration/lua_scripts/archive/**",
    "mesen2_integration/lua_scripts/snes9x_sprite_dumper.lua",
}
