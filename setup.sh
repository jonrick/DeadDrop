#!/bin/bash
set -e

echo "[*] Initializing DeadDrop Environment..."

# Update and install requirements (assuming Debian/Ubuntu LXC)
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip sqlite3

# Setup python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install python dependencies
pip install -r requirements.txt

# Start Uvicorn Server setup in the background or foreground
echo "[*] Starting Uvicorn Server on 0.0.0.0:8000..."
uvicorn main:app --host 0.0.0.0 --port 8000
