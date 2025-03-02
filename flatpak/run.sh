#!/bin/bash

# Get the absolute path of the script's directory
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Set WINECHARM relative to the script's directory
WINECHARM="$SCRIPT_DIR/../src/winecharm.py"

# Copy the file and run flatpak commands
cp "$WINECHARM" ~/.local/share/flatpak/app/io.github.fastrizwaan.WineCharm/current/active/files/bin/winecharm && echo "Copied $WINECHARM"
flatpak kill io.github.fastrizwaan.WineCharm 2> /dev/null
flatpak run io.github.fastrizwaan.WineCharm
