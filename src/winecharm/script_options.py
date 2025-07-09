#!/usr/bin/env python3

import gi
import threading
import subprocess
import os
import shutil
import shlex
import hashlib
import signal
import re
import yaml
import sys
import socket
import time
import glob
import fnmatch
import psutil
import inspect
import argparse
import uuid
import urllib.request
import json
import cairo
import math
from pathlib import Path
from gettext import gettext as _
from threading import Lock
from datetime import datetime, timedelta

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango  # Add Pango here

def show_options_for_script(self, ui_state, row, script_key):
    self.print_method_name()
    """
    Display the options for a specific script with search functionality.
    """
    # Add accelerator context for options view
    self.setup_accelerator_context()

    self.search_button.set_active(False)
    # Store current script info for search functionality
    self.current_script = Path(ui_state['script_path'])
    self.current_script_key = script_key
    self.current_row = row
    self.current_ui_state = ui_state

    # Clear main frame
    self.main_frame.set_child(None)

    scrolled_window = Gtk.ScrolledWindow()
    scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled_window.set_vexpand(True)

    self.script_options_flowbox = Gtk.FlowBox()
    self.script_options_flowbox.set_valign(Gtk.Align.START)
    self.script_options_flowbox.set_halign(Gtk.Align.FILL)
    self.script_options_flowbox.set_max_children_per_line(4)
    self.script_options_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
    self.script_options_flowbox.set_vexpand(True)
    self.script_options_flowbox.set_hexpand(True)
    scrolled_window.set_child(self.script_options_flowbox)

    self.main_frame.set_child(scrolled_window)

    # Store options as instance variable for filtering
    self.script_options = [
        ("Show log", "mail-mark-junk-symbolic", self.show_log_file),
        ("Open Terminal", "utilities-terminal-symbolic", self.open_terminal),
        #("Install dxvk vkd3d", "emblem-system-symbolic", self.install_dxvk_vkd3d),
        ("Open Filemanager", "system-file-manager-symbolic", self.open_filemanager),
        ("Edit Script File", "text-editor-symbolic", self.open_script_file),
        ("Delete Wineprefix", "user-trash-symbolic", self.show_delete_wineprefix_confirmation),
        ("Delete Shortcut", "edit-delete-symbolic", self.show_delete_shortcut_confirmation),
        ("Wine Arguments", "mail-attachment-symbolic", self.show_wine_arguments_entry),
        ("Rename Shortcut", "text-editor-symbolic", self.show_rename_shortcut_entry),
        ("Change Icon", "applications-graphics-symbolic", self.show_change_icon_dialog),
        ("Backup Prefix", "media-floppy-symbolic", self.show_backup_prefix_dialog),
        ("Create Bottle", "package-x-generic-symbolic", self.create_bottle_selected),
        ("Save Wine User Dirs", "folder-symbolic", self.show_save_user_dirs_dialog),
        ("Load Wine User Dirs", "document-open-symbolic", self.show_load_user_dirs_dialog),
        ("Reset Shortcut", "view-refresh-symbolic", self.reset_shortcut_confirmation),
        ("Add Desktop Shortcut", "user-bookmarks-symbolic", self.add_desktop_shortcut),
        ("Remove Desktop Shortcut", "action-unavailable-symbolic", self.remove_desktop_shortcut),
        ("Import Game Directory", "folder-download-symbolic", self.import_game_directory),
        ("Run Other Exe", "system-run-symbolic", self.run_other_exe),
        ("Environment Variables", "document-properties-symbolic", self.set_environment_variables),
        ("Change Runner", "preferences-desktop-apps-symbolic", self.change_runner),
        ("Rename Prefix Directory", "rename-prefix-symbolic", self.rename_prefix_directory),
        ("Wine Config (winecfg)", "preferences-system-symbolic", self.wine_config),
        ("Registry Editor (regedit)", "dialog-password-symbolic", self.wine_registry_editor),
        ("About", "dialog-information-symbolic", self.show_script_about),
    ]

    # Initial population of options
    self.populate_script_options()

    # Update UI elements
    self.headerbar.set_title_widget(self.create_icon_title_widget(self.current_script))
    self.menu_button.set_visible(False)
    self.search_button.set_visible(True)
    self.view_toggle_button.set_visible(False)

    if self.back_button.get_parent() is None:
        self.headerbar.pack_start(self.back_button)
    self.back_button.set_visible(True)

    # Handle button replacement
    if self.search_active:
        if self.search_entry_box.get_parent():
            self.vbox.remove(self.search_entry_box)
        self.search_active = False

    self.open_button.set_visible(False)
    self.replace_launch_button(ui_state, row, script_key)



