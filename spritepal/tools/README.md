# HAL Compression Tools

This directory contains platform-specific binaries for HAL compression tools (exhal/inhal) used by SpritePal for ROM extraction and injection.

**What these tools do:**
- `exhal` / `exhal.exe` - HAL decompression (extracts sprite data from ROM)
- `inhal` / `inhal.exe` - HAL compression (injects modified sprites back into ROM)

## Building the Tools

To compile the tools for your platform, run from the spritepal directory:

```bash
python compile_hal_tools.py          # Build for current platform
python compile_hal_tools.py --check  # Verify tools exist without building
python compile_hal_tools.py --clean  # Remove compiled binaries
python compile_hal_tools.py --force  # Rebuild even if tools exist
```

**Exit codes:**
- 0: Success
- 1: Compiler not found (install gcc/MinGW)
- 2: Source files not found
- 3: Compilation failed (check error output)

### Windows Requirements
- MinGW-w64 (recommended) or Visual Studio
- Download MinGW-w64 from: https://www.mingw-w64.org/downloads/

### Linux/macOS Requirements
- GCC or Clang
- Install with: `sudo apt-get install build-essential` (Ubuntu/Debian)

## Manual Compilation

If the automatic script doesn't work, you can compile manually:

### Windows (MinGW)
```batch
cd ..\archive\obsolete_test_images\ultrathink
gcc -O2 -o exhal.exe exhal.c compress.c
gcc -O2 -o inhal.exe inhal.c compress.c
copy *.exe ..\..\..\..\spritepal\tools\
```

### Linux/macOS
```bash
cd ../archive/obsolete_test_images/ultrathink
gcc -O2 -o exhal exhal.c compress.c
gcc -O2 -o inhal inhal.c compress.c
cp exhal inhal ../../../../spritepal/tools/
chmod +x ../../../../spritepal/tools/*
```

## Expected Files

After compilation, this directory should contain:
- Windows: `exhal.exe`, `inhal.exe`
- Linux/macOS: `exhal`, `inhal`
- `.platform_windows` or `.platform_linux` marker file