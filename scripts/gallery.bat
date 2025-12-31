@echo off
REM SpritePal Gallery Launcher for Windows
REM Usage: gallery.bat

set SCRIPT_DIR=%~dp0
if "%SCRIPT_DIR:~-1%"=="\" set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

set PYTHONPATH=%SCRIPT_DIR%

echo Starting SpritePal Gallery...
python -c "import sys, os; sys.path.insert(0, r'%SCRIPT_DIR%'); from PySide6.QtWidgets import QApplication; from ui.windows.detached_gallery_window import DetachedGalleryWindow; from core.managers.registry import initialize_managers; from core.di_container import inject; from core.protocols.manager_protocols import ApplicationStateManagerProtocol, ExtractionManagerProtocol, ROMCacheProtocol; app = QApplication(sys.argv); initialize_managers(); gallery = DetachedGalleryWindow(extraction_manager=inject(ExtractionManagerProtocol), settings_manager=inject(ApplicationStateManagerProtocol), rom_cache=inject(ROMCacheProtocol)); gallery.show(); sys.exit(app.exec())"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Error: Failed to start gallery window.
    echo Make sure PySide6 is installed: pip install PySide6
    pause
)