def show_log_file(self, script, script_key, *args):
    self.print_method_name()
    log_file_name = f"{script.stem.replace('_', ' ')}.log"
    log_file_path = Path(script.parent) / log_file_name
    print(f"Opening log file: {log_file_path}")  # Debug
    if log_file_path.exists() and log_file_path.stat().st_size > 0:
        try:
            subprocess.run(["xdg-open", str(log_file_path)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error opening log file: {e}")
    else:
        print(f"Log file does not exist or is empty: {log_file_path}")


def open_terminal(self, script, script_key, *args):
    self.count = 0
    self.print_method_name()
    script_data = self.extract_yaml_info(script_key)
    if not script_data:
        return None

    exe_file = Path(str(script_data['exe_file'])).expanduser().resolve()
    progname = script_data['progname']
    script_args = script_data['args']
    script_key = script_data['sha256sum']  # Use sha256sum as the key
    env_vars = script_data.get('env_vars', '')   # Ensure env_vars is initialized if missing
    
    # Split the env_vars string into individual variable assignments
    env_vars_list = env_vars.split(';')

    # Join the variable assignments with '; export ' to create the export command
    export_env_vars = '; export '.join(env_vars_list.strip() for env_vars_list in env_vars_list)

    wine_debug = script_data.get('wine_debug')
    exe_name = Path(exe_file).name

    # Ensure the wineprefix, runner path is valid and resolve it
    script = Path(str(script_data['script_path'])).expanduser().resolve()
    wineprefix = Path(str(script_data['script_path'])).parent.expanduser().resolve()

    try:
        # Get the runner from the script data
        runner_path = self.get_runner(script_data)
        runner_dir = runner_path.parent.resolve()
    except Exception as e:
        print(f"Error getting runner: {e}")
        return

    print(f"Opening terminal for {wineprefix}")

    self.ensure_directory_exists(wineprefix)

    if shutil.which("flatpak-spawn"):
        command = [
            "wcterm", "bash", "--norc", "-c",
            (
                rf'export PS1="[\u@\h:\w]\\$ "; '
                f'export {export_env_vars}; '
                f'export WINEPREFIX={shlex.quote(str(wineprefix))}; '
                f'export PATH={shlex.quote(str(runner_dir))}:$PATH; '
                f'cd {shlex.quote(str(wineprefix))}; '
                'exec bash --norc -i'
            )
        ]
    else:
        # List of terminal commands to check
        terminal_commands = [
            ("ptyxis", ["ptyxis", "--"]),
            ("gnome-terminal", ["gnome-terminal", "--wait", "--"]),
            ("konsole", ["konsole", "-e"]),
            ("xfce4-terminal", ["xfce4-terminal", "--disable-server", "-x"]),
        ]

        # Find the first available terminal
        terminal_command = None
        for terminal, command_prefix in terminal_commands:
            if shutil.which(terminal):
                terminal_command = command_prefix
                break

        if not terminal_command:
            print("No suitable terminal emulator found.")
            return

        command = terminal_command + [
            "bash", "--norc", "-c",
            (
                rf'export PS1="[\u@\h:\w]\\$ "; '
                f'export {export_env_vars}; '
                f'export WINEPREFIX={shlex.quote(str(wineprefix))}; '
                f'export PATH={shlex.quote(str(runner_dir))}:$PATH; '
                f'cd {shlex.quote(str(wineprefix))}; '
                'exec bash --norc -i'
            )
        ]

    print(f"Running command: {command}")

    try:
        subprocess.Popen(command)
    except Exception as e:
        print(f"Error opening terminal: {e}")


#def install_dxvk_vkd3d(self, script, button):
#    self.print_method_name()
#    wineprefix = Path(script).parent
#    self.run_winetricks_script("vkd3d dxvk", wineprefix)
#    self.create_script_list()

def open_filemanager(self, script, script_key, *args):
    self.count = 0
    self.print_method_name()
    wineprefix = Path(script).parent
    print(f"Opening file manager for {wineprefix}")
    command = ["xdg-open", str(wineprefix)]
    try:
        subprocess.Popen(command)
    except Exception as e:
        print(f"Error opening file manager: {e}")

def open_script_file(self, script, script_key, *args):
    self.print_method_name()
    """
    Open the file manager to show the script's location.
    """
    wineprefix = Path(script).parent
    print(f"Opening file manager for {wineprefix}")
    
    # Ensure we're using the updated script path
    script_data = self.script_list.get(script_key)
    if script_data:
        script_path = Path(str(script_data['script_path'])).expanduser().resolve()
    else:
        print(f"Error: Script key {script_key} not found in script_list.")
        return
    
    command = ["xdg-open", str(script_path)]
    try:
        subprocess.Popen(command)
    except Exception as e:
        print(f"Error opening file manager: {e}")
def run_other_exe(self, script, script_key, *args):
    self.print_method_name()
    """copy_game_directory
    Open a file dialog to allow the user to select an EXE or MSI file and run it.
    """
    file_dialog = Gtk.FileDialog.new()
    file_filter = self.create_file_filter()  # Use the same filter for EXE/MSI
    filter_model = Gio.ListStore.new(Gtk.FileFilter)
    filter_model.append(file_filter)
    file_dialog.set_filters(filter_model)

    # Open the file dialog and pass the selected file to on_run_other_exe_response
    file_dialog.open(self.window, None, lambda dlg, res: self.on_run_other_exe_response(dlg, res, script, script_key))

def on_run_other_exe_response(self, dialog, result, script, script_key):
    self.print_method_name()
    script_data = self.script_list.get(script_key)
    if not script_data:
        return None

    unique_id = str(uuid.uuid4())
    env = os.environ.copy()
    env['WINECHARM_UNIQUE_ID'] = unique_id

    exe_file = Path(str(script_data.get('exe_file', ''))).expanduser().resolve()
    script = Path(str(script_data.get('script_path', ''))).expanduser().resolve()
    progname = str(script_data.get('progname', ''))
    script_args = str(script_data.get('args', ''))
    script_key = str(script_data.get('sha256sum', script_key))
    env_vars = str(script_data.get('env_vars', ''))
    wine_debug = str(script_data.get('wine_debug', ''))
    exe_name = Path(str(exe_file)).name
    wineprefix = Path(str(script_data.get('script_path', ''))).parent.expanduser().resolve()

    try:
        # Get the runner from the script data
        runner_path = self.get_runner(script_data)
        runner_dir = runner_path.parent.resolve()
        path_env = f'export PATH="{shlex.quote(str(runner_dir))}:$PATH"'

        file = dialog.open_finish(result)
        if file:
            exe_path = Path(file.get_path()).expanduser().resolve()
            exe_parent = shlex.quote(str(exe_path.parent.resolve()))
            runner = shlex.quote(str(runner_path))
            exe_name = shlex.quote(str(exe_path.name))

            # Formulate the command to run the selected executable
            if path_env:
                command = (f"{path_env}; cd {exe_parent} && "
                        f"{wine_debug} {env_vars} WINEPREFIX={shlex.quote(str(wineprefix))} "
                        f"{runner} {exe_name} {script_args}")
            else:
                command = (f"cd {exe_parent} && "
                        f"{wine_debug} {env_vars} WINEPREFIX={shlex.quote(str(wineprefix))} "
                        f"{runner} {exe_name} {script_args}")

            print(f"Running command: {command}")

            if self.debug:
                print(f"Running command: {command}")

            # Execute the command
            subprocess.Popen(command, shell=True)
            print(f"Running {exe_path} from Wine prefix {wineprefix}")

    except Exception as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")

def set_environment_variables(self, script, script_key, *args):
    self.print_method_name()
    """
    Show a dialog to allow the user to set environment variables for a script.
    Ensures that the variables follow the 'X=Y' pattern, where X is a valid
    variable name and Y is its value.
    """
    # Retrieve script data
    script_data = self.script_list.get(script_key)
    if not script_data:
        print(f"Error: Script key {script_key} not found in script_list.")
        return

    # Get current environment variables or set default
    current_env_vars = script_data.get('env_vars', '')

    # Create a dialog for editing environment variables
    dialog = Adw.AlertDialog(
        heading="Set Environment Variables",
        body="Enter variables in X=Y;Z=W format:"
    )

    # Create an entry field and set the current environment variables
    entry = Gtk.Entry()
    entry.set_text(current_env_vars)

    # Add the entry field to the dialog
    dialog.set_extra_child(entry)

    # Add "OK" and "Cancel" buttons
    dialog.add_response("ok", "OK")
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.add_response("cancel", "Cancel")
    dialog.set_default_response("cancel")

    # Connect the response signal to handle the user's input
    dialog.connect("response", self.on_env_vars_dialog_response, entry, script_key)

    # Present the dialog
    dialog.present(self.window)


def on_env_vars_dialog_response(self, dialog, response_id, entry, script_key):
    self.print_method_name()
    """
    Handle the response from the environment variables dialog.
    Ensure the variables follow the 'X=Y' format and are separated by semicolons.
    """
    if response_id == "ok":
        # Get the new environment variables from the entry
        new_env_vars = entry.get_text().strip()

        # Validate the environment variables
        if self.validate_environment_variables(new_env_vars):
            # Update the script data
            script_data = self.script_list.get(script_key)
            script_data['env_vars'] = new_env_vars

            # Write the updated data back to the YAML file
            script_path = Path(str(script_data['script_path'])).expanduser().resolve()
            with open(script_path, 'w') as file:
                yaml.dump(script_data, file, default_style="'", default_flow_style=False, width=10000)

            print(f"Updated environment variables for {script_path}: {new_env_vars}")
        else:
            print(f"Invalid environment variables format: {new_env_vars}")
            self.show_info_dialog("Invalid Environment Variables", "Please use the correct format: X=Y;Z=W.")

    else:
        print("Environment variable modification canceled")

    # Close the dialog
    dialog.close()


def validate_environment_variables(self, env_vars):
    self.print_method_name()
    """
    Validate the environment variables string to ensure it follows the 'X=Y' pattern.
    Multiple variables should be separated by semicolons.
    Leading and trailing whitespace will be removed from each variable.
    
    Args:
        env_vars (str): The string containing environment variables.

    Returns:
        bool: True if the variables are valid, False otherwise.
    """
    # Regular expression to match a valid environment variable (bash-compliant)
    env_var_pattern = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=.*$')

    # Split the variables by semicolons and validate each one
    variables = [var.strip() for var in env_vars.split(';')]
    for var in variables:
        var = var.strip()  # Remove any leading/trailing whitespace
        if not var or not env_var_pattern.match(var):
            return False  # If any variable is invalid, return False

    return True


        
def rename_prefix_directory(self, script, script_key, *args):
    self.print_method_name()
    script_data = self.script_list.get(script_key)
    if script_data is None:
        print(f"Error: Script key {script_key} not found")
        return

    wineprefix = Path(str(script_data.get('wineprefix'))).expanduser().resolve()
    if not wineprefix.exists():
        print(f"Error: Wine prefix '{wineprefix}' doesn't exist")
        return

    if self.single_prefix and (wineprefix in [self.single_prefix_dir_win64, self.single_prefix_dir_win32]):  # Added confirmation check
        confirm_dialog = Adw.AlertDialog(
            heading="Single Prefix Mode Warning",
            body="You're in Single Prefix mode! Renaming will affect ALL scripts using this prefix.",
            body_use_markup=True
        )
        confirm_dialog.add_response("cancel", "Cancel")
        confirm_dialog.add_response("proceed", "Proceed Anyway")
        confirm_dialog.set_response_appearance("proceed", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm_dialog.connect("response", lambda d, r: self.show_rename_dialog(wineprefix, script_key) if r == "proceed" else None)
        confirm_dialog.present(self.window)
    else:
        self.show_rename_dialog(wineprefix, script_key)

def show_rename_dialog(self, wineprefix, script_key):
    self.print_method_name()
    """Helper to show the actual rename dialog"""
    dialog = Adw.AlertDialog(
        title="Rename Wine Prefix",
        body=f"Enter new name for prefix directory:\nCurrent: {wineprefix.name}"
    )
    
    entry = Gtk.Entry()
    entry.set_text(wineprefix.name)
    dialog.set_extra_child(entry)

    dialog.add_response("cancel", "Cancel")
    dialog.add_response("ok", "Rename")
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.connect("response", self.on_rename_prefix_dialog_response, entry, script_key, wineprefix)
    dialog.present(self.window)


def on_rename_prefix_dialog_response(self, dialog, response, entry, script_key, old_wineprefix):
    self.print_method_name()
    """
    Handle the user's response to the rename prefix dialog.

    :param dialog: The dialog instance.
    :param response: The user's response (e.g., "ok" or "cancel").
    :param entry: The entry widget containing the new directory name.
    :param script_key: The unique key identifying the script.
    :param old_wineprefix: The original Wine prefix directory path.
    """
    if response != "ok":
        #dialog.destroy()
        return

    # Get the new directory name from the entry widget
    new_name = entry.get_text().strip()
    if not new_name or new_name == old_wineprefix.name:
        print("No changes made to the Wine prefix directory name.")
        #dialog.destroy()
        return

    # Define the new Wine prefix path
    new_wineprefix = old_wineprefix.parent / new_name

    try:
        # Rename the Wine prefix directory
        old_wineprefix.rename(new_wineprefix)

        # Update the script data with the new prefix path
        self.script_list[script_key]['wineprefix'] = str(new_wineprefix)

        print(f"Successfully renamed Wine prefix to '{new_name}'.")

        # Update .charm files within the renamed prefix directory
        self.update_charm_files_with_new_prefix(new_wineprefix, old_wineprefix)

        # Update any other script data references (e.g., if paths are stored separately)
        self.update_script_data_references(script_key, str(new_wineprefix))

    except Exception as e:
        print(f"Error renaming Wine prefix directory: {e}")
        # Show an error dialog if needed (not implemented here)
    
    # Clean up the dialog
    #dialog.destroy()

def update_charm_files_with_new_prefix(self, new_wineprefix, old_wineprefix):
    self.print_method_name()
    """
    Update all .charm files within the newly renamed prefix directory to reflect the new prefix path.

    :param new_wineprefix: The new Wine prefix path.
    :param old_wineprefix: The old Wine prefix path.
    """
    # Get the tilde-prefixed versions of the old and new Wine prefixes
    old_wineprefix_tilde = self.replace_home_with_tilde_in_path(str(old_wineprefix))
    new_wineprefix_tilde = self.replace_home_with_tilde_in_path(str(new_wineprefix))

    # Iterate through all .charm files within the new prefix directory
    for charm_file in Path(new_wineprefix).rglob("*.charm"):
        try:
            # Read the content of the .charm file
            with open(charm_file, "r") as file:
                content = file.read()

            # Replace occurrences of the old prefix path with the new prefix path using tilde
            updated_content = content.replace(old_wineprefix_tilde, new_wineprefix_tilde)

            # Write the updated content back to the .charm file
            with open(charm_file, "w") as file:
                file.write(updated_content)

            print(f"Updated .charm file: {charm_file}")

        except Exception as e:
            print(f"Error updating .charm file {charm_file}: {e}")

def update_script_data_references(self, script_key, new_wineprefix):
    self.print_method_name()
    """
    Update internal script data references related to the old prefix.

    :param script_key: The unique key identifying the script.
    :param new_wineprefix: The new Wine prefix path.
    """
    # Get the script data from script_list
    script_data = self.script_list.get(script_key)
    if script_data:
        old_wineprefix = Path(str(script_data['wineprefix'])).expanduser().resolve()
        new_wineprefix_resolved = Path(new_wineprefix).expanduser().resolve()

        # Update the wineprefix path in the script_data
        script_data['wineprefix'] = str(new_wineprefix_resolved)

        # Update exe_file, script_path, and any other fields containing the old wineprefix path
        for key, value in script_data.items():
            if isinstance(value, str) and str(old_wineprefix) in value:
                script_data[key] = value.replace(str(old_wineprefix), str(new_wineprefix_resolved))

        # Special handling for script_path to reflect the new prefix
        if 'script_path' in script_data:
            # Extract the filename from the old script path
            old_script_filename = Path(str(script_data['script_path'])).name
            # Create the new script path using the new prefix and the old script filename
            new_script_path = Path(new_wineprefix_resolved) / old_script_filename
            script_data['script_path'] = str(new_script_path)

        # Print updated script_data for debugging
        print(f"Updated script data for script key: {script_key}")
        for key, value in script_data.items():
            print(f"  {key}: {value}")

        # Update the script list and any other relevant UI data
        self.script_list[script_key] = script_data
        self.script_ui_data[script_key]['script_path'] = script_data['script_path']

        # Reload script list from files
        self.load_script_list()

def wine_config(self, script, script_key, *args):
    self.print_method_name()
    script_data = self.script_list.get(script_key)
    if not script_data:
        return None

    unique_id = str(uuid.uuid4())
    env = os.environ.copy()
    env['WINECHARM_UNIQUE_ID'] = unique_id

    exe_file = Path(str(script_data.get('exe_file', ''))).expanduser().resolve()
    script = Path(str(script_data.get('script_path', ''))).expanduser().resolve()
    progname = str(script_data.get('progname', ''))
    script_args = str(script_data.get('args', ''))
    script_key = str(script_data.get('sha256sum', script_key))
    env_vars = str(script_data.get('env_vars', ''))
    wine_debug = str(script_data.get('wine_debug', ''))
    exe_name = Path(str(exe_file)).name
    wineprefix = Path(str(script_data.get('script_path', ''))).parent.expanduser().resolve()

    try:
        # Get the runner from the script data
        runner_path = self.get_runner(script_data)

        # Formulate the command to run the selected executable
        if isinstance(runner_path, Path):
            runner_dir = shlex.quote(str(runner_path.parent))
            path_env = f'export PATH="{runner_dir}:$PATH"'
        else:
            runner_dir = ""
            path_env = ""

        runner = shlex.quote(str(runner_path))

        # Command to launch
        if path_env:
            command = (f"{path_env}; WINEPREFIX={shlex.quote(str(wineprefix))} winecfg")
        else:
            command = (f"{wine_debug} {env_vars} WINEPREFIX={shlex.quote(str(wineprefix))} {runner} winecfg")

        print(f"Running command: {command}")

        if self.debug:
            print(f"Running command: {command}")

        # Execute the command
        subprocess.Popen(command, shell=True)
        print(f"Running winecfg from Wine prefix {wineprefix}")

    except Exception as e:
        print(f"Error running EXE: {e}")

def wine_registry_editor(self, script, script_key, *args):
    self.print_method_name()
    script_data = self.script_list.get(script_key)
    if not script_data:
        return None

    unique_id = str(uuid.uuid4())
    env = os.environ.copy()
    env['WINECHARM_UNIQUE_ID'] = unique_id

    exe_file = Path(str(script_data.get('exe_file', ''))).expanduser().resolve()
    script = Path(str(script_data.get('script_path', ''))).expanduser().resolve()
    progname = str(script_data.get('progname', ''))
    script_args = str(script_data.get('args', ''))
    script_key = str(script_data.get('sha256sum', script_key))
    env_vars = str(script_data.get('env_vars', ''))
    wine_debug = self.wine_debug
    exe_name = Path(str(exe_file)).name
    wineprefix = Path(str(script_data.get('script_path', ''))).parent.expanduser().resolve()

    try:
        # Get the runner from the script data
        runner_path = str(self.get_runner(script_data))

        # Formulate the command to run the selected executable
        if isinstance(runner_path, Path):
            runner_dir = shlex.quote(str(runner_path.parent))
            path_env = f'export PATH="{runner_dir}:$PATH"'
        else:
            runner_dir = ""
            path_env = ""

        runner = shlex.quote(str(runner_path))

        # Command to launch
        if path_env:
            command = (f"{path_env}; WINEPREFIX={shlex.quote(str(wineprefix))} regedit")
        else:
            command = (f"{wine_debug} {env_vars} WINEPREFIX={shlex.quote(str(wineprefix))} {runner} regedit")

        print(f"Running command: {command}")

        if self.debug:
            print(f"Running command: {command}")

        # Execute the command
        subprocess.Popen(command, shell=True)
        print(f"Running regedit from Wine prefix {wineprefix}")

    except Exception as e:
        print(f"Error running EXE: {e}")

def show_script_about(self, script_path, script_key, button):
    self.print_method_name()
    """Display detailed information about the selected script and its wineprefix."""
    if script_key not in self.script_list:
        self.show_info_dialog("Error", "Script not found.")
        return
    
    script_data = self.script_list[script_key]
    progname = script_data.get('progname', Path(script_key).stem)
    wineprefix = Path(script_data.get('wineprefix', self.prefixes_dir / progname)).expanduser().resolve()
    exe_file = Path(script_data.get('exe_file', '')).expanduser().resolve()
    script_path = Path(script_data.get('script_path', '')).expanduser().resolve()
    runner = script_data.get('runner')
    if not runner:
        system_wine_display, _ = self.get_system_wine()
    args = script_data.get('args', '')
    env_vars = script_data.get('env_vars', '')
    
    # Calculate wineprefix size
    wineprefix_size = self.get_directory_size_for_about(wineprefix)
    
    # Gather additional info
    creation_time = datetime.fromtimestamp(script_path.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S') if script_path.exists() else "Unknown"
    arch = self.get_template_arch(wineprefix) if wineprefix.exists() else "Unknown"
    
    # Create the dialog
    dialog = Adw.AlertDialog(
        heading="",  # Empty heading, we'll use custom header
        body=""
    )
    
    # Set dialog size
    dialog.set_size_request(570, 800)
    
    # Create custom header with icon and title
    header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    header_box.set_margin_top(4)
    header_box.set_margin_bottom(0)
    header_box.set_margin_start(4)
    header_box.set_margin_end(0)
    header_box.set_halign(Gtk.Align.CENTER)  # Center the entire header box
    
    # Create and add the icon title widget with "About" prefix
    icon_title_widget = self.create_icon_title_widget(script_path)
    icon_title_widget.add_css_class("heading")
    
    # Add "About" label as the first child of the icon_title_widget
    about_label = Gtk.Label(label="About")
    about_label.add_css_class("heading")
    about_label.set_margin_end(8)  # Add some spacing after "About"
    icon_title_widget.prepend(about_label)
    
    header_box.append(icon_title_widget)
    
    # Create main content box
    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    
    # Add the custom header at the top
    main_box.append(header_box)
    

    # Create content box for the rest of the content
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.set_margin_top(8)
    content_box.set_margin_bottom(8)
    content_box.set_margin_start(8)
    content_box.set_margin_end(8)
    
    # Helper function to copy text to clipboard
    def copy_to_clipboard(text):
        """Copy text to clipboard"""
        clipboard = dialog.get_clipboard()
        clipboard.set(text)
    def open_directory(path):
        try:
            subprocess.run(['xdg-open', str(path)], check=True)
        except subprocess.CalledProcessError:
            # Fallback to file manager
            try:
                subprocess.run(['nautilus', str(path)], check=True)
            except subprocess.CalledProcessError:
                try:
                    subprocess.run(['thunar', str(path)], check=True)
                except subprocess.CalledProcessError:
                    print(f"Could not open directory: {path}")
    
    # Helper function to create a clickable directory row
    def create_directory_row(title, path, subtitle=None):
        # Create expandable row for paths
        expander_row = Adw.ExpanderRow(title=title)
        if subtitle:
            expander_row.set_subtitle(subtitle)
        
        # Create a suffix box to control order
        suffix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # Show basename as a label beside the title (before buttons)
        basename = path.name if path.name else "Unknown"
        basename_label = Gtk.Label(label=basename)
        basename_label.set_selectable(True)
        basename_label.add_css_class("caption")
        basename_label.add_css_class("dim-label")
        basename_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        basename_label.set_max_width_chars(25)
        suffix_box.append(basename_label)
        
        # Create button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        
        # Add open button
        open_btn = Gtk.Button(icon_name="folder-open-symbolic")
        open_btn.set_tooltip_text("Open in file manager")
        open_btn.add_css_class("flat")
        open_btn.add_css_class("circular")
        open_btn.connect("clicked", lambda btn: open_directory(path.parent if path.is_file() else path))
        button_box.append(open_btn)
        
        # Add copy button
        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        copy_btn.set_tooltip_text("Copy path to clipboard")
        copy_btn.add_css_class("flat")
        copy_btn.add_css_class("circular")
        copy_btn.connect("clicked", lambda btn: copy_to_clipboard(str(path)))
        button_box.append(copy_btn)
        
        suffix_box.append(button_box)
        expander_row.add_suffix(suffix_box)
        
        # Add path as a child row that shows when expanded
        path_row = Adw.ActionRow(title="Full Path")
        path_label = Gtk.Label(label=str(path))
        path_label.set_wrap(True)
        path_label.set_wrap_mode(Gtk.WrapMode.CHAR)
        path_label.set_selectable(True)
        path_label.set_xalign(0.0)
        path_label.add_css_class("caption")
        path_label.add_css_class("dim-label")
        path_label.set_margin_top(8)
        path_label.set_margin_bottom(8)
        path_row.set_child(path_label)
        
        expander_row.add_row(path_row)
        
        return expander_row
    
    # Helper function to create info row with better text wrapping
    def create_info_row(title, value, subtitle=None):
        # For long values, use ExpanderRow
        if len(str(value)) > 60:
            expander_row = Adw.ExpanderRow(title=title)
            if subtitle:
                expander_row.set_subtitle(subtitle)
            
            # Add truncated preview
            preview = str(value)[:75] + "..." if len(str(value)) > 50 else str(value)
            expander_row.set_subtitle(preview)
            
            # Add full value as child row
            value_row = Adw.ActionRow(title="Full Value")
            value_label = Gtk.Label(label=str(value))
            value_label.set_wrap(True)
            value_label.set_wrap_mode(Gtk.WrapMode.WORD)
            value_label.set_selectable(True)
            value_label.set_xalign(0.0)
            value_label.add_css_class("caption")
            value_label.set_margin_top(8)
            value_label.set_margin_bottom(8)
            value_row.set_child(value_label)
            
            expander_row.add_row(value_row)
            return expander_row
        else:
            # Short values use regular ActionRow
            row = Adw.ActionRow(title=title)
            if subtitle:
                row.set_subtitle(subtitle)
            
            value_label = Gtk.Label(label=str(value))
            value_label.set_selectable(True)
            value_label.add_css_class("caption")
            row.add_suffix(value_label)
            
            return row

    # Get default runner from settings
    settings = self.load_settings()
    default_runner = os.path.abspath(os.path.expanduser(settings.get('runner', '')))
        # Validate default runner
    if default_runner:
        if self.validate_runner(default_runner):
            runner_name = Path(default_runner).parent.parent.name
        else:
            print(f"Invalid default runner: {default_runner}")
            default_runner = ''


    # Basic Information Group
    basic_group = Adw.PreferencesGroup(title="Basic Information")
    basic_group.add(create_info_row("Program Name", progname))
    basic_group.add(create_info_row("Architecture", arch))
    basic_group.add(create_info_row("Runner", runner_name))
    basic_group.add(create_info_row("Creation Time", creation_time))
    content_box.append(basic_group)
    
    # Paths Group
    paths_group = Adw.PreferencesGroup(title="Paths")
    
    # Wineprefix row with size info
    wineprefix_row = create_directory_row("Wineprefix", wineprefix, f"Size: {wineprefix_size}")
    paths_group.add(wineprefix_row)
    
    # Executable row
    if exe_file.exists():
        exe_row = create_directory_row("Executable", exe_file)
        paths_group.add(exe_row)
    
    # Script path row
    if script_path.exists():
        script_row = create_directory_row("Script Path", script_path)
        paths_group.add(script_row)
    
    content_box.append(paths_group)
    
    # Configuration Group
    config_group = Adw.PreferencesGroup(title="Configuration")
    
    # Arguments row
    if args:
        config_group.add(create_info_row("Arguments", args))
    else:
        config_group.add(create_info_row("Arguments", "None"))
    
    # Environment Variables row
    if env_vars:
        config_group.add(create_info_row("Environment Variables", env_vars))
    else:
        config_group.add(create_info_row("Environment Variables", "None"))
    
    content_box.append(config_group)
    
    # Add content to main box
    main_box.append(content_box)
    
    # Add to dialog
    dialog.set_extra_child(main_box)
    
    # Add response buttons
    dialog.add_response("close", "Close")
    dialog.set_default_response("close")
    
    # Present the dialog
    dialog.present(self.window)

def get_directory_size_for_about(self, path):
    self.print_method_name()
    """
    Calculate the total size of a directory in human-readable format.
    """
    if not path.exists():
        print(f"The provided path '{path}' does not exist.")
        return "Unknown (Directory not found)"

    try:
        total_size = sum(f.stat().st_size for f in path.glob('**/*') if f.is_file())
        # Convert to human-readable format
        if total_size < 1024:
            return f"{total_size} bytes"
        elif total_size < 1024 * 1024:
            return f"{total_size / 1024:.2f} KB"
        elif total_size < 1024 * 1024 * 1024:
            return f"{total_size / (1024 * 1024):.2f} MB"
        else:
            return f"{total_size / (1024 * 1024 * 1024):.2f} GB"
    except Exception as e:
        print(f"Error calculating directory size: {e}")
        return "Unknown (Error occurred)"


def add_desktop_shortcut(self, script, script_key, *args):
    self.print_method_name()
    """
    Show a dialog with checkboxes to allow the user to select shortcuts for desktop creation.
    """
    # Get script data from registry
    script_data = self.script_list.get(script_key)
    if not script_data:
        print(f"Error: Script key {script_key} not found in script_list.")
        return

    # Resolve paths
    wine_prefix_dir = Path(str(script_data['script_path'])).parent.expanduser().resolve()
    script_path = Path(str(script_data['script_path'])).expanduser().resolve()

    # Find charm files in the prefix directory
    charm_files = list(wine_prefix_dir.rglob("*.charm"))
    if not charm_files:
        self.show_info_dialog("No Shortcuts", f"No shortcuts found in {wine_prefix_dir.name}")
        return

    # Create main dialog
    dialog = Adw.AlertDialog(
        heading="Create Desktop Shortcuts",
        body=f"Select shortcuts to create for {wine_prefix_dir.name}:"
    )

    # Create UI components
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    checkbox_dict = {}

    # Populate checkboxes for each charm file
    for charm_file in charm_files:
        # Create checkbox row
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        checkbox = Gtk.CheckButton()
        hbox.append(checkbox)
        
        # Add icon and label
        icon_label = self.create_icon_title_widget(charm_file)
        hbox.append(icon_label)
        
        vbox.append(hbox)
        checkbox_dict[checkbox] = charm_file

    # Category selection
    category_label = Gtk.Label(label="Application Category:")
    category_label.set_xalign(0)
    vbox.append(category_label)

    # Create DropDown with categories
    categories = [
        "AudioVideo", "Audio", "Video", "Development", "Education",
        "Game", "Graphics", "Network", "Office", "Science",
        "Settings", "System", "Utility"
    ]
    model = Gtk.StringList.new(categories)
    category_dropdown = Gtk.DropDown(model=model)
    
    try:
        category_dropdown.set_selected(categories.index("Game"))
    except ValueError:
        category_dropdown.set_selected(0)
    
    vbox.append(category_dropdown)

    # Configure dialog
    dialog.set_extra_child(vbox)
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("create", "Create")
    dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("create")

    # Connect response handler
    dialog.connect("response", 
                self.on_add_desktop_shortcut_response,
                checkbox_dict,
                category_dropdown)

    # Show dialog
    dialog.present(self.window)

def on_add_desktop_shortcut_response(self, dialog, response_id, checkbox_dict, category_dropdown):
    self.print_method_name()
    """
    Handle the response from the create desktop shortcut dialog.
    
    Args:
        dialog: The Adw.AlertDialog instance
        response_id: The ID of the response clicked by the user
        checkbox_dict: Dictionary mapping checkboxes to charm files
        category_dropdown: The Gtk.DropDown widget for category selection
    """
    if response_id == "create":
        # Get selected category from dropdown
        selected_pos = category_dropdown.get_selected()
        model = category_dropdown.get_model()
        selected_category = model.get_string(selected_pos) if selected_pos >= 0 else "Game"

        # Track successful creations
        created_count = 0
        
        # Iterate through checkboxes
        for checkbox, charm_file in checkbox_dict.items():
            if checkbox.get_active():
                try:
                    # Get script data from charm file
                    script_key = self.get_script_key_from_shortcut(charm_file)
                    script_data = self.script_list.get(script_key)

                    if not script_data:
                        print(f"Error: Script data for {charm_file} not found.")
                        continue

                    # Extract needed values
                    progname = script_data.get('progname', '')
                    script_path = Path(str(script_data['script_path'])).expanduser().resolve()
                    wineprefix = script_path.parent.expanduser().resolve()
                    
                    # Get icon path
                    icon_name = f"{script_path.stem}.png"
                    icon_path = script_path.parent / icon_name

                    # Create desktop entry with selected category
                    self.create_desktop_entry(
                        progname=progname,
                        script_path=script_path,
                        icon_path=icon_path,
                        wineprefix=wineprefix,
                        category=selected_category
                    )
                    created_count += 1
                    print(f"Created desktop shortcut for: {charm_file.name}")

                except Exception as e:
                    print(f"Error creating shortcut for {charm_file.name}: {str(e)}")
                    self.show_info_dialog(
                        "Creation Error",
                        f"Failed to create shortcut for {charm_file.name}:\n{str(e)}"
                    )

        # Show summary dialog
        if created_count > 0:
            self.show_info_dialog(
                "Shortcuts Created",
                f"Successfully created {created_count} desktop shortcut(s)\n" +
                f"Category: {selected_category}"
            )
        else:
            self.show_info_dialog(
                "No Shortcuts Created",
                "No shortcuts were selected for creation."
            )
    else:
        print("Desktop shortcut creation canceled")

    dialog.close()


def remove_desktop_shortcut(self, script, script_key, *args):
    self.print_method_name()
    """
    Show a dialog with checkboxes to allow the user to select desktop shortcuts for deletion.
    """
    # Get script data from registry
    script_data = self.script_list.get(script_key)
    if not script_data:
        print(f"Error: Script key {script_key} not found.")
        return

    # Resolve paths
    wine_prefix_dir = Path(str(script_data['script_path'])).parent.expanduser().resolve()
    desktop_files = list(wine_prefix_dir.glob("*.desktop"))

    if not desktop_files:
        self.show_info_dialog("No Shortcuts", f"No desktop shortcuts found in {wine_prefix_dir.name}")
        return

    # Create AlertDialog
    dialog = Adw.AlertDialog(
        heading="Delete Desktop Shortcuts",
        body=f"Select shortcuts to remove from {wine_prefix_dir.name}:"
    )

    # Create checkbox UI
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    checkbox_dict = {}

    for desktop_file in desktop_files:
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        checkbox = Gtk.CheckButton()
        hbox.append(checkbox)
        
        # Get associated charm file for icon
        charm_file = desktop_file.with_suffix(".charm")
        icon_label = self.create_icon_title_widget(charm_file)
        hbox.append(icon_label)
        
        vbox.append(hbox)
        checkbox_dict[checkbox] = desktop_file

    dialog.set_extra_child(vbox)

    # Configure dialog buttons
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("delete", "Delete")
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")

    # Connect response handler
    dialog.connect("response", self.on_remove_desktop_shortcut_response, checkbox_dict)
    dialog.present(self.window)

def on_remove_desktop_shortcut_response(self, dialog, response_id, checkbox_dict):
    self.print_method_name()
    """Handle desktop shortcut deletion response"""
    if response_id == "delete":
        deleted_count = 0
        for checkbox, desktop_file in checkbox_dict.items():
            if checkbox.get_active():
                try:
                    # Delete desktop file
                    if desktop_file.exists():
                        desktop_file.unlink(missing_ok=True)
                        print(f"Removed desktop file: {desktop_file}")

                        # Remove symlink
                        symlink_name = f"winecharm_{desktop_file.stem}.desktop"
                        symlink_path = self.applicationsdir / symlink_name
                        if symlink_path.exists() or symlink_path.is_symlink():
                            symlink_path.unlink(missing_ok=True)
                            print(f"Removed symlink: {symlink_path}")

                        deleted_count += 1

                except Exception as e:
                    print(f"Error deleting {desktop_file.name}: {str(e)}")
                    self.show_info_dialog(
                        "Deletion Error",
                        f"Failed to delete {desktop_file.name}:\n{str(e)}"
                    )

        # Show summary
        if deleted_count > 0:
            self.show_info_dialog(
                "Shortcuts Removed",
                f"Successfully deleted {deleted_count} desktop shortcut(s)"
            )
        else:
            self.show_info_dialog(
                "Nothing Deleted",
                "No shortcuts were selected for removal."
            )
    else:
        print("Desktop shortcut deletion canceled")

    dialog.close()

        
def show_delete_wineprefix_confirmation(self, script, button):
    self.remove_accelerator_context()
    self.count = 0
    self.print_method_name()
    """
    Show an Adw.AlertDialog to confirm the deletion of the Wine prefix.
    
    Args:
        script: The script that contains information about the Wine prefix.
        button: The button that triggered the deletion request.
    """
    wineprefix = Path(script).parent

    # Get all charm files associated with the wineprefix
    charm_files = list(wineprefix.rglob("*.charm"))

    # Create a confirmation dialog
    dialog = Adw.AlertDialog(
        heading="Delete Wine Prefix",
        body=f"Deleting {wineprefix.name} will remove:"
    )

    # Create a vertical box to hold the program list (without checkboxes)
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    if not charm_files:
        # No charm files found, display a message
        no_programs_label = Gtk.Label(label="No programs found in this Wine prefix.")
        vbox.append(no_programs_label)
    else:
        # Add each charm file's icon and program name to the dialog
        for charm_file in charm_files:
            # Create an icon + label widget (reusing the function for consistency)
            icon_title_widget = self.create_icon_title_widget(charm_file)
            vbox.append(icon_title_widget)

    # Add the program list to the dialog
    dialog.set_extra_child(vbox)

    # Add the "Delete" and "Cancel" buttons
    dialog.add_response("delete", "Delete")
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.add_response("cancel", "Cancel")
    dialog.set_default_response("cancel")

    # Show the dialog and connect the response signal
    dialog.connect("response", self.on_delete_wineprefix_confirmation_response, wineprefix)

    # Present the dialog (use present instead of show to avoid deprecation warning)
    dialog.present(self.window)
    

def on_delete_wineprefix_confirmation_response(self, dialog, response_id, wineprefix):
    self.print_method_name()
    """
    Handle the response from the delete Wine prefix confirmation dialog.
    
    Args:
        dialog: The Adw.AlertDialog instance.
        response_id: The ID of the response clicked by the user.
        wineprefix: The path to the Wine prefix that is potentially going to be deleted.
    """
    if response_id == "delete":
        # Get all script_keys associated with the wineprefix
        script_keys = self.get_script_keys_from_wineprefix(wineprefix)

        if not script_keys:
            print(f"No scripts found for Wine prefix: {wineprefix}")
            return

        # Perform the deletion of the Wine prefix
        try:
            if wineprefix.exists() and wineprefix.is_dir():
                shutil.rmtree(wineprefix)
                print(f"Deleted Wine prefix: {wineprefix}")
                
                # Remove all script_keys associated with this Wine prefix from script_list
                for script_key in script_keys:
                    if script_key in self.script_list:
                        del self.script_list[script_key]
                        print(f"Removed script {script_key} from script_list")
                    else:
                        print(f"Script {script_key} not found in script_list for Wine prefix: {wineprefix}")

                # Trigger the back button to return to the previous view
                self.on_back_button_clicked(None)
            else:
                print(f"Wine prefix does not exist: {wineprefix}")
        except Exception as e:
            print(f"Error deleting Wine prefix: {e}")
    else:
        print("Deletion canceled")

    # Close the dialog
    dialog.close()

def show_delete_shortcut_confirmation(self, script, script_key, button, *args):
    self.print_method_name()
    """
    Show a dialog with checkboxes to allow the user to select shortcuts for deletion.
    
    Args:
        script: The script that contains information about the shortcut.
        script_key: The unique identifier for the script in the script_list.
        button: The button that triggered the deletion request.
    """
    # Ensure we're using the updated script path from the script_data
    script_data = self.script_list.get(script_key)
    if not script_data:
        print(f"Error: Script key {script_key} not found in script_list.")
        return

    # Extract the Wine prefix directory associated with this script
    wine_prefix_dir = Path(str(script_data['script_path'])).parent.expanduser().resolve()
    script_path = Path(str(script_data['script_path'])).expanduser().resolve()


    # Fetch the list of charm files only in the specific Wine prefix directory
    charm_files = list(wine_prefix_dir.rglob("*.charm"))

    # If there are no charm files, show a message
    if not charm_files:
        self.show_info_dialog("No Shortcuts", f"No shortcuts are available for deletion in {wine_prefix_dir}.")
        return

    # Create a new dialog for selecting shortcuts
    dialog = Adw.AlertDialog(
        heading="Delete Shortcuts",
        body=f"Select the shortcuts you want to delete for {wine_prefix_dir.name}:"
    )
    # A dictionary to store the checkboxes and corresponding charm files
    checkbox_dict = {}

    # Create a vertical box to hold the checkboxes
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    # Iterate through the charm files and create checkboxes with icons and labels
    for charm_file in charm_files:
        # Create the icon and title widget (icon + label) for each charm file
        icon_title_widget = self.create_icon_title_widget(charm_file)

        # Create a horizontal box to hold the checkbox and the icon/label widget
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Create a checkbox for each shortcut
        checkbox = Gtk.CheckButton()
        hbox.append(checkbox)

        # Append the icon and title widget (icon + label)
        hbox.append(icon_title_widget)

        # Add the horizontal box (with checkbox and icon+label) to the vertical box
        vbox.append(hbox)

        # Store the checkbox and associated file in the dictionary
        checkbox_dict[checkbox] = charm_file

    # Add the vertical box to the dialog
    dialog.set_extra_child(vbox)

    # Add "Delete" and "Cancel" buttons
    dialog.add_response("delete", "Delete")
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.add_response("cancel", "Cancel")
    dialog.set_default_response("cancel")

    # Connect the response signal to handle deletion
    dialog.connect("response", self.on_delete_shortcuts_response, checkbox_dict)

    # Present the dialog
    dialog.present(self.window)


def on_delete_shortcuts_response(self, dialog, response_id, checkbox_dict):
    self.print_method_name()
    """
    Handle the response from the delete shortcut dialog.
    
    Args:
        dialog: The Adw.AlertDialog instance.
        response_id: The ID of the response clicked by the user.
        checkbox_dict: Dictionary mapping checkboxes to charm files.
    """
    if response_id == "delete":
        # Iterate through the checkboxes and delete selected files
        for checkbox, charm_file in checkbox_dict.items():
            if checkbox.get_active():  # Check if the checkbox is selected
                try:
                    if charm_file.exists():
                        # Delete the shortcut file
                        charm_file.unlink()
                        print(f"Deleted shortcut: {charm_file}")

                        # Remove the script_key from self.script_list
                        script_key = self.get_script_key_from_shortcut(charm_file)
                        if script_key in self.script_list:
                            del self.script_list[script_key]
                            print(f"Removed script {script_key} from script_list")

                        # Optionally, remove from ui_data if applicable
                        if hasattr(self, 'ui_data') and script_key in self.ui_data:
                            del self.ui_data[script_key]
                            print(f"Removed script {script_key} from ui_data")

                        # Optionally update the UI (e.g., refresh the script list or view)
                        self.load_script_list()
                        self.create_script_list()  # Update the UI to reflect changes
                    else:
                        print(f"Shortcut file does not exist: {charm_file}")
                except Exception as e:
                    print(f"Error deleting shortcut: {e}")
    else:
        print("Deletion canceled")

    # Close the dialog
    dialog.close()



def get_script_key_from_shortcut(self, shortcut_file):
    self.print_method_name()
    """
    Retrieve the script_key for a given shortcut file.
    
    Args:
        shortcut_file: The path to the shortcut.
        
    Returns:
        The corresponding script_key from script_list, if found.
    """
    for script_key, script_data in list(self.script_list.items()):
        script_path = Path(str(script_data['script_path'])).expanduser().resolve()
        if script_path == shortcut_file:
            return script_key
    return None

def show_wine_arguments_entry(self, script, script_key, *args):
    self.print_method_name()
    """
    Show an Adw.AlertDialog to allow the user to edit Wine arguments.

    Args:
        script_key: The sha256sum key for the script.
        button: The button that triggered the edit request.
    """
    # Retrieve script_data directly from self.script_list using the sha256sum as script_key
    print("--=---------------------------========-------------")
    print(f"script_key = {script_key}")
    print(f"self.script_list:\n{self.script_list}")
    # Ensure we're using the updated script path
    script_data = self.script_list.get(script_key)
    if script_data:
        script_path = Path(str(script_data['script_path'])).expanduser().resolve()
    else:
        print(f"Error: Script key {script_key} not found in script_list.")
        return
    
    print("--=---------------------------========-------------")
    
    print(script_data)
    # Handle case where the script_key is not found
    if not script_data:
        print(f"Error: Script with key {script_key} not found.")
        return

    # Get the current arguments or set a default value
    current_args = script_data.get('args')
    if not current_args:  # This checks if args is None, empty string, or any falsy value
        current_args = "-opengl -SkipBuildPatchPrereq"

    # Create an Adw.AlertDialog
    dialog = Adw.AlertDialog(
        title="Edit Wine Arguments",
        body="Modify the Wine arguments for this script:"
    )

    # Create an entry field and set the current arguments or default
    entry = Gtk.Entry()
    entry.set_text(current_args)

    # Add the entry field to the dialog
    dialog.set_extra_child(entry)

    # Add "OK" and "Cancel" buttons
    dialog.add_response("ok", "OK")
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.add_response("cancel", "Cancel")
    dialog.set_default_response("cancel")

    # Connect the response signal to handle the user's input
    dialog.connect("response", self.on_wine_arguments_dialog_response, entry, script_key)

    # Present the dialog
    dialog.present(self.window)


def on_wine_arguments_dialog_response(self, dialog, response_id, entry, script_key):
    self.print_method_name()
    """
    Handle the response from the Wine arguments dialog.
    
    Args:
        dialog: The Adw.AlertDialog instance.
        response_id: The ID of the response clicked by the user.
        entry: The Gtk.Entry widget where the user modified the Wine arguments.
        script_key: The key for the script in the script_list.
    """
    if response_id == "ok":
        # Get the new Wine arguments from the entry
        new_args = entry.get_text().strip()

        # Update the script data in both the YAML file and self.script_list
        try:
            # Update the in-memory script data
            script_data = self.extract_yaml_info(script_key)
            script_data['args'] = new_args

            # Update the in-memory representation
            self.script_list[script_key]['args'] = new_args

            # Get the script path from the script info
            script_path = Path(str(script_data['script_path'])).expanduser().resolve()

            # Write the updated info back to the YAML file
            with open(script_path, 'w') as file:
                yaml.dump(script_data, file, default_style="'", default_flow_style=False, width=10000)

            print(f"Updated Wine arguments for {script_path}: {new_args}")

            ## Optionally refresh the script list or UI to reflect the changes
            ##self.create_script_list()

        except Exception as e:
            print(f"Error updating Wine arguments for {script_key}: {e}")

    else:
        print("Wine arguments modification canceled")

    # Close the dialog
    dialog.close()



def show_rename_shortcut_entry(self, script, script_key, *args):
    self.print_method_name()
    """
    Show an Adw.AlertDialog to allow the user to rename a shortcut.

    Args:
        script_key: The sha256sum key for the script.
        button: The button that triggered the rename request.
    """
    # Retrieve script_data directly from self.script_list using the sha256sum as script_key
    print(f"script_key = {script_key}")
    print(f"self.script_list:\n{self.script_list}")
    # Ensure we're using the updated script path
    script_data = self.script_list.get(script_key)
    if script_data:
        script_path = Path(str(script_data['script_path'])).expanduser().resolve()
    else:
        print(f"Error: Script key {script_key} not found in script_list.")
        return

    # Get the current name of the shortcut
    current_name = script_data.get('progname')
    if not current_name:  # In case the current name is missing
        current_name = "New Shortcut"

    # Create an Adw.AlertDialog for renaming
    dialog = Adw.AlertDialog(
        title="Rename Shortcut",
        body="Enter the new name for the shortcut:"
    )

    # Create an entry field and set the current name
    entry = Gtk.Entry()
    entry.set_text(current_name)

    # Add the entry field to the dialog
    dialog.set_extra_child(entry)

    # Add "OK" and "Cancel" buttons
    dialog.add_response("ok", "OK")
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.add_response("cancel", "Cancel")
    dialog.set_default_response("cancel")

    # Connect the response signal to handle the user's input
    dialog.connect("response", self.on_show_rename_shortcut_dialog_response, entry, script_key)

    # Present the dialog
    dialog.present(self.window)

def on_show_rename_shortcut_dialog_response(self, dialog, response_id, entry, script_key):
    self.print_method_name()
    """
    Handle the response from the Rename Shortcut dialog.

    Args:
        dialog: The Adw.AlertDialog instance.
        response_id: The ID of the response clicked by the user.
        entry: The Gtk.Entry widget where the user entered the new shortcut name.
        script_key: The key for the script in the script_list.
    """
    if response_id == "ok":
        # Get the new shortcut name from the entry
        new_name = entry.get_text().strip()

        # Update the script data in both the YAML file and self.script_list
        try:
            # Update the in-memory script data
            script_data = self.extract_yaml_info(script_key)
            old_progname = script_data.get('progname', '')

            # Update the in-memory representation
            script_data['progname'] = new_name

            # Get the script path from the script info
            script_path = Path(str(script_data['script_path'])).expanduser().resolve()

            print("*"*100)
            print("writing script_path = {script_path}")

            # Rename the .charm file and associated icon
            new_script_path = self.rename_script_and_icon(script_path, old_progname, new_name)
            
            # Write the updated info back to the YAML file
            with open(new_script_path, 'w') as file:
                script_data['script_path'] = str(new_script_path).replace(str(Path.home()), "~")
                yaml.dump(script_data, file, default_style="'", default_flow_style=False, width=10000)
                
            # Ensure that script_data still contains the same sha256sum
            existing_sha256sum = script_data.get('sha256sum')

            # Extract icon and create desktop entry
            exe_file = Path(str(script_data['exe_file']))  # Assuming exe_file exists in script_data
            icon_path = new_script_path.with_suffix(".png")  # Correct the icon path generation
            print("#" * 100)
            print(icon_path)

            # Remove the old script_key and update script data with the new path
            if script_key in self.script_list:
                # Load the script data first
                script_data = self.script_list[script_key]
                #print(script_data['script_path'])
                
                # Update the script path with the new script path
                script_data['script_path'] = str(new_script_path)
                script_data['mtime'] = new_script_path.stat().st_mtime
                print(script_data['script_path'])



                # Update the script_list with the updated script_data
                self.script_list[script_key] = script_data

                # Update the UI row for the renamed script
                row = self.create_script_row(script_key, script_data)
                if row:
                    self.flowbox.prepend(row)

                print(f"Removed old script_key {script_key} from script_list")

            if script_key in self.script_ui_data:
                # Update the script_path for the given script_key
                self.script_ui_data[script_key]['script_path'] = str(new_script_path)
                print(f"Updated script_path for {script_key} to {new_script_path}")
            else:
                print(f"Error: script_key {script_key} not found in script_data_two")   
                print("#" * 100)
                
            # Add the updated script data to self.script_list using the existing sha256sum
            self.script_list[existing_sha256sum] = script_data
            
            row = self.create_script_row(existing_sha256sum, script_data)
            
            # Mark the script as new and update the UI
            self.new_scripts.add(new_script_path.stem)

            # Add or update script row in UI
            self.script_list = {existing_sha256sum: script_data, **self.script_list}

            # Refresh the UI to load the renamed script
            # self.create_script_list()

            print(f"Renamed and loaded script: {new_script_path}")

        except Exception as e:
            print(f"Error updating shortcut name for {script_key}: {e}")

    else:
        print("Shortcut rename canceled")

    # Close the dialog
    dialog.close()

def rename_script_and_icon(self, script_path, old_progname, new_name):
    self.print_method_name()
    """
    Rename the script file and its associated icon file.

    Args:
        script_path: The path to the script file.
        old_progname: The old name of the shortcut.
        new_name: The new name of the shortcut.

    Returns:
        Path: The new path of the renamed script file.
    """
    try:
        # Rename the icon file if it exists
        old_icon = script_path.stem
        old_icon_name = f"{old_icon.replace(' ', '_')}.png"
        new_icon_name = f"{new_name.replace(' ', '_')}.png"
        icon_path = script_path.parent / old_icon_name
        print("@"*100)
        print(f"""
        script_path = {script_path}
        script_path.stem = {script_path.stem}
        old_icon = {old_icon}
        old_icon_name = {old_icon_name}
        new_icon_name = {new_icon_name}
        icon_path = {icon_path}
        """)
        if icon_path.exists():
            new_icon_path = script_path.parent / new_icon_name
            icon_path.rename(new_icon_path)
            print(f"Renamed icon from {old_icon_name} to {new_icon_name}")

        # Rename the .charm file
        new_script_path = script_path.with_stem(new_name.replace(' ', '_'))
        script_path.rename(new_script_path)
        print(f"Renamed script from {script_path} to {new_script_path}")
        self.headerbar.set_title_widget(self.create_icon_title_widget(new_script_path))
        return new_script_path

    except Exception as e:
        print(f"Error renaming script or icon: {e}")
        return script_path  # Return the original path in case of failure


def show_change_icon_dialog(self, script, script_key, *args):
    self.print_method_name()
    # Ensure we're using the updated script path
    script_data = self.script_list.get(script_key)
    if script_data:
        script_path = Path(str(script_data['script_path'])).expanduser().resolve()
    else:
        print(f"Error: Script key {script_key} not found in script_list.")
        return
    file_dialog = Gtk.FileDialog.new()
    file_filter = Gtk.FileFilter()
    file_filter.set_name("Image and Executable files")
    file_filter.add_mime_type("image/png")
    file_filter.add_mime_type("image/svg+xml")
    file_filter.add_mime_type("image/jpeg")  # For .jpg and .jpeg

    file_filter.add_mime_type("application/x-ms-dos-executable")

    # Add patterns for case-insensitive extensions
    for ext in ["*.exe", "*.EXE", "*.msi", "*.MSI", "*.wzt", "*.WZT", "*.bottle", "*.BOTTLE", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG", "*.png", "*.PNG", "*.svg", "*.SVG"]:
        file_filter.add_pattern(ext)

    filter_model = Gio.ListStore.new(Gtk.FileFilter)
    filter_model.append(file_filter)
    file_dialog.set_filters(filter_model)

    file_dialog.open(self.window, None, lambda dlg, res: self.on_change_icon_response(dlg, res, script_path))

def on_change_icon_response(self, dialog, result, script_path):
    self.print_method_name()
    try:
        file = dialog.open_finish(result)
        if file:
            file_path = file.get_path()
            suffix = Path(file_path).suffix.lower()
            if suffix in [".png", ".svg", ".jpg", ".jpeg"]:
                self.change_icon(script_path, file_path)
            elif suffix in [".exe", ".msi"]:
                self.extract_and_change_icon(script_path, file_path)
            # Update the icon in the title bar
            self.headerbar.set_title_widget(self.create_icon_title_widget(script_path))
            self.new_scripts.add(script_path.stem)
    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")

def clear_icon_cache_for_script(self, script_path):
    script_str = str(script_path)
    self.icon_cache = {k: v for k, v in self.icon_cache.items() if k[0] != script_str}

def change_icon(self, script_path, new_icon_path):
    self.print_method_name()
    script_path = Path(script_path)
    icon_path = script_path.with_suffix(".png")
    backup_icon_path = icon_path.with_suffix(".bak")

    if icon_path.exists():
        shutil.move(icon_path, backup_icon_path)

    shutil.copy(new_icon_path, icon_path)
    self.clear_icon_cache_for_script(script_path)

def extract_and_change_icon(self, script_path, exe_path):
    self.print_method_name()
    script_path = Path(script_path)
    icon_path = script_path.with_suffix(".png")
    backup_icon_path = icon_path.with_suffix(".bak")

    if icon_path.exists():
        shutil.move(icon_path, backup_icon_path)

    extracted_icon_path = self.extract_icon(exe_path, script_path.parent, script_path.stem, script_path.stem)
    if extracted_icon_path:
        shutil.move(extracted_icon_path, icon_path)
        self.clear_icon_cache_for_script(script_path)
        
def reset_shortcut_confirmation(self, script, script_key, button=None):
    self.print_method_name()
    script_data = self.script_list.get(script_key)
    if script_data:
        exe_file = Path(str(script_data.get('exe_file')))

    # Create a confirmation dialog
    dialog = Adw.AlertDialog(
        title="Reset Shortcut",
        body=f"This will reset all changes and recreate the shortcut for {exe_file.name}. Do you want to proceed?"
    )
    
    # Add the "Reset" and "Cancel" buttons
    dialog.add_response("reset", "Reset")
    dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.add_response("cancel", "Cancel")
    dialog.set_default_response("cancel")
    
    # Show the dialog and connect the response signal to handle the reset
    dialog.connect("response", self.on_reset_shortcut_confirmation_response, script_key)

    # Present the dialog
    dialog.present(self.window)


def on_reset_shortcut_confirmation_response(self, dialog, response_id, script_key):
    self.print_method_name()
    if response_id == "reset":
        # Proceed with resetting the shortcut
        script_data = self.script_list.get(script_key)
        if script_data:
            script = script_data['script_path']
            self.reset_shortcut(script, script_key)
        else:
            print(f"Error: Script key {script_key} not found in script_list.")
    else:
        print("Reset canceled")

    # Close the dialog
    dialog.close()

def reset_shortcut(self, script, script_key, *args):
    self.print_method_name()
    """
    Reset the shortcut by recreating the YAML file for the script.
    
    Args:
        script: The path to the script.
        script_key: The unique key for the script in the script_list.
    """
    # Ensure we're using the updated script path
    script_data = self.script_list.get(script_key)
    if not script_data:
        print(f"Error: Script key {script_key} not found in script_list.")
        return
    
    # Extract exe_file and wineprefix from script_data
    exe_file = Path(str(script_data['exe_file'])).expanduser().resolve()
    wineprefix = str(script_data.get('wineprefix'))
    script =  Path(str(script_data['script_path'])).expanduser().resolve()
    if wineprefix is None:
        wineprefix = script.parent  # Use script's parent directory if wineprefix is not provided
    else:
        wineprefix = Path(str(wineprefix)).expanduser().resolve()

    script_path = Path(str(script_data.get('script_path'))).expanduser().resolve()

    
    # Ensure the exe_file and wineprefix exist
    if not exe_file.exists():
        print(f"Error: Executable file {exe_file} not found.")
        return
    
    if not wineprefix.exists():
        print(f"Error: Wineprefix directory {wineprefix} not found.")
        return
    
    try:
        backup_path = script_path.with_suffix('.bak')
        script_path.rename(backup_path)
        print(f"Renamed existing script to: {backup_path}")
        # Call the method to recreate the YAML file
        self.create_yaml_file(exe_file, wineprefix)
        print(f"Successfully reset the shortcut for script: {exe_file}")
    except Exception as e:
        print(f"Error resetting shortcut: {e}")
    finally:
        script_data = self.script_list.get(script_key)
        if not script_data:
            print(f"Error: Script key {script_key} not found in script_list.")
            return
        script_path = Path(str(script_data.get('script_path'))).expanduser().resolve()
        self.headerbar.set_title_widget(self.create_icon_title_widget(script_path))



def callback_wrapper(self, callback, script, script_key, button=None, *args):
    self.print_method_name()
    # Ensure button is a valid GTK button object, not a string
    if button is None or not hasattr(button, 'get_parent'):
        raise ValueError("Invalid button object passed to replace_button_with_overlay.")

    # Call the callback with the appropriate number of arguments
    callback_params = inspect.signature(callback).parameters

    if len(callback_params) == 2:
        # Callback expects only script and script_key
        return callback(script, script_key)
    elif len(callback_params) == 3:
        # Callback expects script, script_key, and button
        return callback(script, script_key, button)
    else:
        # Default case, pass all arguments (script, script_key, button, and *args)
        return callback(script, script_key, button, *args)

def update_execute_button_icon(self, ui_state):
    self.print_method_name()
    """
    Update the launch button icon based on process state.
    """
    if hasattr(self, 'launch_button') and self.launch_button is not None:
        script_key = self.current_script_key
        if script_key in self.running_processes:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
            self.launch_button.set_tooltip_text("Stop")
        else:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
            self.launch_button.set_tooltip_text("Play")
        self.launch_button.set_child(launch_icon)

def run_winetricks_script(self, script_name, wineprefix):
    self.print_method_name()
    command = f"WINEPREFIX={shlex.quote(str(wineprefix))} winetricks {script_name}"
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Successfully ran {script_name} in {wineprefix}")
    except subprocess.CalledProcessError as e:
        print(f"Error running winetricks script {script_name}: {e}")    
