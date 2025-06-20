# WineCharm

**WineCharm** is a graphical user interface (GUI) application designed to simplify running and managing Windows applications on Linux using Wine. Built with Python and GTK4/Libadwaita, WineCharm provides an intuitive interface for launching `.exe` and `.msi` files, managing Wine prefixes, templates, and runners, and creating portable backups. It supports both GUI and headless modes, making it versatile for different use cases.

![WineCharm Icon View](https://github.com/fastrizwaan/WineCharm/releases/download/0.99.0/WineCharm_icon_view_selected.png)

## Features

  * **Launch Windows Applications** : Easily run `.exe` and `.msi` files with Wine.
  * **Wine Prefix Management** : Create, clone, backup, restore, and delete Wine prefixes.
  * **Template System** : Manage reusable Wine prefix templates with support for 32-bit (`win32`) and 64-bit (`win64`) architectures.
  * **Runner Management** : Use custom Wine runners or the system Wine, with options to download, import, or backup runners.
  * **Portable Backups** : Create and restore `.prefix`, `.bottle`, and `.wzt` backup files for easy sharing and migration.
  * **Script Integration** : Execute `.charm` scripts in headless mode for automation.
  * **Single Prefix Mode** : Optionally use a single Wine prefix for all applications to save space.
  * **Desktop Integration** : Add shortcuts to your desktop or application menu.
  * **Flatpak Support** : Runs seamlessly in a sandboxed Flatpak environment with extensive filesystem access for game and Wine data.

## Installation

### Flatpak Installation (Recommended)

WineCharm can be installed as a Flatpak, providing a sandboxed environment with all dependencies included.

#### Build from Source (Flatpak)

  1. Install Flatpak and Flatpak-builder:

     ```
     sudo apt install flatpak flatpak-builder flatpak # Debian/Ubuntu
     sudo dnf install flatpak flatpak-builder flatpak # Fedora
     ```
  2. Install Flathub repo to download required programs

     ```
     flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
     ```

  3. Install flatpak dependencies:

     ```
     flatpak install -y --user org.gnome.Sdk/x86_64/48 org.gnome.Platform/x86_64/48 org.winehq.Wine//stable-24.08
    ```

  4. Clone the repository:

     ```
     git clone https://github.com/fastrizwaan/WineCharm.git
     cd WineCharm/flatpak
     ```

  5. Build and install the Flatpak:
     
     ```
    flatpak-builder --install --user build-dir io.github.fastrizwaan.WineCharm.yml
     ```

  6. Run the Flatpak:

     ```
     flatpak run io.github.fastrizwaan.WineCharm
     ```


### Python Installation (Recommended for Developers)

WineCharm can be installed as a Python package using `pip` for development or system-wide installation.

#### Prerequisites

  * **System Programs**:
    - `exiftool`
    - `wine` (with `wine32` and `wine64` for full support)
    - `winetricks`
    - `wrestool`
    - `icotool`
    - `pgrep`
    - `gnome-terminal` (or another supported terminal like `ptyxis`, `konsole`, or `xfce4-terminal`)
    - `xdg-open`
    - `procps`
    - `wget`
    - `zstd`
    - `winbind`
  * **Python Modules**:
    - `PyGObject>=3.36` (for GTK4 and Libadwaita)
    - `PyYAML>=5.3` (for YAML parsing)
    - `psutil>=5.7` (for process management)
  * **GUI Requirements**:
    - **GTK4**: Version 4.16 or higher
    - **Libadwaita**: Version 1.7 or higher

On Debian-based systems, install dependencies with:
```
sudo dpkg --add-architecture i386 && sudo apt update -y
sudo apt install zenity wine wine32 wine64 winetricks libimage-exiftool-perl icoutils gnome-terminal wget zstd winbind python3-yaml python3-psutil libgtk-4-1 libadwaita-1-0 python3-gi
```

On Fedora-based systems:
```
sudo dnf install wine winetricks icoutils perl-Image-ExifTool xdg-utils procps-ng wget zstd samba-winbind gtk3 python3-gobject python3-pyyaml python3-psutil
```

#### Install Using pip

  1. Clone the repository:
     ```
     git clone https://github.com/fastrizwaan/WineCharm.git
     cd WineCharm
     ```
  2. Install WineCharm using pip:
     ```
     pip3 install .
     ```
     For a user-specific installation (no root required):
     ```
     pip3 install --user .
     ```
  3. Verify installation:
     ```
     winecharm --help
     ```

### System Installation (Manual, Legacy)

  1. Clone the repository:
     ```
     git clone https://github.com/fastrizwaan/WineCharm.git
     cd WineCharm
     ```
  2. Run the setup script:
     - Install to default prefix (`/usr/local`):
       ```
       sudo ./setup --install
       ```
     - Install to a custom prefix:
       ```
       sudo ./setup --install --prefix /custom/path
       ```
     - Force installation (ignore missing dependencies):
       ```
       sudo ./setup --install --force
       ```
     - Uninstall:
       ```
       sudo ./setup --uninstall
       ```
  3. Verify:
     ```
     winecharm --help
     ```


## Usage

### GUI Mode

Launch WineCharm without arguments (for system or pip installation):
```
winecharm
```

Or via Flatpak:
```
flatpak run io.github.fastrizwaan.WineCharm
```

  * **Open a File**: Click “Open” to select an `.exe` or `.msi` file.

  * **Settings**: Access advanced options via the hamburger menu.

### Headless Mode

Run a `.charm` script:
```
winecharm /path/to/script.charm
```

Process other files:
```
winecharm /path/to/file.exe
winecharm /path/to/backup.wzt
```

### Supported File Types

  * `.exe` / `.msi`: Windows executables and installers.
  * `.charm`: WineCharm script files.
  * `.bottle`: Portable Wine prefix with game and runner data.
  * `.prefix`: Wine prefix backup.
  * `.wzt`: WineZGUI backup files (compatible with WineCharm).

## Configuration

WineCharm stores data in:  
- **Flatpak**: `~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/`  
- **System**: User’s home directory (if installed manually).

Key directories:  
- **Prefixes**: `Prefixes/` - Individual Wine prefixes.  
- **Templates**: `Templates/` - Base prefixes (e.g., `WineCharm-win32`, `WineCharm-win64`).  
- **Runners**: `Runners/` - Custom Wine runners.

Settings are in `Settings.yaml` within the data directory.

## Flatpak Details

The Flatpak manifest provides:  
- **Runtime**: GNOME 48 and Wine stable-24.08.  
- **Filesystem Access**: Broad access to `~/Games`, `.wine`, Bottles, PlayOnLinux, and other common Wine data directories.  
- **Extensions**: Supports 32-bit compatibility, Vulkan, VAAPI, and Steam utilities.  
- **Dependencies**: Includes `icoutils`, `exiftool`, `psutil`, `PyYAML`, and Vulkan tools.

## Development

### Dependencies

  * **GTK4** and **Libadwaita**: GUI framework (GTK4 4.16+, Libadwaita 1.7+).
  * **Python 3.6+**: Core runtime.
  * **Python Modules**: `PyGObject>=3.36`, `PyYAML>=5.3`, `psutil>=5.7`.


### Contributing

Fork the repository, make changes, and submit a pull request. Check issues for feature requests or bugs.

## License

WineCharm is licensed under the GNU General Public License (GPLv3+). See the `LICENSE` file for details.

## Credits

  * **Developer**: Mohammed Asif Ali Rizvan
  * **Project Page**: [GitHub Repository](https://github.com/fastrizwaan/WineCharm)