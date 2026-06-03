#!/bin/bash
#flatpak-builder --user --install --force-clean build-dir io.github.fastrizwaan.diction.yaml
flatpak-builder \
  --force-clean \
  --disable-rofiles-fuse \
  --user \
  --install \
  build-dir io.github.fastrizwaan.WineCharm.yaml

