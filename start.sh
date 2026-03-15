#!/bin/bash
set -e

# Define project root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

echo "[*] Starting DeadDrop Environment..."

# Ensure virtual environment exists
if [ ! -d "venv" ]; then
    echo "[!] Virtual environment not found. Please run setup.sh first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Launch Uvicorn
echo "[*] Launching Uvicorn Server on 0.0.0.0:8000..."
uvicorn main:app --host 0.0.0.0 --port 8000
