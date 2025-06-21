#!/usr/bin/env python3

import gi
import threading
import subprocess
import os
import shutil
import re
import yaml
import time
import urllib.request
import json
import shlex
from pathlib import Path
from datetime import datetime, timedelta

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Adw

def get_runner(self, script_data):
    self.print_method_name()
    """
    Extracts and resolves the runner from the script data.

    Args:
        script_data (dict): The script data containing runner information.

    Returns:
        Path or str: The resolved runner path or command.
    """
    self.debug = True  # Enable debugging

    # Get the runner from the script data, fallback to 'wine' if not provided
    runner = script_data.get('runner', '').strip()
    if not runner:
        if self.debug:
            print("Runner not specified in script data, falling back to 'wine'.")
        runner = "wine"

    if self.debug:
        print(f"Using runner: {runner}")

    # If the runner is a path (e.g., /usr/bin/wine), resolve it
    try:
        if runner != "wine":
            runner = Path(runner).expanduser().resolve()
            if self.debug:
                print(f"Runner resolved as absolute path: {runner}")
    except Exception as e:
        print(f"Error resolving runner path: {e}")
        raise ValueError(f"Invalid runner path: {runner}. Error: {e}")

    # Check if the runner is a valid path or command
    runner_path = None
    if isinstance(runner, Path) and runner.is_absolute():
        runner_path = runner
    else:
        runner_path = self.find_command_in_path(runner)

    # Verify if the runner exists
    if not runner_path:
        raise FileNotFoundError(f"The runner '{runner}' was not found.")

    if self.debug:
        print(f"Resolved runner path: {runner_path}")

    try:
        # Check if the runner works by running 'runner --version'
        result = subprocess.run(
            [str(runner_path), "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy()
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip())
        if self.debug:
            print(f"Runner version: {result.stdout.strip()}")
    except Exception as e:
        raise RuntimeError(f"Failed to run '{runner_path} --version'. Error: {e}")

    return runner_path    
    
def update_runner_path_in_script(self, script_path, new_runner):
    self.print_method_name()
    """
    Update the .charm file to point to the new location of runner.
    """
    try:
        # Read the script file
        with open(script_path, "r") as file:
            script_content = file.readlines()

        # Update the runner path with the new location
        updated_content = []
        for line in script_content:
            if line.startswith("'runner':"):
                updated_content.append(f"'runner': '{new_runner}'\n")
            else:
                updated_content.append(line)

        # Write the updated content back to the file
        with open(script_path, "w") as file:
            file.writelines(updated_content)

        print(f"Updated runner in {script_path} to {new_runner}")

    except Exception as e:
        print(f"Error updating script path: {e}")
        
def change_runner(self, script, script_key, *args):
    self.print_method_name()
    """
    Display a dialog to change the runner for the given script.
    """
    self.selected_script = script
    self.selected_script_key = script_key

    # Gather valid runners (existing logic remains the same)
    all_runners = self.get_valid_runners(self.runners_dir, is_bundled=False)
    wineprefix = Path(script).parent
    prefix_runners_dir = wineprefix / "Runner"
    all_runners.extend(self.get_valid_runners(prefix_runners_dir, is_bundled=True))
    
    # Add System Wine (existing logic remains the same)
    system_wine_display, _ = self.get_system_wine()
    if system_wine_display:
        all_runners.insert(0, (system_wine_display, ""))

    if not all_runners:
        self.show_no_runners_available_dialog()
        return

    # Create AlertDialog
    dialog = Adw.AlertDialog(
        heading="Change Runner",
        body="Select a runner for the script:"
    )

    # Create DropDown with StringList model
    display_names = [display for display, _ in all_runners]
    model = Gtk.StringList.new(display_names)
    dropdown = Gtk.DropDown(model=model)
    
    # Determine current runner
    current_runner = self.script_list.get(script_key, {}).get('runner', '')
    if current_runner:
        current_runner = os.path.abspath(os.path.expanduser(current_runner))

    # Set initial selection
    runner_paths = [path for _, path in all_runners]
    try:
        selected_index = runner_paths.index(current_runner)
    except ValueError:
        selected_index = 0  # Fallback to first item if not found

    dropdown.set_selected(selected_index)

    # Create download button
    download_button = Gtk.Button(
        icon_name="emblem-downloads-symbolic",
        tooltip_text="Download Runner"
    )
    download_button.connect("clicked", lambda btn: self.on_download_runner_clicked(dialog))

    # Create layout
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    hbox.append(dropdown)
    hbox.append(download_button)
    
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.append(hbox)
    dialog.set_extra_child(content_box)

    # Configure dialog buttons
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("ok", "OK")
    dialog.set_default_response("ok")
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

    # Connect response handler
    dialog.connect("response", self.on_change_runner_response, dropdown, all_runners, script_key)
    dialog.present(self.window)

def on_change_runner_response(self, dialog, response_id, dropdown, all_runners, script_key):
    self.print_method_name()
    """Handle runner selection response"""
    if response_id == "ok":
        selected_idx = dropdown.get_selected()
        if 0 <= selected_idx < len(all_runners):
            new_display, new_path = all_runners[selected_idx]
            # System Wine handling and update logic remains the same
            new_value = '' if "System Wine" in new_display else new_path
            script_data = self.script_list.get(script_key, {})
            script_data['runner'] = self.replace_home_with_tilde_in_path(new_value)
            
            try:
                with open(Path(str(script_data['script_path'])).expanduser(), 'w') as f:
                    yaml.dump(script_data, f, default_style="'", default_flow_style=False, width=10000)
                print(f"Updated runner to {new_display}")
            except Exception as e:
                print(f"Update error: {e}")
                self.show_info_dialog("Update Failed", str(e))
    dialog.close()


def get_valid_runners(self, runners_dir, is_bundled=False):
    self.print_method_name()
    """
    Get a list of valid runners from a given directory.

    Args:
        runners_dir: Path to the directory containing runner subdirectories.
        is_bundled: Boolean indicating if these runners are from a wineprefix/Runner directory.

    Returns:
        List of tuples: (display_name, runner_path).
    """
    valid_runners = []
    try:
        for runner_dir in runners_dir.iterdir():
            runner_path = runner_dir / "bin/wine"
            if runner_path.exists() and self.validate_runner(runner_path):
                display_name = runner_dir.name
                if is_bundled:
                    display_name += " (Bundled)"
                valid_runners.append((display_name, str(runner_path)))
    except FileNotFoundError:
        print(f"{runners_dir} not found. Ignoring.")
    return valid_runners

def validate_runner(self, wine_binary):
    self.print_method_name()
    """
    Validate the Wine runner by checking if `wine --version` executes successfully.

    Args:
        wine_binary: Path to the wine binary.

    Returns:
        True if the runner works, False otherwise.
    """
    try:
        result = subprocess.run([str(wine_binary), "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception as e:
        print(f"Error validating runner {wine_binary}: {e}")
        return False



def on_download_runner_clicked(self, dialog):
    self.print_method_name()
    """
    Handle the "Download Runner" button click from the change_runner dialog.
    """
    dialog.close()
    # Pass the callback method to handle the completion
    self.on_settings_download_runner_clicked(callback=self.on_runner_download_complete)

def on_runner_download_complete(self):
    """
    Callback method to handle the completion of the runner download.
    Reopens the change_runner dialog.
    """
    # Reopen the change_runner dialog after the download complete dialog is closed
    self.change_runner(self.selected_script, self.selected_script_key)

def get_system_wine(self):
    self.print_method_name()
    """
    Check if System Wine is available and return its version.
    """
    try:
        result = subprocess.run(["wine", "--version"], capture_output=True, text=True, check=True)
        version = result.stdout.strip()
        return f"System Wine ({version})", ""
    except subprocess.CalledProcessError:
        print("System Wine not available.")
        return None, None

def show_no_runners_available_dialog(self):
    self.print_method_name()
    """
    Show a dialog when no runners are available, prompting the user to download one.
    """
    dialog = Adw.AlertDialog(
        heading="No Runners Available",
        body="No Wine runners were found. Please download a runner to proceed."
    )

    # Add dialog responses (buttons)
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("download", "Download Runner")
    dialog.set_response_appearance("download", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("download")

    # Connect response handler
    dialog.connect("response", lambda d, r: self.on_download_runner_clicked_default(d) if r == "download" else None)
    
    dialog.present(self.window)
        
def set_default_runner(self, action=None):
    self.print_method_name()
    """
    Display a dialog to set the default runner for the application.
    Updates the Settings.yaml file.
    """
    # Gather valid runners
    all_runners = self.get_valid_runners(self.runners_dir, is_bundled=False)

    # Add System Wine to the list if available
    system_wine_display, _ = self.get_system_wine()
    if system_wine_display:
        all_runners.insert(0, (system_wine_display, ""))

    if not all_runners:
        self.show_no_runners_available_dialog()
        return

    # Get default runner from settings
    settings = self.load_settings()
    default_runner = os.path.abspath(os.path.expanduser(settings.get('runner', '')))

    # Build runner paths list
    runner_paths_in_list = [
        os.path.abspath(os.path.expanduser(rp)) for _, rp in all_runners
    ]

    # Validate default runner
    if default_runner and default_runner not in runner_paths_in_list:
        if self.validate_runner(default_runner):
            runner_name = Path(default_runner).parent.name
            all_runners.append((f"{runner_name} (from settings)", default_runner))
        else:
            print(f"Invalid default runner: {default_runner}")
            default_runner = ''

    # Create widgets
    runner_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    
    # Create StringList and populate it
    runner_list = Gtk.StringList()
    combo_runner_paths = []
    for display_name, runner_path in all_runners:
        runner_list.append(display_name)
        combo_runner_paths.append(os.path.abspath(os.path.expanduser(runner_path)))

    # Create factory with proper item rendering
    factory = Gtk.SignalListItemFactory()
    factory.connect("setup", self._on_dropdown_factory_setup)
    factory.connect("bind", self._on_dropdown_factory_bind)

    # Find selected index
    selected_index = next((i for i, rp in enumerate(combo_runner_paths) if rp == default_runner), 0)

    # Create dropdown with factory
    runner_dropdown = Gtk.DropDown(
        model=runner_list,
        factory=factory,
        selected=selected_index
    )
    runner_dropdown.set_hexpand(True)

    # Create download button
    download_button = Gtk.Button(
        icon_name="emblem-downloads-symbolic",
        tooltip_text="Download Runner"
    )
    download_button.connect("clicked", lambda btn: self.on_download_runner_clicked_default(dialog))

    # Assemble widgets
    runner_hbox.append(runner_dropdown)
    runner_hbox.append(download_button)
    
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.append(runner_hbox)

    # Create and configure dialog
    dialog = Adw.AlertDialog(
        heading="Set Default Runner",
        body="Select the default runner for the application:",
        extra_child=content_box
    )
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("ok", "OK")
    dialog.props.default_response = "ok"
    dialog.props.close_response = "cancel"

    # Connect signals
    dialog.connect("response", self.on_set_default_runner_response, runner_dropdown, all_runners)
    dialog.present(self.window)

def _on_dropdown_factory_setup(self, factory, list_item):
    self.print_method_name()
    """Setup factory items for the dropdown"""
    label = Gtk.Label()
    label.set_xalign(0)
    label.set_margin_start(6)
    label.set_margin_end(6)
    list_item.set_child(label)

def _on_dropdown_factory_bind(self, factory, list_item):
    self.print_method_name()
    """Bind data to factory items"""
    label = list_item.get_child()
    string_obj = list_item.get_item()
    if string_obj and isinstance(string_obj, Gtk.StringObject):
        label.set_label(string_obj.get_string())

def on_set_default_runner_response(self, dialog, response_id, runner_dropdown, all_runners):
    self.print_method_name()
    if response_id == "ok":
        selected_index = runner_dropdown.get_selected()
        if selected_index == Gtk.INVALID_LIST_POSITION:
            print("No runner selected.")
            return

        new_runner_display, new_runner_path = all_runners[selected_index]
        print(f"Selected new default runner: {new_runner_display} -> {new_runner_path}")

        # Check architecture compatibility for non-system runners
        if new_runner_path:  # Skip check for System Wine
            runner_path = Path(new_runner_path).expanduser().resolve().parent.parent
            
            print(f"runner_path = {runner_path}")
            # Determine runner architecture
            if (runner_path / "bin/wine64").exists():
                runner_arch = "win64"
            elif (runner_path / "bin/wine").exists():
                runner_arch = "win32"
            else:
                self.show_info_dialog(
                    "Invalid Runner",
                    "Selected runner is missing Wine binaries (bin/wine or bin/wine64)"
                )
                return

            # Get template architecture from settings
            template_arch = self.settings.get("arch", "win64")
            
            # Check for 32-bit runner with 64-bit template
            if template_arch == "win64" and runner_arch == "win32":
                self.show_info_dialog(
                    "Architecture Mismatch",
                    "Cannot use 32-bit runner with 64-bit template.\n\n"
                    f"Template: {self.template} ({template_arch})\n"
                    f"Runner: {new_runner_path} ({runner_arch})"
                )
                return

        # Update settings
        new_runner_value = "" if new_runner_display.startswith("System Wine") else new_runner_path
        self.settings["runner"] = self.replace_home_with_tilde_in_path(new_runner_value)
        self.save_settings()

        # Provide feedback
        confirmation_message = f"The default runner has been set to {new_runner_display}"
        if new_runner_path:
            confirmation_message += f" ({runner_arch})"
        self.show_info_dialog("Default Runner Updated", confirmation_message)
    else:
        print("Set default runner canceled.")

def on_download_runner_clicked_default(self, dialog):
    self.print_method_name()
    """
    Handle the "Download Runner" button click from the set_default_runner dialog.
    """
    dialog.close()
    # Start the download process with the appropriate callback
    self.on_settings_download_runner_clicked(callback=self.on_runner_download_complete_default_runner)

def on_runner_download_complete_default_runner(self):
    self.print_method_name()
    """
    Callback method to handle the completion of the runner download.
    Reopens the set_default_runner dialog.
    """
    # Reopen the set_default_runner dialog after the download completes
    self.set_default_runner()



def maybe_fetch_runner_urls(self):
    self.print_method_name()
    """
    Fetch the runner URLs only if the cache is older than 1 day or missing.
    """
    if self.cache_is_stale():
        print("Cache is stale or missing. Fetching new runner data.")
        runner_data = self.fetch_runner_urls_from_github()
        if runner_data:
            self.save_runner_data_to_cache(runner_data)
        else:
            print("Failed to fetch runner data.")
    else:
        print("Using cached runner data.")

    # Load runner data into memory
    self.runner_data = self.load_runner_data_from_cache()

def cache_is_stale(self):
    self.print_method_name()
    """
    Check if the cache file is older than 24 hours or missing.
    """
    if not self.runner_cache_file.exists():
        return True  # Cache file doesn't exist

    # Get the modification time of the cache file
    mtime = self.runner_cache_file.stat().st_mtime
    last_modified = datetime.fromtimestamp(mtime)
    now = datetime.now()

    # Check if it's older than 1 day
    return (now - last_modified) > timedelta(hours=1)

def fetch_runner_urls_from_github(self):
    self.print_method_name()
    """
    Fetch the runner URLs dynamically from the GitHub API.
    """
    url = "https://api.github.com/repos/Kron4ek/Wine-Builds/releases"
    try:
        with urllib.request.urlopen(url) as response:
            if response.status != 200:
                print(f"Failed to fetch runner URLs: {response.status}")
                return None

            # Parse the response JSON
            release_data = json.loads(response.read().decode('utf-8'))
            return self.parse_runner_data(release_data)

    except Exception as e:
        print(f"Error fetching runner URLs: {e}")
        return None

def parse_runner_data(self, release_data):
    self.print_method_name()
    """
    Parse runner data from the GitHub API response.
    """
    categories = {
        "proton": [],
        "stable": [],
        "devel": [],
        "tkg": [],
        "wow64": []
    }

    for release in release_data:
        for asset in release.get('assets', []):
            download_url = asset.get('browser_download_url')
            if download_url and download_url.endswith(".tar.xz"):
                category = self.get_runner_category(download_url)
                if category:
                    categories[category].append({
                        "name": download_url.split('/')[-1].replace(".tar.xz", ""),
                        "url": download_url
                    })
    return categories

def get_runner_category(self, url):
    #self.print_method_name()
    """
    Determine the category of the runner based on its URL.
    """
    stable_pattern = r"/\d+\.0/"
    if "proton" in url:
        return "proton"
    elif "wow64" in url:
        return "wow64"
    elif "tkg" in url:
        return "tkg"
    elif "staging" in url:
        return "devel"
    elif re.search(stable_pattern, url):
        return "stable"
    else:
        return "devel"

def save_runner_data_to_cache(self, runner_data):
    self.print_method_name()
    """
    Save the runner data to the cache file in YAML format.
    """
    try:
        with open(self.runner_cache_file, 'w') as f:
            yaml.dump(runner_data, f, default_style="'", default_flow_style=False, width=10000)
        print(f"Runner data cached to {self.runner_cache_file}")
    except Exception as e:
        print(f"Error saving runner data to cache: {e}")

def load_runner_data_from_cache(self):
    self.print_method_name()
    """
    Load runner data from the cache file.
    """
    try:
        with open(self.runner_cache_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading runner data from cache: {e}")
        return None

#### RUNNER download issue with progress and cancel    
def on_settings_download_runner_clicked(self, callback=None):
    self.print_method_name()
    """
    Handle the "Runner Download" option click.
    Use the cached runners loaded at startup, or notify if not available.
    """
    if not self.runner_data:
        self.show_info_dialog(
            "Runner data not available",
            "Please try again in a moment or restart the application."
        )
        if callback:
            GLib.idle_add(callback)
        return

    # Create selection dialog using Adw.AlertDialog
    dialog = Adw.AlertDialog(
        heading="Download Wine Runner",
        body="Select the runners you wish to download."
    )

    # Dialog content setup
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    dialog.set_extra_child(content_box)

    # Dropdown setup
    dropdown_data = [
        ("Wine Proton", self.runner_data.get("proton", [])),
        ("Wine Stable", self.runner_data.get("stable", [])),
        ("Wine Devel", self.runner_data.get("devel", [])),
        ("Wine-tkg", self.runner_data.get("tkg", [])),
        ("Wine-WoW64", self.runner_data.get("wow64", []))
    ]

    combo_boxes = {}
    for label_text, file_list in dropdown_data:
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label=label_text, xalign=0, width_chars=12)
        
        # Create dropdown with StringList model
        names = ["Choose..."] + [file['name'] for file in file_list]
        model = Gtk.StringList.new(names)
        dropdown = Gtk.DropDown(model=model)
        dropdown.set_selected(0)
        
        combo_boxes[label_text] = {"dropdown": dropdown, "file_list": file_list}
        hbox.append(label)
        hbox.append(dropdown)
        content_box.append(hbox)

    # Configure dialog buttons
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("download", "Download")
    dialog.set_default_response("download")
    dialog.set_close_response("cancel")

    dialog.connect("response", self.on_download_runner_response, combo_boxes, callback)
    dialog.present(self.window)

def on_download_runner_response(self, dialog, response_id, combo_boxes, callback=None):
    self.print_method_name()
    """Handle response from runner selection dialog."""
    if response_id == "download":
        selected_runners = {}
        for label, data in combo_boxes.items():
            dropdown = data['dropdown']
            file_list = data['file_list']
            selected_pos = dropdown.get_selected()
            
            if selected_pos != 0:
                model = dropdown.get_model()
                selected_name = model.get_string(selected_pos)
                selected_runner = next((r for r in file_list if r['name'] == selected_name), None)
                if selected_runner:
                    selected_runners[label] = selected_runner

        if selected_runners:
            # Create progress dialog
            progress_dialog = Adw.AlertDialog(
                heading="Downloading Runners",
                body=""
            )
            
            # Progress UI setup
            content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            progress_dialog.set_extra_child(content_box)
            
            progress_label = Gtk.Label(label="Starting download...")
            runner_progress_bar = Gtk.ProgressBar()
            total_progress_bar = Gtk.ProgressBar()
            
            content_box.append(progress_label)
            content_box.append(runner_progress_bar)
            
            total_runners = len(selected_runners)
            if total_runners > 1:
                content_box.append(total_progress_bar)
            else:
                total_progress_bar.set_visible(False)

            # Add cancel button
            progress_dialog.add_response("cancel", "Cancel")
            progress_dialog.set_close_response("cancel")
            
            cancel_event = threading.Event()
            progress_dialog.connect("response", 
                lambda d, r: cancel_event.set() if r == "cancel" else None
            )
            
            progress_dialog.present(self.window)

            # Start download thread
            threading.Thread(
                target=self.download_runners_thread,
                args=(selected_runners, progress_dialog, total_progress_bar,
                    runner_progress_bar, progress_label, callback, cancel_event),
                daemon=True
            ).start()
        else:
            if callback:
                GLib.idle_add(callback)
    else:
        if callback:
            GLib.idle_add(callback)

def download_runners_thread(self, selected_runners, progress_dialog, total_progress_bar,
                            runner_progress_bar, progress_label, callback, cancel_event):
    self.print_method_name()
    total_runners = len(selected_runners)
    download_success = True
    current_file = None
    was_cancelled = False

    # Throttle UI updates
    last_update_time = 0
    update_interval = 250  # ms

    def update_progress(label_text, runner_fraction, total_fraction):
        nonlocal last_update_time
        current_time = GLib.get_monotonic_time() // 1000  # ms
        if current_time - last_update_time >= update_interval:
            GLib.idle_add(progress_label.set_text, label_text)
            GLib.idle_add(runner_progress_bar.set_fraction, min(1.0, runner_fraction))
            if total_runners > 1:
                GLib.idle_add(total_progress_bar.set_fraction, min(1.0, total_fraction))
            last_update_time = current_time

    try:
        for idx, (label, runner) in enumerate(selected_runners.items()):
            if cancel_event.is_set():
                download_success = False
                was_cancelled = True
                break

            current_file = self.runners_dir / f"{runner['name']}.tar.xz"
            update_progress(f"Downloading {runner['name']} ({idx + 1}/{total_runners})...", 0.0, idx / total_runners)

            try:
                self.download_and_extract_runner(
                    runner['name'],
                    runner['url'],
                    lambda p: update_progress(
                        f"Downloading {runner['name']} ({idx + 1}/{total_runners})...",
                        p,
                        idx / total_runners + p / total_runners
                    ),
                    cancel_event
                )
            except Exception as e:
                download_success = False
                if "cancelled" in str(e).lower():
                    was_cancelled = True
                    break
                else:
                    GLib.idle_add(
                        lambda: self.show_info_dialog(
                            "Download Error",
                            f"Failed to download {runner['name']}: {e}"
                        )
                    )

            if total_runners > 1:
                update_progress(f"Finished {runner['name']}", 1.0, (idx + 1) / total_runners)

        if download_success and total_runners > 1:
            update_progress("Download Complete", 1.0, 1.0)

    finally:
        if current_file and current_file.exists():
            current_file.unlink(missing_ok=True)

        def finalize_ui(title, message):
            GLib.idle_add(
                lambda: progress_dialog.close() if progress_dialog.get_mapped() else None
            )
            GLib.timeout_add(100, lambda: self.show_info_dialog(
                title,
                message,
                callback=callback if callback else None
            ))

        if was_cancelled:
            finalize_ui(
                "Download Cancelled",
                "The download was cancelled. Partially downloaded files have been deleted."
            )
        elif download_success:
            finalize_ui(
                "Download Complete",
                f"Successfully downloaded {total_runners} runner{'s' if total_runners > 1 else ''}."
            )
        else:
            finalize_ui(
                "Download Incomplete",
                "Some runners failed to download."
            )

def download_and_extract_runner(self, runner_name, download_url, progress_callback, cancel_event):
    self.print_method_name()
    """Download and extract runner with cancellation support and throttled updates."""
    runner_tar_path = self.runners_dir / f"{runner_name}.tar.xz"
    self.runners_dir.mkdir(parents=True, exist_ok=True)

    last_progress = 0
    progress_threshold = 0.05  # Update every 5%

    try:
        with urllib.request.urlopen(download_url) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            
            with open(runner_tar_path, 'wb') as f:
                while True:
                    if cancel_event.is_set():
                        raise Exception("Download cancelled by user")
                    
                    chunk = response.read(4096)  # 4KB chunks
                    if not chunk:
                        break
                    
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if cancel_event.is_set():
                        raise Exception("Download cancelled by user")
                    
                    if total_size > 0 and progress_callback:
                        progress = downloaded / total_size
                        if progress - last_progress >= progress_threshold or progress >= 1.0:
                            progress_callback(progress)
                            last_progress = progress

        # Extract asynchronously to avoid blocking
        process = subprocess.Popen(
            ["tar", "-xf", str(runner_tar_path), "-C", str(self.runners_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise Exception(f"Extraction failed: {stderr.decode()}")

        runner_tar_path.unlink()

    except Exception as e:
        if runner_tar_path.exists():
            runner_tar_path.unlink()
        raise  # Re-raise to handle in download_runners_thread 

#### /RUNNER download issue with progress and cancel        
def delete_runner(self, action=None):
    self.print_method_name()
    """
    Allow the user to delete a selected runner using modern Adw.AlertDialog and DropDown.
    """
    # Get valid runners
    all_runners = self.get_valid_runners(self.runners_dir, is_bundled=False)
    if not all_runners:
        self.show_info_dialog("No Runners Available", "No runners found to delete.")
        return

    # Create AlertDialog
    dialog = Adw.AlertDialog(
        heading="Delete Runner",
        body="Select a runner to delete:"
    )

    # Create DropDown with StringList model
    display_names = [display_name for display_name, _ in all_runners]
    model = Gtk.StringList.new(display_names)
    dropdown = Gtk.DropDown(model=model)
    dropdown.set_selected(0)

    # Build directory paths list
    runner_dirs = [os.path.join(self.runners_dir, name) for name, _ in all_runners]

    # Add dropdown to dialog content
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.append(dropdown)
    dialog.set_extra_child(content_box)

    # Configure dialog buttons
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("delete", "Delete")
    dialog.set_default_response("delete")
    dialog.set_close_response("cancel")

    # Connect response handler
    dialog.connect("response", self.on_delete_runner_response, dropdown, runner_dirs)
    dialog.present(self.window)

def on_delete_runner_response(self, dialog, response_id, dropdown, runner_dirs):
    self.print_method_name()
    """Handle delete dialog response with proper DropDown integration."""
    if response_id == "delete":
        selected_idx = dropdown.get_selected()
        if 0 <= selected_idx < len(runner_dirs):
            target_dir = runner_dirs[selected_idx]
            try:
                if os.path.isdir(target_dir):
                    shutil.rmtree(target_dir)
                    self.show_info_dialog(
                        "Deletion Successful",
                        f"Runner '{os.path.basename(target_dir)}' was successfully deleted."
                    )
                else:
                    raise FileNotFoundError(f"Directory not found: {target_dir}")
            except Exception as e:
                self.show_info_dialog(
                    "Deletion Error",
                    f"Failed to delete runner: {str(e)}"
                )
        else:
            self.show_info_dialog("Invalid Selection", "No valid runner selected.")

    dialog.close()

def backup_runner(self, action=None):
    self.print_method_name()
    """
    Allow the user to backup a runner.
    """
    # Gather valid runners from runners_dir
    all_runners = self.get_valid_runners(self.runners_dir, is_bundled=False)

    # If no runners are available, show a message
    if not all_runners:
        self.show_info_dialog("No Runners Available", "No runners found to backup.")
        return

    # Create the AlertDialog
    dialog = Adw.AlertDialog(
        heading="Backup Runner",
        body="Select a runner to backup:"
    )

    # Create the DropDown for runners
    display_names = [display_name for display_name, _ in all_runners]
    model = Gtk.StringList.new(display_names)
    dropdown = Gtk.DropDown(model=model)
    dropdown.set_selected(0)
    combo_runner_paths = [os.path.abspath(os.path.expanduser(runner_path)) for _, runner_path in all_runners]

    # Add the DropDown to the content box
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.append(dropdown)

    # Configure dialog buttons
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("ok", "OK")
    dialog.set_default_response("ok")
    dialog.set_close_response("cancel")
    dialog.set_extra_child(content_box)

    dialog.connect("response", self.on_backup_runner_response, dropdown, combo_runner_paths)
    dialog.present(self.window)

def on_backup_runner_response(self, dialog, response_id, dropdown, combo_runner_paths):
    self.print_method_name()
    if response_id == "ok":
        selected_index = dropdown.get_selected()
        if selected_index < 0 or selected_index >= len(combo_runner_paths):
            print("No runner selected.")
            self.show_info_dialog("No Runner Selected", "Please select a runner to backup.")
            dialog.close()
            return
        runner_path = combo_runner_paths[selected_index]
        model = dropdown.get_model()
        runner_name = model.get_string(selected_index)
        print(f"Selected runner to backup: {runner_name} -> {runner_path}")

        # Present a Gtk.FileDialog to select the destination to save the backup archive
        file_dialog = Gtk.FileDialog.new()
        file_dialog.set_initial_name(f"{runner_name}.tar.zst")

        # Create file filters
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Tarball archives (*.tar.gz, *.tar.xz, *.tar.zst)")
        file_filter.add_pattern("*.tar.gz")
        file_filter.add_pattern("*.tar.xz")
        file_filter.add_pattern("*.tar.zst")

        # Create a Gio.ListStore to hold the filters
        filter_list_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_list_store.append(file_filter)

        # Set the filters on the dialog
        file_dialog.set_filters(filter_list_store)

        # Define the callback for when the file dialog is closed
        def on_save_file_dialog_response(dialog, result):
            self.print_method_name()
            try:
                save_file = dialog.save_finish(result)
                if save_file:
                    destination_path = save_file.get_path()
                    print(f"Backup destination selected: {destination_path}")
                    # Start the backup process in a separate thread
                    threading.Thread(target=self.create_runner_backup, args=(runner_path, destination_path)).start()
                    self.show_info_dialog("Backup Complete", f"Runner backup saved to {destination_path}.")
            except GLib.Error as e:
                if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                    print(f"An error occurred: {e}")

        # Show the save dialog
        file_dialog.save(self.window, None, on_save_file_dialog_response)
    else:
        print("Backup runner canceled.")

    dialog.close()


def create_runner_backup(self, runner_path, destination_path):
    self.print_method_name()
    """
    Create a backup archive of the runner at runner_path, saving it to destination_path.
    """
    try:
        # Determine the compression based on the file extension
        ext = os.path.splitext(destination_path)[1]
        if ext == ".gz":
            compression_option = "-z"  # gzip
        elif ext == ".xz":
            compression_option = "-J"  # xz
        elif ext == ".zst":
            compression_option = "--zstd"  # zstd
        else:
            compression_option = ""  # no compression

        # Use pathlib.Path for path manipulations
        runner_path = Path(runner_path)
        runner_dir = runner_path.parent.parent # Get the parent directory of the runner binary
        runner_name = runner_dir.name  # Get the name of the runner directory
        print(f"Creating backup of runner: {runner_name} from {runner_dir} to {destination_path}")

        # Use tar to create the archive
        tar_command = ["tar"]
        if compression_option:
            tar_command.append(compression_option)
        tar_command.extend(["-cvf", destination_path, "-C", str(self.runners_dir), runner_name])

        print(f"Running tar command: {' '.join(tar_command)}")

        subprocess.run(tar_command, check=True)

        print("Backup created successfully.")
    except Exception as e:
        print(f"Error creating runner backup: {e}")
        # Show error dialog from the main thread
        GLib.idle_add(self.show_info_dialog, "Backup Error", f"Failed to create runner backup: {e}")
########### Restore RUnner
def restore_runner(self, action=None):
    self.print_method_name()
    """
    Allow the user to restore a runner from a backup archive.
    """
    # Present a Gtk.FileDialog to select the archive file
    file_dialog = Gtk.FileDialog.new()

    # Create file filters
    file_filter = Gtk.FileFilter()
    file_filter.set_name("Tarball archives (*.tar.gz, *.tar.xz, *.tar.zst)")
    file_filter.add_pattern("*.tar.gz")
    file_filter.add_pattern("*.tar.xz")
    file_filter.add_pattern("*.tar.zst")

    # Create a Gio.ListStore to hold the filters
    filter_list_store = Gio.ListStore.new(Gtk.FileFilter)
    filter_list_store.append(file_filter)

    # Set the filters on the dialog
    file_dialog.set_filters(filter_list_store)

    # Define the callback for when the file dialog is closed
    def on_open_file_dialog_response(dialog, result):
        self.print_method_name()
        try:
            file = dialog.open_finish(result)
            if file:
                archive_path = file.get_path()
                print(f"Selected archive to restore: {archive_path}")

                # Check if the archive contains bin/wine
                if self.archive_contains_wine(archive_path):
                    # Start the extraction in a separate thread
                    threading.Thread(target=self.extract_runner_archive, args=(archive_path,)).start()
                    self.show_info_dialog("Restore Complete", "Runner restored successfully.")
                else:
                    print("Selected archive does not contain a valid runner.")
                    self.show_info_dialog("Invalid Archive", "The selected archive does not contain a valid runner.")
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")

    # Show the open dialog
    file_dialog.open(self.window, None, on_open_file_dialog_response)

def extract_runner_archive(self, archive_path):
    self.print_method_name()
    """
    Extract the runner archive to runners_dir.
    """
    try:
        # Ensure the runners directory exists
        self.runners_dir.mkdir(parents=True, exist_ok=True)

        # Use tar to extract the archive
        tar_command = ["tar", "-xvf", archive_path, "-C", str(self.runners_dir)]
        print(f"Running tar command: {' '.join(tar_command)}")
        subprocess.run(tar_command, check=True)

        print("Runner restored successfully.")
    except Exception as e:
        print(f"Error extracting runner archive: {e}")
        # Show error dialog from the main thread
        GLib.idle_add(self.show_info_dialog, "Restore Error", f"Failed to restore runner: {e}")


def archive_contains_wine(self, archive_path):
    self.print_method_name()
    """
    Check if the archive contains bin/wine.
    """
    try:
        # Use tar -tf to list the contents
        tar_command = ["tar", "-tf", archive_path]
        result = subprocess.run(tar_command, check=True, capture_output=True, text=True)
        file_list = result.stdout.splitlines()
        for file in file_list:
            if "bin/wine" in file:
                return True
        return False
    except Exception as e:
        print(f"Error checking archive contents: {e}")
        return False
        
##################### Import runner
def import_runner(self, action=None, param=None):
    self.print_method_name()
    """Import a Wine runner into the runners directory."""
    file_dialog = Gtk.FileDialog.new()
    file_dialog.set_modal(True)
    file_dialog.select_folder(self.window, None, self.on_import_runner_response)

def on_import_runner_response(self, dialog, result):
    self.print_method_name()
    try:
        folder = dialog.select_folder_finish(result)
        if folder:
            src = Path(folder.get_path())
            if not self.verify_runner_source(src):
                GLib.idle_add(self.show_info_dialog, "Invalid Runner", 
                            "Selected directory is not a valid Wine runner")
                return

            runner_name = src.name
            dst = self.runners_dir / runner_name
            backup_dir = self.runners_dir / f"{runner_name}_backup_{int(time.time())}"

            steps = [
                ("Verifying runner", lambda: self.verify_runner_binary(src)),
                ("Backing up existing runner", lambda: self.backup_existing_directory(dst, backup_dir)),
                ("Copying runner files", lambda: self.custom_copytree(src, dst)),
                ("Validating installation", lambda: self.validate_runner(dst / "bin/wine")),
                ("Setting permissions", lambda: self.set_runner_permissions(dst)),
            ]

            self.show_processing_spinner(f"Importing {runner_name}")
            self.connect_open_button_with_import_wine_directory_cancel()
            threading.Thread(target=self.process_runner_import, args=(steps, dst, backup_dir)).start()

    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"Runner import error: {e}")

def process_runner_import(self, steps, dst, backup_dir):
    self.print_method_name()
    """Handle runner import with error handling and rollback"""
    self.stop_processing = False
    self.total_steps = len(steps)
    
    try:
        for index, (step_text, step_func) in enumerate(steps, 1):
            if self.stop_processing:
                raise Exception("Operation cancelled by user")
                
            GLib.idle_add(self.show_initializing_step, step_text)
            step_func()
            GLib.idle_add(self.mark_step_as_done, step_text)
            GLib.idle_add(lambda: self.progress_bar.set_fraction(index / self.total_steps))

        GLib.idle_add(self.show_info_dialog, "Success", 
                    f"Runner '{dst.name}' imported successfully")
        self.cleanup_backup(backup_dir)
        GLib.idle_add(self.refresh_runner_list)

    except Exception as e:
        GLib.idle_add(self.handle_runner_import_error, dst, backup_dir, str(e))
        
    finally:
        GLib.idle_add(self.on_import_runner_directory_completed)

def verify_runner_source(self, src):
    self.print_method_name()
    """Validate the source directory contains a valid Wine runner"""
    wine_binary = src / "bin/wine"
    return wine_binary.exists() and self.validate_runner(wine_binary)

def verify_runner_binary(self, src):
    self.print_method_name()
    """Explicit validation check for the runner binary"""
    wine_binary = src / "bin/wine"
    if not wine_binary.exists():
        raise Exception("Missing Wine binary (bin/wine)")
    if not self.validate_runner(wine_binary):
        raise Exception("Wine binary validation failed")

def set_runner_permissions(self, runner_path):
    self.print_method_name()
    """Set executable permissions for critical runner files"""
    wine_binary = runner_path / "bin/wine"
    wineserver = runner_path / "bin/wineserver"
    
    try:
        wine_binary.chmod(0o755)
        wineserver.chmod(0o755)
        for bin_file in (runner_path / "bin").glob("*"):
            if bin_file.is_file():
                bin_file.chmod(0o755)
    except Exception as e:
        print(f"Warning: Could not set permissions - {e}")

def handle_runner_import_error(self, dst, backup_dir, error_msg):
    self.print_method_name()
    """Handle runner import errors and cleanup"""
    try:
        if dst.exists():
            shutil.rmtree(dst)
        if backup_dir.exists():
            backup_dir.rename(dst)
    except Exception as e:
        error_msg += f"\nCleanup error: {str(e)}"
    
    self.show_info_dialog("Runner Import Failed", error_msg)

def on_import_runner_directory_completed(self):
    self.print_method_name()
    """Finalize runner import UI updates"""
    self.set_open_button_label("Open")
    self.set_open_button_icon_visible(True)
    self.hide_processing_spinner()
    self.reconnect_open_button()
    self.show_options_for_settings()
    print("Runner import process completed.")

def refresh_runner_list(self):
    self.print_method_name()
    """Refresh the runner list in settings UI"""
    if hasattr(self, 'runner_dropdown'):
        all_runners = self.get_all_runners()
        string_objs = [Gtk.StringObject.new(r[0]) for r in all_runners]
        self.runner_dropdown.set_model(Gtk.StringList.new([r[0] for r in all_runners]))


########## setting default template should wineboot -u
def show_confirm_dialog(self, title, message, callback=None):
    self.print_method_name()
    dialog = Adw.AlertDialog(
        heading=title,
        body=message
    )
    
    # Add Yes and No responses
    dialog.add_response("yes", "Yes")
    dialog.add_response("no", "No")
    
    # Configure dialog properties
    dialog.props.default_response = "yes"
    dialog.props.close_response = "no"

    def on_response(d, response_id):
        self.print_method_name()
        if callback is not None:
            callback(d, response_id)

    dialog.connect("response", on_response)
    dialog.present(self.window)

def on_set_default_runner_response(self, dialog, response_id, runner_dropdown, all_runners):
    self.print_method_name()
    if response_id == "ok":
        selected_index = runner_dropdown.get_selected()
        if selected_index == Gtk.INVALID_LIST_POSITION:
            print("No runner selected.")
            return

        new_runner_display, new_runner_path = all_runners[selected_index]
        print(f"Selected new default runner: {new_runner_display} -> {new_runner_path}")

        # Check architecture compatibility for non-system runners
        if new_runner_path:  # Skip check for System Wine
            runner_path = Path(new_runner_path).expanduser().resolve().parent.parent
            print(f"runner_path = {runner_path}")
            # Determine runner architecture
            if (runner_path / "bin/wine64").exists():
                print("win64 detected")
                runner_arch = "win64"
            elif (runner_path / "bin/wine").exists() and "wow64" in str(runner_path):
                print("wow64 detected")
                runner_arch = "win64"                
            elif (runner_path / "bin/wine").exists():
                print("win32 detected")
                runner_arch = "win32"
            else:
                self.show_info_dialog(
                    "Invalid Runner",
                    "Selected runner is missing Wine binaries (bin/wine or bin/wine64)"
                )
                return

            # Get template architecture from settings
            template_arch = self.settings.get("arch", "win64")
            
            # Check for 32-bit runner with 64-bit template
            if template_arch == "win64" and runner_arch == "win32":
                self.show_info_dialog(
                    "Architecture Mismatch",
                    "Cannot use 32-bit runner with 64-bit template.\n\n"
                    f"Template: {self.template} ({template_arch})\n"
                    f"Runner: {new_runner_path} ({runner_arch})"
                )
                return

        # Update settings
        new_runner_value = "" if new_runner_display.startswith("System Wine") else new_runner_path
        self.settings["runner"] = self.replace_home_with_tilde_in_path(new_runner_value)
        self.save_settings()

        # Resolve and expand self.template for WINEPREFIX
        wineprefix = Path(self.template).expanduser().resolve()

        # Show confirmation dialog for runner update
        confirmation_message = f"The default runner has been set to {new_runner_display}"
        if new_runner_path:
            confirmation_message += f" ({runner_arch})"
        self.show_info_dialog("Default Runner Updated", confirmation_message)

        # Ask user if they want to run wineboot -u for non-system runners
        if new_runner_path:  # Only prompt for wineboot if a non-system runner is selected
            def on_wineboot_confirm_response(dialog, response_id):
                if response_id == "yes":
                    def wineboot_operation():
                        try:
                            runner_dir = Path(new_runner_path).expanduser().resolve().parent
                            prerun_command = [
                                "sh", "-c",
                                f"export PATH={shlex.quote(str(runner_dir))}:$PATH; "
                                f"WINEPREFIX={shlex.quote(str(wineprefix))} wineserver -k; "
                                f"WINEPREFIX={shlex.quote(str(wineprefix))} wineboot -u;"
                            ]
                            
                            if self.debug:
                                print(f"Running wineboot: {' '.join(prerun_command)}")

                            subprocess.run(prerun_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            
                            # Provide feedback in the main thread
                            GLib.idle_add(self.show_info_dialog, "Wineboot Completed", f"Updated Wine prefix for {new_runner_display} at {wineprefix}")

                        except subprocess.CalledProcessError as e:
                            error_msg = f"Wineboot failed (code {e.returncode}): {e.stderr}"
                            GLib.idle_add(self.show_info_dialog, "Wineboot Error", error_msg)
                        except Exception as e:
                            error_msg = f"Wineboot error: {str(e)}"
                            GLib.idle_add(self.show_info_dialog, "Wineboot Error", error_msg)

                    # Start wineboot in a separate thread
                    threading.Thread(target=wineboot_operation, daemon=True).start()

            # Show confirmation dialog for running wineboot
            self.show_confirm_dialog(
                "Run Wineboot?",
                f"Do you want to run wineboot to update the Wine prefix for {new_runner_display} at {wineprefix}?",
                callback=on_wineboot_confirm_response
            )
    else:
        print("Set default runner canceled.")
        

        
