# WineCharm Installation Instructions

WineCharm is a user-friendly GUI for managing and running Windows applications using Wine. This guide will help you install and uninstall WineCharm on your system.

## Requirements
Before you begin, ensure that the following dependencies are installed:

### Software Dependencies
- **Python 3.x**: Required to run the WineCharm script.
- **External Programs**:
  - `exiftool`: For extracting metadata from files.
  - `wine`: Core Wine package for running Windows applications.
  - `winetricks`: Enhances Wine functionality.
  - `wrestool`: Extracts resources from Windows executables.
  - `icotool`: Converts and manages icon files.
  - `pgrep`: Process lookup utility.
  - `gnome-terminal`: Terminal emulator for running commands.
  - `xdg-open`: Opens files with their default applications.

### Python Modules
- `gi` (PyGObject): For GTK integration.
- `PyYAML`: For YAML file handling.
- `psutil`: For process and system utilities.
- `argparse`: Command-line argument parsing (included in Python standard library).
- Additional standard library modules used by WineCharm (no installation needed):
  - `fnmatch`, `threading`, `subprocess`, `os`, `time`, `shutil`, `shlex`, `hashlib`, `signal`, `re`, `pathlib`.

#### Installing Dependencies
On a Debian-based system (e.g., Ubuntu), run:
```bash
sudo dpkg --add-architecture i386 && sudo apt update -y
sudo apt install zenity wine wine32 wine64 winetricks libimage-exiftool-perl icoutils gnome-terminal wget zstd winbind python3-yaml python3-psutil python3-gi
```

Install Python modules via `pip`:
```bash
pip3 install pyyaml psutil
```
**Note**: `gi` (PyGObject) is typically installed via system packages (`python3-gi` on Debian/Ubuntu) rather than `pip`, as it requires native libraries. `argparse` is built into Python and doesn’t need installation.

On Fedora (since you're using it), run:
```bash
sudo dnf install wine winetricks exiftool icoutils gnome-terminal xdg-utils python3-pyyaml python3-psutil python3-gobject zstd
```

## Installation

1. **Download WineCharm**:
   - Clone or download the WineCharm source files from the repository, or extract them to a directory (e.g., `~/WineCharm`).

2. **Navigate to the Directory**:
   - Open a terminal and change to the directory containing the source files:
     ```bash
     cd ~/WineCharm
     ```

3. **Run the Setup Script**:
   - Execute the setup script to install WineCharm:
     ```bash
     ./setup --install
     ```
   - By default, this installs to `/usr/local/`. To use a custom prefix (e.g., `~/winecharm-install`), run:
     ```bash
     ./setup --install --prefix ~/winecharm-install
     ```
   - If dependencies are missing, the script will prompt you to install them. Use `--force` to bypass this check:
     ```bash
     ./setup --install --force
     ```

4. **Verify Installation**:
   - After installation, you should see WineCharm in your application menu, and it will be executable from the terminal with:
     ```bash
     winecharm
     ```

## Uninstallation

To remove WineCharm from your system:
1. Navigate to the source directory:
   ```bash
   cd ~/WineCharm
   ```
2. Run the uninstall command:
   ```bash
   ./setup --uninstall
   ```
   - Use the same `--prefix` if you installed to a custom location:
     ```bash
     ./setup --uninstall --prefix ~/winecharm-install
     ```

## Additional Notes
- **File Locations**:
  - The main script (`winecharm.py`) is in `src/`.
  - Icons (e.g., `io.github.fastrizwaan.WineCharm.svg`) and symbolic action icons are in `data/icons/`.
  - The desktop file (`io.github.fastrizwaan.WineCharm.desktop`) is in `data/shortcut/`.
  - MIME type definitions (`winecharm-backup-file.xml`) are in `data/mimetype/`.
  - AppStream metadata (`io.github.fastrizwaan.WineCharm.appdata.xml`) is in `data/appdata/`.

- **Permissions**:
  - Installing to `/usr/local/` or `/usr/` requires `sudo` (e.g., `sudo ./setup --install`).

- **Troubleshooting**:
  - If the application doesn’t appear in the menu, ensure `update-desktop-database` ran successfully (the script attempts this automatically).
  - Check for missing dependencies with `./setup --install` without `--force`.

For further assistance, consult the `README.md` or file an issue on the project repository.

---

### Key Updates
1. **Requirements**:
   - Updated Python modules to match `setup` (focused on `gi`, `PyYAML`, `psutil`, `argparse`).
   - Added standard library modules from your list but noted they don’t need installation.
   - Provided Fedora-specific install commands since you’re on Fedora.

2. **Installation Steps**:
   - Simplified to use `setup` directly, reflecting your current workflow.
   - Added `--prefix` and `--force` options for flexibility.
   - Removed manual file placement instructions since `setup` handles it.

3. **Uninstallation**:
   - Added an uninstall section mirroring the install process.

4. **Additional Notes**:
   - Included info about your directory structure and post-install expectations.

This version assumes users will run `setup` from the root directory (`winecharm/`), consistent with your setup. Save this as `INSTALL.md` in `winecharm/`, and it should guide users effectively. Let me know if you’d like further tweaks!
