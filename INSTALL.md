# WineCharm Installation Instructions


WineCharm is a user-friendly GUI for managing and running Windows applications using Wine. This guide will help you install and uninstall WineCharm on your system.

## Requirements
------------
Before you begin, ensure that you have the following dependencies installed:

- Python 3.x
- Python modules: gi, fnmatch, threading, subprocess, os, time, shutil, shlex, hashlib, signal, re, yaml, pathlib
- External programs: exiftool, wine, winetricks, wrestool, icotool, pgrep, gnome-terminal, xdg-open


You can install the required Python modules using pip:

```bash
pip install pycairo PyGObject pyyaml


## Installation
------------
1. Download the WineCharm source files, including `winecharm.py`, `io.github.fastrizwaan.WineCharm.svg`, and `io.github.fastrizwaan.WineCharm.desktop`.

2. Place the files in a directory of your choice.

3. Open a terminal and navigate to the directory where the files are located.

4. Run the setup script with the install option:

   ```bash
   ./setup.sh --install



