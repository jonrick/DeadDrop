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

# Make start script executable
chmod +x start.sh

# Start Uvicorn Server using the new start script
echo "[*] Setup complete. Launching start.sh..."
./start.sh
