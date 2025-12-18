#!/bin/bash
# Script to run the sprite gallery layout test with proper environment setup

echo "🔧 Sprite Gallery Layout Test Runner"
echo "=================================="
echo ""

# Check if we're in the right directory
if [ ! -f "test_gallery_layout_fix.py" ]; then
    echo "❌ Error: test_gallery_layout_fix.py not found"
    echo "Please run this script from the spritepal directory"
    exit 1
fi

# Check for Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found"
    echo "Please install Python 3"
    exit 1
fi

# Check if virtual environment exists and activate it if available
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
elif [ -d "../venv" ]; then
    echo "📦 Activating virtual environment from parent directory..."
    source ../venv/bin/activate
else
    echo "⚠️  No virtual environment found, using system Python"
fi

# Set up display for headless environments if needed
if [ -z "$DISPLAY" ]; then
    echo "🖥️  No display detected, using Qt offscreen mode..."
    export QT_QPA_PLATFORM=offscreen
fi
PYTHON_CMD="python3"

# Check for required dependencies
echo "🔍 Checking dependencies..."
if ! $PYTHON_CMD -c "import PySide6" 2>/dev/null; then
    echo "❌ Error: PySide6 not installed"
    echo "Install with: pip install PySide6"
    exit 1
fi

echo "✅ Dependencies OK"
echo ""

# Run the test
echo "🚀 Launching Gallery Layout Test..."
echo "Press Ctrl+C to stop the test"
echo ""

$PYTHON_CMD test_gallery_layout_fix.py

# Check exit status
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Test completed successfully"
else
    echo ""
    echo "❌ Test failed or was interrupted"
    exit 1
fi