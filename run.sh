#!/bin/bash

# Define the virtual environment directory
VENV_DIR="venv"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
else
    echo "Warning: requirements.txt not found."
fi

# Check for system dependencies (ffmpeg, exiftool)
echo "Checking system dependencies..."

if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    else
        echo "Error: Homebrew not found. Please install ffmpeg manually."
    fi
else
    echo "ffmpeg is already installed."
fi

if ! command -v exiftool &> /dev/null; then
    echo "exiftool not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install exiftool
    else
        echo "Error: Homebrew not found. Please install exiftool manually."
    fi
else
    echo "exiftool is already installed."
fi

# Run the main script
echo "Starting Media Organizer..."
python3 media_organizer.py
