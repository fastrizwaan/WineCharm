echo "flatpak install org.gnome.Sdk/x86_64/47 org.gnome.Platform/x86_64/47 org.winehq.Wine//stable-24.08"
flatpak-builder --user --install --repo=repo --force-clean build-dir io.github.fastrizwaan.WineCharm.yaml ; flatpak kill io.github.fastrizwaan.WineCharm; flatpak run io.github.fastrizwaan.WineCharm
