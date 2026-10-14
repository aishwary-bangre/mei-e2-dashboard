#!/bin/bash

# Make sure we are in the script's directory
cd "$(dirname "$0")"

echo "=========================================================="
echo "      Lens Shape Correction QC Dashboard Startup"
echo "=========================================================="

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "Error: python is not installed or not in PATH."
    exit 1
fi

# Print current dir
echo "Working directory: $(pwd)"

# Install dependencies if not already installed (done in system path if possible)
echo "Ensuring required Python libraries are installed..."
python -c "import pandas, openpyxl, fastapi, uvicorn, calamine, rapidfuzz" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing missing libraries (pandas, openpyxl, fastapi, uvicorn, python-calamine, python-multipart, rapidfuzz)..."
    python -m pip install pandas openpyxl fastapi uvicorn python-calamine python-multipart rapidfuzz 2>/dev/null || \
    python -m pip install --break-system-packages pandas openpyxl fastapi uvicorn python-calamine python-multipart rapidfuzz 2>/dev/null || \
    uv pip install pandas openpyxl fastapi uvicorn python-calamine python-multipart rapidfuzz
else
    echo "All dependencies verified successfully."
fi

# Start backend server
echo "----------------------------------------------------------"
echo "Starting FastAPI server on http://localhost:8000"
echo "You can open http://localhost:8000 in your browser."
echo "Press Ctrl+C to stop the server."
echo "----------------------------------------------------------"

PYTHONPATH=. python backend/main.py
