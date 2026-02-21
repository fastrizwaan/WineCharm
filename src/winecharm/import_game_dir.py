#!/usr/bin/env python3
''' imports the game directory inside winecharm's sandbox'''

import gi
import threading
import subprocess
import shutil
import shlex
import yaml
import time
import os
import re
import fnmatch
from pathlib import Path

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango
def import_game_directory(self, script, script_key, *args):
    self.print_method_name()
    script_data = self.script_list.get(script_key)
    if not script_data:
        print(f"Error: Script key {script_key} not found in script_list.")
        return

    # Extract exe_file and wineprefix from script_data
    exe_file = Path(str(script_data['exe_file'])).expanduser().resolve()
    script_path = Path(str(script_data['script_path'])).expanduser().resolve()
    wineprefix = script_path.parent

    exe_path = exe_file.parent
    exe_name = exe_file.name
    game_dir = wineprefix / "drive_c" / "GAMEDIR"

    print("=======")
    print(exe_path)
    print(exe_file)
    print(exe_name)

    # Check if exe_file already exists inside the wineprefix
    existing_game_dir = wineprefix / "drive_c"
    existing_exe_files = list(existing_game_dir.rglob(exe_name))

    if existing_exe_files:
        self.show_info_dialog(
            _("Game Directory Already Exists"),
            _("The game directory for '%s' is already in the Wine prefix. No action is needed.") % exe_name
        )
        return

    # Check if the game directory is in DO_NOT_BUNDLE_FROM directories
    if str(exe_path) in self.get_do_not_bundle_directories():
        msg1 = _("Cannot copy the selected game directory")
        msg2 = _("Please move the files to a different directory to create a bundle.")
        self.show_info_dialog(msg1, msg2)
        return

    # Check disk space in the source and destination directories
    if not self.has_enough_disk_space(exe_path, wineprefix):
        self.show_info_dialog(_("Insufficient Disk Space"), _("There is not enough space to import the game directory."))
        return

    # Proceed with copying if conditions are met
    # Step 1: Disconnect the UI elements and initialize the spinner
    self.on_back_button_clicked(None)
    self.disconnect_open_button()
    self.show_processing_spinner(_("Importing %(name)s") % {"name": exe_path.name})

    # Copy the game directory in a new thread and update script_path
    threading.Thread(target=self.copy_game_directory, args=(exe_path, exe_name, game_dir, script_path, script_key)).start()


def copy_game_directory(self, src, exe_name, dst, script_path, script_key):
    self.print_method_name()
    dst_path = dst / src.name

    # Create the destination directory if it doesn't exist
    dst_path.mkdir(parents=True, exist_ok=True)

    dst_path = dst / src.name
    new_exe_file = dst_path / exe_name

    print("-----------------")
    print(dst_path)
    print(exe_name)
    print(new_exe_file)
    
    steps = [
        (_("Copying Game Directory"), lambda: shutil.copytree(src, dst_path, dirs_exist_ok=True)),
        (_("Updating Script Path"), lambda: self.update_exe_file_path_in_script(script_path, dst_path / exe_name)),
    ]


    def perform_import_steps():
        for step_text, step_func in steps:
            GLib.idle_add(self.show_initializing_step, step_text)
            try:
                step_func()
                GLib.idle_add(self.mark_step_as_done, step_text)
            except Exception as e:
                print(f"Error during step '{step_text}': {e}")
                break

        GLib.idle_add(self.on_import_game_directory_completed, script_key)

    threading.Thread(target=perform_import_steps).start()

def on_import_game_directory_completed(self, script_key):
    self.print_method_name()
    """
    Called when the import process is complete. Updates UI, restores scripts, and resets the open button.
    """
    # Reconnect open button and reset its label
    self.set_open_button_label(_("Open"))
    self.set_open_button_icon_visible(True)
    self.reconnect_open_button()
    self.hide_processing_spinner()

    for key, data in self.script_ui_data.items():
        row_button = data['row']
        row_play_button = data['play_button']
        row_options_button = data['options_button']
    self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)

    script_data = self.reload_script_data_from_charm(script_key)
    print("Game directory import completed.")

def update_exe_file_path_in_script(self, script_path, new_exe_file):
    self.print_method_name()
    """
    Update the .charm file to point to the new location of exe_file.
    """
    try:
        # Read the script file
        with open(script_path, "r") as file:
            script_content = file.readlines()

        # Convert PosixPath to string and update the exe_file path
        new_exe_file_str = str(new_exe_file)  # Ensure it's a string
        new_exe_file_tilde = self.replace_home_with_tilde_in_path(new_exe_file_str)

        # Update the exe_file path with the new location
        updated_content = []
        for line in script_content:
            if line.startswith("'exe_file':"):
                updated_content.append(f"'exe_file': '{new_exe_file_tilde}'\n")
            else:
                updated_content.append(line)

        # Write the updated content back to the file
        with open(script_path, "w") as file:
            file.writelines(updated_content)

        print(f"Updated exe_file in {script_path} to {new_exe_file}")

    except Exception as e:
        print(f"Error updating script path: {e}")



def get_do_not_bundle_directories(self):
    self.print_method_name()
    # Return a list of directories that should not be bundled
    return [
        "/", "/boot", "/dev", "/etc", "/home", "/media", "/mnt", "/opt",
        "/proc", "/root", "/run", "/srv", "/sys", "/tmp", "/usr", "/var",
        f"{os.getenv('HOME')}/Desktop", f"{os.getenv('HOME')}/Documents",
        f"{os.getenv('HOME')}/Downloads", f"{os.getenv('HOME')}/Music",
        f"{os.getenv('HOME')}/Pictures", f"{os.getenv('HOME')}/Public",
        f"{os.getenv('HOME')}/Templates", f"{os.getenv('HOME')}/Videos"
    ]

def has_enough_disk_space(self, source, destination):
    self.print_method_name()
    source_size = sum(f.stat().st_size for f in source.glob('**/*') if f.is_file())
    destination_free_space = shutil.disk_usage(destination.parent).free
    return destination_free_space > source_size
