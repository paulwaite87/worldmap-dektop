#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Styling variables
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== WorldMap Quick Installer ===${NC}"

# Check for prerequisites
if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Setup installation directory
INSTALL_DIR="$HOME/worldmap"
echo -e "Setting up World Map in ${GREEN}${INSTALL_DIR}${NC}..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Download the production docker-compose file
echo "Downloading configuration..."
curl -fsSL https://raw.githubusercontent.com/paulwaite87/worldmap/refs/heads/master/docker-compose-prod.yml -o docker-compose.yml

# Start the system
echo -e "${BLUE}Starting World Map containers...${NC}"
docker compose -f docker-compose.yml up -d

echo -e "${GREEN}=== Installation Complete! ===${NC}"
echo "World Map is now running in the background."
