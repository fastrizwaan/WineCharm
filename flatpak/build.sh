#!/bin/bash

# Ensure required runtimes are installed
echo "Installing required runtimes..."
flatpak install -y org.gnome.Sdk/x86_64/47 org.gnome.Platform/x86_64/47 org.winehq.Wine//stable-24.08

if [ "$1" = "bundle" ]; then
    echo "Building and bundling WineCharm..."
    flatpak-builder --force-clean build-dir io.github.fastrizwaan.WineCharm.yaml
    flatpak build-bundle build-dir WineCharm.flatpak io.github.fastrizwaan.WineCharm
else
    echo "Building and running WineCharm..."
    flatpak-builder --user --install --repo=repo --force-clean build-dir io.github.fastrizwaan.WineCharm.yaml
    flatpak kill io.github.fastrizwaan.WineCharm  # Kill any running instance
    flatpak run io.github.fastrizwaan.WineCharm
fi
