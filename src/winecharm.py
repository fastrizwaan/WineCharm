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



class WineCharmApp(Gtk.Application):
    def __init__(self):
        self.count = 0
        self.log_file_path = os.path.expanduser('~/logfile.log')
        creation_date_and_time = datetime.now()
        log_message = f"=>{creation_date_and_time}\n" + "-"*50 + "\n"

        #with open(self.log_file_path, 'a') as log_file:
        #    log_file.write(log_message)

        self.print_method_name()
        super().__init__(application_id='io.github.fastrizwaan.WineCharm', flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None  # Initialize window as None
        Adw.init()
        
        # Move the global variables to instance attributes
        self.debug = False
        self.version = "0.99"
        # Paths and directories
        self.winecharmdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm")).resolve()
        self.prefixes_dir = self.winecharmdir / "Prefixes"
        self.templates_dir = self.winecharmdir / "Templates"
        self.runners_dir = self.winecharmdir / "Runners"
        self.default_template_win64 = self.templates_dir / "WineCharm-win64"
        self.default_template_win32 = self.templates_dir / "WineCharm-win32"
        self.single_prefix_dir_win64 = self.prefixes_dir / "WineCharm-Single_win64"
        self.single_prefix_dir_win32 = self.prefixes_dir / "WineCharm-Single_win32"

        self.applicationsdir = Path(os.path.expanduser("~/.local/share/applications")).resolve()
        self.tempdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/tmp")).resolve()
        self.iconsdir = Path(os.path.expanduser("~/.local/share/icons")).resolve()
        self.do_not_kill = "bin/winecharm"
        
        self.SOCKET_FILE = self.winecharmdir / "winecharm_socket"
        self.settings_file = self.winecharmdir / "Settings.yaml"
        # Variables that need to be dynamically updated
        self.runner = ""  # which wine
        self.wine_version = ""  # runner --version
        self.template = ""  # default: WineCharm-win64, if not found in Settings.yaml
        self.arch = "win64"  # default: win
                
        self.connect("activate", self.on_activate)
        self.connect("startup", self.on_startup)
        self.connect("open", self.on_open)
        
        # Initialize other attributes here
        self.new_scripts = set()  # Initialize new_scripts as an empty set
        self.file_lock = Lock()
        
        # Initialize other attributes that might be missing
        self.selected_script = None
        self.selected_script_name = None
        self.selected_row = None
        self.initializing_template = False
        self.running_processes = {}
        self.script_buttons = {}
        self.play_stop_handlers = {}
        self.options_listbox = None
        self.launch_button = None
        self.search_active = False
        self.command_line_file = None
        self.monitoring_active = True  # Flag to control monitoring
        self.scripts = []  # Or use a list of script objects if applicable
        self.count = 0
        self.focus_event_timer_id = None        
        self.create_required_directories() # Create Required Directories
        self.icon_view = False
        self.script_list = {}
        self.import_steps_ui = {}
        self.current_script = None
        self.current_script_key = None
        self.stop_processing = False
        self.processing_thread = None
        self.current_backup_path = None
        self.current_process = None
        self.runner_to_use = None
        self.process_lock = threading.Lock()
        self.called_from_settings = False
        self.open_button_handler_id = None
        self.lnk_processed_success_status = False
        self.manually_killed = False

        # Register the SIGINT signal handler
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.script_buttons = {}
        self.current_clicked_row = None  # Initialize current clicked row
        self.hamburger_actions = [
            ("🛠️ Settings...", self.show_options_for_settings),
            ("☠️ Kill all...", self.on_kill_all_clicked),
            ("🍾 Restore...", self.restore_from_backup),
            ("📥 Import Wine Directory", self.on_import_wine_directory_clicked),
            ("❓ Help...", self.on_help_clicked),
            ("📖 About...", self.on_about_clicked),
            ("🚪 Quit...", self.quit_app)
        ]

        self.css_provider = Gtk.CssProvider()
        self.css_provider.load_from_data(b"""
            .menu-button.flat:hover {
                background-color: @headerbar_bg_color;
            }
            .button-box button {
                min-width: 80px;
                min-height: 36px;
            }
            .highlighted {
                background-color: rgba(127, 127, 127, 0.15); 
            }
            .yellow {
                background-color: rgba(255, 255, 0, 0.25);
                font-weight: bold;
            }
            .red {
                background-color: rgba(228, 0, 0, 0.25);
                font-weight: bold;
            }
            .blue {
                background-color: rgba(53, 132, 228, 0.25);
                font-weight: bold;
            }
            .normal-font {  /* Add the CSS rule for the normal-font class */
            font-weight: normal;
            }
            progressbar.header-progress {
                min-height: 4px;
                background: none;
                border: none;
                padding: 0;
            }
            progressbar.header-progress trough {
                min-height: 4px;
                border: none;
            }
            progressbar.header-progress progress {
                min-height: 4px;
            }
            .rounded-container {
                border-radius: 5px;
            }
        """)

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.back_button.connect("clicked", self.on_back_button_clicked)
        self.open_button_handler_id = None

        # Runner cache file
        self.runner_cache_file = self.winecharmdir / "runner_cache.yaml"
        self.runner_data = None  # Will hold the runner data after fetching
        self.settings = self.load_settings()  # Add this line

        # Set keyboard accelerators
        self.set_accels_for_action("win.search", ["<Ctrl>f"])
        self.set_accels_for_action("win.open", ["<Ctrl>o"])
        self.set_accels_for_action("win.on_kill_all_clicked", ["<Ctrl>k"])
        self.set_accels_for_action("win.toggle_view", ["<Ctrl>v"])
        self.set_accels_for_action("win.back", ["<Ctrl>BackSpace"])

        self.count = 0

    def print_method_name(self):
        return
        self.count = self.count + 1 
        current_frame = sys._getframe(1)  # Get the caller's frame
        method_name = current_frame.f_code.co_name
        print(f"=>{self.count} {method_name}")
        # uncomment below to write to log file
        # log_message = f"=>{self.count} {method_name}\n"

        # with open(self.log_file_path, 'a') as log_file:
        #     log_file.write(log_message)
        
    def ensure_directory_exists(self, directory):
        self.print_method_name()
        directory = Path(directory)  # Ensure it's a Path object
        if not directory.exists():
            try:
                directory.mkdir(parents=True, exist_ok=True)
                print(f"Created directory: {directory}")
            except Exception as e:
                print(f"Error creating directory {directory}: {e}")
        else:
            pass 
            #print(f"Directory already exists: {directory}")

    def create_required_directories(self):
        self.print_method_name()
        winecharm_data_dir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data")).resolve()
        self.tempdir =  winecharm_data_dir / "tmp"
        self.winecharmdir = winecharm_data_dir / "winecharm"
        self.prefixes_dir = self.winecharmdir / "Prefixes"
        self.templates_dir = self.winecharmdir / "Templates"
        self.runners_dir = self.winecharmdir / "Runners"

        directories = [self.winecharmdir, self.prefixes_dir, self.templates_dir, self.runners_dir, self.tempdir]

        for directory in directories:
            self.ensure_directory_exists(directory)


    def on_settings_clicked(self, action=None, param=None):
        self.print_method_name()
        print("Settings action triggered")
        # You can add code here to open a settings window or dialog.

    def find_matching_processes(self, exe_name_pattern):
        self.print_method_name()
        matching_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                # Retrieve the process name, executable path, or command line arguments
                proc_name = proc.info['name']
                proc_exe = proc.info['exe']
                proc_cmdline = proc.info['cmdline']
                
                # Match the executable name pattern
                if proc_exe and exe_name_pattern in proc_exe:
                    matching_processes.append(proc)
                elif proc_name and exe_name_pattern in proc_name:
                    matching_processes.append(proc)
                elif proc_cmdline and any(exe_name_pattern in arg for arg in proc_cmdline):
                    matching_processes.append(proc)
            
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Ignore processes that are no longer available or cannot be accessed
                pass
        
        return matching_processes


    def on_kill_all_clicked(self, action=None, param=None):
        self.print_method_name()

        # Set the manually_stopped flag to True
        self.manually_killed = True
        
        try:
            winecharm_pids = []
            wine_exe_pids = []
            exe_name_pattern = ".exe"  # Pattern for executables

            # Find all processes that match the .exe pattern using find_matching_processes
            matching_processes = self.find_matching_processes(exe_name_pattern)

            for proc in matching_processes:
                try:
                    pid = proc.info['pid']
                    proc_cmdline = proc.info['cmdline']

                    # Build command string for matching (similar to pgrep)
                    command = " ".join(proc_cmdline) if proc_cmdline else proc.info['name']

                    # Check if this is a WineCharm process (using self.do_not_kill pattern)
                    if self.do_not_kill in command:
                        winecharm_pids.append(pid)
                    # Check if this is a .exe process and exclude PID 1 (system process)
                    elif pid != 1:
                        wine_exe_pids.append(pid)

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Ignore processes that are no longer available or cannot be accessed
                    pass

            # Reverse to kill child processes first (if applicable)
            wine_exe_pids.reverse()

            # Kill the Wine exe processes, excluding WineCharm PIDs
            for pid in wine_exe_pids:
                if pid not in winecharm_pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                        print(f"Terminated process with PID: {pid}")
                    except ProcessLookupError:
                        print(f"Process with PID {pid} not found")
                    except PermissionError:
                        print(f"Permission denied to kill PID: {pid}")

        except Exception as e:
            print(f"Error retrieving process list: {e}")

        finally:
            self.manually_killed = False
            # Optionally, clear the running processes dictionary
            self.running_processes.clear()
            GLib.timeout_add_seconds(0.5, self.load_script_list)

    def on_help_clicked(self, action=None, param=None):
        self.print_method_name()
        print("Help action triggered")
        # You can add code here to show a help dialog or window.

    def on_about_clicked(self, action=None, param=None):
        self.print_method_name()
        about_dialog = Adw.AboutWindow(
            transient_for=self.window,
            application_name="WineCharm",
            application_icon="io.github.fastrizwaan.WineCharm",
            version=f"{self.version}",
            copyright="GNU General Public License (GPLv3+)",
            comments="A Charming Wine GUI Application",
            website="https://github.com/fastrizwaan/WineCharm",
            developer_name="Mohammed Asif Ali Rizvan",
            license_type=Gtk.License.GPL_3_0,
            issue_url="https://github.com/fastrizwaan/WineCharm/issues"
        )
        about_dialog.present()

    def quit_app(self, action=None, param=None):
        self.print_method_name()
        self.quit()


    def get_default_icon_path(self):
        #self.print_method_name()
        xdg_data_dirs = os.getenv("XDG_DATA_DIRS", "").split(":")
        icon_relative_path = "icons/hicolor/128x128/apps/org.winehq.Wine.png"

        for data_dir in xdg_data_dirs:
            icon_path = Path(data_dir) / icon_relative_path
            if icon_path.exists():
                return icon_path

        # Fallback icon path in case none of the paths in XDG_DATA_DIRS contain the icon
        return Path("/app/share/icons/hicolor/128x128/apps/org.winehq.Wine.png")

    def on_startup(self, app):
        self.create_main_window()
        # Clear or initialize the script list
        self.set_dynamic_variables()
        self.script_list = {}
        self.load_script_list()
        self.create_script_list()

        if not self.template:
            self.template = getattr(self, f'default_template_{self.arch}')
            self.template = self.expand_and_resolve_path(self.template)


        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        else:
            if not self.template.exists():
                self.initialize_template(self.template, self.on_template_initialized)
            else:
                self.set_dynamic_variables()
                # Process the command-line file if the template already exists
                if self.command_line_file:
                    print("Template exists. Processing command-line file after UI initialization.")
                    self.process_cli_file_later(self.command_line_file)
        # After loading scripts and building the UI, check for running processes
        self.set_dynamic_variables()
        self.check_running_processes_on_startup()

        # Start fetching runner URLs asynchronously
        threading.Thread(target=self.maybe_fetch_runner_urls).start()

    def remove_symlinks_and_create_directories(self, wineprefix):
        """
        Remove all symbolic link files in the specified directory (drive_c/users/{user}) and 
        create normal directories in their place.
        
        Args:
            wineprefix: The path to the Wine prefix where symbolic links will be removed.
        """
        userhome = os.getenv("USER") or os.getenv("USERNAME")
        if not userhome:
            print("Error: Unable to determine the current user from environment.")
            return
        
        user_dir = Path(wineprefix) / "drive_c" / "users"
        print(f"Removing symlinks from: {user_dir}")

        # Iterate through all symbolic links in the user's directory
        for item in user_dir.rglob("*"):
            if item.is_symlink():
                try:
                    # Remove the symlink and create a directory in its place
                    item.unlink()
                    item.mkdir(parents=True, exist_ok=True)
                    print(f"Replaced symlink with directory: {item}")
                except Exception as e:
                    print(f"Error processing {item}: {e}")


    def initialize_template(self, template_dir, callback, arch='win64'):
        """
        Modified template initialization with architecture support
        """
        template_dir = Path(template_dir) if not isinstance(template_dir, Path) else template_dir
        
        self.create_required_directories()
        self.initializing_template = True
        self.stop_processing = False
        self.current_arch = arch  # Store current architecture
        
        # Disabled Cancel/Interruption
        ## Disconnect open button handler
        #if self.open_button_handler_id is not None:
        #    self.open_button.disconnect(self.open_button_handler_id)
        #    self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_init_clicked)
        self.disconnect_open_button()
        

        # Architecture-specific steps
        steps = [
            ("Initializing wineprefix", 
            f"WINEARCH={arch} WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
            ("Replace symbolic links with directories", 
            lambda: self.remove_symlinks_and_create_directories(template_dir)),
            ("Installing arial", 
            f"WINEPREFIX='{template_dir}' winetricks -q arial"),
            # ("Installing tahoma", 
            # f"WINEPREFIX='{template_dir}' winetricks -q tahoma"),
            # ("Installing times", 
            # f"WINEPREFIX='{template_dir}' winetricks -q times"),
            # ("Installing courier", 
            # f"WINEPREFIX='{template_dir}' winetricks -q courier"),
            # ("Installing webdings", 
            # f"WINEPREFIX='{template_dir}' winetricks -q webdings"),
            ("Installing openal", 
            f"WINEPREFIX='{template_dir}' winetricks -q openal"),
            #("Installing vkd3d", 
            #f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
            #("Installing dxvk", 
            #f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
        ]
        
        # Set total steps and initialize progress UI
        self.total_steps = len(steps)
        self.show_processing_spinner(f"Initializing {template_dir.name} Template...")

        def initialize():
            for index, (step_text, command) in enumerate(steps, 1):
                if self.stop_processing:
                    GLib.idle_add(self.cleanup_cancelled_template_init, template_dir)
                    return
                    
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    if callable(command):
                        command()
                    else:
                        process = subprocess.Popen(command, shell=True, 
                                                stdout=subprocess.PIPE, 
                                                stderr=subprocess.PIPE)
                        while process.poll() is None:
                            if self.stop_processing:
                                process.terminate()
                                try:
                                    process.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                                GLib.idle_add(self.cleanup_cancelled_template_init, template_dir)
                                return
                            time.sleep(0.1)
                        
                        if process.returncode != 0:
                            raise subprocess.CalledProcessError(process.returncode, command)
                    
                    GLib.idle_add(self.mark_step_as_done, step_text)
                    if hasattr(self, 'progress_bar'):
                        GLib.idle_add(lambda: self.progress_bar.set_fraction(index / self.total_steps))
                    
                except subprocess.CalledProcessError as e:
                    print(f"Error initializing template: {e}")
                    GLib.idle_add(self.cleanup_cancelled_template_init, template_dir)
                    return
                    
            if not self.stop_processing:
                GLib.idle_add(lambda: self.on_template_initialized(arch))
                GLib.idle_add(self.hide_processing_spinner)
                self.disconnect_open_button()
                GLib.idle_add(self.reset_ui_after_template_init)
        threading.Thread(target=initialize).start()

    def on_template_initialized(self, arch=None):
        print(f"Template initialization complete for {arch if arch else 'default'} architecture.")
        self.initializing_template = False
        # Update architecture setting if we were initializing a specific arch
        if arch:
            self.arch = arch
            # Set template path based on architecture
            self.template = self.default_template_win32 if arch == 'win32' \
                else self.default_template_win64
            self.save_settings()
        
        # Ensure the spinner is stopped after initialization
        self.hide_processing_spinner()
        
        #self.set_open_button_label("Open")
        #self.set_open_button_icon_visible(True)
        #self.search_button.set_sensitive(True)
        #self.view_toggle_button.set_sensitive(True)
        
        # Disabled Cancel/Interruption
        #if self.open_button_handler_id is not None:
        #    self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)

        print("Template initialization completed and UI updated.")
        self.show_initializing_step("Initialization Complete!")
        self.mark_step_as_done("Initialization Complete!")
        
        if self.command_line_file:
            print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
            print(self.command_line_file)

            file_extension = Path(self.command_line_file).suffix.lower()
            if file_extension in ['.exe', '.msi']:
                print("A"*100)
                print(f"Processing file: {self.command_line_file} (Valid extension: {file_extension})")
                print("Trying to process file inside on template initialized")

                GLib.idle_add(self.show_processing_spinner, "Processing...")
                self.process_cli_file(self.command_line_file)
            elif file_extension in ['.wzt', '.bottle', '.prefix']:
                print("B"*100)
                self.restore_prefix_bottle_wzt_tar_zst(self.command_line_file)

            else:
                print("C"*100)
                print(f"Invalid file type: def on_open: {file_extension}. Only .exe or .msi files are allowed.")
                GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Invalid File Type", "Only .exe and .msi files are supported.")
                self.command_line_file = None
                return False

        # If not called from settings create script list else go to settings
        if not self.called_from_settings:
            self.reconnect_open_button()
            GLib.timeout_add_seconds(0.5, self.create_script_list)
        
        if self.called_from_settings:
            GLib.idle_add(lambda: self.replace_open_button_with_settings())
            self.show_options_for_settings()
        
        self.set_dynamic_variables()
        #self.disconnect_open_button()
        ##self.reconnect_open_button()
        #self.show_options_for_settings()
        #self.revert_open_button()
        #self.called_from_settings = False
        

    def process_cli_file_later(self, file_path):
        #self.create_main_window()
        print("D"*100)

        if file_path:

            file_extension = Path(file_path).suffix.lower()
            if file_extension in ['.exe', '.msi']:
                print("A"*100)
                print(f"Processing file: {file_path} (Valid extension: {file_extension})")
                print("Trying to process file inside on template initialized")

                GLib.idle_add(self.show_processing_spinner, "Processing")
                self.process_cli_file_in_thread(file_path)
            elif file_extension in ['.wzt', '.bottle', '.prefix']:
                print("B"*100)
                GLib.idle_add(self.show_processing_spinner, "Restoring")
                self.restore_prefix_bottle_wzt_tar_zst(file_path)

            else:
                print("C"*100)
                print(f"Invalid file type: def on_open: {file_extension}. Only .exe or .msi files are allowed.")
                GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Invalid File Type", "Only .exe and .msi files are supported.")
                self.command_line_file = None
                return False

        self.create_script_list()

    def set_open_button_label(self, label_text):
        self.print_method_name()
        """Helper method to update the open button's label"""
        box = self.open_button.get_child()
        if not box:
            return
            
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Label):
                child.set_label(label_text)
            elif isinstance(child, Gtk.Image):
                child.set_visible(False)  # Hide the icon during processing
            child = child.get_next_sibling()

    def show_initializing_step(self, step_text):
        self.print_method_name()
        """
        Show a new processing step in the flowbox
        """
        

        if hasattr(self, 'progress_bar'):
            # Calculate total steps dynamically
            if hasattr(self, 'total_steps'):
                total_steps = self.total_steps
            else:
                # Default for bottle creation
                total_steps = 8
            
            current_step = len(self.step_boxes) + 1
            progress = current_step / total_steps
            
            # Update progress bar
            self.progress_bar.set_fraction(progress)
            self.progress_bar.set_text(f"Step {current_step}/{total_steps}")
            
            # Create step box
            step_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            step_box.set_margin_start(12)
            step_box.set_margin_end(12)
            step_box.set_margin_top(6)
            step_box.set_margin_bottom(6)
            
            # Add status icon and label
            step_spinner = Gtk.Spinner()
            step_label = Gtk.Label(label=step_text)
            step_label.set_halign(Gtk.Align.START)
            step_label.set_hexpand(True)
            
            step_box.append(step_spinner)
            step_box.append(step_label)
            step_spinner.start()

            
            # Add to flowbox
            flowbox_child = Gtk.FlowBoxChild()
            flowbox_child.set_child(step_box)
            self.flowbox.append(flowbox_child)
            
            # Store reference
            self.step_boxes.append((step_box, step_spinner, step_label))

    def mark_step_as_done(self, step_text):
        self.print_method_name()
        """
        Mark a step as completed in the flowbox
        """
        if hasattr(self, 'step_boxes'):
            for step_box, step_spinner, step_label in self.step_boxes:
                if step_label.get_text() == step_text:
                    step_box.remove(step_spinner)
                    done_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                    step_box.prepend(done_icon)
                    break

    def check_required_programs(self):
        self.print_method_name()
        #if shutil.which("flatpak-spawn"):
        #    return []
            
        # List of supported terminals
        terminal_options = [
            'ptyxis',
            'gnome-terminal',
            'konsole',
            'xfce4-terminal',
            'wcterm'
        ]
        
        # Base required programs
        required_programs = [
            'exiftool',
            'wine',
            'winetricks',
            'wrestool',
            'icotool',
            'pgrep',
            'xdg-open'
        ]
        
        # Check if at least one terminal is available
        terminal_found = any(shutil.which(term) for term in terminal_options)
        if not terminal_found:
            # If no terminal is found, add "terminal-emulator" as a missing requirement
            missing_programs = [prog for prog in required_programs if not shutil.which(prog)]
            missing_programs.append("terminal-emulator")
            return missing_programs
            
        return [prog for prog in required_programs if not shutil.which(prog)]

    def show_missing_programs_dialog(self, missing_programs):
        self.print_method_name()
        if not missing_programs:
            return
            
        message_parts = []
        
        # Handle terminal emulator message
        if "terminal-emulator" in missing_programs:
            message_parts.append(
                "Missing required terminal emulator.\nPlease install one of the following:\n"
                "• ptyxis\n"
                "• gnome-terminal\n"
                "• konsole\n"
                "• xfce4-terminal"
            )
            # Remove terminal-emulator from the list for other missing programs
            other_missing = [prog for prog in missing_programs if prog != "terminal-emulator"]
            if other_missing:
                message_parts.append("\nOther missing required programs:\n" + 
                                  "\n".join(f"• {prog}" for prog in other_missing))
        else:
            message_parts.append("The following required programs are missing:\n" +
                               "\n".join(f"• {prog}" for prog in missing_programs))
            
        message = "\n".join(message_parts)
        
        GLib.timeout_add_seconds(1, self.show_info_dialog,"Missing Programs", message)

        
    def set_dynamic_variables(self):
        self.print_method_name()
        # Check if Settings.yaml exists and set the template and arch accordingly
        if self.settings_file.exists():
            settings = self.load_settings()  # Assuming load_settings() returns a dictionary
            self.template = self.expand_and_resolve_path(settings.get('template', self.default_template_win64))
            self.arch = settings.get('arch', "win64")
            self.icon_view = settings.get('icon_view', False)
            self.single_prefix = settings.get('single-prefix', False)
        else:
            self.template = self.expand_and_resolve_path(self.default_template_win64)
            self.arch = "win64"
            self.runner = ""
            self.template = self.default_template_win64  # Set template to the initialized one
            self.icon_view = False
            self.single_prefix = False

        self.save_settings()

    def save_settings(self):
        self.print_method_name()
        """Save current settings to the Settings.yaml file."""
        settings = {
            'template': self.replace_home_with_tilde_in_path(str(self.template)),
            'arch': self.arch,
            'runner': self.replace_home_with_tilde_in_path(str(self.settings.get('runner', ''))),
            'wine_debug': "WINEDEBUG=-fixme-all DXVK_LOG_LEVEL=none",
            'env_vars': '',
            'icon_view': self.icon_view,
            'single-prefix': self.single_prefix
        }

        try:
            with open(self.settings_file, 'w') as settings_file:
                yaml.dump(settings, settings_file, default_style="'", default_flow_style=False, width=10000)
            #print(f"Settings saved to {self.settings_file} with content:\n{settings}")
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        self.print_method_name()
        """Load settings from the Settings.yaml file."""
        if self.settings_file.exists():
            with open(self.settings_file, 'r') as settings_file:
                settings = yaml.safe_load(settings_file) or {}

            # Expand and resolve paths when loading
            self.template = self.expand_and_resolve_path(settings.get('template', self.default_template_win64))
            self.runner = self.expand_and_resolve_path(settings.get('runner', ''))
            self.arch = settings.get('arch', "win64")
            self.icon_view = settings.get('icon_view', False)
            self.env_vars = settings.get('env_vars', '')
            self.wine_debug = settings.get('wine_debug', '')
            self.single_prefix = settings.get('single-prefix', False)
            return settings

        # If no settings file, return an empty dictionary
        return {}
        
    def set_open_button_icon_visible(self, visible):
        self.print_method_name()
        box = self.open_button.get_child()
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Image):
                child.set_visible(visible)
            child = child.get_next_sibling()
            
    def on_activate(self, *args):
        self.print_method_name()
        if not self.window:
            self.window = Adw.ApplicationWindow(application=self)
        self.window.present()

 

    def handle_sigint(self, signum, frame):
        self.print_method_name()
        if self.SOCKET_FILE.exists():
            self.SOCKET_FILE.unlink()
        self.quit()

    def create_main_window(self):
        self.print_method_name()

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Wine Charm")
        self.window.set_default_size(520, 680)
        self.window.add_css_class("common-background")

        self.headerbar = Gtk.HeaderBar()
        self.headerbar.set_show_title_buttons(True)
        self.headerbar.add_css_class("flat")
        self.window.set_titlebar(self.headerbar)

        # Create a box to hold the app icon and the title label
        self.title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # App icon
        app_icon = Gtk.Image.new_from_icon_name("io.github.fastrizwaan.WineCharm")
        app_icon.set_pixel_size(18)  # Set icon size to 18
        self.title_box.append(app_icon)

        # Title label
        title_label = Gtk.Label(label="Wine Charm")
        title_label.set_markup("<b>Wine Charm</b>")  # Use Pango Markup to make the text bold
        title_label.set_use_markup(True)  # Enable markup for this label
        self.title_box.append(title_label)

        # Set the title_box as the title widget of the headerbar
        self.headerbar.set_title_widget(self.title_box)

        # Back button
        self.back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.back_button.add_css_class("flat")
        self.back_button.set_visible(False)  # Hide it initially
        self.back_button.connect("clicked", self.on_back_button_clicked)
        self.headerbar.pack_start(self.back_button)

        # Create a box to hold the Search button and the view toggle button
        view_and_sort_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)

        # Search button
        self.search_button = Gtk.ToggleButton()
        search_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        self.search_button.set_child(search_icon)
        self.search_button.connect("toggled", self.on_search_button_clicked)
        self.search_button.add_css_class("flat")
        view_and_sort_box.append(self.search_button)  # Add search button to the left

        # Icon/List view toggle button
        self.view_toggle_button = Gtk.ToggleButton()
        icon_view_icon = Gtk.Image.new_from_icon_name("view-grid-symbolic")
        list_view_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        self.view_toggle_button.set_child(icon_view_icon if self.icon_view else list_view_icon)
        self.view_toggle_button.add_css_class("flat")
        self.view_toggle_button.set_tooltip_text("Toggle Icon/List View")
        self.view_toggle_button.connect("toggled", self.on_view_toggle_button_clicked)
        view_and_sort_box.append(self.view_toggle_button)

        # Add the view_and_sort_box to the headerbar
        self.headerbar.pack_start(view_and_sort_box)

        # Keep the existing menu button on the right side of the headerbar
        self.menu_button = Gtk.MenuButton()
        menu_icon = Gtk.Image.new_from_icon_name("open-menu-symbolic")
        self.menu_button.set_child(menu_icon)
        self.menu_button.add_css_class("flat")
        self.menu_button.set_tooltip_text("Menu")
        self.headerbar.pack_end(self.menu_button)

        # Create the main menu for the right menu button
        menu = Gio.Menu()

        # Create a "Sort" submenu and add sorting options
        sort_submenu = Gio.Menu()
        sort_submenu.append("Name (A-Z)", "win.sort::progname::False")
        sort_submenu.append("Name (Z-A)", "win.sort::progname::True")
        sort_submenu.append("Wineprefix (A-Z)", "win.sort::wineprefix::False")
        sort_submenu.append("Wineprefix (Z-A)", "win.sort::wineprefix::True")
        sort_submenu.append("Time (Newest First)", "win.sort::mtime::True")
        sort_submenu.append("Time (Oldest First)", "win.sort::mtime::False")

        # Add the sort submenu to the main menu
        menu.append_submenu("🔠 Sort", sort_submenu)

        # Create a "Open" submenu and add open filemanager and terminal at winezguidir
        open_submenu = Gio.Menu()
        open_submenu.append("Open Filemanager", "win.open_filemanager_winecharm")
        open_submenu.append("Open Terminal", "win.open_terminal_winecharm")

        menu.append_submenu("📂 Open", open_submenu)
        self.menu_button.set_menu_model(menu)

        # Add other existing options in the hamburger menu
        for label, action in self.hamburger_actions:
            menu.append(label, f"win.{action.__name__}")
            action_item = Gio.SimpleAction.new(action.__name__, None)
            action_item.connect("activate", action)
            self.window.add_action(action_item)

        # Create actions for sorting options
        self.create_sort_actions()

        # Create actions for open options
        self.create_open_actions()

        # Rest of the UI setup...
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.vbox.set_margin_start(10)
        self.vbox.set_margin_end(10)
        #self.vbox.set_margin_top(3)
        self.vbox.set_margin_bottom(10)
        self.window.set_child(self.vbox)

        self.open_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.open_button_box.set_halign(Gtk.Align.CENTER)
        open_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
        open_label = Gtk.Label(label="Open")
        self.open_button_box.append(open_icon)
        self.open_button_box.append(open_label)

        self.open_button = Gtk.Button()
        self.open_button.set_child(self.open_button_box)
        self.open_button.set_size_request(-1, 40    )  # Set height to 36 pixels
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
        self.vbox.append(self.open_button)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_size_request(-1, 40)
        self.search_entry.set_placeholder_text("Search")
        self.search_entry.connect("activate", self.on_search_entry_activated)
        self.search_entry.connect("changed", self.on_search_entry_changed)

        self.search_entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        self.search_entry_box.append(self.search_entry)
        self.search_entry_box.set_hexpand(True)
        self.search_entry.set_hexpand(True)

        self.main_frame = Gtk.Frame()
        self.main_frame.set_margin_top(0)
        self.vbox.append(self.main_frame)

        self.scrolled = Gtk.ScrolledWindow()  # Make scrolled an instance variable
        self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_hexpand(True)
        self.main_frame.set_child(self.scrolled)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_halign(Gtk.Align.FILL)

        # if self.icon_view:
        #    self.flowbox.set_max_children_per_line(8)
        # else:
        #    self.flowbox.set_max_children_per_line(4)

        self.flowbox.set_homogeneous(True)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.scrolled.set_child(self.flowbox)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.window.add_controller(key_controller)

        self.create_script_list()

        # Add keyboard actions
        self.add_keyboard_actions()

    def add_keyboard_actions(self):
        self.print_method_name()
        # Search action
        search_action = Gio.SimpleAction.new("search", None)
        search_action.connect("activate", lambda *_: self.search_button.set_active(not self.search_button.get_active()))
        self.window.add_action(search_action)

        # Open action (fixed signature)
        open_action = Gio.SimpleAction.new("open", None)
        open_action.connect("activate", lambda *_: self.on_open_button_clicked(None))
        self.window.add_action(open_action)

        # Toggle view action
        toggle_view_action = Gio.SimpleAction.new("toggle_view", None)
        toggle_view_action.connect("activate", lambda *_: self.on_view_toggle_button_clicked(self.view_toggle_button))
        self.window.add_action(toggle_view_action)

        # Kill all action
        kill_all_action = Gio.SimpleAction.new("kill_all", None)
        kill_all_action.connect("activate", self.on_kill_all_clicked)
        self.window.add_action(kill_all_action)

        # Back navigation action
        back_action = Gio.SimpleAction.new("back", None)
        back_action.connect("activate", lambda *_: self.on_back_button_clicked(None))
        self.window.add_action(back_action)

    def create_sort_actions(self):
        self.print_method_name()
        """
        Create a single sorting action for the sorting options in the Sort submenu.
        """
        # Use 's' to denote that the action expects a string type parameter
        sort_action = Gio.SimpleAction.new("sort", GLib.VariantType('s'))
        sort_action.connect("activate", self.on_sort)
        self.window.add_action(sort_action)


    def on_sort(self, action, param):
        self.print_method_name()
        """
        Handle sorting by parsing the parameter to determine the sorting key and order.
        """
        if param is None:
            return

        param_str = param.get_string()
        # Parse the parameter in the format "key::reverse"
        key, reverse_str = param_str.split("::")
        reverse = reverse_str == "True"

        print(f"Sorting by {key} {'descending' if reverse else 'ascending'}")
        
        def sort_key(item):
            _, value = item
            if key == 'mtime':
                # Convert to float for proper numerical comparison
                return float(value.get(key, 0))
            else:
                # For string values, convert to lowercase for case-insensitive sorting
                val = value.get(key, '')
                return val.lower() if isinstance(val, str) else str(val)

        sorted_scripts = sorted(self.script_list.items(), key=sort_key, reverse=reverse)
        self.script_list = {key: value for key, value in sorted_scripts}
        GLib.idle_add(self.create_script_list)

    def create_open_actions(self):
        self.print_method_name()
        """
        Create actions for the open options in the Open submenu.
        """
        open_filemanager_action = Gio.SimpleAction.new("open_filemanager_winecharm", None)
        open_filemanager_action.connect("activate", self.open_filemanager_winecharm)
        self.window.add_action(open_filemanager_action)

        open_terminal_action = Gio.SimpleAction.new("open_terminal_winecharm", None)
        open_terminal_action.connect("activate", self.open_terminal_winecharm)
        self.window.add_action(open_terminal_action)

    def open_filemanager_winecharm(self, action, param):
        self.print_method_name()
        wineprefix = Path(self.winecharmdir)  # Replace with the actual wineprefix path
        print(f"Opening file manager for {wineprefix}")
        command = ["xdg-open", str(wineprefix)]
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening file manager: {e}")

    def open_terminal_winecharm(self, param=None, action=None):
        self.print_method_name()
        # Set wineprefix to self.template
        wineprefix = Path(self.template).expanduser().resolve()

        print(f"Opening terminal for {wineprefix}")

        self.ensure_directory_exists(wineprefix)

        # Load settings to get the runner
        settings = self.load_settings()
        runner = settings.get('runner', 'wine')  # Default to 'wine' if runner is not specified
        runner_path = Path(runner).expanduser().resolve()
        runner_dir = runner_path.parent.resolve()

        if shutil.which("flatpak-spawn"):
            command = [
                "wcterm", "bash", "--norc", "-c",
                (
                    rf'export PS1="[\u@\h:\w]\$ "; '
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
                    rf'export PS1="[\u@\h:\w]\$ "; '
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



    def on_key_pressed(self, controller, keyval, keycode, state):
        self.print_method_name()
        if keyval == Gdk.KEY_Escape:
            self.search_button.set_active(False)
            
            # Reset the appropriate view based on context
            if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
                self.search_entry.set_text("")
                self.populate_settings_options()
            elif hasattr(self, 'script_options_flowbox') and self.script_options_flowbox.get_parent() is not None:
                self.search_entry.set_text("")
                self.populate_script_options()  # Removed extra arguments
            else:
                self.filter_script_list("")

    def on_search_button_clicked(self, button):
        self.print_method_name()
        try:
            if self.search_active:
                # Before removing search entry, make sure it's in the vbox
                if self.search_entry_box.get_parent() == self.vbox:
                    self.vbox.remove(self.search_entry_box)
                
                # Before adding open/launch button, make sure it's not already in the vbox
                if hasattr(self, 'launch_button') and self.launch_button is not None:
                    if self.launch_button.get_parent() != self.vbox:
                        self.vbox.prepend(self.launch_button)
                else:
                    if self.open_button.get_parent() != self.vbox:
                        self.vbox.prepend(self.open_button)
                
                self.search_active = False
                
                # Reset the appropriate view based on context
                if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
                    self.search_entry.set_text("")
                    self.populate_settings_options()
                elif hasattr(self, 'script_options_flowbox') and self.script_options_flowbox.get_parent() is not None:
                    self.search_entry.set_text("")
                    self.populate_script_options()
                else:
                    self.filter_script_list("")
            else:
                # Only try to remove if button is in the vbox
                current_button = self.launch_button if hasattr(self, 'launch_button') and self.launch_button is not None else self.open_button
                if current_button.get_parent() == self.vbox:
                    self.vbox.remove(current_button)
                
                # Only add search entry if it's not already in the vbox
                if self.search_entry_box.get_parent() != self.vbox:
                    self.vbox.prepend(self.search_entry_box)
                
                self.search_entry.grab_focus()
                self.search_active = True
        except Exception as e:
            print(f"Error in search button handling: {e}")


    def on_search_entry_activated(self, entry):
        self.print_method_name()
        search_term = entry.get_text().lower()
        self.filter_script_list(search_term)

    def on_search_entry_changed(self, entry):
        self.print_method_name()
        search_term = entry.get_text().lower()
        # Check if we're in settings view
        if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
            self.populate_settings_options(search_term)
        elif hasattr(self, 'script_options_flowbox') and self.script_options_flowbox.get_parent() is not None:
            self.populate_script_options(search_term)  # Only pass search term
        else:
            self.filter_script_list(search_term)

    def filter_script_list(self, search_term):
        self.print_method_name()
        """
        Filters the script list based on the search term and updates the UI accordingly.
        
        Parameters:
            search_term (str): The term to search for within exe_name, script_name (script_path.stem), or progname.
        """
        # Normalize the search term for case-insensitive matching
        search_term = search_term.lower()
        
        # Clear the existing flowbox to prepare for the filtered scripts
        self.flowbox.remove_all()
        
        # Flag to check if any scripts match the search term
        found_match = False
        
        # Iterate over all scripts in self.script_list using script_key and script_data
        for script_key, script_data in list(self.script_list.items()):
            # Resolve the script path, executable name, and get the progname
            script_path = Path(str(script_data['script_path'])).expanduser().resolve()
            exe_name = Path(str(script_data['exe_file'])).expanduser().resolve().name
            progname = str(script_data.get('progname', '')).lower()  # Fallback to empty string if 'progname' is missing
            
            # Check if the search term is present in the exe_name, script_name (stem), or progname
            if (search_term in exe_name.lower() or 
                search_term in script_path.stem.lower() or 
                search_term in progname):
                found_match = True
                
                # Create a script row. Ensure that create_script_row accepts script_key and script_data
                row = self.create_script_row(script_key, script_data)
                
                # Append the created row to the flowbox for display
                self.flowbox.append(row)
                
                # If the script is currently running, update the UI to reflect its running state
                if script_key in self.running_processes:
                    #self.update_ui_for_running_process(script_key, row, self.running_processes)
                    self.update_ui_for_running_process(self.running_processes)


        if not found_match:
            print(f"No matches found for search term: {search_term}")


    def on_open_button_clicked(self, button):
        self.print_method_name()
        self.open_file_dialog()

    def open_file_dialog(self):
        self.print_method_name()
        file_dialog = Gtk.FileDialog.new()
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        filter_model.append(self.create_file_filter())
        file_dialog.set_filters(filter_model)
        file_dialog.open(self.window, None, self.on_open_file_dialog_response)

    def create_file_filter(self):
        self.print_method_name()
        file_filter = Gtk.FileFilter()
        file_filter.set_name("EXE and MSI files")
        file_filter.add_mime_type("application/x-ms-dos-executable")
        file_filter.add_pattern("*.exe")
        file_filter.add_pattern("*.msi")
        return file_filter

    def on_open_file_dialog_response(self, dialog, result):
        self.print_method_name()
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = file.get_path()
                print("- - - - - - - - - - - - - -self.show_processing_spinner")
                self.monitoring_active = False
                
                # If there's already a processing thread, stop it
                if hasattr(self, 'processing_thread') and self.processing_thread and self.processing_thread.is_alive():
                    self.stop_processing = True
                    self.processing_thread.join(timeout=0.5)  # Wait briefly for thread to stop
                    self.hide_processing_spinner()
                    self.set_open_button_label("Open")
                    self.set_open_button_icon_visible(True)
                    return

                # Show processing spinner
                self.show_processing_spinner("Processing...")
                
                # Start a new background thread to process the file
                self.stop_processing = False
                self.processing_thread = threading.Thread(target=self.process_cli_file_in_thread, args=(file_path,))
                self.processing_thread.start()

        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")
        finally:
            self.window.set_visible(True)
            self.monitoring_active = True

    def process_cli_file_in_thread(self, file_path):
        try:
            print(f"Processing CLI file in thread: {file_path}")
            abs_file_path = str(Path(file_path).resolve())
            print(f"Resolved absolute CLI file path: {abs_file_path}")

            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return

            # Perform the heavy processing here
            self.create_yaml_file(abs_file_path, None)

            # Schedule GUI updates in the main thread
            #GLib.idle_add(self.update_gui_after_file_processing, abs_file_path)

        except Exception as e:
            print(f"Error processing file in background: {e}")
        finally:
            if self.initializing_template:
                pass  # Keep showing spinner
            else:
                GLib.idle_add(self.hide_processing_spinner)
            
            GLib.timeout_add_seconds(0.5, self.create_script_list)

    def on_back_button_clicked(self, button):
        self.print_method_name()
        # If search is active, toggle it off first
        if self.search_active:
            self.search_button.set_active(False)

        # Reset the header bar title and visibility of buttons
        self.headerbar.set_title_widget(self.title_box)
        self.menu_button.set_visible(True)
        self.search_button.set_visible(True)
        self.view_toggle_button.set_visible(True)
        self.back_button.set_visible(False)

        # Remove the "Launch" button if it exists
        if hasattr(self, 'launch_button') and self.launch_button is not None:
            if self.launch_button.get_parent() == self.vbox:
                self.vbox.remove(self.launch_button)
            self.launch_button = None

        # Restore the "Open" button
        if self.open_button.get_parent() != self.vbox:
            self.vbox.prepend(self.open_button)
        self.open_button.set_visible(True)
        
        # Restore original open button functionality
        self.restore_open_button()

        # Ensure the correct child is set in the main_frame
        if self.main_frame.get_child() != self.scrolled:
            self.main_frame.set_child(self.scrolled)

        self.remove_accelerator_context()
            
        # Restore the script list
        self.create_script_list()
        
    def remove_accelerator_context(self):
        # Cleanup accelerator group when leaving options view
        if hasattr(self, 'accel_group'):
            self.window.remove_accel_group(self.accel_group)
            del self.accel_group
            
    def setup_accelerator_context(self):
        self.print_method_name()
        controller = Gtk.ShortcutController()
        shortcut = Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Ctrl>BackSpace"),
            action=Gtk.CallbackAction.new(lambda *_: self.on_back_button_clicked(None))
        )
        controller.add_shortcut(shortcut)
        self.window.add_controller(controller)
        
    def wrap_text_at_24_chars(self, text):
        #self.print_method_name()
        if len(text) <= 24:
            # If text is short enough, assign to label1
            label1 = text
            label2 = ""
            label3 = ""
            return label1, label2, label3

        # Find first split point near 24 chars
        wrap_pos1 = -1
        for i in range(16, min(25, len(text))):  # Check from 16 to 24
            if text[i] in [' ', '-']:
                wrap_pos1 = i + 1
                break
        if wrap_pos1 == -1:
            wrap_pos1 = 25  # Split at 25 if no space/hyphen

        # Find second split point
        wrap_pos2 = -1
        for i in range(wrap_pos1 + 16, min(wrap_pos1 + 25, len(text))):
            if text[i] in [' ', '-']:
                wrap_pos2 = i + 1
                break
        if wrap_pos2 == -1:
            wrap_pos2 = min(wrap_pos1 + 25, len(text))

        # Split the text
        label1 = text[:wrap_pos1].strip()
        label2 = text[wrap_pos1:wrap_pos2].strip()
        label3 = text[wrap_pos2:].strip()

        # Truncate label3 if too long
        if len(label3) > 22:
            label3 = label3[:22] + "..."
            
        return label1, label2, label3
        
    def find_charm_files(self, prefixdir=None):
        self.print_method_name()
        """
        Finds .charm files within the provided prefix directory, searching up to 2 levels deep.
        
        Args:
            prefixdir (Path or str): The directory to search in. Defaults to self.prefixes_dir.

        Returns:
            List[Path]: A sorted list of .charm files found, sorted by modification time (newest first).
        """
        if prefixdir is None:
            prefixdir = self.prefixes_dir
        
        # Ensure prefixdir is a Path object
        prefixdir = Path(prefixdir).expanduser().resolve()

        # Check if the directory exists
        if not prefixdir.exists() or not prefixdir.is_dir():
            print(f"Directory does not exist: {prefixdir}")
            return []

        scripts = []
        
        # Walk through the directory, but limit the depth to 2
        for root, dirs, files in os.walk(prefixdir):
            current_depth = Path(root).relative_to(prefixdir).parts

            # If the depth is greater than 2, prune the search space by not descending into subdirectories
            if len(current_depth) >= 2:
                dirs[:] = []  # Prune subdirectories
                continue

            # Collect .charm files
            scripts.extend([Path(root) / file for file in files if file.endswith(".charm")])

        # Sort files by modification time (newest first)
        scripts.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        return scripts

    def replace_open_button_with_launch(self, script, row, script_key):
        self.print_method_name()
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            return None
            
        if self.open_button.get_parent():
            self.vbox.remove(self.open_button)

        self.launch_button = Gtk.Button()
        self.launch_button.set_size_request(-1, 40)

        #yaml_info = self.extract_yaml_info(script)
        script_key = script_data['sha256sum']  # Use sha256sum as the key

        if script_key in self.running_processes:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
            self.launch_button.set_tooltip_text("Stop")
        else:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
            self.launch_button.set_tooltip_text("Play")

        self.launch_button.set_child(launch_icon)
        self.launch_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, self.launch_button, row))

        # Store the script_key associated with this launch button
        self.launch_button_exe_name = script_key

        self.vbox.prepend(self.launch_button)
        self.launch_button.set_visible(True)

    def replace_launch_button(self, ui_state, row, script_key):
        self.print_method_name()
        """
        Replace the open button with a launch button.
        """
        try:
            # Remove existing launch button if it exists
            if hasattr(self, 'launch_button') and self.launch_button is not None:
                parent = self.launch_button.get_parent()
                if parent is not None:
                    parent.remove(self.launch_button)

            # Create new launch button
            self.launch_button = Gtk.Button()
            self.launch_button.set_size_request(-1, 40)
            
            # Set initial icon state
            is_running = script_key in self.running_processes
            launch_icon = Gtk.Image.new_from_icon_name(
                "media-playback-stop-symbolic" if is_running
                else "media-playback-start-symbolic"
            )
            self.launch_button.set_tooltip_text("Stop" if is_running else "Play")
            self.launch_button.set_child(launch_icon)
            
            # Connect click handler
            self.launch_button.connect(
                "clicked",
                lambda btn: self.toggle_play_stop(script_key, self.launch_button, row)
            )
            
            # Add to vbox
            if hasattr(self, 'vbox') and self.vbox is not None:
                if self.open_button.get_parent() == self.vbox:
                    self.vbox.remove(self.open_button)
                self.vbox.prepend(self.launch_button)
                self.launch_button.set_visible(True)
            
        except Exception as e:
            print(f"Error in replace_launch_button: {e}")
            self.launch_button = None

############################### 1050 - 1682 ########################################
    def create_script_list(self):
        self.print_method_name()
        # Clear the flowbox
        self.flowbox.remove_all()

        # Rebuild the script list
        self.script_ui_data = {}  # Use script_data to hold all script-related data

        # Iterate over self.script_list
        for script_key, script_data in list(self.script_list.items()):
            row = self.create_script_row(script_key, script_data)
            if row:
                self.flowbox.append(row)

            # After row creation, highlight if the process is running
            if script_key in self.running_processes:
                self.update_row_highlight(row, True)
                self.script_ui_data[script_key]['highlighted'] = True
                self.script_ui_data[script_key]['is_running'] = True  # Set is_running to True
            else:
                self.update_row_highlight(row, False)
                self.script_ui_data[script_key]['highlighted'] = False
                self.script_ui_data[script_key]['is_running'] = False  # Ensure is_running is False


    def create_script_row(self, script_key, script_data):
        script = Path(str(script_data['script_path'])).expanduser()
        
        if self.icon_view:
            # ICON VIEW
            container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            container.set_hexpand(True)
            container.set_vexpand(True)
            container.set_valign(Gtk.Align.CENTER)  # Center vertically for better alignment
            container.set_halign(Gtk.Align.CENTER)  # Center horizontally
            container.add_css_class("rounded-container")
            
            # Top horizontal box: options button | icon | play button
            top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            top_box.set_hexpand(True)
            top_box.set_vexpand(True)
            top_box.set_valign(Gtk.Align.CENTER)
            top_box.set_halign(Gtk.Align.FILL)
            
            # Options button (expanded to fill available space)
            options_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options")
            options_button.add_css_class("flat")
            options_button.set_hexpand(True)
            options_button.set_halign(Gtk.Align.FILL)
            
            # Icon (fixed size, centered)
            icon = self.load_icon(script, 96, 96, 10)
            if icon:
                icon_container = Gtk.Box()
                icon_container.add_css_class("rounded-icon")
                icon_image = Gtk.Image.new_from_paintable(icon)
                icon_image.set_pixel_size(96)
                icon_image.set_halign(Gtk.Align.CENTER)
                icon_container.append(icon_image)
                icon_container.set_hexpand(False)
            else:
                icon_container = Gtk.Box()
                icon_image = Gtk.Image()
                icon_container.append(icon_image)
                icon_container.set_hexpand(False)
            
            # Play button (expanded to fill available space)
            play_button = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Play")
            play_button.add_css_class("flat")
            play_button.set_hexpand(True)
            play_button.set_halign(Gtk.Align.FILL)
            play_button.set_valign(Gtk.Align.FILL)

            top_box.append(options_button)
            top_box.append(icon_container)
            top_box.append(play_button)
            container.append(top_box)
            
            # Bottom: Label area with Gtk.Label
            label_text = str(script_data.get('progname', script.stem)).replace('_', ' ')
            if script.stem in self.new_scripts:
                label_text = f"<b>{label_text}</b>"
            label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            label_box.set_halign(Gtk.Align.CENTER)
            #label_box.set_valign(Gtk.Align.CENTER)

            main_label = Gtk.Label()
            main_label.set_wrap(True)
            main_label.set_max_width_chars(20)  # Wrap after ~20 chars
            main_label.set_lines(2)  # Limit to 2 lines
            main_label.set_ellipsize(Pango.EllipsizeMode.END)  # Ellipsis if too long
            main_label.set_halign(Gtk.Align.CENTER)
            main_label.set_markup(label_text)
            label_box.append(main_label)

            container.append(label_box)
            
            # Set fixed size for the container
            container.set_size_request(200, 150)
            
            # Initial button states
            play_button.set_opacity(0)
            options_button.set_opacity(0)
            play_button.set_sensitive(False)
            options_button.set_sensitive(False)
            
            # Store UI data
            self.script_ui_data[script_key] = {
                'row': container,
                'play_button': play_button,
                'options_button': options_button,
                'is_running': False,
                'script_path': script
            }
            
            # Add click gesture
            click = Gtk.GestureClick()
            click.connect("released", lambda gesture, n, x, y: self.toggle_overlay_buttons(script_key))
            container.add_controller(click)
            
            # Connect button signals
            play_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, btn, container))
            options_button.connect("clicked", lambda btn: self.show_options_for_script(
                self.script_ui_data[script_key], container, script_key))
            
            return container

        else:
            # LIST VIEW (unchanged)
            title_text = str(script_data.get('progname', script.stem)).replace('_', ' ')
            if script.stem in self.new_scripts:
                title_text = f"<b>{title_text}</b>"
            
            row = Adw.ActionRow(
                title=title_text,
                activatable=True
            )
            row.set_hexpand(True)
            row.set_vexpand(True)
            row.add_css_class('activatable')
            row.add_css_class('rounded-container')
            row.set_use_markup(True)
            
            icon = self.load_icon(script, 40, 40, 4)
            if icon:
                icon_container = Gtk.Box()
                icon_container.add_css_class("rounded-icon")
                icon_image = Gtk.Image.new_from_paintable(icon)
                icon_image.set_pixel_size(40)
                icon_container.append(icon_image)
                row.add_prefix(icon_container)
            
            button_box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
            
            play_button = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Play")
            play_button.set_size_request(60, 36)
            
            options_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options")
            
            button_box.append(play_button)
            button_box.append(options_button)
            row.add_suffix(button_box)
            
            play_button.set_opacity(0)
            options_button.set_opacity(0)
            play_button.set_sensitive(False)
            options_button.set_sensitive(False)
            
            self.script_ui_data[script_key] = {
                'row': row,
                'play_button': play_button,
                'options_button': options_button,
                'is_running': False,
                'script_path': script
            }
            
            click = Gtk.GestureClick()
            click.connect("released", lambda gesture, n, x, y: self.toggle_overlay_buttons(script_key))
            row.add_controller(click)
            
            play_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, btn, row))
            options_button.connect("clicked", lambda btn: self.show_options_for_script(
                self.script_ui_data[script_key], row, script_key))

            return row

    def toggle_overlay_buttons(self, script_key):
        # Hide overlay buttons and remove "blue" CSS from all other rows.
        for key, ui in self.script_ui_data.items():
            if key != script_key:
                ui['play_button'].set_opacity(0)
                ui['options_button'].set_opacity(0)
                ui['play_button'].set_sensitive(False)
                ui['options_button'].set_sensitive(False)
                ui['row'].remove_css_class("blue")
        ui = self.script_ui_data.get(script_key)
        if not ui:
            return
        pb = ui['play_button']
        ob = ui['options_button']
        row = ui['row']
        # Toggle overlay buttons without changing layout.
        if pb.get_opacity() > 0:
            pb.set_opacity(0)
            ob.set_opacity(0)
            pb.set_sensitive(False)
            ob.set_sensitive(False)
            row.remove_css_class("blue")
        else:
            pb.set_opacity(1)
            ob.set_opacity(1)
            pb.set_sensitive(True)
            ob.set_sensitive(True)
            row.add_css_class("blue")
        # Update play button icon based on running state.
        if ui.get("is_running"):
            pb.set_icon_name("media-playback-stop-symbolic")
        else:
            pb.set_icon_name("media-playback-start-symbolic")
       
    def show_buttons(self, play_button, options_button):
        self.print_method_name()
        play_button.set_visible(True)
        options_button.set_visible(True)

    def hide_buttons(self, play_button, options_button):
        self.print_method_name()
        if play_button is not None:
            play_button.set_visible(False)
        if options_button is not None:
            options_button.set_visible(False)

    def on_script_row_clicked(self, script_key):
        self.count = 0
        self.print_method_name()
        """
        Handles the click event on a script row, manages row highlighting, and play/stop button state.
        
        Args:
            script_key (str): The unique key for the script (e.g., sha256sum).
        """
        # Retrieve the current script data for the clicked row
        current_data = self.script_ui_data.get(script_key)
        if not current_data:
            print(f"No script data found for script_key: {script_key}")
            return

        # Track the previously clicked row and update the `is_clicked_row` state
        for key, data in self.script_ui_data.items():
            if data['is_clicked_row']:
                # If the previously clicked row is not the current one, remove the blue highlight
                if key != script_key:
                    data['is_clicked_row'] = False
                    data['row'].remove_css_class("blue")
                    self.hide_buttons(data['play_button'], data['options_button'])
                    print(f"Removing 'blue' highlight for previously clicked row with script_key: {key}")

        # Toggle the `is_clicked_row` state for the currently clicked row
        current_data['is_clicked_row'] = not current_data['is_clicked_row']
        print(f"script_key = {script_key} is set to data['is_clicked_row'] = {current_data['is_clicked_row']}")

        # Update the UI based on the new `is_clicked_row` state
        row = current_data['row']
        play_button = current_data['play_button']
        options_button = current_data['options_button']
        is_running = current_data['is_running']
        is_clicked = current_data['is_clicked_row']

        if is_clicked:
            # Highlight the current row in blue and show the buttons
            row.remove_css_class("highlight")
            row.add_css_class("blue")
            self.show_buttons(play_button, options_button)
            print(f"Highlighting clicked row for script_key: {script_key} with 'blue'")
        else:
            # Remove highlight and hide buttons for the current row if it's not running
            row.remove_css_class("blue")
            self.hide_buttons(play_button, options_button)
            print(f"Removing 'blue' highlight for clicked row with script_key: {script_key}")

        # Update the play/stop button state
        if is_running:
            # If the script is running: set play button to 'Stop' and add 'highlighted' class
            self.set_play_stop_button_state(play_button, True)
            row.add_css_class("highlighted")
            print(f"Script {script_key} is running. Setting play button to 'Stop' and adding 'highlighted'.")
        else:
            # If the script is not running and not clicked, reset play button and highlight
            if not is_clicked:
                self.set_play_stop_button_state(play_button, False)
                row.remove_css_class("highlighted")
                print(f"Script {script_key} is not running. Setting play button to 'Play' and removing 'highlighted'.")

            # If the script is not running but clicked, ensure it stays highlighted in blue
            if is_clicked and not is_running:
                row.add_css_class("blue")
                print(f"Preserving 'blue' highlight for clicked but not running script_key: {script_key}")

    def set_play_stop_button_state(self, button, is_playing):
        # Check if the button already has a child (Gtk.Image)
        current_child = button.get_child()
        
        if current_child and isinstance(current_child, Gtk.Image):
            # Reuse the existing Gtk.Image child
            image = current_child
        else:
            # Create a new Gtk.Image if none exists
            image = Gtk.Image()
            button.set_child(image)
        
        # Set the icon name and tooltip based on the state
        if is_playing:
            image.set_from_icon_name("media-playback-stop-symbolic")
            button.set_tooltip_text("Stop")
        else:
            image.set_from_icon_name("media-playback-start-symbolic")
            button.set_tooltip_text("Play")
        
        # Explicitly set pixel size to ensure crisp rendering
        # image.set_pixel_size(24)
        
        # Ensure the icon is re-rendered cleanly
        image.queue_draw()
        
    def update_row_highlight(self, row, highlight):
        #self.print_method_name()
        if highlight:
            row.add_css_class("highlighted")
        else:
            #row.remove_css_class("blue")
            row.remove_css_class("highlighted")

    def find_and_remove_wine_created_shortcuts(self):
        self.print_method_name()
        """
        Searches for .desktop files in self.applicationsdir/wine and deletes any
        that contain references to self.prefixes_dir.
        """
        wine_apps_dir = self.applicationsdir / "wine"

        if not wine_apps_dir.exists():
            print(f"Directory {wine_apps_dir} does not exist.")
            return

        # Iterate through all .desktop files under wine-related directories
        for root, _, files in os.walk(wine_apps_dir):
            for file in files:
                if file.endswith(".desktop"):
                    desktop_file_path = Path(root) / file

                    try:
                        # Check if the file contains a reference to self.prefixes_dir
                        with open(desktop_file_path, 'r') as f:
                            content = f.read()

                        if str(self.prefixes_dir) in content:
                            print(f"Deleting {desktop_file_path} as it contains {self.prefixes_dir}")
                            desktop_file_path.unlink()  # Delete the file
                    except Exception as e:
                        print(f"Error processing {desktop_file_path}: {e}")

    def toggle_play_stop(self, script_key, play_stop_button, row):
        self.print_method_name()
        if script_key in self.running_processes:
            # Process is running; terminate it
            self.terminate_script(script_key)
            self.set_play_stop_button_state(play_stop_button, False)
            self.update_row_highlight(row, False)
        else:
            # Process is not running; launch it
            self.launch_script(script_key, play_stop_button, row)
            self.set_play_stop_button_state(play_stop_button, True)
            self.update_row_highlight(row, True)

    def process_ended(self, script_key):
        self.print_method_name()
        print(f"--> I'm called by {script_key}")
        ui_state = self.script_ui_data.get(script_key)
        if not ui_state:
            print(f"No script data found for script_key: {script_key}")
            return

        row = ui_state.get('row')
        play_button = ui_state.get('play_button')
        options_button = ui_state.get('options_button')
        is_clicked = ui_state.get('is_clicked_row', False)

        # Handle wineprefix and process linked files if necessary.
        process_info = self.running_processes.pop(script_key, None)
        exe_name = None
        exe_parent_name = None
        unique_id = None
        if process_info:
            script = self.expand_and_resolve_path(process_info.get("script"))
            exe_name = process_info.get("exe_name")
            exe_parent_name = process_info.get("exe_parent_name")
            unique_id = process_info.get("unique_id")
            if script and script.exists():
                wineprefix = script.parent
                print(f"Processing wineprefix: {wineprefix}")
                if wineprefix:
                    script_data = self.script_list.get(script_key, {})
                    parent_runner = script_data.get('runner', '')
                    self.create_scripts_for_lnk_files(wineprefix, parent_runner)
                    self.find_and_remove_wine_created_shortcuts()

        if exe_name and exe_parent_name:
            is_still_running = False
            new_pid = None
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    proc_cmdline = proc.info['cmdline'] or []
                    if proc_name.lower() == exe_name.lower() or any(exe_name.lower() in arg.lower() for arg in proc_cmdline):
                        for arg in proc_cmdline:
                            if exe_name.lower() in arg.lower():
                                proc_exe_path = Path(arg)
                                proc_exe_parent_name = proc_exe_path.parent.name
                                if proc_exe_parent_name == exe_parent_name:
                                    is_still_running = True
                                    new_pid = proc.pid
                                    break
                        if is_still_running:
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            if is_still_running:
                self.running_processes[script_key] = {
                    "process": None,
                    "wineprefix": process_info.get("wineprefix") if process_info else None,
                    "runner": process_info.get("runner") if process_info else None,
                    "row": row,
                    "script": script if process_info else None,
                    "exe_name": exe_name,
                    "exe_parent_name": exe_parent_name,
                    "pid": new_pid,
                    "unique_id": unique_id
                }
                print(f"Process with exe_name {exe_name} and parent '{exe_parent_name}' is still running (respawned).")
                threading.Thread(target=self.monitor_external_process, args=(script_key, new_pid), daemon=True).start()
                ui_state['is_running'] = True
                if row:
                    self.update_row_highlight(row, True)
                    row.add_css_class("highlighted")
                if play_button:
                    self.set_play_stop_button_state(play_button, True)
                if is_clicked:
                    row.add_css_class("blue")
                    self.show_buttons(play_button, options_button)
                    print(f"Maintaining 'blue' highlight and buttons for script_key: {script_key}")
                return

        # Reset UI elements when process has ended.
        if row:
            row.remove_css_class("highlighted")
            row.remove_css_class("blue")
        if play_button:
            self.set_play_stop_button_state(play_button, False)
        if self.launch_button:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
        # Instead of fully hiding the overlay buttons, reset their opacity and sensitivity.
        if play_button and options_button:
            play_button.set_opacity(0)
            options_button.set_opacity(0)
            play_button.set_sensitive(False)
            options_button.set_sensitive(False)
        ui_state['is_clicked_row'] = False
        ui_state['is_running'] = False

        if not self.running_processes:
            print("All processes ended.")
        self.runner_to_use = None
        self.check_running_processes_on_startup()

    def launch_script(self, script_key, play_stop_button, row):
        self.print_method_name()
        script_data = self.reload_script_data_from_charm(script_key)
        if not script_data:
            print("Error: Script data could not be reloaded.")
            self.handle_ui_error(play_stop_button, row, "Script Error", "Failed to reload script data.", "Script Error")
            return

        self.debug = True
        unique_id = str(uuid.uuid4())
        env = os.environ.copy()
        env['WINECHARM_UNIQUE_ID'] = unique_id

        exe_file = Path(str(script_data.get('exe_file', ''))).expanduser().resolve()
        wineprefix = Path(str(script_data.get('script_path', ''))).parent.expanduser().resolve()
        env_vars = str(script_data.get('env_vars', ''))
        args = str(script_data.get('args', ''))
        wine_debug = self.wine_debug
        wineboot_file_path = Path(wineprefix) / "wineboot-required.yml"

        try:
            runner_path = self.get_runner(script_data)
        except Exception as e:
            print(f"Error getting runner: {e}")
            self.handle_ui_error(play_stop_button, row, "Runner Error", f"Failed to get runner. Error: {e}", "Runner Error")
            return

        if not exe_file.exists():
            self.handle_ui_error(play_stop_button, row, "Executable Not Found", str(exe_file), "Exe Not Found")
            return

        log_file_path = Path(wineprefix) / f"{exe_file.stem}.log"
        # Safely process arguments
        try:
            # Expand $WINEPREFIX first
            expanded_args = args.replace('$WINEPREFIX', str(wineprefix))
            
            # Custom argument parsing for switches and spaced filenames
            args_list = []
            current_arg = []
            for part in expanded_args.split():
                if part.startswith('-'):
                    if current_arg:
                        args_list.append(' '.join(current_arg))
                        current_arg = []
                    args_list.append(part)
                else:
                    current_arg.append(part)
            if current_arg:
                args_list.append(' '.join(current_arg))

            # Process each argument individually
            processed_args = []
            for arg in args_list:
                # Convert to Windows path format if needed
                drive_c_prefix = f"{wineprefix}/drive_c/"
                if arg.startswith(drive_c_prefix):
                    win_path = arg.replace(drive_c_prefix, "C:/").replace("/", "/")
                    processed_args.append(shlex.quote(win_path))
                else:
                    processed_args.append(shlex.quote(arg))

            safe_args = ' '.join(processed_args)

        except Exception as e:
            print(f"Error processing arguments: {e}")
            self.handle_ui_error(play_stop_button, row, 
                            "Argument Error", f"Invalid arguments: {e}", 
                            "Launch Failed")
            return

        # Prepare command components
        command = [
            "sh", "-c",
            f"export WINEPREFIX={shlex.quote(str(wineprefix))}; "
            f"cd {shlex.quote(str(exe_file.parent))} && "
            f"{wine_debug} {env_vars} "
            f"WINEPREFIX={shlex.quote(str(wineprefix))} "
            f"{shlex.quote(str(runner_path))} "
            f"{shlex.quote(exe_file.name)} {safe_args}"
        ]
        
        print("\n" + "="*40 + " FINAL COMMAND " + "="*40)
        print("EXECUTING:", ' '.join(command))
        print("="*94 + "\n")
        
        def execute_launch():
            try:
                with open(log_file_path, 'w') as log_file:
                    process = subprocess.Popen(
                        command,
                        preexec_fn=os.setsid,
                        stdout=subprocess.DEVNULL,
                        stderr=log_file,
                        env=env
                    )

                    self.running_processes[script_key] = {
                        "process": process,
                        "unique_id": unique_id,
                        "pgid": os.getpgid(process.pid),
                        "row": row,
                        "script": Path(str(script_data['script_path'])),
                        "exe_file": exe_file,
                        "exe_name": exe_file.name,
                        "runner": str(runner_path),
                        "wineprefix": str(wineprefix)
                    }

                    self.runner_to_use = runner_path
                    self.set_play_stop_button_state(play_stop_button, True)
                    self.update_row_highlight(row, True)

                    if ui_state := self.script_ui_data.get(script_key):
                        ui_state['is_running'] = True

                    threading.Thread(target=self.monitor_process, args=(script_key,), daemon=True).start()
                    GLib.timeout_add_seconds(5, self.get_child_pid_async, script_key)

            except Exception as e:
                error_message = f"Error launching script: {e}"
                print(error_message)
                traceback_str = traceback.format_exc()
                with open(log_file_path, 'a') as log_file:
                    log_file.write(f"\n{error_message}\n{traceback_str}\n")

                GLib.idle_add(self.handle_ui_error, play_stop_button, row,
                            "Launch Error", f"Failed to launch: {e}", "Launch Failed")
                GLib.idle_add(self.show_info_dialog, "Launch Error", f"Failed to launch: {e}")

        if wineboot_file_path.exists():
            runner_dir = runner_path.parent.resolve()
            
            # Show loading state
            GLib.idle_add(self.set_play_stop_button_state, play_stop_button, True)
            GLib.idle_add(self.update_row_highlight, row, True)
            GLib.idle_add(play_stop_button.set_sensitive, False)

            def wineboot_operation():
                try:
                    prerun_command = [
                        "sh", "-c",
                        f"export PATH={shlex.quote(str(runner_dir))}:$PATH; "
                        f"WINEPREFIX={shlex.quote(str(wineprefix))} wineboot -u"
                    ]
                    
                    if self.debug:
                        print(f"Running wineboot: {' '.join(prerun_command)}")

                    subprocess.run(prerun_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    wineboot_file_path.unlink(missing_ok=True)
                    
                    # Schedule main launch after wineboot completes
                    GLib.idle_add(execute_launch)

                except subprocess.CalledProcessError as e:
                    error_msg = f"Wineboot failed (code {e.returncode}): {e.stderr}"
                    GLib.idle_add(self.handle_ui_error, play_stop_button, row,
                                "Wineboot Error", error_msg, "Prefix Update Failed")
                except Exception as e:
                    error_msg = f"Wineboot error: {str(e)}"
                    GLib.idle_add(self.handle_ui_error, play_stop_button, row,
                                "Wineboot Error", error_msg, "Prefix Update Failed")
                finally:
                    GLib.idle_add(play_stop_button.set_sensitive, True)

            threading.Thread(target=wineboot_operation, daemon=True).start()
        else:
            execute_launch()

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

    def find_command_in_path(self, command):
        self.print_method_name()
        """
        Checks if a command exists in the system's PATH.
        Returns the absolute path if found, otherwise None.
        """
        self.debug = True
        if self.debug:
            print(f"Looking for command: {command} in PATH")

        try:
            result = subprocess.run(
                ["which", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if self.debug:
                print(f"'which' result for {command}: returncode={result.returncode}, stdout={result.stdout.strip()}, stderr={result.stderr.strip()}")

            if result.returncode == 0:
                path = Path(result.stdout.strip())
                if path.exists():
                    if self.debug:
                        print(f"Command found: {path}")
                    return path
                else:
                    if self.debug:
                        print(f"Command found but path does not exist: {path}")
        except Exception as e:
            print(f"Error finding command '{command}': {e}")

        if self.debug:
            print(f"Command '{command}' not found in PATH")
        
        self.debug = True
        return None


    def handle_ui_error(self, play_stop_button, row, title, message, tooltip):
        self.print_method_name()
        """
        Updates the UI to reflect an error state and shows an info dialog.
        """
        GLib.idle_add(self.update_row_highlight, row, False)
        GLib.idle_add(play_stop_button.add_css_class, "red")
        GLib.idle_add(play_stop_button.set_child, Gtk.Image.new_from_icon_name("action-unavailable-symbolic"))
        GLib.idle_add(play_stop_button.set_tooltip_text, tooltip)
        GLib.timeout_add_seconds(0.5, self.show_info_dialog, title, message)


    def reload_script_data_from_charm(self, script_key):
        self.print_method_name()
        script_data = self.script_list.get(script_key)
        if not script_data:
            print(f"Error: Script with key {script_key} not found in script_list.")
            return None

        script_path = Path(str(script_data.get('script_path', ''))).expanduser().resolve()

        if not script_path.exists():
            print(f"Error: Script path {script_path} does not exist.")
            return None

        try:
            # Load the script data from the .charm file
            with open(script_path, 'r') as f:
                new_script_data = yaml.safe_load(f)

            # Update the script_list with the new data
            if isinstance(new_script_data, dict):
                self.script_list[script_key] = new_script_data
                print(f"Reloaded script data from {script_path}")
                return new_script_data
            else:
                print(f"Error: Invalid data format in {script_path}")
                return None

        except Exception as e:
            print(f"Error reloading script from {script_path}: {e}")
            return None

    def show_error_with_log_dialog(self, title, message, log_file_path):
        self.print_method_name()
        """
        Show an error dialog with an option to view log content.
        """
        # Create the main error dialog
        dialog = Adw.AlertDialog(
            heading=title,
            body=message
        )

        # Add buttons to the dialog
        dialog.add_response("close", "Close")
        dialog.add_response("show_log", "Show Log")
        dialog.set_default_response("close")
        dialog.set_close_response("close")

        # Variable to store the log content
        log_content = ""

        # Load the log content asynchronously
        def load_log_content():
            self.print_method_name()
            nonlocal log_content
            try:
                with open(log_file_path, 'r') as log_file:
                    log_content = log_file.read()
            except Exception as e:
                log_content = f"Failed to load log: {e}"

        threading.Thread(target=load_log_content, daemon=True).start()

        # Function to show the log content dialog
        def show_log_dialog():
            self.print_method_name()
            log_dialog = Adw.AlertDialog(
                heading="Log Content",
                body=""
            )

            # Create scrolled text view for log content
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled_window.set_min_content_width(640)
            scrolled_window.set_min_content_height(480)

            log_view = Gtk.TextView()
            log_view.set_editable(False)
            log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            scrolled_window.set_child(log_view)

            # Set log content
            GLib.idle_add(lambda: log_view.get_buffer().set_text(log_content))

            # Add content to dialog
            log_dialog.set_extra_child(scrolled_window)

            # Configure dialog buttons
            log_dialog.add_response("close", "Close")
            log_dialog.set_default_response("close")
            log_dialog.set_close_response("close")

            # Present the log dialog
            log_dialog.present(self.window)

        # Handle main dialog responses
        def on_response(dialog, response):
            self.print_method_name()
            if response == "show_log":
                show_log_dialog()
            dialog.close()

        # Connect response handler
        dialog.connect("response", on_response)

        # Present the main dialog
        dialog.present(self.window)

    def monitor_process(self, script_key):
        self.print_method_name()
        process_info = self.running_processes.get(script_key)
        if not process_info:
            return

        process = process_info.get("process")
        if not process:
            return

        process.wait()  # Wait for the process to complete
        return_code = process.returncode

        # Check if the process was manually stopped
        #manually_stopped = process_info.get("manually_stopped", False)
        manually_stopped = process_info.get("manually_stopped", False) or self.manually_killed

        # Update the UI in the main thread
        GLib.idle_add(self.process_ended, script_key)

        if return_code != 0 and not manually_stopped:
            # Handle error code 2 (cancelled by the user) gracefully
            if return_code == 2:
                print("Process was cancelled by the user.")
                return
            if return_code == -9:
                print("All Processes killed by the user.")
                return

            # Show error dialog only if the process was not stopped manually
            script = process_info.get('script')
            wineprefix = process_info.get('wineprefix')
            exe_file = process_info.get('exe_file')

            log_file_path = Path(wineprefix) / f"{exe_file.stem}.log"
            error_message = f"The script failed with error code {return_code}."

            # Show the error dialog
            GLib.idle_add(
                self.show_error_with_log_dialog,
                "Command Execution Error",
                error_message,
                log_file_path
            )



    def get_child_pid_async(self, script_key):
        self.print_method_name()
        # Run get_child_pid in a separate thread
        if script_key not in self.running_processes:
            print("Process already ended, nothing to get child PID for")
            return False

        process_info = self.running_processes[script_key]
        pid = process_info.get('pid')
        script = process_info.get('script')
        wineprefix = Path(process_info.get('wineprefix')).expanduser().resolve()
        exe_file = Path(process_info.get('exe_file', '')).expanduser().resolve()
        exe_name = process_info.get('exe_name')

        try:
            # Get the runner from the script data
            runner_path = self.get_runner(process_info)
            runner_dir = runner_path.parent.resolve()
            path_env = f'export PATH="{shlex.quote(str(runner_dir))}:$PATH"'
        except Exception as e:
            print(f"Error getting runner: {e}")
            return False

        exe_name = shlex.quote(str(exe_name))
        runner_dir = shlex.quote(str(runner_dir))

        print("="*100)
        print(f"runner = {runner_path}")
        print(f"exe_file = {exe_file}")
        print(f"exe_name = {exe_name}")

        def run_get_child_pid():
            self.print_method_name()
            try:
                print("---------------------------------------------")
                print(f"Looking for child processes of: {exe_name}")

                # Prepare command to filter processes using winedbg
                if path_env:
                    winedbg_command_with_grep = (
                        f"export PATH={shlex.quote(str(runner_dir))}:$PATH; "
                        f"WINEPREFIX={shlex.quote(str(wineprefix))} winedbg --command 'info proc' | "
                        f"grep -A9 \"{exe_name}\" | grep -v 'grep' | grep '_' | "
                        f"grep -v 'start.exe'    | grep -v 'winedbg.exe' | grep -v 'conhost.exe' | "
                        f"grep -v 'explorer.exe' | grep -v 'services.exe' | grep -v 'rpcss.exe' | "
                        f"grep -v 'svchost.exe'   | grep -v 'plugplay.exe' | grep -v 'winedevice.exe' | "
                        f"cut -f2- -d '_' | tr \"'\" ' '"
                    )
                else:
                    winedbg_command_with_grep = (
                        f"WINEPREFIX={shlex.quote(str(wineprefix))} winedbg --command 'info proc' | "
                        f"grep -A9 \"{exe_name}\" | grep -v 'grep' | grep '_' | "
                        f"grep -v 'start.exe'    | grep -v 'winedbg.exe' | grep -v 'conhost.exe' | "
                        f"grep -v 'explorer.exe' | grep -v 'services.exe' | grep -v 'rpcss.exe' | "
                        f"grep -v 'svchost.exe'   | grep -v 'plugplay.exe' | grep -v 'winedevice.exe' | "
                        f"cut -f2- -d '_' | tr \"'\" ' '"
                    )
                if self.debug:
                    print("---------run_get_child_pid's winedbg_command_with_grep---------------")
                    print(winedbg_command_with_grep)
                    print("--------/run_get_child_pid's winedbg_command_with_grep---------------")

                winedbg_output_filtered = subprocess.check_output(winedbg_command_with_grep, shell=True, text=True).strip().splitlines()
                if self.debug:
                    print("--------- run_get_child_pid's winedbg_output_filtered ---------------")
                    print(winedbg_output_filtered)
                    print("---------/run_get_child_pid's winedbg_output_filtered ---------------")

                # Retrieve the parent directory name and search for processes
                exe_parent = exe_file.parent.name
                child_pids = set()

                for filtered_exe in winedbg_output_filtered:
                    filtered_exe = filtered_exe.strip()
                    cleaned_exe_parent_name = re.escape(exe_parent)

                    # Command to get PIDs for matching processes
                    pgrep_command = (
                        f"ps -ax --format pid,command | grep \"{filtered_exe}\" | "
                        f"grep \"{cleaned_exe_parent_name}\" | grep -v 'grep' | "
                        f"sed 's/^ *//g' | cut -f1 -d ' '"
                    )
                    if self.debug:
                        print("--------- run_get_child_pid's pgrep_command ---------------")
                        print(f"{pgrep_command}")
                        print("---------/run_get_child_pid's pgrep_command ---------------")
                    pgrep_output = subprocess.check_output(pgrep_command, shell=True, text=True).strip()
                    child_pids.update(pgrep_output.splitlines())

                    if self.debug:
                        print("--------- run_get_child_pid's pgrep_output ---------------")
                        print(f"{pgrep_output}")
                        print("---------/run_get_child_pid's pgrep_output ---------------")

                        print("--------- run_get_child_pid's child_pids pgrep_output.splitlines() ---------------")
                        print(f"{pgrep_output.splitlines()}")
                        print("---------/run_get_child_pid's child_pids pgrep_output.splitlines() ---------------")

                if child_pids:
                    print(f"Found child PIDs: {child_pids}\n")
                    GLib.idle_add(self.add_child_pids_to_running_processes, script_key, child_pids)
                else:
                    print(f"No child process found for {exe_name}")

            except subprocess.CalledProcessError as e:
                print(f"Error executing command: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")

        # Start the background thread
        threading.Thread(target=run_get_child_pid, daemon=True).start()

        return False


    def add_child_pids_to_running_processes(self, script_key, child_pids):
        self.print_method_name()
        # Add the child PIDs to the running_processes dictionary
        if script_key in self.running_processes:
            process_info = self.running_processes.get(script_key)

            # Merge the existing PIDs with the new child PIDs, ensuring uniqueness
            current_pids = set(process_info.get('pids', []))  # Convert existing PIDs to a set for uniqueness
            current_pids.update([int(pid) for pid in child_pids])  # Update with child PIDs

            # Update the running processes with the merged PIDs
            self.running_processes[script_key]["pids"] = list(current_pids)

            print(f"Updated {script_key} with child PIDs: {self.running_processes[script_key]['pids']}")
        else:
            print(f"Script key {script_key} not found in running processes.")



    def terminate_script(self, script_key):
        self.print_method_name()
        process_info = self.running_processes.get(script_key)
        if not process_info:
            print(f"No running process found for script_key: {script_key}")
            return

        # Set the manually_stopped flag to True
        process_info["manually_stopped"] = True

        unique_id = process_info.get("unique_id")
        wineprefix = process_info.get("wineprefix")
        runner = process_info.get("runner") or "wine"
        runner_dir = Path(runner).expanduser().resolve().parent
        pids = process_info.get("pids", [])

        if unique_id:
            # Terminate processes by unique_id
            pids_to_terminate = []
            for proc in psutil.process_iter(['pid', 'environ']):
                try:
                    env = proc.environ()
                    if env.get('WINECHARM_UNIQUE_ID') == unique_id:
                        pids_to_terminate.append(proc.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if not pids_to_terminate:
                print(f"No processes found with unique ID {unique_id}")
                return

            pids = pids_to_terminate

        if pids:
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f"Successfully sent SIGTERM to process with PID {pid}")
                except Exception as e:
                    print(f"Error sending SIGTERM to process with PID {pid}: {e}")

            # If still running, send SIGKILL
            for pid in pids:
                if psutil.pid_exists(pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                        print(f"Successfully sent SIGKILL to process with PID {pid}")
                    except Exception as e:
                        print(f"Error sending SIGKILL to process with PID {pid}: {e}")
        else:
            print(f"No PIDs found to terminate for script_key: {script_key}")
            # Fallback to wineserver -k
            try:
                command = (
                    f"export PATH={shlex.quote(str(runner_dir))}:$PATH; "
                    f"WINEPREFIX={shlex.quote(str(wineprefix))} wineserver -k"
                )
                bash_command = f"bash -c {shlex.quote(command)}"
                subprocess.run(bash_command, shell=True, check=True)
                print(f"Successfully terminated all processes in Wine prefix {wineprefix}")
            except Exception as e:
                print(f"Error terminating processes in Wine prefix {wineprefix}: {e}")

        self.running_processes.pop(script_key, None)
        GLib.idle_add(self.process_ended, script_key)




    def monitor_external_process(self, script_key, pid):
        self.print_method_name()
        try:
            proc = psutil.Process(pid)
            proc.wait()  # Wait for the process to terminate
        except psutil.NoSuchProcess:
            pass
        finally:
            # Process has ended; update the UI in the main thread
            GLib.idle_add(self.process_ended, script_key)

    def check_running_processes_on_startup(self):
        self.print_method_name()
        if not hasattr(self, 'script_ui_data') or not self.script_ui_data:
            return
        for script_key, script_data in list(self.script_list.items()):
            wineprefix = Path(str(script_data['script_path'])).parent.expanduser().resolve()
            target_exe_path = Path(str(script_data['exe_file'])).expanduser().resolve()
            target_exe_name = target_exe_path.name
            runner = script_data.get('runner', 'wine')

            is_running = False
            running_pids = []  # List to store all PIDs associated with the script

            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'environ']):
                try:
                    proc_name = proc.info['name']
                    proc_cmdline = proc.cmdline() or []
                    proc_environ = proc.environ()
                    proc_wineprefix = proc_environ.get('WINEPREFIX', '')

                    # Check if the process is using the same wineprefix
                    if Path(proc_wineprefix).expanduser().resolve() != wineprefix:
                        continue

                    # Check if process name matches the target executable name
                    if proc_name == target_exe_name or any(target_exe_name in arg for arg in proc_cmdline):
                        is_running = True
                        # Collect the PID of the process
                        running_pids.append(proc.pid)
                        # Also collect PIDs of child processes
                        child_pids = [child.pid for child in proc.children(recursive=True)]
                        running_pids.extend(child_pids)
                        # Continue to find all processes matching the criteria
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, KeyError):
                    continue

            if running_pids:
                # Remove duplicates
                running_pids = list(set(running_pids))
                print(f"Found running PIDs for script_key {script_key}: {running_pids}")

            ui_state = self.script_ui_data.get(script_key)
            if ui_state:
                row = ui_state.get('row')
                play_button = ui_state.get('play_button')

                if is_running:
                    if script_key not in self.running_processes:
                        # Store the list of PIDs and start monitoring the processes
                        self.running_processes[script_key] = {
                            "process": None,
                            "wineprefix": str(wineprefix),
                            "runner": runner,
                            "row": row,
                            "script": Path(str(script_data['script_path'])),
                            "exe_name": target_exe_name,
                            "pids": running_pids  # Store the list of PIDs
                        }
                        self.update_ui_for_running_script_on_startup(script_key)
                        # Start a thread to monitor the processes
                        threading.Thread(target=self.monitor_multiple_processes, args=(script_key, running_pids), daemon=True).start()
                else:
                    # Remove script from running processes and reset UI
                    if script_key in self.running_processes:
                        self.running_processes.pop(script_key, None)
                    ui_state['is_running'] = False
                    # Do NOT reset 'is_clicked_row' here
                    if row:
                        # Only update row highlight if the row is not clicked
                        if not ui_state.get('is_clicked_row', False):
                            self.update_row_highlight(row, False)
                    if play_button:
                        self.set_play_stop_button_state(play_button, False)

    def monitor_multiple_processes(self, script_key, pids):
        self.print_method_name()
        try:
            procs = [psutil.Process(pid) for pid in pids if psutil.pid_exists(pid)]
            psutil.wait_procs(procs)
        except Exception as e:
            print(f"Error monitoring processes for script_key {script_key}: {e}")
        finally:
            # Processes have ended; update the UI in the main thread
            GLib.idle_add(self.process_ended, script_key)

       
    def update_ui_for_running_script_on_startup(self, script_key):
        self.print_method_name()
        ui_state = self.script_ui_data.get(script_key)
        if not ui_state:
            print(f"No UI state found for script_key: {script_key}")
            return

        row = ui_state.get('row')
        play_button = ui_state.get('play_button')

        # Update UI elements
        if row:
            self.update_row_highlight(row, True)
            row.add_css_class("highlighted")

        if play_button:
            self.set_play_stop_button_state(play_button, True)
            ui_state['is_running'] = True  # Ensure is_running is set

            
############################### 1050 - 1682 ########################################

    def update_running_processes(self, current_running_processes):
        self.print_method_name()
        """
        Update `self.running_processes` to match `current_running_processes`.
        Remove processes that have ended externally.
        """
        ended_keys = [key for key in self.running_processes if key not in current_running_processes]

        for script_key in ended_keys:
            self.monitoring_active = True
            self.start_monitoring()
            self.process_ended(script_key)

        # Update `self.running_processes` to reflect currently running processes
        self.running_processes = current_running_processes

    def update_ui_for_running_process(self, current_running_processes):
        self.print_method_name()
        """
        Update the UI to reflect the state of running processes.
        
        Args:
            current_running_processes (dict): A dictionary containing details of the current running processes.
        """
        # Iterate over all scripts in script_ui_data to update the UI state
        for script_key, ui_state in self.script_ui_data.items():
            if not ui_state:
                print(f"No script data found for script_key: {script_key}")
                continue

            # Retrieve row, play_button, and options_button
            row = ui_state.get('row')
            play_button = ui_state.get('play_button')
            options_button = ui_state.get('options_button')

            if script_key in current_running_processes:
                # If the script is running, add the highlighted class and update button states
                if not ui_state['is_running']:  # Only update if the current state is not already running
                    if row:
                        self.update_row_highlight(row, True)
                        row.add_css_class("highlighted")
                        print(f"Added 'highlighted' to row for script_key: {script_key}")

                    # Set the play button to 'Stop' since the script is running
                    if play_button:
                        self.set_play_stop_button_state(play_button, True)

                    # Update internal running state
                    ui_state['is_running'] = True

            else:
                # If the script is not running, remove highlight and reset buttons, but only if it's marked as running
                if ui_state['is_running']:  # Only update if the current state is marked as running
                    if row:
                        self.update_row_highlight(row, False)
                        row.remove_css_class("highlighted")
                        #row.remove_css_class("blue")
                        print(f"Removed 'highlighted' from row for script_key: {script_key}")

                    # Set play button back to 'Play'
                    if play_button:
                        self.set_play_stop_button_state(play_button, False)

                    # Update internal state to not running
                    ui_state['is_running'] = False
                    ui_state['is_clicked_row'] = False

            # Update the play/stop button visibility if the script row is currently clicked
            if ui_state.get('is_clicked_row', False):
                if play_button and options_button:
                    self.show_buttons(play_button, options_button)
                    self.set_play_stop_button_state(play_button, True)
                    print(f"Updated play/stop button for clicked row with script_key: {script_key}")

            # Update the launch button state if it matches the script_key
            if self.launch_button and getattr(self, 'launch_button_exe_name', None) == script_key:
                if script_key in current_running_processes:
                    self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
                    self.launch_button.set_tooltip_text("Stop")
                else:
                    self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                    self.launch_button.set_tooltip_text("Play")
                print(f"Updated launch button for script_key: {script_key}")

    def extract_yaml_info(self, script_key):
        self.print_method_name()
        script_data = self.script_list.get(script_key)
        if script_data:
            return script_data
        else:
            print(f"Warning: Script with key {script_key} not found in script_list.")
            return {}

    def determine_progname(self, productname, exe_no_space, exe_name):
        self.print_method_name()
        """
        Determine the program name based on the product name extracted by exiftool, or fallback to executable name.
        Args:
            productname (str): The product name extracted from the executable.
            exe_no_space (str): The executable name without spaces.
            exe_name (str): The original executable name.
        Returns:
            str: The determined program name.
        """
        # Logic to determine the program name based on exe name and product name
        if "setup" in exe_name.lower() or "install" in exe_name.lower():
            return productname + '*'
        elif "setup" in productname.lower() or "install" in productname.lower():
            return productname
        else:
            # Fallback to product name or executable name without spaces if productname contains numbers or is non-ascii
            return productname if productname and not any(char.isdigit() for char in productname) and productname.isascii() else exe_no_space


    def create_yaml_file(self, exe_path, prefix_dir=None, use_exe_name=False, runner_override=None):
        self.print_method_name()
        # Determine runner_to_use
        if runner_override is not None:
            runner_to_use = runner_override
        else:
            if self.runner_to_use:
                runner_to_use = self.replace_home_with_tilde_in_path(str(self.runner_to_use))
            else:
                runner_to_use = ""

        self.create_required_directories()
        exe_file = Path(exe_path).resolve()
        exe_name = exe_file.stem
        exe_no_space = exe_name.replace(" ", "_")

        # Calculate SHA256 hash
        sha256_hash = hashlib.sha256()
        with open(exe_file, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        sha256sum = sha256_hash.hexdigest()[:10]
        script_key = sha256_hash.hexdigest()
        # string to path
        self.template = Path(self.template).expanduser().resolve()
        print(f"         => create_yaml_file -> self.template = {self.template}")
        # Determine prefix directory
        if prefix_dir is None:
            if self.single_prefix:
                # Use architecture-specific single prefix directory
                if self.arch == 'win32':
                    prefix_dir = self.single_prefix_dir_win32
                    template_to_use = self.default_template_win32
                else:
                    prefix_dir = self.single_prefix_dir_win64
                    template_to_use = self.default_template_win64
                

                # Create prefix from template if needed
                if not prefix_dir.exists():
                    #self.copy_template(prefix_dir, template_to_use)
                    print("--->if not prefix_dir.exists():")
                    self.custom_copytree(self.template, prefix_dir)
            else:
                # if the user has deleted the current in use runner and open an exe, it should use the default arch based runner.
                if not self.template.exists():
                    # Use architecture-specific single prefix directory
                    if self.arch == 'win32':
                        template_to_use = self.default_template_win32
                    else:
                        template_to_use = self.default_template_win64
                    print(f"Error: {self.template} has been deleted, using {template_to_use}")
                    GLib.idle_add(self.show_info_dialog, "Template Deleted", f"{self.template}.name has been deleted, using {template_to_use}.name")
                    self.template = template_to_use

                # Create new unique prefix per executable
                prefix_dir = self.prefixes_dir / f"{exe_no_space}-{sha256sum[:10]}"
                if not prefix_dir.exists():
                    if self.template.exists():
                        print("===>if self.template.exists():")
                        print(f"->>>{self.template} is being copied")
                        self.custom_copytree(self.template, prefix_dir)
                    else:
                        self.ensure_directory_exists(prefix_dir)
            # Resolve the generated or selected prefix directory
            prefix_dir = Path(prefix_dir).resolve()
        else:
            # Resolve the user-provided prefix directory
            prefix_dir = Path(prefix_dir).expanduser().resolve()

        # Check if a script with the same sha256sum and wineprefix already exists
        if script_key in self.script_list:
            existing_script_data = self.script_list[script_key]
            existing_script_path = Path(existing_script_data['script_path']).expanduser().resolve()
            existing_wineprefix = existing_script_path.parent

            current_wineprefix = prefix_dir

            # Compare resolved paths to ensure accuracy
            if existing_wineprefix == current_wineprefix:
                # Remove existing .charm file and its entry
                if existing_script_path.exists():
                    existing_script_path.unlink()
                    print(f"Removed existing charm file: {existing_script_path}")
                del self.script_list[script_key]
                print(f"Removed old script_key {script_key} from script_list")
            else:
                print(f"Existing charm file in different prefix '{existing_wineprefix}' left intact.")

        # Proceed to create the YAML configuration and charm file
        wineprefix_name = prefix_dir.name

        # Extract product name using exiftool
        product_cmd = ['exiftool', shlex.quote(str(exe_file))]
        product_output = self.run_command(" ".join(product_cmd))
        if product_output is None:
            productname = exe_no_space
        else:
            productname_match = re.search(r'Product Name\s+:\s+(.+)', product_output)
            productname = productname_match.group(1).strip() if productname_match else exe_no_space

        # Determine program name based on use_exe_name flag
        if use_exe_name:
            progname = exe_name  # Use exe_name if flag is set
        else:
            progname = self.determine_progname(productname, exe_no_space, exe_name)
            
        # Create YAML file with proper naming
        yaml_file_path = prefix_dir / f"{exe_no_space if use_exe_name else progname.replace(' ', '_')}.charm"

        # Prepare YAML data with runner_to_use
        yaml_data = {
            'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
            'script_path': self.replace_home_with_tilde_in_path(str(yaml_file_path)),
            'wineprefix': self.replace_home_with_tilde_in_path(str(prefix_dir)),
            'progname': progname,
            'args': "",
            'sha256sum': sha256_hash.hexdigest(),
            'runner': runner_to_use,  # Use the determined runner
            'wine_debug': "WINEDEBUG=-fixme-all DXVK_LOG_LEVEL=none",
            'env_vars': ""
        }

        # Write the new YAML file
        with open(yaml_file_path, 'w') as yaml_file:
            yaml.dump(yaml_data, open(yaml_file_path, 'w'), default_style="'", default_flow_style=False, width=10000)

        # Update yaml_data with resolved paths
        yaml_data['exe_file'] = str(exe_file.expanduser().resolve())
        yaml_data['script_path'] = str(yaml_file_path.expanduser().resolve())
        yaml_data['wineprefix'] = str(prefix_dir.expanduser().resolve())
        # Extract icon and create desktop entry
        icon_path = self.extract_icon(exe_file, prefix_dir, exe_no_space, progname)
        #self.create_desktop_entry(progname, yaml_file_path, icon_path, prefix_dir)

        # Add the new script data directly to self.script_list
        self.new_scripts.add(yaml_file_path.stem)

        # Add or update script row in UI
        self.script_list[script_key] = yaml_data
        # Update the UI row for the renamed script
        row = self.create_script_row(script_key, yaml_data)
        if row:
            self.flowbox.prepend(row)
        # 
        self.script_list = {script_key: yaml_data, **self.script_list}
        self.script_ui_data[script_key]['script_path'] = yaml_data['script_path']
        #script_data['script_path'] = yaml_data['script_path']
        
        print(f"Created new charm file: {yaml_file_path} with script_key {script_key}")
        
        GLib.idle_add(self.create_script_list)



    def extract_icon(self, exe_file, wineprefix, exe_no_space, progname):
        self.print_method_name()
        self.create_required_directories()
        icon_path = wineprefix / f"{progname.replace(' ', '_')}.png"
        #print(f"------ {wineprefix}")
        ico_path = self.tempdir / f"{exe_no_space}.ico"
       # print(f"-----{ico_path}")
        try:
            bash_cmd = f"""
            wrestool -x -t 14 {shlex.quote(str(exe_file))} > {shlex.quote(str(ico_path))} 2>/dev/null
            icotool -x {shlex.quote(str(ico_path))} -o {shlex.quote(str(self.tempdir))} 2>/dev/null
            """
            try:
                subprocess.run(bash_cmd, shell=True, executable='/bin/bash', check=True)
            except subprocess.CalledProcessError as e:
                print(f"Warning: Command failed with error {e.returncode}, but continuing.")

            png_files = sorted(self.tempdir.glob(f"{exe_no_space}*.png"), key=lambda x: x.stat().st_size, reverse=True)
            if png_files:
                best_png = png_files[0]
                shutil.move(best_png, icon_path)

        finally:
            # Clean up only the temporary files created, not the directory itself
            for file in self.tempdir.glob(f"{exe_no_space}*"):
                try:
                    file.unlink()
                except FileNotFoundError:
                    print(f"File {file} not found for removal.")
            # Optionally remove the directory only if needed
            # self.tempdir.rmdir()

        return icon_path if icon_path.exists() else None


    def track_all_lnk_files(self, wineprefix):
        self.print_method_name()
        lnk_files = self.find_lnk_files(wineprefix)
        
        for lnk_file in lnk_files:
            # Skip if already processed
            if self.is_lnk_file_processed(wineprefix, lnk_file):
                continue  
            # Add the .lnk file to the processed list
            self.add_lnk_file_to_processed(wineprefix, lnk_file)

    def find_lnk_files(self, wineprefix):
        self.print_method_name()
        drive_c = wineprefix / "drive_c" 
        lnk_files = []

        for root, dirs, files in os.walk(drive_c):
            current_path = Path(root)

            # Exclude any directory that includes 'Recent' in its path
            if "Recent" in current_path.parts:
                continue  # Skip processing .lnk files in 'Recent' directory

            for file in files:
                file_path = current_path / file

                if file_path.suffix.lower() == ".lnk" and file_path.is_file():
                    lnk_files.append(file_path)

        return lnk_files


    def add_lnk_file_to_processed(self, wineprefix, lnk_file):
        self.print_method_name()
        found_lnk_files_path = wineprefix / "found_lnk_files.yaml"
        if found_lnk_files_path.exists():
            with open(found_lnk_files_path, 'r') as file:
                found_lnk_files = yaml.safe_load(file) or []
        else:
            found_lnk_files = []

        filename = lnk_file.name
        if filename not in found_lnk_files:
            found_lnk_files.append(filename)

        with open(found_lnk_files_path, 'w') as file:
            yaml.dump(found_lnk_files, file, default_style="'", default_flow_style=False, width=10000)

    def is_lnk_file_processed(self, wineprefix, lnk_file):
        self.print_method_name()
        found_lnk_files_path = wineprefix / "found_lnk_files.yaml"
        if found_lnk_files_path.exists():
            with open(found_lnk_files_path, 'r') as file:
                found_lnk_files = yaml.safe_load(file) or []
                return lnk_file.name in found_lnk_files
        return False

    def create_scripts_for_lnk_files(self, wineprefix, parent_runner=None):
        self.print_method_name()
        self.lnk_processed_success_status = False
        lnk_files = self.find_lnk_files(wineprefix)
        exe_files = self.extract_exe_files_from_lnk(lnk_files, wineprefix)
        product_name_map = {}

        for exe_file in exe_files:
            exe_name = exe_file.stem
            product_name = self.get_product_name(exe_file) or exe_name
            product_name_map.setdefault(product_name, []).append(exe_file)

        for product_name, exe_files in product_name_map.items():
            if len(exe_files) > 1:
                for exe_file in exe_files:
                    self.create_yaml_file(exe_file, wineprefix, use_exe_name=True, runner_override=parent_runner)
            else:
                self.create_yaml_file(exe_files[0], wineprefix, use_exe_name=False, runner_override=parent_runner)

        self.find_and_remove_wine_created_shortcuts()
         
    def extract_exe_files_from_lnk(self, lnk_files, wineprefix):
        self.print_method_name()
        exe_files = []
        for lnk_file in lnk_files:
            if not self.is_lnk_file_processed(wineprefix, lnk_file):
                target_cmd = f'exiftool "{lnk_file}"'
                target_output = self.run_command(target_cmd)
                if target_output is None:
                    print(f"Error: Failed to retrieve target for {lnk_file}")
                    continue
                target_dos_name_match = re.search(r'Target File DOS Name\s+:\s+(.+)', target_output)
                target_dos_name = target_dos_name_match.group(1).strip() if target_dos_name_match else None
                
                # Skip if the target DOS name is not an .exe file
                if target_dos_name and not target_dos_name.lower().endswith('.exe'):
                    print(f"Skipping non-exe target: {target_dos_name}")
                    continue
                    
                if target_dos_name:
                    exe_name = target_dos_name.strip()
                    exe_path = self.find_exe_path(wineprefix, exe_name)
                    if exe_path and "unins" not in exe_path.stem.lower():
                        exe_files.append(exe_path)
                        self.add_lnk_file_to_processed(wineprefix, lnk_file)  # Track the .lnk file, not the .exe file
        return exe_files


    def show_info_dialog(self, title, message, callback=None):
        self.print_method_name()
        dialog = Adw.AlertDialog(
            heading=title,
            body=message
        )
        
        # Add response using non-deprecated method
        dialog.add_response("ok", "OK")
        
        # Configure dialog properties
        dialog.props.default_response = "ok"
        dialog.props.close_response = "ok"

        def on_response(d, r):
            self.print_method_name()
            #d.close()
            if callback is not None:
                callback()

        dialog.connect("response", on_response)
        dialog.present(self.window)

    def reverse_process_reg_files(self, wineprefix):
        self.print_method_name()
        print(f"Processing .reg files in {wineprefix}")
        current_username = os.getenv("USER")
        if not current_username:
            print("No username found")
            return

        user_reg_path = os.path.join(wineprefix, "user.reg")
        if not os.path.exists(user_reg_path):
            print(f"No user.reg at {user_reg_path}")
            return

        with self.file_lock:  # Ensure thread safety
            with open(user_reg_path, 'r') as file:
                content = file.read()
            
            match = re.search(r'"USERNAME"="([^"]+)"', content, re.IGNORECASE)
            if not match:
                print("No USERNAME in user.reg")
                return
            wine_username = match.group(1)

            replacements = {
                f"\\\\users\\\\{current_username}": f"\\\\users\\\\%USERNAME%",
                f"\\\\home\\\\{current_username}": f"\\\\home\\\\%USERNAME%",
                f'"USERNAME"="{current_username}"': f'"USERNAME"="%USERNAME%"'
            }

            for root, dirs, files in os.walk(wineprefix):
                for file in files:
                    if file.endswith(".reg"):
                        file_path = os.path.join(root, file)
                        with open(file_path, 'r') as reg_file:
                            reg_content = reg_file.read()
                        modified = False
                        for old, new in replacements.items():
                            if old in reg_content:
                                reg_content = reg_content.replace(old, new)
                                modified = True
                        if modified:
                            with open(file_path, 'w') as reg_file:
                                reg_file.write(reg_content)
                                print(f"Updated {file_path}")
        print(f"Completed processing .reg files in {wineprefix}")


##### BACKUP PREFIX
    def show_backup_prefix_dialog(self, script, script_key, button):
        self.print_method_name()
        self.stop_processing = False
        wineprefix = Path(script).parent
        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = self.expand_and_resolve_path(str(script_data['exe_file']))
        #exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_path = exe_file.parent
        exe_name = exe_file.name
        game_dir = wineprefix / "drive_c" / "GAMEDIR"
        game_dir_exe = game_dir / exe_path.name / exe_name


        # Check if game directory is inside the prefix
        is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

        creation_date_and_time = datetime.now().strftime("%Y%m%d%H%M")
        # Step 1: Suggest the backup file name
        default_backup_name = f"{script.stem}-{creation_date_and_time}.prefix"
        

        # Create a Gtk.FileDialog instance for saving the file
        file_dialog = Gtk.FileDialog.new()

        # Set the initial file name using set_initial_name() method
        file_dialog.set_initial_name(default_backup_name)

        # Open the dialog asynchronously to select the save location
        file_dialog.save(self.window, None, self.on_backup_prefix_dialog_response, script, script_key)

        print("FileDialog presented for saving the backup.")

    def on_backup_prefix_dialog_response(self, dialog, result, script, script_key):
        self.print_method_name()
        try:
            # Retrieve the selected file (save location) using save_finish()
            backup_file = dialog.save_finish(result)
            if backup_file:
                self.on_back_button_clicked(None)
                self.flowbox.remove_all()
                backup_path = backup_file.get_path()  # Get the backup file path
                print(f"Backup will be saved to: {backup_path}")
                
                # Start the backup process in a separate thread
                threading.Thread(target=self.backup_prefix, args=(script, script_key,  backup_path)).start()

        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")

    def on_backup_prefix_completed(self, script_key, backup_path):
        self.print_method_name()
        """
        Called when the backup process is complete. Updates the UI safely.
        """
        try:
            GLib.idle_add(self._complete_backup_ui_update, script_key, backup_path)
        except Exception as e:
            print(f"Error scheduling backup completion UI update: {e}")
            self.show_info_dialog("Warning", "Backup completed but there was an error updating the UI")

    def _complete_backup_ui_update(self, script_key, backup_path):
        self.print_method_name()
        """
        Performs the actual UI updates on the main thread after backup completion
        """
        try:
            # First disconnect any existing handlers
            if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
                if hasattr(self, 'open_button'):
                    try:
                        self.open_button.disconnect(self.open_button_handler_id)
                    except:
                        pass
                    self.open_button_handler_id = None
            
            # Then reset the UI elements
            self.hide_processing_spinner()
            
            # Now reconnect the open button
            if hasattr(self, 'open_button'):
                self.open_button_handler_id = self.open_button.connect(
                    "clicked", 
                    self.on_open_button_clicked
                )
            
            # Update labels and icons
            self.set_open_button_label("Open")
            self.set_open_button_icon_visible(True)
            
            # Show completion dialog
            self.show_info_dialog("Backup Complete", f"Backup saved to {backup_path}")
            print("Backup process completed successfully.")

            # Update script options if available
            if hasattr(self, 'script_ui_data') and script_key in self.script_ui_data:
                self.show_options_for_script(
                    self.script_ui_data[script_key],
                    self.script_ui_data[script_key]['row'],
                    script_key
                )
            
            return False  # Required for GLib.idle_add
            
        except Exception as e:
            print(f"Error during backup completion UI update: {e}")
            self.show_info_dialog("Warning", "Backup completed but there was an error updating the UI")
            return False



    def backup_prefix(self, script, script_key, backup_path):
        self.print_method_name()
        """
        Backs up the Wine prefix in a stepwise manner, indicating progress via spinner and label updates.
        """
        # Store current script info for cancellation handling
        self.current_script = script
        self.current_script_key = script_key
        self.stop_processing = False
        self.current_backup_path = backup_path
        wineprefix = Path(script).parent

        try:
            # Step 1: Initialize the UI for backup process
            self.show_processing_spinner("Exporting...")
            self.connect_open_button_with_backup_cancel(script_key)

            # Get the user's home directory to replace with `~`
            usershome = os.path.expanduser('~')
            find_replace_pairs = {usershome: '~'}
            
            def perform_backup_steps():
                self.print_method_name()
                try:
                    steps = [
                        (f"Replace \"{usershome}\" with '~' in script files", 
                        lambda: self.replace_strings_in_files(wineprefix, find_replace_pairs)),
                        ("Reverting user-specific .reg changes", 
                        lambda: self.reverse_process_reg_files(wineprefix)),
                        ("Creating backup archive", 
                        lambda: self.create_backup_archive(wineprefix, backup_path)),
                        ("Re-applying user-specific .reg changes", 
                        lambda: self.process_reg_files(wineprefix))
                    ]
                    
                    self.total_steps = len(steps)
                    
                    for step_text, step_func in steps:
                        if self.stop_processing:
                            GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)
                            return

                        GLib.idle_add(self.show_initializing_step, step_text)
                        try:
                            step_func()
                            if self.stop_processing:
                                GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)
                                return
                            GLib.idle_add(self.mark_step_as_done, step_text)
                        except Exception as e:
                            print(f"Error during step '{step_text}': {e}")
                            if not self.stop_processing:
                                GLib.idle_add(self.show_info_dialog, "Backup Failed", 
                                            f"Error during '{step_text}': {str(e)}")
                            GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)
                            return

                    if not self.stop_processing:
                        GLib.idle_add(self.on_backup_prefix_completed, script_key, backup_path)
                        
                except Exception as e:
                    print(f"Backup process failed: {e}")
                    GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)

            # Run the backup steps in a separate thread
            self.processing_thread = threading.Thread(target=perform_backup_steps)
            self.processing_thread.start()

        except Exception as e:
            print(f"Error initializing backup process: {e}")
            self.cleanup_cancelled_backup(script, script_key)

    def create_backup_archive(self, wineprefix, backup_path):
        self.print_method_name()
        """
        Create a backup archive with interruption support
        """
        if self.stop_processing:
            raise Exception("Operation cancelled by user")

        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")

        tar_command = [
            'tar',
            '-I', 'zstd -T0',
            '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",
            '-cf', backup_path,
            '-C', str(wineprefix.parent),
            wineprefix.name
        ]

        print(f"Running backup command: {' '.join(tar_command)}")

        process = subprocess.Popen(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        while process.poll() is None:
            if self.stop_processing:
                process.terminate()
                try:
                    process.wait(timeout=2)
                    if Path(backup_path).exists():
                        Path(backup_path).unlink()
                except subprocess.TimeoutExpired:
                    process.kill()
                raise Exception("Operation cancelled by user")
            time.sleep(0.1)

        if process.returncode != 0 and not self.stop_processing:
            stderr = process.stderr.read().decode()
            raise Exception(f"Backup failed: {stderr}")

    def connect_open_button_with_backup_cancel(self, script_key):
        self.print_method_name()
        """
        Connect cancel handler to the open button for backup process
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_backup_clicked, script_key)
        
        self.set_open_button_icon_visible(False)

    def cleanup_cancelled_backup(self, script, script_key):
        self.print_method_name()
        """
        Clean up after backup is cancelled
        """
        try:
            # Clean up partial backup file if it exists
            if hasattr(self, 'current_backup_path') and Path(self.current_backup_path).exists():
                try:
                    Path(self.current_backup_path).unlink()
                    self.current_backup_path = None
                except Exception as e:
                    print(f"Error deleting partial backup file: {e}")
        except Exception as e:
            print(f"Error during backup cleanup: {e}")
        finally:
            try:
                # Reset UI state
                self.set_open_button_label("Open")
                self.set_open_button_icon_visible(True)
                self.hide_processing_spinner()
                
                if self.stop_processing:
                    self.show_info_dialog("Cancelled", "Backup was cancelled")
                
                # Safely update UI elements
                if hasattr(self, 'script_ui_data') and script_key in self.script_ui_data:
                    self.show_options_for_script(self.script_ui_data[script_key], 
                                            self.script_ui_data[script_key]['row'], 
                                            script_key)
            except Exception as e:
                print(f"Error during UI cleanup: {e}")
                self.show_info_dialog("Warning", "There was an error updating the UI")

    def on_cancel_backup_clicked(self, button, script_key):
        self.print_method_name()
        """
        Handle cancel button click during backup
        """
        dialog = Adw.AlertDialog(
            heading="Cancel Backup",
            body="Do you want to cancel the backup process?"
        )

        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Backup")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_backup_dialog_response, script_key)
        dialog.present(self.window)

    def on_cancel_backup_dialog_response(self, dialog, response, script_key):
        self.print_method_name()
        """
        Handle cancel dialog response for backup
        """
        if response == "cancel":
            self.stop_processing = True
        dialog.close()

##### /BACKUP PREFIX xx

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
            ("Install dxvk vkd3d", "emblem-system-symbolic", self.install_dxvk_vkd3d),
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
            ("Registry Editor (regedit)", "dialog-password-symbolic", self.wine_registry_editor)
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

    def populate_script_options(self, filter_text=""):
        self.print_method_name()
        """
        Populate the script options flowbox with filtered options.
        """
        # Clear existing options
        while child := self.script_options_flowbox.get_first_child():
            self.script_options_flowbox.remove(child)

        # Add filtered options
        filter_text = filter_text.lower()
        for label, icon_name, callback in self.script_options:
            if filter_text in label.lower():
                option_button = Gtk.Button()
                option_button.set_size_request(-1, 40)
                option_button.add_css_class("flat")
                option_button.add_css_class("normal-font")

                option_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                option_button.set_child(option_hbox)

                option_icon = Gtk.Image.new_from_icon_name(icon_name)
                option_label = Gtk.Label(label=label)
                option_label.set_xalign(0)
                option_label.set_hexpand(True)
                option_label.set_ellipsize(Pango.EllipsizeMode.END)
                option_hbox.append(option_icon)
                option_hbox.append(option_label)

                self.script_options_flowbox.append(option_button)

                # Handle the log button sensitivity
                if label == "Show log":
                    log_file_path = self.current_script.parent / f"{self.current_script.stem}.log"
                    if not log_file_path.exists() or log_file_path.stat().st_size == 0:
                        option_button.set_sensitive(False)

                # Connect the button callback
                option_button.connect(
                    "clicked",
                    lambda btn, cb=callback: self.callback_wrapper(cb, self.current_script, self.current_script_key, btn)
                )

######################### CREATE BOTTLE
    # Get directory size method
    def get_directory_size(self, path):
        self.print_method_name()
        if not path.exists():
            print(f"The provided path '{path}' does not exist.")
            return 0

        try:
            total_size = sum(f.stat().st_size for f in path.glob('**/*') if f.is_file())
            return total_size
        except Exception as e:
            print(f"Error calculating directory size: {e}")
            return 0

    def create_bottle(self, script, script_key, backup_path):
        self.print_method_name()
        """
        Backs up the Wine prefix in a stepwise manner, indicating progress via spinner and label updates.
        """
        # Store current script info for cancellation handling
        self.current_script = script
        self.current_script_key = script_key
        self.stop_processing = False
        self.current_backup_path = backup_path
        wineprefix = Path(script).parent

        self.hide_processing_spinner()

        # Step 1: Disconnect the UI elements and initialize the spinner
        self.show_processing_spinner("Bottling...")
        self.connect_open_button_with_bottling_cancel(script_key)

        # Get the user's home directory to replace with `~`
        usershome = os.path.expanduser('~')

        # Get the current username from the environment
        user = os.getenv("USER") or os.getenv("USERNAME")
        if not user:
            raise Exception("Unable to determine the current username from the environment.")
        
        find_replace_pairs = {usershome: '~', f'\'{usershome}': '\'~\''}
        find_replace_media_username = {f'/media/{user}/': '/media/%USERNAME%/'}
        restore_media_username = {'/media/%USERNAME%/': f'/media/{user}/'}

        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = self.expand_and_resolve_path(str(script_data['exe_file']))
        exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_path = exe_file.parent
        exe_name = exe_file.name

        runner = self.expand_and_resolve_path(str(script_data['runner']))

        # If runner is inside the script
        if runner:
            print(f"RUNNER FOUND = {runner}")
            # Check if the runner is inside runners_dir
            is_runner_inside_prefix = runner.is_relative_to(self.runners_dir)
            print("===========================================================")
            if is_runner_inside_prefix:
                print("RUNNER INSIDE PREFIX")
                runner_dir = runner.parent.parent
                runner_dir_exe = runner_dir / "bin/wine"

                target_runner_dir = wineprefix / "Runner" 
                target_runner_exe = target_runner_dir / runner_dir.name / "bin/wine"
            else:
                target_runner_exe = runner
                runner_dir_exe = runner
                print("RUNNER IS NOT INSIDE PREFIX")

        # Check if game directory is inside the prefix
        is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

        print("==========================================================")
        # exe_file path replacement should use existing exe_file if it's already inside prefix
        if is_exe_inside_prefix:
            game_dir = exe_path
            game_dir_exe = exe_file
            print(f"""
            exe_file is inside wineprefix:
            game_dir = {game_dir}
            game_dir_exe = {game_dir_exe}
            """)
        else:
            game_dir = wineprefix / "drive_c" / "GAMEDIR"
            game_dir_exe = game_dir / exe_path.name / exe_name
            print(f"""
            exe_file is OUTSIDE wineprefix:
            game_dir = {game_dir}
            game_dir_exe = {game_dir_exe}
            """)

        def perform_backup_steps():
            self.print_method_name()
            try:
                # Basic steps that are always needed
                basic_steps = [
                    (f"Replace \"{usershome}\" with '~' in files", lambda: self.replace_strings_in_files(wineprefix, find_replace_pairs)),
                    ("Reverting user-specific .reg changes", lambda: self.reverse_process_reg_files(wineprefix)),
                    (f"Replace \"/media/{user}\" with '/media/%USERNAME%' in files", lambda: self.replace_strings_in_files(wineprefix, find_replace_media_username)),
                    ("Updating exe_file Path in Script", lambda: self.update_exe_file_path_in_script(script, self.replace_home_with_tilde_in_path(str(game_dir_exe)))),
                    ("Creating Bottle archive", lambda: self.create_bottle_archive(script_key, wineprefix, backup_path)),
                    ("Re-applying user-specific .reg changes", lambda: self.process_reg_files(wineprefix)),
                    (f"Revert %USERNAME% with \"{user}\" in script files", lambda: self.replace_strings_in_files(wineprefix, restore_media_username)),
                    ("Reverting exe_file Path in Script", lambda: self.update_exe_file_path_in_script(script, self.replace_home_with_tilde_in_path(str(exe_file))))
                ]
                
                # Set total steps and initialize progress UI
                self.total_steps = len(basic_steps)

                # Add runner-related steps only if runner exists and is not empty
                steps = basic_steps.copy()
                if runner and str(runner).strip():
                    is_runner_inside_prefix = runner.is_relative_to(self.runners_dir)
                    if is_runner_inside_prefix:
                        runner_update_index = next(i for i, (text, _) in enumerate(steps) if text == "Creating Bottle archive")
                        steps.insert(runner_update_index, 
                            ("Updating runner Path in Script", lambda: self.update_runner_path_in_script(script, self.replace_home_with_tilde_in_path(str(target_runner_exe))))
                        )
                        steps.append(
                            ("Reverting runner Path in Script", lambda: self.update_runner_path_in_script(script, self.replace_home_with_tilde_in_path(str(runner))))
                        )

                for step_text, step_func in steps:
                    if self.stop_processing:
                        GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)
                        return

                    GLib.idle_add(self.show_initializing_step, step_text)
                    try:
                        step_func()
                        if self.stop_processing:
                            GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)
                            return
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        print(f"Error during step '{step_text}': {e}")
                        if not self.stop_processing:
                            GLib.idle_add(self.show_info_dialog, "Backup Failed", f"Error during '{step_text}': {str(e)}")
                        GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)
                        return

                if not self.stop_processing:
                    GLib.idle_add(self.on_create_bottle_completed, script_key, backup_path)
                
            except Exception as e:
                print(f"Backup process failed: {e}")
                GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)

        # Run the backup steps in a separate thread to keep the UI responsive
        self.processing_thread = threading.Thread(target=perform_backup_steps)
        self.processing_thread.start()

    def on_create_bottle_completed(self, script_key, backup_path):
        self.print_method_name()
        """
        Called when the bottle creation process is complete. Schedules UI updates safely.
        """
        try:
            GLib.idle_add(self._complete_bottle_creation_ui_update, script_key, backup_path)
        except Exception as e:
            print(f"Error scheduling bottle creation UI update: {e}")
            self.show_info_dialog("Warning", "Bottle created but there was an error updating the UI")

    def _complete_bottle_creation_ui_update(self, script_key, backup_path):
        self.print_method_name()
        """
        Performs the actual UI updates on the main thread after bottle creation completion
        """
        try:
            # First disconnect any existing handlers
            if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
                if hasattr(self, 'open_button'):
                    try:
                        self.open_button.disconnect(self.open_button_handler_id)
                    except:
                        pass
                    self.open_button_handler_id = None
            
            # Reset the UI elements
            self.hide_processing_spinner()
            
            # Reconnect the open button
            if hasattr(self, 'open_button'):
                self.open_button_handler_id = self.open_button.connect(
                    "clicked", 
                    self.on_open_button_clicked
                )
            
            # Update labels and icons
            self.set_open_button_label("Open")
            self.set_open_button_icon_visible(True)
            
            # Show completion dialog
            self.show_info_dialog("Bottle Created", f"{backup_path}")
            print("Bottle creating process completed successfully.")

            # Safely update UI elements
            if hasattr(self, 'script_ui_data') and script_key in self.script_ui_data:
                self.show_options_for_script(self.script_ui_data[script_key], 
                                        self.script_ui_data[script_key]['row'], 
                                        script_key)

            return False  # Required for GLib.idle_add
            
        except Exception as e:
            print(f"Error during bottle creation UI update: {e}")
            self.show_info_dialog("Warning", "Bottle created but there was an error updating the UI")
            return False


    def on_backup_confirmation_response(self, dialog, response_id, script, script_key):
        self.print_method_name()
        if response_id == "continue":
            dialog.close()
            self.show_create_bottle_dialog(script, script_key)
        else:
            return

    def create_bottle_selected(self, script, script_key, button):
        self.print_method_name()
        self.stop_processing = False
        # Step 1: Check if the executable file exists
        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        wineprefix = Path(script).parent
        exe_file = self.expand_and_resolve_path(script_data['exe_file'])
        #exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_path = exe_file.parent
        exe_name = exe_file.name
        game_dir = wineprefix / "drive_c" / "GAMEDIR"
        game_dir_exe = game_dir / exe_path.name / exe_name

        # Check if the game directory is in DO_NOT_BUNDLE_FROM directories
        if str(exe_path) in self.get_do_not_bundle_directories():
            msg1 = "Cannot copy the selected game directory"
            msg2 = "Please move the files to a different directory to create a bundle."
            self.show_info_dialog(msg1, msg2)
            return

        # If exe_not found i.e., game_dir is not accessble due to unmounted directory
        if not exe_file.exists():
            GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Exe Not Found", f"Not Mounted or Deleted?\n{exe_file}")
            return

        # Step 2: Check for size if > 3GB ask the user:
        # Calculate the directory size in bytes
        directory_size = self.get_directory_size(exe_path)

        # Convert directory size to GB for comparison
        directory_size_gb = directory_size / (1024 ** 3)  # 1 GB is 1024^3 bytes
        directory_size_gb = round(directory_size_gb, 2)  # round to two decimal places

        print("----------------------------------------------------------")
        print(directory_size)
        print(directory_size_gb)

        if directory_size_gb > 3:
            print("Size Greater than 3GB")
            # Show confirmation dialog
            dialog = Adw.AlertDialog(
                heading="Large Game Directory",
                body=f"The game directory size is {directory_size_gb}GB. Do you want to continue?"
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("continue", "Continue")
            dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
            dialog.connect("response", self.on_backup_confirmation_response, script, script_key)
            dialog.present(self.window)
            print("----------------------------------------------------------")
        else:
            self.show_create_bottle_dialog(script, script_key)

    def show_create_bottle_dialog(self, script, script_key):
        self.print_method_name()

        creation_date_and_time = datetime.now().strftime("%Y%m%d%H%M")
        # Suggest the backup file name
        default_backup_name = f"{script.stem}-{creation_date_and_time}.bottle"

        # Create a Gtk.FileDialog instance for saving the file
        file_dialog = Gtk.FileDialog.new()

        # Set the initial file name using set_initial_name() method
        file_dialog.set_initial_name(default_backup_name)

        # Open the dialog asynchronously to select the save location
        file_dialog.save(self.window, None, self.on_create_bottle_dialog_response, script, script_key)

        print("FileDialog presented for saving the backup.")

    def on_create_bottle_dialog_response(self, dialog, result, script, script_key):
        self.print_method_name()
        try:
            # Retrieve the selected file (save location) using save_finish()
            backup_file = dialog.save_finish(result)
            if backup_file:
                self.on_back_button_clicked(None)
                self.flowbox.remove_all()
                backup_path = backup_file.get_path()  # Get the backup file path
                print(f"Backup will be saved to: {backup_path}")

                # Start the backup process in a separate thread
                threading.Thread(target=self.create_bottle, args=(script, script_key, backup_path)).start()

        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")

    def create_bottle_archive(self, script_key, wineprefix, backup_path):
        self.print_method_name()
        """
        Create a bottle archive with interruption support
        """

        if self.stop_processing:
            raise Exception("Operation cancelled by user")

        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")

        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = Path(str(script_data['exe_file'])).expanduser().resolve()
        exe_file = Path(str(exe_file).replace("%USERNAME%", current_username))
        exe_path = exe_file.parent
        tar_game_dir_name = exe_path.name
        tar_game_dir_path = exe_path.parent

        runner = self.expand_and_resolve_path(script_data['runner'])

        # Build tar command with transforms
        tar_command = [
            'tar',
            '-I', 'zstd -T0',
            '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",
        ]

        is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)
        if not is_exe_inside_prefix:
            tar_command.extend([
                '--transform', rf"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g"
            ])

        sources = []
        sources.append(('-C', str(wineprefix.parent), wineprefix.name))

        if runner and runner.is_relative_to(self.runners_dir):
            runner_dir = runner.parent.parent
            runner_dir_name = runner_dir.name
            runner_dir_path = runner_dir.parent
            tar_command.extend([
                '--transform', rf"s|^\./{runner_dir_name}|{wineprefix.name}/Runner/{runner_dir_name}|g"
            ])
            sources.append(('-C', str(runner_dir_path), rf"./{runner_dir_name}"))

        if not is_exe_inside_prefix:
            sources.append(('-C', str(tar_game_dir_path), rf"./{tar_game_dir_name}"))

        tar_command.extend(['-cf', backup_path])

        for source in sources:
            tar_command.extend(source)

        print(f"Running create bottle command: {' '.join(tar_command)}")

        process = subprocess.Popen(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        while process.poll() is None:
            if self.stop_processing:
                process.terminate()
                try:
                    process.wait(timeout=2)
                    if Path(backup_path).exists():
                        Path(backup_path).unlink()
                except subprocess.TimeoutExpired:
                    process.kill()
                raise Exception("Operation cancelled by user")
            time.sleep(0.1)

        if process.returncode != 0 and not self.stop_processing:
            stderr = process.stderr.read().decode()
            raise Exception(f"Backup failed: {stderr}")

        # Get the current username from the environment
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")

        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = Path(str(script_data['exe_file'])).expanduser().resolve()
        exe_file = Path(str(exe_file).replace("%USERNAME%", current_username))
        exe_path = exe_file.parent

        # Check if game directory is inside the prefix
        is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

        tar_game_dir_name = exe_path.name
        tar_game_dir_path = exe_path.parent

        runner = self.expand_and_resolve_path(script_data['runner'])

        # Start building the tar command with common options
        tar_command = [
            'tar',
            '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
            '--transform', rf"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",
        ]

        # If game is not in prefix, add game directory transform
        if not is_exe_inside_prefix:
            tar_command.extend([
                '--transform', rf"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g"
            ])

        # Initialize the list of source directories and their base paths
        sources = []
        
        # Always add the wineprefix
        sources.append(('-C', str(wineprefix.parent), wineprefix.name))

        # If runner exists and is inside runners_dir
        if runner and runner.is_relative_to(self.runners_dir):
            runner_dir = runner.parent.parent
            runner_dir_name = runner_dir.name
            runner_dir_path = runner_dir.parent
            tar_command.extend([
                '--transform', rf"s|^\./{runner_dir_name}|{wineprefix.name}/Runner/{runner_dir_name}|g"
            ])
            sources.append(('-C', str(runner_dir_path), rf"./{runner_dir_name}"))


        # If game is not in prefix, add it as a source
        if not is_exe_inside_prefix:
            sources.append(('-C', str(tar_game_dir_path), rf"./{tar_game_dir_name}"))

        # Add the output file path
        tar_command.extend(['-cf', backup_path])

        # Add all sources to the command
        for source in sources:
            tar_command.extend(source)

        print(f"Running create bottle command: {' '.join(tar_command)}")

        # Execute the tar command
        result = subprocess.run(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            raise Exception(f"Backup failed: {result.stderr}")

        print(f"Backup archive created at {backup_path}")

    def connect_open_button_with_bottling_cancel(self, script_key):
        self.print_method_name()
        """
        Connect cancel handler to the open button
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_bottle_clicked, script_key)
        
        self.set_open_button_icon_visible(False)

    def cleanup_cancelled_bottle(self, script, script_key):
        self.print_method_name()
        """
        Clean up after bottle creation is cancelled
        """
        try:
            if Path(script).exists():
                script_data = self.extract_yaml_info(script_key)
                if script_data:
                    # Revert exe_file path
                    if 'exe_file' in script_data:
                        original_exe = script_data['exe_file']
                        self.update_exe_file_path_in_script(script, original_exe)
                    
                    # Revert runner path if it exists
                    if 'runner' in script_data and script_data['runner']:
                        original_runner = script_data['runner']
                        self.update_runner_path_in_script(script, original_runner)

        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            #self.reconnect_open_button()
            self.hide_processing_spinner()
            if self.stop_processing:
                self.show_info_dialog("Cancelled", "Bottle creation was cancelled")
            # Iterate over all script buttons and update the UI based on `is_clicked_row`
                for key, data in self.script_ui_data.items():
                    row_button = data['row']
                    row_play_button = data['play_button']
                    row_options_button = data['options_button']
                self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)
                # Delete partial backup file if it exists
                if hasattr(self, 'current_backup_path') and Path(self.current_backup_path).exists():
                    try:
                        Path(self.current_backup_path).unlink()
                        self.current_backup_path = None
                    except Exception as e:
                        print(f"Error deleting partial backup file: {e}")

    def on_cancel_bottle_clicked(self, button, script_key):
        self.print_method_name()
        """
        Handle cancel button click
        """
        dialog = Adw.AlertDialog(
            heading="Cancel Bottle Creation",
            body="Do you want to cancel the bottle creation process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Creation")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_bottle_dialog_response, script_key)
        dialog.present(self.window)


    def on_cancel_bottle_dialog_response(self, dialog, response, script_key):
        self.print_method_name()
        """
        Handle cancel dialog response
        """
        if response == "cancel":
            self.stop_processing = True
            dialog.close()
            #GLib.timeout_add_seconds(0.5, dialog.close)
#            self.set_open_button_label("Open")
#            self.set_open_button_icon_visible(True)
#            self.reconnect_open_button()
#            self.hide_processing_spinner()


#            # Iterate over all script buttons and update the UI based on `is_clicked_row`
#            for key, data in self.script_ui_data.items():
#                row_button = data['row']
#                row_play_button = data['play_button']
#                row_options_button = data['options_button']
#            self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)
        else:
            self.stop_processing = False
            dialog.close()
            #GLib.timeout_add_seconds(0.5, dialog.close)

###################################### / CREATE BOTTLE  end



    def show_log_file(self, script, script_key, *args):
        self.print_method_name()
        log_file_path = Path(script.parent) / f"{script.stem}.log"
        if log_file_path.exists() and log_file_path.stat().st_size > 0:
            try:
                subprocess.run(["xdg-open", str(log_file_path)], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error opening log file: {e}")


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


    def install_dxvk_vkd3d(self, script, button):
        self.print_method_name()
        wineprefix = Path(script).parent
        self.run_winetricks_script("vkd3d dxvk", wineprefix)
        self.create_script_list()

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

########################################  delete wineprefix
    def load_icon(self, script, x, y, radius=3):
        if not hasattr(self, 'icon_cache'):
            self.icon_cache = {}
        
        cache_key = (str(script), x, y)
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]

        icon_name = script.stem + ".png"
        icon_path = script.parent / icon_name
        default_icon_path = self.get_default_icon_path()

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon_path), 128, 128)
        except Exception:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(default_icon_path), 128, 128)
            except Exception:
                pixbuf = None

        if pixbuf:
            scaled_pixbuf = pixbuf.scale_simple(x, y, GdkPixbuf.InterpType.BILINEAR)
            
            # Create a new surface and context for the rounded corners
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, x, y)
            context = cairo.Context(surface)
            
            # Draw rounded rectangle
            radius = radius  # Corner radius
            context.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
            context.arc(x - radius, radius, radius, 3 * math.pi / 2, 0)
            context.arc(x - radius, y - radius, radius, 0, math.pi / 2)
            context.arc(radius, y - radius, radius, math.pi / 2, math.pi)
            context.close_path()
            
            # Create pattern from pixbuf and set as source
            Gdk.cairo_set_source_pixbuf(context, scaled_pixbuf, 0, 0)
            context.clip()
            context.paint()
            
            # Get the surface data as bytes
            surface_bytes = surface.get_data()
            
            # Create GBytes from the surface data
            gbytes = GLib.Bytes.new(surface_bytes)
            
            # Create texture from the bytes
            texture = Gdk.MemoryTexture.new(
                x, y,
                Gdk.MemoryFormat.B8G8R8A8,
                gbytes,
                surface.get_stride()
            )
        else:
            texture = None

        self.icon_cache[cache_key] = texture
        return texture


    def create_icon_title_widget(self, script):
        self.print_method_name()
        # Find the matching script data from self.script_list
        script_data = next((data for key, data in self.script_list.items() if Path(data['script_path']) == script), None)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        # Load the icon associated with the script
        icon = self.load_icon(script, 24, 24)
        if icon:
            icon_image = Gtk.Image.new_from_paintable(icon)
            icon_image.set_pixel_size(24)
            hbox.append(icon_image)

        # Use the progname from script_data if available, otherwise fallback to script stem
        if script_data and 'progname' in script_data:
            label_text = f"<b>{script_data['progname'].replace('_', ' ')}</b>"
        else:
            label_text = f"<b>{script.stem.replace('_', ' ')}</b>"

        # Create and append the label
        label = Gtk.Label(label=label_text)
        label.set_use_markup(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        hbox.append(label)

        return hbox
            
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

######################################## / delete wineprefix

    def get_script_keys_from_wineprefix(self, wineprefix):
        self.print_method_name()
        """
        Retrieve the list of script_keys for a given Wine prefix.
        
        Args:
            wineprefix: The path to the Wine prefix.
            
        Returns:
            A list of script_keys corresponding to the given wineprefix.
        """
        script_keys = []
        for script_key, script_data in list(self.script_list.items()):
            script_path = Path(str(script_data['script_path'])).expanduser().resolve()
            if script_path.parent == wineprefix:
                script_keys.append(script_key)
        return script_keys


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
        file_filter.add_pattern("*.exe")
        file_filter.add_pattern("*.msi")
        file_filter.add_pattern("*.jpg")
        file_filter.add_pattern("*.jpeg")
        
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

    def process_file(self, file_path):
        self.print_method_name()
        print("""
         = = = = = = > process - file < = = = = = =  
        """)
        try:
            print("process_file")
            abs_file_path = str(Path(file_path).resolve())
            print(f"Resolved absolute file path: {abs_file_path}")  # Debugging output

            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return

            self.create_yaml_file(abs_file_path, None)
        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            print("hide_processing_spinner")
            GLib.idle_add(self.hide_processing_spinner)
            GLib.timeout_add_seconds(0.5, self.create_script_list)

    def on_confirm_action(self, button, script, action_type, parent, original_button):
        self.print_method_name()
        try:
            if action_type == "wineprefix":
                # Delete the wineprefix directory
                wineprefix = Path(script).parent
                if wineprefix.exists() and wineprefix.is_dir():
                    shutil.rmtree(wineprefix)
                    print(f"Deleted wineprefix: {wineprefix}")
                    
            elif action_type == "shortcut":
                # Delete the shortcut file
                shortcut_file = script
                if shortcut_file.exists() and shortcut_file.is_file():
                    os.remove(shortcut_file)
                    print(f"Deleted shortcut: {shortcut_file}")
                    
        except Exception as e:
            print(f"Error during deletion: {e}")
        finally:
            # Restore the original button
            parent.set_child(original_button)
            original_button.set_sensitive(True)

            # Go back to the previous view
            self.on_back_button_clicked(None)

    def on_cancel_button_clicked(self, button, parent, original_button):
        self.print_method_name()
        # Restore the original button as the child of the FlowBoxChild
        parent.set_child(original_button)
        original_button.set_sensitive(True)

    def run_command(self, command):
        self.print_method_name()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e.stderr}")
            return None
    
    def find_exe_path(self, wineprefix, exe_name):
        self.print_method_name()
        drive_c = Path(wineprefix) / "drive_c"
        for root, dirs, files in os.walk(drive_c):
            for file in files:
                if file.lower() == exe_name.lower():
                    return Path(root) / file
        return None

    def get_product_name(self, exe_file):
        self.print_method_name()
        product_cmd = [
            'exiftool', shlex.quote(str(exe_file))
        ]

        product_output = self.run_command(" ".join(product_cmd))
        if product_output is None:
            print(f"Error: Failed to retrieve product name for {exe_file}")
            return None
        else:
            productname_match = re.search(r'Product Name\s+:\s+(.+)', product_output)
            return productname_match.group(1).strip() if productname_match else None

    def copy_template(self, dest_dir, source_template=None):
        self.print_method_name()
        if source_template is None:
            source_template = self.template
        source_template = Path(source_template)
        dest_dir = Path(dest_dir)
        
        if source_template.exists():
            #shutil.copytree(source_template, dest_dir, symlinks=True, dirs_exist_ok=True)
            self.custom_copytree(source_template, dest_dir)
            print(f"Copied template {source_template} to {dest_dir}")
        else:
            print(f"Template {source_template} does not exist. Creating empty prefix.")
            self.ensure_directory_exists(dest_dir)

    def create_desktop_entry(self, progname, script_path, icon_path, wineprefix, category = "Game"):
        self.print_method_name()
#        return; # do not create
        # Create desktop shortcut based on flatpak sandbox or system
        if shutil.which("flatpak-spawn"):
            exec_command = f"flatpak run io.github.fastrizwaan.WineCharm '{script_path}'"
        else: #system
            exec_command = f'winecharm "{script_path}"'
            
        desktop_file_content = (
            f"[Desktop Entry]\n"
            f"Name={progname}\n"
            f"Type=Application\n"
            f"Exec={exec_command}\n"
            f"Icon={icon_path if icon_path else 'wine'}\n"
            f"Keywords=winecharm;game;{progname};\n"
            f"NoDisplay=false\n"
            f"StartupNotify=true\n"
            f"Terminal=false\n"
            f"Categories={category};\n"
        )
        desktop_file_path = script_path.with_suffix(".desktop")
        
        try:
            # Write the desktop entry to the specified path
            with open(desktop_file_path, "w") as desktop_file:
                desktop_file.write(desktop_file_content)

            # Create a symlink to the desktop entry in the applications directory
            symlink_path = self.applicationsdir / f"winecharm_{progname}.desktop"
            
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            symlink_path.symlink_to(desktop_file_path)

            # Create a symlink to the icon in the icons directory if it exists
            if icon_path:
                icon_symlink_path = self.iconsdir / f"{icon_path.name}"
                if icon_symlink_path.exists() or icon_symlink_path.is_symlink():
                    icon_symlink_path.unlink(missing_ok=True)
                icon_symlink_path.symlink_to(icon_path)

            print(f"Desktop entry created: {desktop_file_path}")
        except Exception as e:
            print(f"Error creating desktop entry: {e}")

    def start_socket_server(self):
        self.print_method_name()
        def server_thread():
            self.print_method_name()
            socket_dir = self.SOCKET_FILE.parent

            # Ensure the directory for the socket file exists
            self.create_required_directories()

            # Remove existing socket file if it exists
            if self.SOCKET_FILE.exists():
                self.SOCKET_FILE.unlink()

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(self.SOCKET_FILE))
                server.listen()

                while True:
                    conn, _ = server.accept()
                    with conn:
                        message = conn.recv(1024).decode()
                        if message:
                            command_parts = message.split("||")
                            command = command_parts[0]

                            if command == "show_dialog":
                                title = command_parts[1]
                                body = command_parts[2]
                                # Call show_info_dialog in the main thread using GLib.idle_add
                                GLib.timeout_add_seconds(0.5, self.show_info_dialog, title, body)
                            elif command == "process_file":
                                file_path = command_parts[1]
                                GLib.idle_add(self.process_cli_file_later, file_path)

        # Run the server in a separate thread
        threading.Thread(target=server_thread, daemon=True).start()

    def process_cli_file(self, file_path):
        print(f"Processing CLI file: {file_path}")
        abs_file_path = str(Path(file_path).resolve())
        print(f"Resolved absolute CLI file path: {abs_file_path}")

        try:
            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return
            self.create_yaml_file(abs_file_path, None)

        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            if self.initializing_template:
                pass  # Keep showing spinner
            else:
                GLib.timeout_add_seconds(1, self.hide_processing_spinner)
                
            GLib.timeout_add_seconds(0.5, self.create_script_list)

    def initialize_app(self):
        
        if not hasattr(self, 'window') or not self.window:
            # Call the startup code
            self.create_main_window()
            self.create_script_list()

        self.set_dynamic_variables()


    def show_processing_spinner(self, label_text):
        self.print_method_name()

        # Clear existing content
        self.flowbox.remove_all()

        if hasattr(self, 'progress_bar'):
            self.vbox.remove(self.progress_bar)
            del self.progress_bar

        # Ensure main flowbox is visible
        self.main_frame.set_child(self.scrolled)
        
        # Add progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("header-progress")
        self.progress_bar.set_show_text(False)
        self.progress_bar.set_margin_top(0)
        self.progress_bar.set_margin_bottom(0)
        self.progress_bar.set_fraction(0.0)
        #self.progress_bar.set_size_request(420, -1)
        self.vbox.prepend(self.progress_bar)
        self.flowbox.remove_all()
        
        # Update button label
        self.set_open_button_label(label_text)
        
        # Initialize steps
        self.step_boxes = []
        
        # Disable UI elements
        self.search_button.set_sensitive(False)
        self.view_toggle_button.set_sensitive(False)
        self.menu_button.set_sensitive(False)

    def hide_processing_spinner(self):
        self.print_method_name()
        """Restore UI state after process completion with safe widget removal"""
        try:
            if hasattr(self, 'progress_bar'):
                self.vbox.remove(self.progress_bar)
                del self.progress_bar

            # Update button back to original state
            self.set_open_button_label("Open")
                
            # Safely re-enable UI elements
            if hasattr(self, 'search_button'):
                self.search_button.set_sensitive(True)
            if hasattr(self, 'view_toggle_button'):
                self.view_toggle_button.set_sensitive(True)
            if hasattr(self, 'menu_button'):    
                self.menu_button.set_sensitive(True)

            # Clear step tracking safely
            if hasattr(self, 'step_boxes'):
                self.step_boxes = []
                
        except Exception as e:
            print(f"Error in hide_processing_spinner: {e}")

    def on_open(self, app, files, *args):
        # Ensure the application is fully initialized
        #print("1. on_open method called")
        
        # Initialize the application if it hasn't been already
        self.initialize_app()
        #print("2. self.initialize_app initiated")
        
        # Present the window as soon as possible
        GLib.idle_add(self.window.present)
        #print("3. self.window.present() Complete")

        #self.check_running_processes_and_update_buttons()
        if not self.template:
            self.template = getattr(self, f'default_template_{self.arch}')
            #print("77777777777777777777777777777777777777777777777777777777777777777")
            #print(self.template)
            self.template = self.expand_and_resolve_path(self.template)
            #print(self.template)

        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)

        self.check_running_processes_on_startup()


    def on_view_toggle_button_clicked(self, button):
        self.print_method_name()
        # Toggle the icon view state
        self.icon_view = not self.icon_view

        # Update the icon for the toggle button based on the current view state
        icon_name = "view-grid-symbolic" if self.icon_view else "view-list-symbolic"
        button.set_child(Gtk.Image.new_from_icon_name(icon_name))

        # Update the maximum children per line in the flowbox based on the current view state
        max_children_per_line = 8 if self.icon_view else 4
        self.flowbox.set_max_children_per_line(max_children_per_line)
        # Recreate the script list with the new view
        self.create_script_list()
        GLib.idle_add(self.save_settings)

############# IMPORT Wine Directory
    def rename_and_merge_user_directories(self, wineprefix):
        self.print_method_name()
        # Get the current username from the environment
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")
        
        # Define the path to the "drive_c/users/" directory within the wineprefix
        users_dir = Path(wineprefix) / 'drive_c' / 'users'
        
        if not users_dir.exists() or not users_dir.is_dir():
            raise Exception(f"The directory '{users_dir}' does not exist or is not a directory.")

        # Iterate over all directories in "drive_c/users/"
        for user_dir in users_dir.iterdir():
            if user_dir.is_dir() and user_dir.name not in ['Public', 'steamuser', current_username]:
                # This is a directory that belongs to a different user and needs to be renamed/merged
                
                current_user_dir = users_dir / current_username

                if not current_user_dir.exists():
                    # If the current user's directory does not exist, simply rename the directory
                    shutil.move(str(user_dir), str(current_user_dir))
                    print(f"Renamed directory {user_dir} to {current_user_dir}")
                else:
                    # If the current user's directory exists, merge the contents
                    print(f"Merging contents of {user_dir} into {current_user_dir}")

                    for item in user_dir.iterdir():
                        target_path = current_user_dir / item.name
                        
                        if target_path.exists():
                            if target_path.is_dir() and item.is_dir():
                                # Recursively merge directories
                                self.merge_directories(item, target_path)
                            elif target_path.is_file() and item.is_file():
                                # Handle file conflicts by renaming
                                new_name = target_path.with_suffix(target_path.suffix + ".old")
                                shutil.move(str(target_path), new_name)
                                shutil.move(str(item), target_path)
                        else:
                            # If the target path does not exist, simply move the item
                            shutil.move(str(item), target_path)
                    
                    # Remove the old directory after merging
                    user_dir.rmdir()
                    print(f"Merged and removed directory: {user_dir}")

    def merge_directories(self, source_dir, target_dir):
        self.print_method_name()
        """
        Recursively merge contents of source_dir into target_dir.
        """
        for item in source_dir.iterdir():
            target_path = target_dir / item.name

            if target_path.exists():
                if target_path.is_dir() and item.is_dir():
                    # Recursively merge sub-directories
                    self.merge_directories(item, target_path)
                elif target_path.is_file() and item.is_file():
                    # Handle file conflicts by renaming existing files
                    new_name = target_path.with_suffix(target_path.suffix + ".old")
                    shutil.move(str(target_path), new_name)
                    shutil.move(str(item), target_path)
            else:
                # If the target path does not exist, simply move the item
                shutil.move(str(item), target_path)

        # Remove the source directory after merging its contents
        source_dir.rmdir()

    def on_import_wine_directory_clicked(self, action, param):
        self.print_method_name()
        # Create a new Gtk.FileDialog for selecting a directory
        file_dialog = Gtk.FileDialog.new()

        # Set the action to select a folder (in GTK 4, it's done by default via FileDialog)
        file_dialog.set_modal(True)

        # Open the dialog to select a folder (async operation)
        file_dialog.select_folder(self.window, None, self.on_import_directory_response)

        print("FileDialog presented for importing Wine directory.")

    def on_import_directory_response(self, dialog, result):
        self.print_method_name()
        try:
            # Retrieve the selected directory using select_folder_finish() in GTK 4
            folder = dialog.select_folder_finish(result)
            if folder:
                directory = folder.get_path()  # Get the directory path
                print(f"Selected directory: {directory}")

                # Check if it's a valid Wine directory by verifying the existence of "system.reg"
                if directory and (Path(directory) / "system.reg").exists():
                    print(f"Valid Wine directory selected: {directory}")

                    self.show_processing_spinner(f"Importing {Path(directory).name}")

                    # Destination directory
                    dest_dir = self.prefixes_dir / Path(directory).name

                    # Check if destination directory already exists
                    if dest_dir.exists():
                        print(f"Destination directory already exists: {dest_dir}")
                        # Show confirmation dialog for overwriting
                        GLib.idle_add(self.show_import_wine_directory_overwrite_confirmation_dialog, directory, dest_dir)
                    else:
                        # Proceed with copying if the directory doesn't exist
                        threading.Thread(target=self.import_wine_directory, args=(directory, dest_dir)).start()
                else:
                    print(f"Invalid directory selected: {directory}")
                    GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Invalid Directory", "The selected directory does not appear to be a valid Wine directory.")

        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")

        print("FileDialog operation complete.")

    def import_wine_directory(self, src, dst):
        self.print_method_name()
        """
        Import the Wine directory with improved safety, rollback capability, and cancellation support.
        """
        self.stop_processing = False
        backup_dir = dst.parent / f"{dst.name}_backup_{int(time.time())}"
        
        # Clear the flowbox and initialize progress UI
        GLib.idle_add(self.flowbox.remove_all)
        
        steps = [
            ("Backing up existing directory", lambda: self.backup_existing_directory(dst, backup_dir)),
            ("Copying Wine directory", lambda: self.custom_copytree(src, dst)),
            ("Processing registry files", lambda: self.process_reg_files(dst)),
            ("Performing Replacements", lambda: self.perform_replacements(dst)),
            ("Renaming and Merging User Directories", lambda: self.rename_and_merge_user_directories(dst)),
            ("Creating scripts for .exe files", lambda: self.create_scripts_for_exe_files(dst)),
            ("Replace symbolic links with directories", lambda: self.remove_symlinks_and_create_directories(dst)),
            ("Create Wineboot Required file", lambda: self.create_wineboot_required_file(dst)),
        ]
        
        self.total_steps = len(steps)
        self.show_processing_spinner("Importing Wine Directory...")
        self.connect_open_button_with_import_wine_directory_cancel()

        def perform_import_steps():
            self.print_method_name()
            try:
                for index, (step_text, step_func) in enumerate(steps, 1):
                    if self.stop_processing:
                        GLib.idle_add(lambda: self.handle_import_cancellation(dst, backup_dir))
                        return
                        
                    GLib.idle_add(self.show_initializing_step, step_text)
                    try:
                        step_func()
                        GLib.idle_add(self.mark_step_as_done, step_text)
                        GLib.idle_add(lambda: self.progress_bar.set_fraction(index / self.total_steps))
                    except Exception as step_error:
                        if "Operation cancelled by user" in str(step_error):
                            GLib.idle_add(lambda: self.handle_import_cancellation(dst, backup_dir))
                        else:
                            print(f"Error during step '{step_text}': {step_error}")
                            GLib.idle_add(
                                lambda error=step_error, text=step_text: self.handle_import_error(
                                    dst, 
                                    backup_dir, 
                                    f"An error occurred during '{text}': {error}"
                                )
                            )
                        return

                if not self.stop_processing:
                    self.cleanup_backup(backup_dir)
                    GLib.idle_add(self.on_import_wine_directory_completed)
                    
            except Exception as import_error:
                print(f"Error during import process: {import_error}")
                GLib.idle_add(
                    lambda error=import_error: self.handle_import_error(
                        dst, 
                        backup_dir, 
                        f"Import failed: {error}"
                    )
                )

        threading.Thread(target=perform_import_steps).start()

    def on_import_wine_directory_completed(self):
        self.print_method_name()
        """
        Called when the import process is complete. Updates UI, restores scripts, and resets the open button.
        """
        # Reconnect open button and reset its label
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        
        self.hide_processing_spinner()

        # This will disconnect open_button handler, use this then reconnect the open
        #if self.open_button_handler_id is not None:
        #    self.open_button.disconnect(self.open_button_handler_id)

        self.reconnect_open_button()
        self.load_script_list()
        # Restore the script list in the flowbox
        GLib.idle_add(self.create_script_list)

        print("Wine directory import completed and script list restored.")

    def copy_wine_directory(self, src, dst):
        self.print_method_name()
        try:
            self.custom_copytree(src, dst)
            print(f"Successfully copied Wine directory to {dst}")
            
            self.process_reg_files(dst)
            
            print(f"Creating scripts for .lnk files in {dst}")
            self.create_scripts_for_lnk_files(dst)
            print(f"Scripts created for .lnk files in {dst}")
            
            print(f"Creating scripts for .exe files in {dst}")
            self.create_scripts_for_exe_files(dst)
            print(f"Scripts created for .exe files in {dst}")

            GLib.idle_add(self.create_script_list)
        finally:
            GLib.idle_add(self.enable_open_button)
            GLib.idle_add(self.hide_processing_spinner)
            print("Completed importing Wine directory process.")

    def show_import_wine_directory_overwrite_confirmation_dialog(self, src, dest_dir):
        self.print_method_name()
        """
        Show a confirmation dialog asking the user whether to overwrite the existing directory.
        """
        dialog = Adw.AlertDialog(
            title="Overwrite Existing Directory?",
            body=f"The directory {dest_dir.name} already exists. Do you want to overwrite it?"
        )

        # Add overwrite and cancel buttons
        dialog.add_response("overwrite", "Overwrite")
        dialog.set_response_appearance("overwrite", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")

        # Connect the dialog response to the overwrite handler
        dialog.connect("response", self.on_import_wine_directory_overwrite_response, src, dest_dir)

        # Show the dialog
        dialog.present(self.window)


    def on_import_wine_directory_overwrite_response(self, dialog, response_id, src, dest_dir):
        self.print_method_name()
        """
        Handle the response from the overwrite confirmation dialog.
        """
        if response_id == "overwrite":
            print(f"User chose to overwrite the directory: {dest_dir}")
            
            # Clear the flowbox now because the user chose to overwrite
            GLib.idle_add(self.flowbox.remove_all)
            
            # Delete the existing directory and start the import process
            try:
                #shutil.rmtree(dest_dir)  # Remove the directory
                #print(f"Deleted existing directory: {dest_dir}")
                # Start the import process after deletion
                threading.Thread(target=self.import_wine_directory, args=(src, dest_dir)).start()
            except Exception as e:
                print(f"Error deleting directory: {e}")
                GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Error", f"Could not delete directory: {e}")
        else:
            print("User canceled the overwrite.")
            # If canceled, restore the UI to its original state
            self.reconnect_open_button()
            self.hide_processing_spinner()
            GLib.idle_add(self.create_script_list)
            # No need to restore the script list as it wasn't cleared

    def on_cancel_import_wine_direcotory_dialog_response(self, dialog, response):
        self.print_method_name()
        """
        Handle cancel dialog response
        """
        if response == "cancel":
            self.stop_processing = True
            dialog.close()
        else:
            self.stop_processing = False
            dialog.close()
            #GLib.timeout_add_seconds(0.5, dialog.close)

    def on_cancel_import_wine_directory_clicked(self, button):
        self.print_method_name()
        """
        Handle cancel button click
        """
        dialog = Adw.AlertDialog(
            title="Cancel Import",
            body="Do you want to cancel the wine directory import process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Creation")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_import_wine_direcotory_dialog_response)
        dialog.present(self.window)


    def connect_open_button_with_import_wine_directory_cancel(self):
        self.print_method_name()
        """
        Connect cancel handler to the open button
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_import_wine_directory_clicked)
        
        self.set_open_button_icon_visible(False)


    def backup_existing_directory(self, dst, backup_dir):
        self.print_method_name()
        """
        Safely backup the existing directory if it exists.
        """
        if dst.exists():
            try:
                # Create the parent directory if it doesn't exist
                backup_dir.parent.mkdir(parents=True, exist_ok=True)
                # First create the destination directory
                dst.rename(backup_dir)
                print(f"Created backup of existing directory: {backup_dir}")
            except Exception as e:
                raise Exception(f"Failed to create backup: {e}")

    def handle_import_cancellation(self, dst, backup_dir):
        self.print_method_name()
        """
        Handle import cancellation by restoring from backup.
        """
        try:
            if dst.exists():
                shutil.rmtree(dst)
                print(f"Removed incomplete import directory: {dst}")
            
            if backup_dir.exists():
                # Create the parent directory if it doesn't exist
                dst.parent.mkdir(parents=True, exist_ok=True)
                backup_dir.rename(dst)
                print(f"Restored original directory from backup")
                
        except Exception as e:
            print(f"Error during cancellation cleanup: {e}")
            # Still show cancelled message but also show error
            GLib.idle_add(self.show_info_dialog, "Error", 
                        f"Wine directory import was cancelled but encountered errors during cleanup: {e}\n"
                        f"Backup directory may still exist at: {backup_dir}")
            return
        
        self.stop_processing = False
        GLib.idle_add(self.on_import_wine_directory_completed)
        GLib.idle_add(self.show_info_dialog, "Cancelled", "Wine directory import was cancelled")

    def handle_import_error(self, dst, backup_dir, error_message):
        self.print_method_name()
        """
        Handle errors during import by restoring from backup.
        """
        try:
            if dst.exists():
                shutil.rmtree(dst)
                print(f"Removed failed import directory: {dst}")
                
            if backup_dir.exists():
                backup_dir.rename(dst)
                print(f"Restored original directory after error")
                
        except Exception as e:
            print(f"Error during error cleanup: {e}")
            error_message += f"\nAdditional error during cleanup: {e}"
            if backup_dir.exists():
                error_message += f"\nBackup directory may still exist at: {backup_dir}"
        
        self.stop_processing = False
        GLib.idle_add(self.on_import_wine_directory_completed)
        GLib.idle_add(self.show_info_dialog, "Error", error_message)

    def cleanup_backup(self, backup_dir):
        self.print_method_name()
        """
        Clean up backup directory after successful import.
        """
        try:
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
                print(f"Removed backup directory after successful import: {backup_dir}")
        except Exception as e:
            print(f"Warning: Failed to remove backup directory: {e}")
            # Continue anyway since the import was successful


    def cleanup_cancelled_import(self, temp_dir):
        self.print_method_name()
        """
        Clean up temporary directory and reset UI after cancelled import
        """
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                print(f"Removed temporary directory: {temp_dir}")
        except Exception as e:
            print(f"Error cleaning up temporary directory: {e}")
        finally:
            self.stop_processing = False
            GLib.idle_add(self.on_import_wine_directory_completed)
            if not self.stop_processing:
                GLib.idle_add(self.show_info_dialog, "Cancelled", "Wine directory import was cancelled")

            #self.open_button.disconnect(self.open_button_handler_id)

            #self.reconnect_open_button()
            #self.load_script_list()
            ## Restore the script list in the flowbox
            GLib.idle_add(self.create_script_list)

    def disconnect_open_button(self):
        self.print_method_name()
        """
        Disconnect the open button's handler and update its label to "Importing...".
        """
        if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = None  # Reset the handler ID after disconnecting
        
        # Update the label and hide the icon
        self.set_open_button_label("Importing...")
        self.set_open_button_icon_visible(False)  # Hide the open-folder icon
        print("Open button disconnected and spinner shown.")

    def reconnect_open_button(self):
        self.print_method_name()
        """
        Reconnect the open button's handler and reset its label.
        """
        # Disconnect before reconnecting
        self.disconnect_open_button()

        if hasattr(self, 'open_button') and self.open_button is not None:
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
        
        # Reset the label and show the icon
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        print("Open button reconnected and UI reset.")

        
    def create_scripts_for_exe_files(self, wineprefix):
        self.print_method_name()
        exe_files = self.find_exe_files(wineprefix)
        for exe_file in exe_files:
            self.create_yaml_file(exe_file, wineprefix, use_exe_name=True)
            
        #GLib.timeout_add_seconds(0.5, self.create_script_list)

    def find_exe_files(self, wineprefix):
        self.print_method_name()
        drive_c = Path(wineprefix) / "drive_c"
        exclude_patterns = [
            "windows", "dw20.exe", "BsSndRpt*.exe", "Rar.exe", "tdu2k.exe",
            "python.exe", "pythonw.exe", "zsync.exe", "zsyncmake.exe", "RarExtInstaller.exe",
            "UnRAR.exe", "wmplayer.exe", "iexplore.exe", "LendaModTool.exe", "netfx*.exe",
            "wordpad.exe", "quickSFV*.exe", "UnityCrashHand*.exe", "CrashReportClient.exe",
            "installericon.exe", "dwtrig*.exe", "ffmpeg*.exe", "ffprobe*.exe", "dx*setup.exe",
            "*vshost.exe", "*mgcb.exe", "cls-lolz*.exe", "cls-srep*.exe", "directx*.exe",
            "UnrealCEFSubProc*.exe", "UE4PrereqSetup*.exe", "dotnet*.exe", "oalinst.exe",
            "*redist*.exe", "7z*.exe", "unins*.exe"
        ]
        
        exe_files_found = []

        for root, dirs, files in os.walk(drive_c):
            # Exclude "windows" directory in a case-insensitive way
            dirs[:] = [d for d in dirs if not fnmatch.fnmatchcase(d.lower(), "windows")]

            for file in files:
                # Check if file matches any exclude pattern
                if any(fnmatch.fnmatch(file.lower(), pattern.lower()) for pattern in exclude_patterns):
                    continue
                
                file_path = Path(root) / file
                if file_path.suffix.lower() == ".exe" and file_path.is_file():
                    exe_files_found.append(file_path)

        return exe_files_found

    def process_reg_files(self, wineprefix):
        self.print_method_name()
        print(f"Starting to process .reg files in {wineprefix}")
        
        # Get current username from the environment
        current_username = os.getenv("USERNAME") or os.getenv("USER")
        if not current_username:
            print("Unable to determine the current username from the environment.")
            return
        print(f"Current username: {current_username}")

        # Read the USERNAME from user.reg
        user_reg_path = os.path.join(wineprefix, "user.reg")
        if not os.path.exists(user_reg_path):
            print(f"File not found: {user_reg_path}")
            return
        
        print(f"Reading user.reg file from {user_reg_path}")
        with open(user_reg_path, 'r') as file:
            content = file.read()
        
        match = re.search(r'"USERNAME"="([^"]+)"', content, re.IGNORECASE)
        if not match:
            print("Unable to determine the USERNAME from user.reg.")
            return
        
        wine_username = match.group(1)
        print(f"Found USERNAME in user.reg: {wine_username}")

        # Define replacements
        replacements = {
            f"\\\\users\\\\{wine_username}": f"\\\\users\\\\{current_username}",
            f"\\\\home\\\\{wine_username}": f"\\\\home\\\\{current_username}",
            f'"USERNAME"="{wine_username}"': f'"USERNAME"="{current_username}"'
        }
        print("Defined replacements:")
        for old, new in replacements.items():
            print(f"  {old} -> {new}")

        # Process all .reg files in the wineprefix
        for root, dirs, files in os.walk(wineprefix):
            for file in files:
                if file.endswith(".reg"):
                    file_path = os.path.join(root, file)
                    print(f"Processing {file_path}")
                    
                    with open(file_path, 'r') as reg_file:
                        reg_content = reg_file.read()
                    
                    for old, new in replacements.items():
                        if old in reg_content:
                            reg_content = reg_content.replace(old, new)
                            print(f"Replaced {old} with {new} in {file_path}")
                        else:
                            print(f"No instances of {old} found in {file_path}")

                    with open(file_path, 'w') as reg_file:
                        reg_file.write(reg_content)
                    print(f"Finished processing {file_path}")

        print(f"Completed processing .reg files in {wineprefix}")

    def custom_copytree(self, src, dst):
        self.print_method_name()
        """
        Robust directory copy using cp -a that:
        - Preserves symlinks and attributes
        - Copies contents of src directory into dst
        - Handles spaces in paths
        - Provides cancellation and progress pulse
        """
        try:
            src_path = Path(src).resolve()
            dst_path = Path(dst).resolve()

            # Ensure source exists
            if not src_path.exists():
                raise FileNotFoundError(f"Source directory {src_path} does not exist")

            # Create parent directory for destination
            dst_path.mkdir(parents=True, exist_ok=True)

            def preexec_function():
                """Ensure child processes don't receive signals"""
                os.setpgrp()

            # Use cp -a to copy contents of src to dst (not the directory itself)
            # The '/.' ensures we copy directory contents rather than the directory
            copy_process = subprocess.Popen(
                ['cp', '-a', f'{src_path}/.', str(dst_path)],
                preexec_fn=preexec_function,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            with self.process_lock:
                self.current_process = copy_process

            # Monitor process and handle cancellation
            while copy_process.poll() is None:
                if self.stop_processing:
                    print("Cancellation requested, terminating copy process...")
                    self._kill_current_process()
                    if dst_path.exists():
                        print(f"Cleaning up partially copied files at {dst_path}")
                        shutil.rmtree(dst_path, ignore_errors=True)
                    print("Operation cancelled by user")
                    return

                # Pulse progress bar if available
                if hasattr(self, 'progress_bar'):
                    GLib.idle_add(lambda: self.progress_bar.pulse())

                time.sleep(0.1)  # Reduce CPU usage

            # Handle completion
            if copy_process.returncode != 0:
                error_msg = copy_process.stderr.read().decode() if copy_process.stderr else "Unknown error"
                raise RuntimeError(f"Copy failed with code {copy_process.returncode}: {error_msg}")

            # Final progress update
            if hasattr(self, 'progress_bar'):
                GLib.idle_add(lambda: self.progress_bar.set_fraction(1.0))

        except Exception as e:
            print(f"Copy error: {str(e)}")
            if dst_path.exists():
                shutil.rmtree(dst_path, ignore_errors=True)
            raise
        finally:
            with self.process_lock:
                self.current_process = None

    def disable_open_button(self):
        self.print_method_name()
        if self.open_button:
            self.open_button.set_sensitive(False)
        print("Open button disabled.")

    def enable_open_button(self):
        self.print_method_name()
        if self.open_button:
            self.open_button.set_sensitive(True)
        print("Open button enabled.")

    def replace_home_with_tilde_in_path(self, path_str):
        #self.print_method_name()
        """Replace the user's home directory with '~' in the given path string."""
        user_home = os.getenv("HOME")
        if path_str.startswith(user_home):
            return path_str.replace(user_home, "~", 1)
        return path_str

    def expand_and_resolve_path(self, path):
        self.print_method_name()
        """Expand '~' to the home directory and resolve the absolute path."""
        return Path(path).expanduser().resolve()
        
    def load_script_list(self, prefixdir=None):
        self.print_method_name()
        """
        Loads all .charm files from the specified directory (or the default self.prefixes_dir)
        into the self.script_list dictionary.

        Args:
            prefixdir (str or Path, optional): The directory to search for .charm files.
                                               Defaults to self.prefixes_dir.
        """
        if prefixdir is None:
            prefixdir = self.prefixes_dir

        # Clear existing script list when loading from default directory
        if prefixdir == self.prefixes_dir:
            self.script_list = {}

        # Find all .charm files in the directory
        scripts = self.find_charm_files(prefixdir)

        for script_file in scripts:
            try:
                with open(script_file, 'r') as f:
                    script_data = yaml.safe_load(f)

                if not isinstance(script_data, dict):
                    print(f"Warning: Invalid format in {script_file}, skipping.")
                    continue

                # Ensure required keys are present and correctly populated
                updated = False
                required_keys = ['exe_file', 'script_path', 'wineprefix', 'sha256sum']

                # Initialize script_path to the current .charm file path if missing
                if 'script_path' not in script_data:
                    script_data['script_path'] = self.replace_home_with_tilde_in_path(str(script_file))
                    updated = True
                    print(f"Warning: script_path missing in {script_file}. Added default value.")

                # Set wineprefix to the parent directory of script_path if missing
                if 'wineprefix' not in script_data or not script_data['wineprefix']:
                    wineprefix = str(Path(script_file).parent)
                    script_data['wineprefix'] = self.replace_home_with_tilde_in_path(wineprefix)
                    updated = True
                    print(f"Warning: wineprefix missing in {script_file}. Set to {wineprefix}.")

                # Replace any $HOME occurrences with ~ in all string paths
                for key in required_keys:
                    if isinstance(script_data.get(key), str) and script_data[key].startswith(os.getenv("HOME")):
                        new_value = self.replace_home_with_tilde_in_path(script_data[key])
                        if new_value != script_data[key]:
                            script_data[key] = new_value
                            updated = True

                # Regenerate sha256sum if missing
                should_generate_hash = False
                if 'sha256sum' not in script_data or script_data['sha256sum'] == None:
                    should_generate_hash = True

                if should_generate_hash:
                    if 'exe_file' in script_data and script_data['exe_file']:
                        # Generate hash from exe_file if it exists
                        exe_path = Path(str(script_data['exe_file'])).expanduser().resolve()
                        if os.path.exists(exe_path):
                            sha256_hash = hashlib.sha256()
                            with open(exe_path, "rb") as f:
                                for byte_block in iter(lambda: f.read(4096), b""):
                                    sha256_hash.update(byte_block)
                            script_data['sha256sum'] = sha256_hash.hexdigest()
                            updated = True
                            print(f"Generated sha256sum from exe_file in {script_file}")
                        else:
                            print(f"Warning: exe_file not found, not updating sha256sum from script file: {script_file}")

                # If updates are needed, rewrite the file
                if updated:
                    with open(script_file, 'w') as f:
                        yaml.safe_dump(script_data, f)
                    print(f"Updated script file: {script_file}")

                # Store the actual file modification time
                script_data['mtime'] = os.path.getmtime(script_file)

                # Use 'sha256sum' as the key in script_list
                script_key = script_data['sha256sum']
                if prefixdir == self.prefixes_dir:
                    self.script_list[script_key] = script_data
                else:
                    self.script_list = {script_key: script_data, **self.script_list}

            except yaml.YAMLError as yaml_err:
                print(f"YAML error in {script_file}: {yaml_err}")
            except Exception as e:
                print(f"Error loading script {script_file}: {e}")

        print(f"Loaded {len(self.script_list)} scripts.")

##########################


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
########################
    def is_valid_directory(self, path_obj, wineprefix):
        """
        Validate if a directory can be added to the backup list.
        
        Args:
            path_obj (Path): The selected directory path.
            wineprefix (Path): The wineprefix path.
        
        Returns:
            tuple: (bool, str) - (is_valid, error_message)
        """
        # Ensure the directory is within the wineprefix
        if not path_obj.is_relative_to(wineprefix):
            return False, "Directory must be within Wine prefix"
        
        # Define directories to exclude exactly (not their subdirectories)
        exact_exclusions = [
            wineprefix,              # Wineprefix itself
            wineprefix / "drive_c"   # drive_c itself
        ]
        
        # Define directories to exclude including their subdirectories
        subtree_exclusions = {
            wineprefix / "dosdevices": "Cannot select dosdevices or its subdirectories",
            wineprefix / "drive_c" / "windows": "Cannot select drive_c/windows or its subdirectories"
        }
        
        # Check exact exclusions
        if path_obj in exact_exclusions:
            if path_obj == wineprefix:
                return False, "Cannot select the wineprefix directory"
            elif path_obj == wineprefix / "drive_c":
                return False, "Cannot select the drive_c directory"
        
        # Check subtree exclusions
        for excl, msg in subtree_exclusions.items():
            try:
                path_obj.relative_to(excl)
                return False, msg  # Path is excl or a subdirectory of excl
            except ValueError:
                pass  # Not a match, continue checking
        
        return True, ""  # Directory is valid
        
    def show_save_user_dirs_dialog(self, script, script_key, button):
        """Show dialog to select directories for backup."""
        global _  # Explicitly declare _ as global to prevent shadowing
        print("Method: show_save_user_dirs_dialog")
        wineprefix = Path(script).parent
        default_dir = wineprefix / "drive_c" / "users"

        # Create Adw.AlertDialog
        dialog = Adw.AlertDialog(
            heading=_("Select Directories to Backup"),
            body=_("Choose which directories to include in the backup.")
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("ok", _("OK"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        # Create content container
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        # Scrollable directory list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        
        # ListBox with CSS class
        self.dir_list = Gtk.ListBox()
        self.dir_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.dir_list.add_css_class("boxed-list")  # Modern GTK 4 styling
        
        # Add default directory
        default_row = Gtk.ListBoxRow()
        default_check = Gtk.CheckButton(label=str(default_dir))
        default_check.set_active(True)
        default_row.set_child(default_check)
        self.dir_list.append(default_row)
        
        # Load saved directories from .charm file
        script_data = self.extract_yaml_info(script_key)
        saved_dirs = script_data.get('save_dirs', [])
        for saved_dir in saved_dirs:
            saved_path = Path(saved_dir).expanduser().resolve()
            # Validate saved directory
            valid, _unused = self.is_valid_directory(saved_path, wineprefix)
            if valid and str(saved_path) != str(default_dir):
                row = Gtk.ListBoxRow()
                check = Gtk.CheckButton(label=str(saved_path))
                check.set_active(True)
                row.set_child(check)
                self.dir_list.append(row)
        
        scrolled.set_child(self.dir_list)
        content_box.append(scrolled)

        # Add directory button
        add_btn = Gtk.Button(label=_("Add Directory"))
        add_btn.connect("clicked", self.on_add_directory, self.window, wineprefix)
        content_box.append(add_btn)

        dialog.set_extra_child(content_box)
        dialog.connect("response", self.on_directory_dialog_response, script, script_key)
        dialog.present(self.window)

    def on_directory_dialog_response(self, dialog, response_id, script, script_key):
        """Handle dialog response and save selected directories to .charm file."""
        if response_id == "ok":
            selected_dirs = [row.get_child().get_label() for row in self.dir_list 
                            if row.get_child().get_active()]
            self.show_save_file_dialog(script, script_key, selected_dirs)
            
            # Update the .charm file with selected directories
            try:
                script_data = self.extract_yaml_info(script_key)
                script_path = Path(str(script_data['script_path'])).expanduser().resolve()
                
                # Convert paths to tilde format for storage
                save_dirs = [self.replace_home_with_tilde_in_path(dir) for dir in selected_dirs]
                script_data['save_dirs'] = save_dirs
                
                # Write updated data back to .charm file
                with open(script_path, 'w') as file:
                    yaml.dump(script_data, file, default_style="'", default_flow_style=False, width=10000)
                print(f"Saved directories to {script_path}: {save_dirs}")
            except Exception as e:
                print(f"Error saving directories to .charm file: {e}")
                GLib.idle_add(self.show_error_dialog, _("Error"), 
                            _("Failed to save directories: {}").format(str(e)))
        
        dialog.close()

    def on_add_directory(self, button, parent_dialog, wineprefix):
        """Add a new directory to the backup list with validation."""
        dir_dialog = Gtk.FileDialog()
        dir_dialog.set_title(_("Select Directory to Add"))
        dir_dialog.set_initial_folder(Gio.File.new_for_path(str(wineprefix)))

        def on_dir_response(dlg, result):
            try:
                folder = dlg.select_folder_finish(result)
                path = folder.get_path()
                path_obj = Path(path)

                # Validate the directory
                valid, msg = self.is_valid_directory(path_obj, wineprefix)
                if not valid:
                    self.show_error_dialog(_("Error"), msg)
                    return
                
                # Check for duplicates
                if any(row.get_child().get_label() == path for row in self.dir_list):
                    return  # Silently ignore duplicates
                
                # Add the directory to the list
                row = Gtk.ListBoxRow()
                check = Gtk.CheckButton(label=path)
                check.set_active(True)
                row.set_child(check)
                self.dir_list.append(row)
            except GLib.Error as e:
                if e.code != Gtk.DialogError.DISMISSED:
                    print(f"Directory selection error: {e}")

        dir_dialog.select_folder(parent_dialog, None, on_dir_response)


    def show_save_file_dialog(self, script, script_key, selected_dirs):
        """Show dialog to choose backup file location."""
        print("Method: show_save_file_dialog")
        creation_date_and_time = datetime.now().strftime("%Y%m%d%H%M")
        default_backup_name = f"{script.stem}-{creation_date_and_time}.saved"
        file_dialog = Gtk.FileDialog()
        file_dialog.set_initial_name(default_backup_name)
        file_dialog.save(self.window, None, 
                        lambda dlg, res: self.on_save_user_dirs_dialog_response(dlg, res, script, script_key, selected_dirs))

    def on_save_user_dirs_dialog_response(self, dialog, result, script, script_key, selected_dirs):
        """Handle save file dialog response."""
        print("Method: on_save_user_dirs_dialog_response")
        try:
            backup_file = dialog.save_finish(result)
            if backup_file:
                backup_path = backup_file.get_path()
                print(f"Backup will be saved to: {backup_path}")
                threading.Thread(
                    target=self.save_user_dirs,
                    args=(script, script_key, backup_path, selected_dirs)
                ).start()
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"Save error: {e}")

    def save_user_dirs(self, script, script_key, backup_path, selected_dirs):
        """Save selected directories to a compressed archive."""
        print("Method: save_user_dirs")
        wineprefix = Path(script).parent
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            print("Error: Couldn't determine username")
            return
        rel_paths = [str(Path(path).relative_to(wineprefix)) for path in selected_dirs 
                    if Path(path).is_relative_to(wineprefix)]
        if not rel_paths:
            print("No valid directories selected")
            return
        try:
            tar_command = [
                'tar', '-I', 'zstd -T0',
                '--transform', f"s|{current_username}|%USERNAME%|g",
                '-cf', backup_path,
                '-C', str(wineprefix)
            ] + rel_paths
            print(f"Executing: {' '.join(tar_command)}")
            result = subprocess.run(tar_command, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Backup failed: {result.stderr}")
            print(f"Backup created at {backup_path}")
            GLib.idle_add(self.show_info_dialog, _("Backup Complete"), 
                         _("User directories saved to:\n{}").format(backup_path))
        except Exception as e:
            print(f"Backup error: {e}")
            GLib.idle_add(self.show_error_dialog, _("Backup Failed"), str(e))

    def show_load_user_dirs_dialog(self, script, script_key, button):
        """Show dialog to load a backup file."""
        print("Method: show_load_user_dirs_dialog")
        file_dialog = Gtk.FileDialog()
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Saved Files (*.sav.tar.zst, *.saved)")
        file_filter.add_pattern("*.sav.tar.zst")
        file_filter.add_pattern("*.saved")
        filter_list_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_list_store.append(file_filter)
        file_dialog.set_filters(filter_list_store)
        file_dialog.open(self.window, None, 
                        lambda dlg, res: self.on_load_user_dirs_dialog_response(dlg, res, script, script_key))

    def on_load_user_dirs_dialog_response(self, dialog, result, script, script_key):
        """Handle load file dialog response with confirmation."""
        print("Method: on_load_user_dirs_dialog_response")
        try:
            backup_file = dialog.open_finish(result)
            if backup_file:
                backup_path = backup_file.get_path()
                print(f"Backup will be loaded from: {backup_path}")
                def on_confirm(confirm):
                    if confirm:
                        threading.Thread(target=self.load_user_dirs, 
                                       args=(script, script_key, backup_path)).start()
                self.confirm_restore(backup_path, on_confirm)
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"Load error: {e}")

    def confirm_restore(self, backup_path, callback):
        """Show confirmation dialog before restoring."""
        dialog = Adw.AlertDialog(
            heading=_("Confirm Restore"),
            body=_("Restoring from {} will overwrite existing user directories. Proceed?").format(backup_path)
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restore", _("Restore"))
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda d, r: callback(r == "restore"))
        dialog.present(self.window)

    def load_user_dirs(self, script, script_key, backup_path):
        """Restore user directories from a backup file."""
        print("Method: load_user_dirs")
        wineprefix = Path(script).parent
        if not wineprefix.exists():
            print(f"Error: Wineprefix not found at {wineprefix}")
            return
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            print("Error: Unable to determine username")
            return
        try:
            extract_dir = wineprefix / "drive_c" / "users" if backup_path.endswith('.sav.tar.zst') else wineprefix
            extract_dir.mkdir(parents=True, exist_ok=True)
            tar_command = [
                'tar', '-I', 'zstd -d',
                '-xf', backup_path,
                '--transform', f"s|%USERNAME%|{current_username}|g",
                '--transform', f"s|XOUSERXO|{current_username}|g",
                '-C', str(extract_dir)
            ]
            print(f"Executing: {' '.join(tar_command)}")
            result = subprocess.run(tar_command, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Restore failed: {result.stderr}")
            print(f"Backup loaded to {extract_dir}")
            GLib.idle_add(self.show_info_dialog, _("Restore Complete"), 
                         _("User directories restored to:\n{}").format(extract_dir))
        except Exception as e:
            print(f"Restore error: {e}")
            GLib.idle_add(self.show_error_dialog, _("Restore Failed"), str(e))


    def show_error_dialog(self, title, message):
        """Display an error dialog."""
        dialog = Adw.AlertDialog(heading=title, body=message)
        dialog.add_response("ok", _("OK"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.present(self.window)
########################
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
                "Game Directory Already Exists",
                f"The game directory for '{exe_name}' is already in the Wine prefix. No action is needed."
)
            return

        # Check if the game directory is in DO_NOT_BUNDLE_FROM directories
        if str(exe_path) in self.get_do_not_bundle_directories():
            msg1 = "Cannot copy the selected game directory"
            msg2 = "Please move the files to a different directory to create a bundle."
            self.show_info_dialog(msg1, msg2)
            return

        # Check disk space in the source and destination directories
        if not self.has_enough_disk_space(exe_path, wineprefix):
            self.show_info_dialog("Insufficient Disk Space", "There is not enough space to import the game directory.")
            return

        # Proceed with copying if conditions are met
        # Step 1: Disconnect the UI elements and initialize the spinner
        self.on_back_button_clicked(None)
        self.disconnect_open_button()
        self.show_processing_spinner(f"Importing {exe_path.name}")

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
            ("Copying Game Directory", lambda: shutil.copytree(src, dst_path, dirs_exist_ok=True)),
            ("Updating Script Path", lambda: self.update_exe_file_path_in_script(script_path, dst_path / exe_name))
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
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.reconnect_open_button()
        self.hide_processing_spinner()

        for key, data in self.script_ui_data.items():
            row_button = data['row']
            row_play_button = data['play_button']
            row_options_button = data['options_button']
        self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)


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

            # Update the exe_file path with the new location
            updated_content = []
            for line in script_content:
                if line.startswith("exe_file:"):
                    updated_content.append(f"exe_file: '{new_exe_file}'\n")
                else:
                    updated_content.append(line)

            # Write the updated content back to the file
            with open(script_path, "w") as file:
                file.writelines(updated_content)

            print(f"Updated exe_file in {script_path} to {new_exe_file}")

        except Exception as e:
            print(f"Error updating script path: {e}")

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
                if line.startswith("runner:"):
                    updated_content.append(f"runner: '{new_runner}'\n")
                else:
                    updated_content.append(line)

            # Write the updated content back to the file
            with open(script_path, "w") as file:
                file.writelines(updated_content)

            print(f"Updated runner in {script_path} to {new_runner}")

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



########### 
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
        self.on_settings_download_runner_clicked(callback=self.on_download_complete)

    def on_download_complete(self):
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

        # Build the info message with Pango markup
        info = (
            f"<b>Program Name:</b> {progname}\n"
            f"<b>Wineprefix:</b> {wineprefix}\n"
            f"<b>Wineprefix Size:</b> {wineprefix_size}\n"
            f"<b>Executable:</b> {exe_file}\n"
            f"<b>Script Path:</b> {script_path}\n"
            f"<b>Runner:</b> {runner or f"{system_wine_display}"}\n"
            f"<b>Architecture:</b> {arch}\n"
            f"<b>Arguments:</b> {args or 'None'}\n"
            f"<b>Environment Variables:</b> {env_vars or 'None'}\n"
            f"<b>Creation Time:</b> {creation_time}"
        )

        # Create a custom dialog with a label that supports markup
        dialog = Adw.AlertDialog(
            heading=f"About {progname}",
            body=""
        )

        # Create a label with markup
        info_label = Gtk.Label(label=info)
        info_label.set_use_markup(True)  # Enable Pango markup
        info_label.set_wrap(True)       # Wrap long lines
        info_label.set_max_width_chars(50)  # Limit width for readability

        # Add the label to a box for better layout control
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(info_label)
        dialog.set_extra_child(content_box)

        # Add a close button
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

#########   ######
    def replace_open_button_with_settings(self):
        self.print_method_name()
        # Remove existing click handler from open button only if it exists
        if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
        
        self.set_open_button_label("Settings")
        self.set_open_button_icon_visible(False)
        
        # Connect new click handler
        self.open_button_handler_id = self.open_button.connect(
            "clicked",
            lambda btn: print("Settings clicked")
        )


    def restore_open_button(self):
        self.print_method_name()
        # Remove settings click handler
        if hasattr(self, 'open_button_handler_id'):
            self.open_button.disconnect(self.open_button_handler_id)
        
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        # Reconnect original click handler
        self.open_button_handler_id = self.open_button.connect(
            "clicked",
            self.on_open_button_clicked
        )

    def show_options_for_settings(self, action=None, param=None):
        self.print_method_name()
        """
        Display the settings options with search functionality using existing search mechanism.
        """
        # Add accelerator context for settings view
        self.setup_accelerator_context()

        self.search_button.set_active(False)
        # Ensure the search button is visible and the search entry is cleared
        self.search_button.set_visible(True)
        self.search_entry.set_text("")
        self.main_frame.set_child(None)

        # Create a scrolled window for settings options
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)

        self.settings_flowbox = Gtk.FlowBox()
        self.settings_flowbox.set_valign(Gtk.Align.START)
        self.settings_flowbox.set_halign(Gtk.Align.FILL)
        self.settings_flowbox.set_max_children_per_line(4)
        self.settings_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.settings_flowbox.set_vexpand(True)
        self.settings_flowbox.set_hexpand(True)
        scrolled_window.set_child(self.settings_flowbox)

        self.main_frame.set_child(scrolled_window)

        # Store settings options as instance variable for filtering
        self.settings_options = [
            ("Runner Set Default", "runner-set-default-symbolic", self.set_default_runner),
            ("Runner Download", "runner-download-symbolic", self.on_settings_download_runner_clicked),
            ("Runner Import", "runner-import-symbolic", self.import_runner),
            ("Runner Backup", "runner-backup-symbolic", self.backup_runner),
            ("Runner Restore", "runner-restore-symbolic", self.restore_runner),
            ("Runner Delete", "runner-delete-symbolic", self.delete_runner),
            ("Template Set Default", "template-default-symbolic", self.set_default_template),
            ("Template Configure", "template-configure-symbolic", self.configure_template),
            ("Template Terminal", "template-terminal-symbolic", self.open_terminal_winecharm),
            ("Template Import", "template-import-symbolic", self.import_template),
            ("Template Create", "template-create-symbolic", self.create_template),
            ("Template Clone", "template-clone-symbolic", self.clone_template),
            ("Template Backup", "template-backup-symbolic", self.backup_template),
            ("Template Restore", "template-restore-symbolic", self.restore_template_from_backup),
            ("Template Delete", "template-delete-symbolic", self.delete_template),
            ("Set Wine Arch", "set-wine-arch-symbolic", self.set_wine_arch),
            ("Single Prefix Mode", "single-prefix-mode-symbolic", self.single_prefix_mode),
        ]

        # Initial population of options
        self.populate_settings_options()

        # Hide unnecessary UI components
        self.menu_button.set_visible(False)
        self.view_toggle_button.set_visible(False)

        if self.back_button.get_parent() is None:
            self.headerbar.pack_start(self.back_button)
        self.back_button.set_visible(True)

        self.replace_open_button_with_settings()
        self.selected_row = None

    def populate_settings_options(self, filter_text=""):
        self.print_method_name()
        """
        Populate the settings flowbox with filtered options.
        """
        # Clear existing options using GTK4's method
        while child := self.settings_flowbox.get_first_child():
            self.settings_flowbox.remove(child)

        # Add filtered options
        filter_text = filter_text.lower()
        for label, icon_name, callback in self.settings_options:
            if filter_text in label.lower():
                option_button = Gtk.Button()
                option_button.set_size_request(-1, 40)
                option_button.add_css_class("flat")
                option_button.add_css_class("normal-font")

                option_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                option_button.set_child(option_hbox)

                option_icon = Gtk.Image.new_from_icon_name(icon_name)
                option_label = Gtk.Label(label=label)
                option_label.set_xalign(0)
                option_label.set_hexpand(True)
                option_label.set_ellipsize(Pango.EllipsizeMode.END)
                option_hbox.append(option_icon)
                option_hbox.append(option_label)

                self.settings_flowbox.append(option_button)
                option_button.connect("clicked", lambda btn, cb=callback: cb())

#####################  single prefix mode

    def single_prefix_mode(self):
        self.print_method_name()
        dialog = Adw.AlertDialog(
            heading="Single Prefix Mode",
            body="Choose prefix mode for new games:\nSingle prefix saves space but makes it harder to backup individual games."
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        # Create radio buttons with fresh state
        single_prefix_radio = Gtk.CheckButton(label="Single Prefix Mode")
        multiple_prefix_radio = Gtk.CheckButton(label="Multiple Prefix Mode")
        multiple_prefix_radio.set_group(single_prefix_radio)
        
        # Always refresh from settings before showing dialog
        self.load_settings()  # Ensure latest values
        current_state = self.single_prefix
        single_prefix_radio.set_active(current_state)
        multiple_prefix_radio.set_active(not current_state)

        vbox.append(single_prefix_radio)
        vbox.append(multiple_prefix_radio)
        dialog.set_extra_child(vbox)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", "Apply")
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")

        def on_response(dialog, response):
            self.print_method_name()
            if response == "apply":
                new_state = single_prefix_radio.get_active()
                if new_state != current_state:
                    self.handle_prefix_mode_change(new_state)
            dialog.close()

        dialog.connect("response", on_response)
        dialog.present(self.window)

    def handle_prefix_mode_change(self, new_state):
        self.print_method_name()
        previous_state = self.single_prefix
        self.single_prefix = new_state
        
        try:
            # Determine architecture-specific paths
            template_dir = (self.default_template_win32 if self.arch == 'win32' 
                            else self.default_template_win64)
            single_dir = (self.single_prefix_dir_win32 if self.arch == 'win32'
                        else self.single_prefix_dir_win64)

            # Initialize template if needed
            if not template_dir.exists():
                self.initialize_template(template_dir, 
                                    lambda: self.finalize_prefix_mode_change(single_dir),
                                    arch=self.arch)
            else:
                self.finalize_prefix_mode_change(single_dir)
                
            self.save_settings()
            print(f"Prefix mode changed to {'Single' if new_state else 'Multiple'}")
            
        except Exception as e:
            print(f"Error changing prefix mode: {e}")
            self.single_prefix = previous_state  # Rollback on error
            self.save_settings()
            self.show_error_dialog("Mode Change Failed", str(e))
        
        finally:
            self.set_dynamic_variables()

    def finalize_prefix_mode_change(self, single_dir):
        self.print_method_name()
        if self.single_prefix:
            if not single_dir.exists():
                print("Creating single prefix copy...")
                self.copy_template(single_dir)
        else:
            print("Reverting to multiple prefixes")
##################### / single prefix mode

    # Implement placeholders for each setting's callback function
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
            else:
                new_runner_display, new_runner_path = all_runners[selected_index]
                print(f"Selected new default runner: {new_runner_display} -> {new_runner_path}")

                # Set the new runner path in self.settings
                new_runner_value = '' if new_runner_display.startswith("System Wine") else new_runner_path
                self.settings['runner'] = self.replace_home_with_tilde_in_path(new_runner_value)

                print(f"Runner path to be saved: {self.settings['runner']}")

                # Save the updated settings
                self.save_settings()

                # Provide user feedback
                self.show_info_dialog(
                    "Default Runner Updated",
                    f"The default runner has been set to {new_runner_display}."
                )
        else:
            print("Set default runner canceled.")

        #dialog.close()

    def on_download_runner_clicked_default(self, dialog):
        self.print_method_name()
        """
        Handle the "Download Runner" button click from the set_default_runner dialog.
        """
        dialog.close()
        # Start the download process with the appropriate callback
        self.on_settings_download_runner_clicked(callback=self.on_download_complete_default_runner)

    def on_download_complete_default_runner(self):
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

    def set_wine_arch(self):
        self.print_method_name()
        """
        Allow the user to set the Wine architecture using Adw.AlertDialog.
        """
        # Create AlertDialog
        dialog = Adw.AlertDialog(
            heading="Set Wine Architecture",
            body="Select the default architecture for new prefixes:"
        )

        # Create radio buttons for architecture selection
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        win32_radio = Gtk.CheckButton(label="32-bit (win32)")
        win64_radio = Gtk.CheckButton(label="64-bit (win64)")
        win64_radio.set_group(win32_radio)

        # Set current selection
        current_arch = self.arch
        win32_radio.set_active(current_arch == 'win32')
        win64_radio.set_active(current_arch == 'win64')

        # Add radio buttons to dialog
        vbox.append(win32_radio)
        vbox.append(win64_radio)
        dialog.set_extra_child(vbox)

        # Configure dialog buttons
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        # Response handler
        def on_response(dialog, response):
            self.print_method_name()
            if response == "ok":
                new_arch = 'win32' if win32_radio.get_active() else 'win64'
                if new_arch != current_arch:
                    self.main_frame.set_child(None)
                    handle_architecture_change(new_arch)
            dialog.close()

        # Architecture change handler
        def handle_architecture_change(new_arch):
            self.print_method_name()
            # Determine paths based on selected architecture
            new_template = self.default_template_win32 if new_arch == 'win32' else self.default_template_win64
            single_prefix_dir = self.single_prefix_dir_win32 if new_arch == 'win32' else self.single_prefix_dir_win64

            # Update settings
            self.arch = new_arch
            self.template = new_template
 
            self.settings['template'] = self.replace_home_with_tilde_in_path(str(new_template))
            self.settings['arch'] = self.replace_home_with_tilde_in_path(str(new_arch))
            self.save_settings()
            
            # Resolve template path
            new_template = Path(new_template).expanduser().resolve()
            
            # Initialize new template if needed
            if not new_template.exists():
                print(f"Initializing new {new_arch} template...")
                self.on_back_button_clicked(None)
                self.called_from_settings = True
                self.initialize_template(new_template, 
                                    lambda: finalize_arch_change(single_prefix_dir),
                                    arch=new_arch)
            else:
                print(f"Using existing {new_arch} template")
                self.show_options_for_settings()
                finalize_arch_change(single_prefix_dir)

        # Finalization handler
        def finalize_arch_change(single_prefix_dir):
            self.print_method_name()
            if self.single_prefix and not single_prefix_dir.exists():
                print(f"Copying to {single_prefix_dir.name}...")
                self.copy_template(single_prefix_dir)
            self.set_dynamic_variables()
            self.show_options_for_settings()

        self.show_options_for_settings()
        # Connect response signal and present dialog
        dialog.connect("response", on_response)
        dialog.present(self.window)
        
################
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
######################################################### Initiazlie template and import directory imrpovement



    def on_cancel_template_init_clicked(self, button):
        self.print_method_name()
        """
        Handle cancel button click during template initialization
        """
        dialog = Adw.AlertDialog(
            title="Cancel Initialization",
            body="Do you want to cancel the template initialization process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Initialization")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_template_init_dialog_response)
        dialog.present(self.window)

    def on_cancel_template_init_dialog_response(self, dialog, response):
        self.print_method_name()
        """
        Handle cancel dialog response for template initialization
        """
        if response == "cancel":
            self.stop_processing = True
        dialog.close()

    def cleanup_cancelled_template_init(self, template_dir):
        self.print_method_name()
        """
        Clean up after template initialization is cancelled, create a basic template,
        and update settings.yml
        """
        template_dir = Path(template_dir) if not isinstance(template_dir, Path) else template_dir
        
        try:
            if template_dir.exists():
                shutil.rmtree(template_dir)
                print(f"Removed incomplete template directory: {template_dir}")
            
            # Create the directory
            template_dir.mkdir(parents=True, exist_ok=True)
                
            # Initialize basic wineprefix with minimal setup
            basic_steps = [
                ("Creating basic wineprefix", f"WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
                ("Setting up directories", lambda: self.remove_symlinks_and_create_directories(template_dir))
            ]
            
            for step_text, command in basic_steps:
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    if callable(command):
                        command()
                    else:
                        subprocess.run(command, shell=True, check=True)
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    print(f"Error during basic template setup: {e}")
                    raise
                    
            print("Initialized basic wineprefix")
            
            # Update template in settings
            self.template = template_dir
            self.save_settings()
            print(f"Updated settings with new template path: {template_dir}")
            
        except Exception as e:
            print(f"Error during template cleanup: {e}")
        finally:
            self.initializing_template = False
            self.stop_processing = False
            GLib.idle_add(self.reset_ui_after_template_init)
            self.show_info_dialog("Basic Template Created", 
                        "A basic template was created and settings were updated. Some features may be limited.")


    def reset_ui_after_template_init(self):
        self.print_method_name()
        """
        Reset UI elements after template initialization and show confirmation
        """
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.hide_processing_spinner()
        
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
        
        self.flowbox.remove_all()



    def on_cancel_import_clicked(self, button):
        self.print_method_name()
        """
        Handle cancel button click during wine directory import
        """
        dialog = Adw.AlertDialog(
            title="Cancel Import",
            body="Do you want to cancel the wine directory import process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Import")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_import_dialog_response)
        dialog.present(self.window)

    def on_cancel_import_dialog_response(self, dialog, response):
        self.print_method_name()
        """
        Handle cancel dialog response for wine directory import
        """
        if response == "cancel":
            self.stop_processing = True
        dialog.close()

############################################### 4444444444444444444444444 New initialize template

####################### Restore Backup (prefix, bottle, .tar.zst, .wzt)

    def restore_from_backup(self, action=None, param=None):
        self.print_method_name()
        # Step 1: Create required directories (if needed)
        self.create_required_directories()

        # Step 2: Create a new Gtk.FileDialog instance
        file_dialog = Gtk.FileDialog.new()

        # Step 3: Create file filters for .tar.zst and .wzt files
        file_filter_combined = Gtk.FileFilter()
        file_filter_combined.set_name("Backup Files (*.prefix, *.bottle, *.wzt)")
        file_filter_combined.add_pattern("*.prefix")
        file_filter_combined.add_pattern("*.bottle")
        file_filter_combined.add_pattern("*.wzt")

        file_filter_botle_tar = Gtk.FileFilter()
        file_filter_botle_tar.set_name("WineCharm Bottle Files (*.bottle)")
        file_filter_botle_tar.add_pattern("*.bottle")

        file_filter_tar = Gtk.FileFilter()
        file_filter_tar.set_name("WineCharm Prefix Backup (*.prefix)")
        file_filter_tar.add_pattern("*.prefix")

        file_filter_wzt = Gtk.FileFilter()
        file_filter_wzt.set_name("Winezgui Backup Files (*.wzt)")
        file_filter_wzt.add_pattern("*.wzt")

        # Step 4: Set the filters on the dialog
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        
        # Add the combined filter as the default option
        filter_model.append(file_filter_combined)

        # Add individual filters for .tar.zst and .wzt files
        filter_model.append(file_filter_tar)
        filter_model.append(file_filter_botle_tar)
        filter_model.append(file_filter_wzt)
        
        # Apply the filters to the file dialog
        file_dialog.set_filters(filter_model)

        # Step 5: Open the dialog and handle the response
        file_dialog.open(self.window, None, self.on_restore_file_dialog_response)

    def get_total_uncompressed_size(self, archive_path):
        self.print_method_name()
        """
        Calculate the total uncompressed size of a tar archive without extracting it.

        Args:
            archive_path (str): The path to the tar archive.

        Returns:
            int: Total uncompressed size of the archive in bytes.
        """
        # Run the tar command and capture the output
        command = ['tar', '-tvf', archive_path]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check if there was an error
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return 0

        total_size = 0

        # Process each line of the tar output
        for line in result.stdout.splitlines():
            # Split the line by spaces and extract the third field (file size)
            parts = line.split()
            if len(parts) > 2:
                try:
                    size = int(parts[2])  # The size is in the third field
                    total_size += size
                except ValueError:
                    pass  # Skip lines where we can't parse the size

        print(f"Total uncompressed size: {total_size} bytes")
        return total_size


    def check_disk_space_and_uncompressed_size(self, prefixes_dir, file_path):
        self.print_method_name()
        """
        Check the available disk space and uncompressed size of the backup file.

        Args:
            prefixes_dir (Path): The directory where the wine prefixes are stored.
            file_path (str): Path to the backup .tar.zst file.

        Returns:
            (bool, int, int): Tuple containing:
                - True if there's enough space, False otherwise.
                - Available disk space in bytes.
                - Uncompressed size of the archive in bytes.
        """
        try:
            # Step 1: Get available disk space in the prefixes directory
            df_output = subprocess.check_output(['df', '--output=avail', str(prefixes_dir)]).decode().splitlines()[1]
            available_space_kb = int(df_output.strip()) * 1024  # Convert KB to bytes

            # Step 2: Get the total uncompressed size of the tar.zst file
            uncompressed_size_bytes = self.get_total_uncompressed_size(file_path)

            print(f"Available space: {available_space_kb / (1024 * 1024)} MB")
            print(f"Uncompressed size: {uncompressed_size_bytes / (1024 * 1024)} MB")

            # Step 3: Compare available space with uncompressed size
            return available_space_kb >= uncompressed_size_bytes, available_space_kb, uncompressed_size_bytes

        except subprocess.CalledProcessError as e:
            print(f"Error checking disk space or uncompressed size: {e}")
            return False, 0, 0


    def on_restore_file_dialog_response(self, dialog, result):
        self.print_method_name()
        try:
            # Retrieve the selected file using open_finish() for Gtk.FileDialog in GTK 4
            file = dialog.open_finish(result)
            if file:
                # Get the file path
                file_path = file.get_path()
                print(f"Selected file: {file_path}")

                # the restore
                self.restore_prefix_bottle_wzt_tar_zst(file_path)

        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")


    def restore_prefix_bottle_wzt_tar_zst(self, file_path):
        self.print_method_name()
        """
        Restore from a .prefix or .bottle which is a .tar.zst compressed file.
        """
        self.stop_processing = False
        
        try:
            # Extract prefix name before starting
            extracted_prefix = self.extract_prefix_dir(file_path)
            print("= ="*50)
            print(f"extracted_prefix ={extracted_prefix}")
            if not extracted_prefix:
                raise Exception("Failed to determine prefix directory name")
            
            # Handle existing directory
            backup_dir = None
            if extracted_prefix.exists():
                timestamp = int(time.time())
                backup_dir = extracted_prefix.parent / f"{extracted_prefix.name}_backup_{timestamp}"
                shutil.move(str(extracted_prefix), str(backup_dir))
                print(f"Backed up existing directory to: {backup_dir}")

            # Clear the flowbox and show progress spinner
            GLib.idle_add(self.flowbox.remove_all)
            self.show_processing_spinner(f"Restoring")
            #self.disconnect_open_button()
            #self.connect_open_button_with_import_wine_directory_cancel()
            self.connect_open_button_with_restore_backup_cancel()
            def restore_process():
                try:
                    if file_path.endswith(".wzt"):
                        restore_steps = self.get_wzt_restore_steps(file_path)
                    else:
                        restore_steps = self.get_restore_steps(file_path)

                    for step_text, step_func in restore_steps:
                        if self.stop_processing:
                            if backup_dir and backup_dir.exists():
                                if extracted_prefix.exists():
                                    shutil.rmtree(extracted_prefix)
                                shutil.move(str(backup_dir), str(extracted_prefix))
                                print(f"Restored original directory from: {backup_dir}")
                            return  # Finally block will handle UI reset

                        GLib.idle_add(self.show_initializing_step, step_text)
                        try:
                            step_func()
                            GLib.idle_add(self.mark_step_as_done, step_text)
                        except Exception as e:
                            print(f"Error during step '{step_text}': {e}")
                            if backup_dir and backup_dir.exists():
                                if extracted_prefix.exists():
                                    shutil.rmtree(extracted_prefix)
                                shutil.move(str(backup_dir), str(extracted_prefix))
                            GLib.idle_add(self.show_info_dialog, "Error", f"Failed during step '{step_text}': {str(e)}")
                            return  # Finally block will handle UI reset

                    # Success case
                    if backup_dir and backup_dir.exists():
                        shutil.rmtree(backup_dir)
                        print(f"Removed backup directory: {backup_dir}")

                except Exception as e:
                    print(f"Error during restore process: {e}")
                    if backup_dir and backup_dir.exists():
                        if extracted_prefix.exists():
                            shutil.rmtree(extracted_prefix)
                        shutil.move(str(backup_dir), str(extracted_prefix))
                    GLib.idle_add(self.show_info_dialog, "Error", f"Restore failed: {str(e)}")

                finally:
                    GLib.idle_add(self.on_restore_completed)
            # Start the restore process in a new thread
            threading.Thread(target=restore_process).start()

        except Exception as e:
            print(f"Error initiating restore process: {e}")
            GLib.idle_add(self.show_info_dialog, "Error", f"Failed to start restore: {str(e)}")



    def get_restore_steps(self, file_path):
        self.print_method_name()
        """
        Return the list of steps for restoring a prefix/bottle backup.
        """
        return [
            ("Checking Uncompressed Size", lambda: self.check_disk_space_and_show_step(file_path)),
            ("Extracting Backup File", lambda: self.extract_backup(file_path)),
            ("Processing Registry Files", lambda: self.process_reg_files(self.extract_prefix_dir(file_path))),
            ("Performing Replacements", lambda: self.perform_replacements(self.extract_prefix_dir(file_path))),
            ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
            ("Renaming and merging user directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(file_path))),
            ("Add Shortcuts to Script List", lambda: self.add_charm_files_to_script_list(self.extract_prefix_dir(file_path))),
            ("Create Wineboot Required file", lambda: self.create_wineboot_required_file(self.extract_prefix_dir(file_path))),
        ]

    def get_wzt_restore_steps(self, file_path):
        self.print_method_name()
        """
        Return the list of steps for restoring a WZT backup.
        """
        return [
            ("Checking Disk Space", lambda: self.check_disk_space_and_show_step(file_path)),
            ("Extracting WZT Backup File", lambda: self.extract_backup(file_path)),
            ("Performing User Related Replacements", lambda: self.perform_replacements(self.extract_prefix_dir(file_path))),
            ("Processing WineZGUI Script Files", lambda: self.process_sh_files(self.extract_prefix_dir(file_path))),
            ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
            ("Renaming and Merging User Directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(file_path))),
            ("Search LNK Files and Append to Found List", lambda: self.find_and_save_lnk_files(self.extract_prefix_dir(file_path))),
            ("Create Wineboot Required file", lambda: self.create_wineboot_required_file(self.extract_prefix_dir(file_path))),
        ]

    def create_wineboot_required_file(self, wineprefix):
        wineboot_file_path = Path(wineprefix) / "wineboot-required.yml"

        data = {
            'wineboot': 'required'
        }

        try:
            with open(wineboot_file_path, 'w') as file:
                yaml.dump(data, file, default_flow_style=False, width=10000)
            print(f"wineboot-required.yml file created successfully at {wineboot_file_path}")
        except Exception as e:
            print(f"Error creating wineboot-required.yml file: {e}")

    def perform_replacements(self, directory):
        self.print_method_name()
        user = os.getenv('USER')
        usershome = os.path.expanduser('~')
        datadir = os.getenv('DATADIR', '/usr/share')

        # Simplified replacements using plain strings
        find_replace_pairs = {
            "XOCONFIGXO": "\\\\?\\H:\\.config",
            "XOFLATPAKNAMEXO": "io.github.fastrizwaan.WineCharm",
            "XOINSTALLTYPEXO": "flatpak",
            "XOPREFIXXO": ".var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Prefixes",
            "XOWINEZGUIDIRXO": ".var/app/io.github.fastrizwaan.WineCharm/data/winecharm",
            "XODATADIRXO": datadir,
            "XODESKTOPDIRXO": ".local/share/applications/winecharm",
            "XOAPPLICATIONSXO": ".local/share/applications",
            "XOAPPLICATIONSDIRXO": ".local/share/applications",
            "XOREGUSERSUSERXO": f"\\\\users\\\\{user}",
            "XOREGHOMEUSERXO": f"\\\\home\\\\{user}",
            "XOREGUSERNAMEUSERXO": f'"USERNAME"="{user}"',
            "XOREGINSTALLEDBYUSERXO": f'"InstalledBy"="{user}"',
            "XOREGREGOWNERUSERXO": f'"RegOwner"="{user}"',
            "XOUSERHOMEXO": usershome,
            "XOUSERSUSERXO": f"/users/{user}",
            "XOMEDIASUSERXO": f"/media/{user}",
            "XOFLATPAKIDXO": "io.github.fastrizwaan.WineCharm",
            "XOWINEEXEXO": "",
            "XOWINEVERXO": "wine-9.0",
            "/media/%USERNAME%/": f'/media/{user}/',
        }

        self.replace_strings_in_files(directory, find_replace_pairs)
        

    def replace_strings_in_files(self, directory, find_replace_pairs):
        self.print_method_name()
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)

                # Skip binary files
                if self.is_binary_file(file_path):
                    #print(f"Skipping binary file: {file_path}")
                    continue

                # Skip files where permission is denied
                if not os.access(file_path, os.R_OK | os.W_OK):
                    #print(f"Skipping file: {file_path} (Permission denied)")
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    for find, replace in find_replace_pairs.items():
                        content = content.replace(find, replace)

                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    print(f"Replacements applied to file: {file_path}")
                except (UnicodeDecodeError, FileNotFoundError, PermissionError) as e:
                    print(f"Skipping file: {file_path} ({e})")

    def is_binary_file(self, file_path):
        self.print_method_name()
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                if b'\0' in chunk:
                    return True
        except Exception as e:
            print(f"Could not check file {file_path} ({e})")
        return False
        
    def process_sh_files(self, directory):
        self.print_method_name()
        """
        Process all .sh files and convert them to .charm files.
        """
        sh_files = self.find_sh_files(directory)
        created_charm_files = False  # Track whether any .charm file is created
        
        print(f"sh_files = \n {sh_files}")
        
        for sh_file in sh_files:
            variables = self.extract_infofile_path_from_sh(sh_file)
            exe_file = variables.get('EXE_FILE', '')
            progname = variables.get('PROGNAME', '')
            sha256sum = variables.get('CHECKSUM', '')

            print(" = "*20)
            print(f"""
            exe_file = {exe_file}
            progname = {progname}
            sha256sum = {sha256sum}
            """)
            # Regenerate sha256sum if missing
            if exe_file and not sha256sum:
                sha256_hash = hashlib.sha256()
                try:
                    with open(exe_file, "rb") as f:
                        for byte_block in iter(lambda: f.read(4096), b""):
                            sha256_hash.update(byte_block)
                    sha256sum = sha256_hash.hexdigest()
                    print(f"Warning: sha256sum missing in {exe_file}. Regenerated hash.")
                except FileNotFoundError:
                    print(f"Error: {exe_file} not found. Cannot compute sha256sum.")

            info_file_path = variables.get('INFOFILE')
            if info_file_path:
                info_file_path = os.path.join(os.path.dirname(sh_file), info_file_path)
                if os.path.exists(info_file_path):
                    try:
                        info_data = self.parse_info_file(info_file_path)
                        runner = info_data.get('Runner', '')

                        # Locate environment-variable.yml and cmdline.yml
                        env_var_file_path = os.path.join(os.path.dirname(sh_file), "environment-variable.yml")
                        cmdline_file_path = os.path.join(os.path.dirname(sh_file), "cmdline.yml")

                        # Load environment variables and command-line arguments
                        env_vars = self.load_and_fix_yaml(env_var_file_path, "environment-variable.yml")
                        args = self.load_and_fix_yaml(cmdline_file_path, "cmdline.yml")

                        yml_path = sh_file.replace('.sh', '.charm')
                        self.create_charm_file({
                            'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
                            'script_path': self.replace_home_with_tilde_in_path(str(yml_path)),
                            'wineprefix': self.replace_home_with_tilde_in_path(str(directory)),
                            'progname': progname,
                            'sha256sum': sha256sum,
                            'runner': runner,
                            'args': args,  # Include command-line arguments
                            'env_vars': env_vars  # Include environment variables
                        }, yml_path)

                        
                        ## Add the new script data directly to the script list
                        self.new_scripts.add(Path(yml_path).stem)
                        print(f"Created {yml_path}")
                        created_charm_files = True  # Mark that at least one .charm file was created
                        

                    except Exception as e:
                        print(f"Error parsing INFOFILE {info_file_path}: {e}")
                else:
                    print(f"INFOFILE {info_file_path} not found")
            else:
                print(f"No INFOFILE found in {sh_file}")

        # If no .charm files were created, create scripts for .lnk and .exe files
        if not created_charm_files:
            print(f"No .charm files created. Proceeding to create scripts for .lnk and .exe files in {directory}")
            self.create_scripts_for_lnk_files(directory)
            print(f"Scripts created for .lnk files in {directory}")

            if self.lnk_processed_success_status:
                print("Skipping create_scripts_for_exe_files creation: .lnk files processed successfully.")
            else:
                self.create_scripts_for_exe_files(directory)
                print(f"Scripts created for .exe files in {directory}")
        else:
            self.track_all_lnk_files(directory)

    def load_and_fix_yaml(self, yaml_file_path, filename):
        self.print_method_name()
        """
        Load data from the specified YAML file, fixing missing spaces around colons.
        """
        if not os.path.exists(yaml_file_path):
            print(f"{filename} not found at {yaml_file_path}")
            return ""

        try:
            with open(yaml_file_path, 'r') as f:
                content = f.read()

            # Fix any missing spaces around colons using regex
            fixed_content = re.sub(r'(\S):(\S)', r'\1: \2', content)

            # Load the fixed YAML content
            yaml_data = yaml.safe_load(fixed_content)

            # Log what we found to debug the issue
            print(f"Loaded data from {filename}: {yaml_data}")

            # Handle different formats gracefully
            if isinstance(yaml_data, dict):
                return yaml_data.get('args', '')  # Return the 'args' value
            else:
                print(f"Unexpected data format in {filename}: {yaml_data}")
                return ""

        except Exception as e:
            print(f"Error reading or parsing {filename} at {yaml_file_path}: {e}")
            return ""

    def create_charm_file(self, info_data, yml_path):
        self.print_method_name()
        """
        Create a .charm file with the provided information.
        """
        # Print to confirm the function is being executed
        print(f"Creating .charm file at path: {yml_path}")

        # Extract data with default empty values to prevent KeyErrors
        exe_file = info_data.get('exe_file', '')
        progname = info_data.get('progname', '')
        args = info_data.get('args', '')
        sha256sum = info_data.get('sha256sum', '')
        runner = info_data.get('runner', '')
        env_vars = info_data.get('env_vars', '')  # Now treating env_vars as a string
        script_path = info_data.get('script_path', '')
        wineprefix = info_data.get('wineprefix', '')

        # Debugging: Print all values before writing
        print(f"exe_file: {exe_file}")
        print(f"progname: {progname}")
        print(f"args: {args}")
        print(f"sha256sum: {sha256sum}")
        print(f"runner: {runner}")
        print(f"env_vars: {env_vars}")
        print(f"script_path: {script_path}")
        print(f"wineprefix: {wineprefix}")

        try:
            # Open the file and write all key-value pairs in YAML format
            with open(yml_path, 'w') as yml_file:
                yml_file.write(f"exe_file: '{exe_file}'\n")
                yml_file.write(f"progname: '{progname}'\n")
                yml_file.write(f"args: '{args}'\n")
                yml_file.write(f"sha256sum: '{sha256sum}'\n")
                yml_file.write(f"runner: '{runner}'\n")
                yml_file.write(f"script_path: '{script_path}'\n")
                yml_file.write(f"wineprefix: '{wineprefix}'\n")
                yml_file.write(f"env_vars: '{env_vars}'\n")

            print(f"Actual content successfully written to {yml_path}")

        except Exception as e:
            print(f"Error writing to file: {e}")


    def extract_infofile_path_from_sh(self, file_path):
        self.print_method_name()
        variables = {}
        with open(file_path, 'r') as file:
            for line in file:
                if line.startswith('export '):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].replace('export ', '').strip()
                        value = parts[1].strip().strip('"')
                        variables[key] = value
        #print(f"Variables: {variables}")
        return variables
                
    def find_sh_files(self, directory):
        self.print_method_name()
        sh_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(".sh"):
                    sh_files.append(os.path.join(root, file))
        return sh_files

    def find_and_save_lnk_files(self, wineprefix):
        self.print_method_name()
        drive_c = wineprefix / "drive_c" / "ProgramData"
        found_lnk_files_path = wineprefix / "found_lnk_files.yaml"
        lnk_files = []

        for root, dirs, files in os.walk(drive_c):
            for file in files:
                file_path = Path(root) / file

                if file_path.suffix.lower() == ".lnk" and file_path.is_file():
                    print(f"Found .lnk file: {file_path}")
                    lnk_files.append(file_path.name)

        # Read existing found_lnk_files if the file exists
        if found_lnk_files_path.exists():
            with open(found_lnk_files_path, 'r') as file:
                existing_lnk_files = yaml.safe_load(file) or []
        else:
            existing_lnk_files = []

        # Merge found lnk files with existing ones, avoiding duplicates
        updated_lnk_files = list(set(existing_lnk_files + lnk_files))

        # Save the updated list back to found_lnk_files.yaml
        with open(found_lnk_files_path, 'w') as file:
            yaml.dump(updated_lnk_files, file, default_style="'", default_flow_style=False, width=10000)

        print(f"Saved {len(lnk_files)} .lnk files to {found_lnk_files_path}")
        self.load_script_list(wineprefix)

    def parse_info_file(self, file_path):
        self.print_method_name()
        info_data = {}
        with open(file_path, 'r') as file:
            for line in file:
                if ':' in line:
                    key, value = line.split(':', 1)
                    info_data[key.strip()] = value.strip()
        return info_data



    def add_charm_files_to_script_list(self, extracted_prefix_dir):
        self.print_method_name()
        """
        Find all .charm files in the extracted prefix directory and add them to self.script_list.
        
        Args:
            extracted_prefix_dir: The directory where the Wine prefix has been extracted.
        """
        # Look for all .charm files in the extracted directory
        charm_files = list(Path(extracted_prefix_dir).rglob("*.charm"))  # Recursively find all .charm files
        
        if not charm_files:
            print(f"No .charm files found in {extracted_prefix_dir}")
            #GLib.idle_add(self.show_initializing_step, "Checking Available Disk Space")
            return

        print(f"Found {len(charm_files)} .charm files in {extracted_prefix_dir}")

        for charm_file in charm_files:
            try:
                with open(charm_file, 'r') as file:
                    script_data = yaml.safe_load(file)  # Load the YAML content from the .charm file
                    
                    if not isinstance(script_data, dict):
                        print(f"Invalid format in {charm_file}")
                        continue

                    # Extract the script key (e.g., sha256sum) from the loaded data
                    script_key = script_data.get('sha256sum')
                    if not script_key:
                        print(f"Missing 'sha256sum' in {charm_file}, skipping...")
                        continue

                    # Add the new script data directly to self.script_list
                    self.new_scripts.add(charm_file.stem)
                    # Set 'script_path' to the charm file itself if not already set
                    script_data['script_path'] = str(charm_file.expanduser().resolve())
                    self.script_list = {script_key: script_data, **self.script_list}
                    # Add to self.script_list using the script_key
                    self.script_list[script_key] = script_data
                    print(f"Added {charm_file} to script_list with key {script_key}")

                    # Update the timestamp of the .charm file
                    charm_file.touch()
                    print(f"Updated timestamp for {charm_file}")
                    
            except Exception as e:
                print(f"Error loading .charm file {charm_file}: {e}")
        
        # Once done, update the UI
       # GLib.idle_add(self.create_script_list)

        
    def on_restore_completed(self):
        self.print_method_name()
        """
        Called when the restore process is complete. Updates UI, restores scripts, and resets the open button.
        """
        # Reconnect open button and reset its label
        
        #if self.open_button_handler_id is not None:
         #   self.open_button.disconnect(self.open_button_handler_id)
        #self.disconnect_open_button()
        #self.set_open_button_label("Open")
        #self.set_open_button_icon_visible(True)
        self.hide_processing_spinner()
        self.reconnect_open_button()


        # Restore the script list in the flowbox
        GLib.idle_add(self.create_script_list)

        print("Restore process completed and script list restored.")

    def extract_backup(self, file_path):
        self.print_method_name()
        """
        Extract the .tar.zst backup to the Wine prefixes directory with proper process management.
        """
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")

        try:
            # Get the prefix directory using the dedicated method
            extracted_prefix_dir = self.extract_prefix_dir(file_path)
            if not extracted_prefix_dir:
                raise Exception("Failed to determine the prefix directory from the backup.")

            print(f"Extracted prefix directory: {extracted_prefix_dir}")

            # Create a new process group
            def preexec_function():
                os.setpgrp()

            # Extract the archive with process tracking
            extract_process = subprocess.Popen(
                ['tar', '-I', 'zstd -T0', '-xf', file_path, '-C', self.prefixes_dir,
                 "--transform", rf"s|XOUSERXO|{current_username}|g", 
                 "--transform", rf"s|%USERNAME%|{current_username}|g"],
                preexec_fn=preexec_function
            )
            
            with self.process_lock:
                self.current_process = extract_process

            while extract_process.poll() is None:
                if self.stop_processing:
                    print("Cancellation requested, terminating tar process...")
                    self._kill_current_process()
                    
                    # Clean up partially extracted files
                    if extracted_prefix_dir.exists():
                        print(f"Cleaning up partially extracted files at {extracted_prefix_dir}")
                        shutil.rmtree(extracted_prefix_dir, ignore_errors=True)
                    
                    raise Exception("Operation cancelled by user")
                time.sleep(0.1)

            if extract_process.returncode != 0:
                raise Exception(f"Tar extraction failed with return code {extract_process.returncode}")

            return extracted_prefix_dir

        except Exception as e:
            print(f"Error during extraction: {e}")
            if "Operation cancelled by user" not in str(e):
                raise
            return None
        finally:
            with self.process_lock:
                self.current_process = None

    def _kill_current_process(self):
        self.print_method_name()
        """
        Helper method to kill the current process and its process group.
        """
        with self.process_lock:
            if self.current_process:
                try:
                    # Kill the entire process group
                    pgid = os.getpgid(self.current_process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    
                    # Give it a moment to terminate gracefully
                    try:
                        self.current_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # If it doesn't terminate gracefully, force kill
                        os.killpg(pgid, signal.SIGKILL)
                    
                    return True
                except ProcessLookupError:
                    # Process already terminated
                    return True
                except Exception as e:
                    print(f"Error killing process: {e}")
                    return False
        return False


    def extract_prefix_dir(self, file_path):
        self.print_method_name()
        """
        Return the extracted prefix directory for the backup file.
        This method ensures that only the first directory is returned, not individual files.
        """
        try:
            # Extract only directories by filtering those that end with '/'
            extracted_prefix_name = subprocess.check_output(
                ["bash", "-c", f"tar -tf '{file_path}' | head -n2 | grep '/$' |head -n1 | cut -f1 -d '/'"]
            ).decode('utf-8').strip()
            print(f"extracted_prefix_name={extracted_prefix_name}")

            # Handle .tar.zst or .wzt with ./ or ../ in the directory name
            if extracted_prefix_name == '.' or extracted_prefix_name == '..':
                extracted_prefix_name = subprocess.check_output(
                ["bash", "-c", f"tar -tf '{file_path}' | head -n2 | grep '/$' |head -n1 | cut -f2 -d '/'"]
            ).decode('utf-8').strip()
                print(f"extracted_prefix_name={extracted_prefix_name}")

            if not extracted_prefix_name:
                raise Exception("No directory found in the tar archive.")
            

            # Print the correct path for debugging
            extracted_prefix_path = Path(self.prefixes_dir) / extracted_prefix_name
            print("_" * 100)
            print(extracted_prefix_name)
            print(extracted_prefix_path)
            
            return extracted_prefix_path
        except subprocess.CalledProcessError as e:
            print(f"Error extracting prefix directory: {e}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None


    def check_disk_space_and_show_step(self, file_path):
        self.print_method_name()
        """
        Check available disk space and the uncompressed size of the backup file, showing this as a step.
        First checks if compressed file size is < 1/4 of available space for quick approval.
        """
        # Update the UI to indicate that disk space is being checked
        #GLib.idle_add(self.show_initializing_step, "Checking Available Disk Space")

        # Perform the quick disk space check first
        enough_space, available_space, size_to_check = self.check_disk_space_quick(self.prefixes_dir, file_path)

        if not enough_space:
            # Show warning about disk space
            GLib.idle_add(self.show_info_dialog, "Insufficient Disk Space",
                        f"The estimated required space is {size_to_check / (1024 * 1024):.2f} MB, "
                        f"but only {available_space / (1024 * 1024):.2f} MB is available. Please free up space.")
            return False

        # If enough space, update the UI and log the success
        message = f"Disk space check passed: {size_to_check / (1024 * 1024):.2f} MB required"
        GLib.idle_add(self.show_initializing_step, message)
        print(message)
        GLib.idle_add(self.mark_step_as_done, message)
        return True

    def check_disk_space_quick(self, prefixes_dir, file_path):
        self.print_method_name()
        """
        Quick check of disk space by comparing compressed file size with available space.
        Only if compressed size is > 10x of available space, we need the full uncompressed check.
        
        Args:
            prefixes_dir (Path): The directory where the wine prefixes are stored.
            file_path (str): Path to the backup .tar.zst file.

        Returns:
            (bool, int, int): Tuple containing:
                - True if there's enough space, False otherwise
                - Available disk space in bytes
                - Size checked (either compressed or uncompressed) in bytes
        """
        try:
            # Get available disk space
            df_output = subprocess.check_output(['df', '--output=avail', str(prefixes_dir)]).decode().splitlines()[1]
            available_space = int(df_output.strip()) * 1024  # Convert KB to bytes

            # Get compressed file size
            compressed_size = Path(file_path).stat().st_size

            # If compressed file is less than 10x of available space, we're safe to proceed
            if compressed_size * 10 <= available_space:
                print(f"Quick check passed - Compressed size: {compressed_size / (1024 * 1024):.2f} MB")
                return True, available_space, compressed_size

            # Otherwise, check the actual uncompressed size
            uncompressed_size = self.get_total_uncompressed_size(file_path)
            return available_space >= uncompressed_size, available_space, uncompressed_size

        except (subprocess.CalledProcessError, OSError) as e:
            print(f"Error checking disk space: {e}")
            return False, 0, 0

    def connect_open_button_with_restore_backup_cancel(self):
        self.print_method_name()
        """
        Connect cancel handler to the open button
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_restore_backup_clicked)
        
        self.set_open_button_icon_visible(False)

    def on_cancel_restore_backup_clicked(self, button):
        self.print_method_name()
        """
        Handle cancel button click with immediate process termination
        """
        dialog = Adw.AlertDialog(
            title="Cancel Restoring Backup?",
            body="This will immediately stop the extraction process. Any partially extracted files will be cleaned up."
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Restore")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_restore_backup_dialog_response)
        dialog.present(self.window,)

    def on_cancel_restore_backup_dialog_response(self, dialog, response):
        self.print_method_name()
        """
        Handle cancel dialog response with cleanup
        """
        if response == "cancel":
            self.stop_processing = True
            dialog.close()
            
            def cleanup():
                try:
                    self._kill_current_process()
                    GLib.idle_add(self.on_restore_completed)
                    GLib.idle_add(self.show_info_dialog, "Cancelled", 
                                "Restore process was cancelled and cleaned up successfully")
                except Exception as e:
                    print(f"Error during cleanup: {e}")
                    GLib.idle_add(self.show_info_dialog, "Error", 
                                f"Error during cleanup: {str(e)}")
            
            # Run cleanup in a separate thread to avoid blocking the UI
            threading.Thread(target=cleanup).start()
        else:
            self.stop_processing = False
            dialog.close()


#################3 Replace strings update with interruption

    def replace_strings_in_files(self, directory, find_replace_pairs):
        self.print_method_name()
        """
        Replace strings in files with interruption support, progress tracking and error handling
        """
        try:
            # Count total files for progress tracking
            total_files = sum(1 for _, _, files in os.walk(directory) 
                            for _ in files)
            processed_files = 0

            for root, dirs, files in os.walk(directory):
                if self.stop_processing:
                    raise Exception("Operation cancelled by user")

                for file in files:
                    if self.stop_processing:
                        raise Exception("Operation cancelled by user")

                    processed_files += 1
                    file_path = Path(root) / file

                    # Update progress
                    if hasattr(self, 'progress_bar'):
                        GLib.idle_add(
                            lambda: self.progress_bar.set_fraction(processed_files / total_files)
                        )

                    # Skip binary files
                    if self.is_binary_file(file_path):
                        #print(f"Skipping binary file: {file_path}")
                        continue

                    # Skip files where permission is denied
                    if not os.access(file_path, os.R_OK | os.W_OK):
                        #print(f"Skipping file: {file_path} (Permission denied)")
                        continue

                    try:
                        # Read file content
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        modified = False
                        new_content = content

                        # Perform replacements
                        for find_str, replace_str in find_replace_pairs.items():
                            if find_str in new_content:
                                new_content = new_content.replace(find_str, replace_str)
                                modified = True

                        # Write modified content if changes were made
                        if modified:
                            if self.stop_processing:
                                raise Exception("Operation cancelled by user")
                            
                            # Create temporary file
                            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
                            try:
                                with open(temp_path, 'w', encoding='utf-8') as f:
                                    f.write(new_content)
                                # Atomic replace
                                temp_path.replace(file_path)
                                print(f"Replacements applied to file: {file_path}")
                            except Exception as e:
                                if temp_path.exists():
                                    temp_path.unlink()
                                raise e

                    except (UnicodeDecodeError, FileNotFoundError, PermissionError) as e:
                        #   print(f"Skipping file: {file_path} ({e})")
                        continue

        except Exception as e:
            if "Operation cancelled by user" in str(e):
                print("String replacement operation cancelled")
            raise

    def is_binary_file(self, file_path):
        #self.print_method_name()
        """
        Check if a file is binary with interruption support
        """
        try:
            if self.stop_processing:
                raise Exception("Operation cancelled by user")
                
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                if b'\0' in chunk:
                    return True
        except Exception as e:
            if "Operation cancelled by user" in str(e):
                raise
            #print(f"Could not check file {file_path} ({e})")
        return False


##################################################################################### 
    def get_template_arch(self, template_path):
        self.print_method_name()
        """Extract architecture from template's system.reg file"""
        system_reg = Path(template_path) / "system.reg"
        if not system_reg.exists():
            return "win64"  # Default assumption
        
        try:
            with open(system_reg, "r") as f:
                for line in f:
                    if line.startswith("#arch="):
                        return line.strip().split("=")[1].lower()
        except Exception as e:
            print(f"Error reading {system_reg}: {e}")
        
        return "win64"  # Fallback if not found

    def set_default_template(self, action=None):
        self.print_method_name()
        """Set default template with architecture auto-detection and update"""
        # Collect templates with architecture info
        templates = []
        for template_dir in self.templates_dir.iterdir():
            if template_dir.is_dir() and (template_dir / "system.reg").exists():
                arch = self.get_template_arch(template_dir)
                display_name = f"{template_dir.name} ({arch.upper()})"
                templates.append((display_name, str(template_dir.resolve()), arch))

        # Add default templates if they exist
        default_templates = [
            (self.default_template_win64, "win64"),
            (self.default_template_win32, "win32")
        ]
        for dt_path, dt_arch in default_templates:
            if dt_path.exists() and not any(str(dt_path) == t[1] for t in templates):
                display_name = f"{dt_path.name} ({dt_arch.upper()})"
                templates.append((display_name, str(dt_path.resolve()), dt_arch))

        if not templates:
            self.show_info_dialog("No Templates", "No valid templates found.")
            return

        # Create dropdown list
        template_list = Gtk.StringList()
        current_template = self.expand_and_resolve_path(self.settings.get('template', ""))
        current_index = 0
        
        # Sort templates and find current selection
        sorted_templates = sorted(templates, key=lambda x: x[0].lower())
        for i, (display, path, arch) in enumerate(sorted_templates):
            template_list.append(display)
            if Path(path) == current_template:
                current_index = i

        dropdown = Gtk.DropDown(model=template_list, selected=current_index)
        dropdown.set_hexpand(True)

        # Dialog layout
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.append(Gtk.Label(label="Select template:"))
        content.append(dropdown)

        dialog = Adw.AlertDialog(
            heading="Set Default Template",
            body="Template architecture will be set automatically",
            extra_child=content
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Save")
        dialog.set_default_response("ok")

        def on_response(dialog, response_id):
            self.print_method_name()
            if response_id == "ok":
                selected_idx = dropdown.get_selected()
                if selected_idx != Gtk.INVALID_LIST_POSITION:
                    # Get selected template data
                    display_name, template_path, arch = sorted_templates[selected_idx]
                    
                    # Update settings
                    self.settings['template'] = self.replace_home_with_tilde_in_path(template_path)
                    self.settings['arch'] = arch
                    
                    # Update instance variables
                    self.template = Path(template_path).resolve()
                    self.arch = arch
                    
                    self.save_settings()
                    
                    self.show_info_dialog(
                        "Template Updated",
                        f"Set default template to:\n{display_name}\n"
                        f"Architecture: {arch.upper()}"
                    )
        dialog.connect("response", on_response)
        dialog.present(self.window)

############# Delete template
    def delete_template(self, action=None):
        self.print_method_name()
        """Delete a template directory with safety checks and settings updates"""
        self.load_settings()  # Ensure fresh settings
        current_arch = self.settings.get('arch', 'win64')
        self.template = self.settings.get('template', self.default_template_win64)
        print("-="*50)
        # Resolve default template paths for current architecture
        default_templates = {
            'win64': self.default_template_win64.expanduser().resolve(),
            'win32': self.default_template_win32.expanduser().resolve()
        }
        current_default = default_templates[current_arch]

        # Collect templates with architecture info
        templates = []
        for template_dir in self.templates_dir.iterdir():
            tpl_path = template_dir.resolve()
            if template_dir.is_dir() and (template_dir / "system.reg").exists():
                arch = self.get_template_arch(template_dir)
                display_name = f"{template_dir.name} ({arch.upper()})"
                is_current_default = (tpl_path == current_default)
                templates.append((display_name, tpl_path, arch, is_current_default))

        if not templates:
            self.show_info_dialog("No Templates", "No templates found to delete.")
            return

        # Create dialog components
        dialog = Adw.AlertDialog(
            heading="Delete Template",
            body="Select a template to permanently delete:"
        )

        # Create dropdown with template names
        model = Gtk.StringList.new([name for name, _, _, _ in templates])
        dropdown = Gtk.DropDown(model=model)
        dropdown.set_selected(0)

        # Add to dialog content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(dropdown)
        dialog.set_extra_child(content_box)

        # Configure dialog buttons
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_default_response("delete")

        def on_response(dialog, response_id, dropdown, templates):
            self.print_method_name()
            if response_id == "delete":
                selected_idx = dropdown.get_selected()
                if 0 <= selected_idx < len(templates):
                    display_name, template_path, template_arch, is_current_default = templates[selected_idx]
                    
                    # Immediate prevention checks
                    if is_current_default:
                        self.show_info_dialog(
                            "Protected Template",
                            f"Cannot delete the active / default {current_arch} template!\n"
                            "Switch architectures / template first to delete this template."
                        )
                        return

                    # Deletion execution
                    def perform_deletion():
                        try:
                            shutil.rmtree(template_path)
                            # Clear settings reference if needed
                            if self.settings.get('template', '') == str(template_path):
                                self.settings['template'] = ''
                                self.save_settings()
                            self.show_info_dialog("Deleted", f"Removed: {display_name}")
                        except Exception as e:
                            self.show_info_dialog("Error", f"Deletion failed: {str(e)}")

                    # Additional confirmation for non-default templates
                    confirm_dialog = Adw.AlertDialog(
                        heading="Confirm Deletion",
                        body=f"Permanently delete:\n{display_name}?"
                    )
                    confirm_dialog.add_response("cancel", "Keep")
                    confirm_dialog.add_response("delete", "Delete Forever")
                    confirm_dialog.connect("response", 
                        lambda d, r: perform_deletion() if r == "delete" else None
                    )
                    confirm_dialog.present(self.window)

            dialog.close()

        dialog.connect("response", on_response, dropdown, templates)
        dialog.present(self.window)

################## import template
    def import_template(self, action=None, param=None):
        self.print_method_name()
        """Import a Wine directory as a template into the templates directory."""
        file_dialog = Gtk.FileDialog.new()
        file_dialog.set_modal(True)
        file_dialog.select_folder(self.window, None, self.on_import_template_response)

    def on_import_template_response(self, dialog, result):
        self.print_method_name()
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                src = Path(folder.get_path())
                if not (src / "system.reg").exists():
                    GLib.idle_add(self.show_info_dialog, "Invalid Template", 
                                "Selected directory is not a valid Wine prefix")
                    return

                template_name = src.name
                dst = self.templates_dir / template_name
                backup_dir = self.templates_dir / f"{template_name}_backup_{int(time.time())}"

                steps = [
                    ("Verifying template", lambda: self.verify_template_source(src)),
                    ("Backing up existing template", lambda: self.backup_existing_directory(dst, backup_dir)),
                    ("Copying template files", lambda: self.custom_copytree(src, dst)),
                    ("Processing registry files", lambda: self.process_reg_files(dst)),
                    ("Standardizing user directories", lambda: self.rename_and_merge_user_directories(dst)),
                    ("Cleaning template files", lambda: self.clean_template_files(dst)),
                ]

                self.show_processing_spinner(f"Importing {template_name}")
                self.connect_open_button_with_import_wine_directory_cancel()
                threading.Thread(target=self.process_template_import, args=(steps, dst, backup_dir)).start()

        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"Template import error: {e}")

    def process_template_import(self, steps, dst, backup_dir):
        self.print_method_name()
        """Handle template import with error handling and rollback"""
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
                        f"Template '{dst.name}' imported successfully")
            self.cleanup_backup(backup_dir)

        except Exception as e:
            GLib.idle_add(self.handle_template_import_error, dst, backup_dir, str(e))
            
        finally:
            GLib.idle_add(self.on_import_template_directory_completed)

    def verify_template_source(self, src):
        self.print_method_name()
        """Validate the source directory contains a valid Wine prefix"""
        required_files = ["system.reg", "userdef.reg", "dosdevices"]
        missing = [f for f in required_files if not (src / f).exists()]
        if missing:
            raise Exception(f"Missing required Wine files: {', '.join(missing)}")

    def clean_template_files(self, template_path):
        self.print_method_name()
        """Remove unnecessary files from the template"""
        # Remove any existing charm files
        for charm_file in template_path.glob("*.charm"):
            charm_file.unlink()
        
        # Clean desktop files
        applications_dir = template_path / "drive_c/users" / os.getenv("USER") / "Desktop"
        if applications_dir.exists():
            for desktop_file in applications_dir.glob("*.desktop"):
                desktop_file.unlink()

    def handle_template_import_error(self, dst, backup_dir, error_msg):
        self.print_method_name()
        """Handle template import errors and cleanup"""
        try:
            if dst.exists():
                shutil.rmtree(dst)
            if backup_dir.exists():
                backup_dir.rename(dst)
        except Exception as e:
            error_msg += f"\nCleanup error: {str(e)}"
        
        self.show_info_dialog("Template Import Failed", error_msg)
    
    def on_import_template_directory_completed(self):
        self.print_method_name()
        """
        Called when the template import process is complete. Updates UI, restores scripts, and resets the open button.
        """
        # Reconnect open button and reset its label
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        
        self.hide_processing_spinner()

        # This will disconnect open_button handler, use this then reconnect the open
        #if self.open_button_handler_id is not None:
        #    self.open_button.disconnect(self.open_button_handler_id)

        self.reconnect_open_button()
        self.show_options_for_settings()
        print("Template directory import completed.")
        
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

########################## fix default runner to handle arch difference
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

##### Template Backup
    def backup_template(self, action=None):
        self.print_method_name()
        """
        Allow the user to backup a template with interruptible process.
        """
        all_templates = [t.name for t in self.templates_dir.iterdir() if t.is_dir()]
        if not all_templates:
            self.show_info_dialog("No Templates Available", "No templates found to backup.")
            return

        dialog = Adw.AlertDialog(
            heading="Backup Template",
            body="Select a template to backup:"
        )
        model = Gtk.StringList.new(all_templates)
        dropdown = Gtk.DropDown(model=model)
        dropdown.set_selected(0)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(dropdown)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")
        dialog.set_extra_child(content_box)

        dialog.connect("response", self.on_backup_template_response, dropdown, all_templates)
        dialog.present(self.window)

    def on_backup_template_response(self, dialog, response_id, dropdown, templates):
        self.print_method_name()
        if response_id == "ok":
            selected_index = dropdown.get_selected()
            if 0 <= selected_index < len(templates):
                template_name = templates[selected_index]
                template_path = self.templates_dir / template_name

                file_dialog = Gtk.FileDialog.new()
                file_dialog.set_initial_name(f"{template_name}.template")
                file_filter = Gtk.FileFilter()
                file_filter.set_name("Template Archives")
                file_filter.add_pattern("*.template")
                filters = Gio.ListStore.new(Gtk.FileFilter)
                filters.append(file_filter)
                file_dialog.set_filters(filters)

                def on_save_response(dlg, result):
                    try:
                        save_file = dlg.save_finish(result)
                        if save_file:
                            dest_path = save_file.get_path()
                            threading.Thread(
                                target=self.create_template_backup,
                                args=(template_path, dest_path)
                            ).start()
                    except GLib.Error as e:
                        if e.domain == 'gtk-dialog-error-quark' and e.code == 2:
                            print("Backup Template Cancelled!")
                            return
                        print(f"Backup Template failedfailed: {e}")

                file_dialog.save(self.window, None, on_save_response)
        dialog.close()

    def create_template_backup(self, template_path, dest_path):
        self.print_method_name()
        """
        Create compressed template archive using zstd compression with interruptible progress.
        """
        self.stop_processing = False
        self.current_backup_path = dest_path
        usershome = os.path.expanduser('~')
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")
        find_replace_pairs = {usershome: '~', f'\'{usershome}': '\'~\''}
        find_replace_media_username = {f'/media/{current_username}/': '/media/%USERNAME%/'}
        restore_media_username = {'/media/%USERNAME%/': f'/media/{current_username}/'}

        def perform_backup_steps():
            self.print_method_name()
            try:
                steps = [
                    (f"Replace \"{usershome}\" with '~' in files", lambda: self.replace_strings_in_files(template_path, find_replace_pairs)),
                    ("Reverting user-specific .reg changes", lambda: self.reverse_process_reg_files(template_path)),
                    (f"Replace \"/media/{current_username}\" with '/media/%USERNAME%' in files", lambda: self.replace_strings_in_files(template_path, find_replace_media_username)),
                    ("Creating backup archive", lambda: run_backup()),
                    ("Re-applying user-specific .reg changes", lambda: self.process_reg_files(template_path)),
                    (f"Revert %USERNAME% with \"{current_username}\" in script files", lambda: self.replace_strings_in_files(template_path, restore_media_username)),
                ]

                self.total_steps = len(steps)
                
                for step_text, step_func in steps:
                    if self.stop_processing:
                        GLib.idle_add(self.cleanup_cancelled_template_backup)
                        return

                    GLib.idle_add(self.show_initializing_step, step_text)
                    try:
                        # Run step and handle output
                        step_func()
                        if self.stop_processing:
                            GLib.idle_add(self.cleanup_cancelled_template_backup)
                            return
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        if not self.stop_processing:
                            GLib.idle_add(self.show_info_dialog, "Backup Failed", 
                                        f"Error during '{step_text}': {e}")
                        GLib.idle_add(self.cleanup_cancelled_template_backup)
                        return

                GLib.idle_add(self.show_info_dialog, "Backup Complete", 
                            f"Template saved to {dest_path}")
            finally:
                GLib.idle_add(self.hide_processing_spinner)
                GLib.idle_add(self.revert_open_button)

        def run_backup():
            self.print_method_name()
            if self.stop_processing:
                raise Exception("Operation cancelled by user")

            cmd = [
                'tar',
                '-I', 'zstd -T0',
                '--transform', f"s|{template_path.name}/drive_c/users/{current_username}|{template_path.name}/drive_c/users/%USERNAME%|g",
                '-cvf', dest_path,
                '-C', str(template_path.parent),
                template_path.name
            ]

            # Start process with piped output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            # Start output reader thread
            def read_output():
                self.print_method_name()
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        print(output.strip())

            output_thread = threading.Thread(target=read_output)
            output_thread.start()

            # Monitor process with periodic checks
            while process.poll() is None:
                if self.stop_processing:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                        if Path(dest_path).exists():
                            Path(dest_path).unlink()
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise Exception("Backup cancelled by user")
                time.sleep(0.1)

            output_thread.join()

            if process.returncode != 0 and not self.stop_processing:
                raise Exception(f"Backup failed with code {process.returncode}")

        self.show_processing_spinner("Exporting...")
        self.connect_cancel_button_for_template_backup()
        threading.Thread(target=perform_backup_steps, daemon=True).start()

    def connect_cancel_button_for_template_backup(self):
        self.print_method_name()
        if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_backup_clicked)
        self.set_open_button_label("Cancel")
        self.set_open_button_icon_visible(False)

    def on_cancel_template_backup_clicked(self, button):
        self.print_method_name()
        dialog = Adw.AlertDialog(
            heading="Cancel Backup",
            body="Do you want to cancel the template backup process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Backup")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_template_backup_dialog_response)
        dialog.present(self.window)

    def on_cancel_template_backup_dialog_response(self, dialog, response):
        self.print_method_name()
        if response == "cancel":
            self.stop_processing = True
        dialog.close()

    def cleanup_cancelled_template_backup(self):
        self.print_method_name()
        try:
            if hasattr(self, 'current_backup_path') and self.current_backup_path and Path(self.current_backup_path).exists():
                Path(self.current_backup_path).unlink()
        except Exception as e:
            print(f"Error deleting partial backup file: {e}")
        finally:
            self.hide_processing_spinner()
            self.show_info_dialog("Cancelled", "Template backup was cancelled")
            self.revert_open_button()

    def revert_open_button(self):
        self.print_method_name()
        """
        Cleanup after template restore completion.
        """
        self.hide_processing_spinner()
        self.reconnect_open_button()
        self.show_options_for_settings()
        print("Template created successfully")
    

#################### NEW RESTORE template like restore wzt
    def restore_template_from_backup(self, action=None, param=None):
        self.print_method_name()
        # Step 1: Create required directories if needed
        self.create_required_directories()

        # Step 2: Create a new Gtk.FileDialog instance
        file_dialog = Gtk.FileDialog.new()

        # Step 3: Create file filter for .wzt files only
        file_filter_wzt = Gtk.FileFilter()
        file_filter_wzt.set_name("WineCharm Template Files (*.template)")
        file_filter_wzt.add_pattern("*.template")

        # Step 4: Set the filter on the dialog
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        filter_model.append(file_filter_wzt)  # Only WZT files for templates
        file_dialog.set_filters(filter_model)

        # Step 5: Open the dialog and handle the response
        file_dialog.open(self.window, None, self.on_restore_template_file_dialog_response)

    def on_restore_template_file_dialog_response(self, dialog, result):
        self.print_method_name()
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = file.get_path()
                print(f"Selected template file: {file_path}")
                self.restore_template_tar_zst(file_path)
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")

    def restore_template_tar_zst(self, file_path):
        self.print_method_name()
        """
        Restore a template from a .wzt backup file to the templates directory.
        """
        self.stop_processing = False
        
        try:
            # Determine extracted template directory
            extracted_template = self.extract_template_dir(file_path)
            if not extracted_template:
                raise Exception("Failed to determine template directory name")
            
            # Handle existing directory
            backup_dir = None
            if extracted_template.exists():
                timestamp = int(time.time())
                backup_dir = extracted_template.parent / f"{extracted_template.name}_backup_{timestamp}"
                shutil.move(str(extracted_template), str(backup_dir))
                print(f"Backed up existing template directory to: {backup_dir}")

            # UI setup
            GLib.idle_add(self.flowbox.remove_all)
            self.show_processing_spinner("Restoring Template")
            self.connect_open_button_with_restore_backup_cancel()

            def restore_process():
                self.print_method_name()
                try:
                    # Get WZT restore steps modified for templates
                    restore_steps = self.get_template_restore_steps(file_path)

                    for step_text, step_func in restore_steps:
                        if self.stop_processing:
                            # Handle cancellation by restoring backup
                            if backup_dir and backup_dir.exists():
                                if extracted_template.exists():
                                    shutil.rmtree(extracted_template)
                                shutil.move(str(backup_dir), str(extracted_template))
                                print(f"Restored original template directory from: {backup_dir}")
                            GLib.idle_add(self.on_template_restore_completed)
                            return

                        GLib.idle_add(self.show_initializing_step, step_text)
                        try:
                            step_func()
                            GLib.idle_add(self.mark_step_as_done, step_text)
                        except Exception as e:
                            print(f"Error during step '{step_text}': {e}")
                            # Restore backup on failure
                            if backup_dir and backup_dir.exists():
                                if extracted_template.exists():
                                    shutil.rmtree(extracted_template)
                                shutil.move(str(backup_dir), str(extracted_template))
                            GLib.idle_add(self.show_info_dialog, "Error", f"Failed during step '{step_text}': {str(e)}")
                            return

                    # Cleanup backup after successful restore
                    if backup_dir and backup_dir.exists():
                        shutil.rmtree(backup_dir)
                        print(f"Removed backup directory: {backup_dir}")

                    GLib.idle_add(self.on_template_restore_completed)

                except Exception as e:
                    print(f"Error during template restore: {e}")
                    if backup_dir and backup_dir.exists():
                        if extracted_template.exists():
                            shutil.rmtree(extracted_template)
                        shutil.move(str(backup_dir), str(extracted_template))
                    GLib.idle_add(self.show_info_dialog, "Error", f"Template restore failed: {str(e)}")

            # Start restore thread
            threading.Thread(target=restore_process).start()

        except Exception as e:
            print(f"Error initiating template restore: {e}")
            GLib.idle_add(self.show_info_dialog, "Error", f"Failed to start template restore: {str(e)}")

    def extract_template_backup(self, file_path):
        self.print_method_name()
        """
        Extract template backup to templates directory with process management.
        """
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine current username")

        try:
            # Create new process group
            def preexec_function():
                os.setpgrp()

            # Get template name from archive
            list_process = subprocess.Popen(
                ['tar', '-tf', file_path],
                stdout=subprocess.PIPE,
                preexec_fn=preexec_function,
                universal_newlines=True
            )
            
            with self.process_lock:
                self.current_process = list_process
            
            if self.stop_processing:
                self._kill_current_process()
                raise Exception("Operation cancelled by user")
                
            output, _ = list_process.communicate()
            extracted_template_name = output.splitlines()[0].split('/')[0]
            extracted_template_dir = Path(self.templates_dir) / extracted_template_name

            print(f"Extracting template to: {extracted_template_dir}")

            # Extract archive
            extract_process = subprocess.Popen(
                ['tar', '-xf', file_path, '-C', self.templates_dir,
                "--transform", rf"s|XOUSERXO|{current_username}|g", 
                "--transform", rf"s|%USERNAME%|{current_username}|g"],
                preexec_fn=preexec_function
            )
            
            with self.process_lock:
                self.current_process = extract_process

            while extract_process.poll() is None:
                if self.stop_processing:
                    print("Cancelling template extraction...")
                    self._kill_current_process()
                    if extracted_template_dir.exists():
                        shutil.rmtree(extracted_template_dir, ignore_errors=True)
                    raise Exception("Operation cancelled by user")
                time.sleep(0.1)

            if extract_process.returncode != 0:
                raise Exception(f"Template extraction failed with code {extract_process.returncode}")

            return extracted_template_dir

        except Exception as e:
            print(f"Template extraction error: {e}")
            if "Operation cancelled by user" not in str(e):
                raise
            return None
        finally:
            with self.process_lock:
                self.current_process = None

    def extract_template_dir(self, file_path):
        self.print_method_name()
        """
        Determine template directory name from backup file.
        """
        try:
            extracted_template_name = subprocess.check_output(
                ["bash", "-c", f"tar -tf '{file_path}' | head -n2 | grep '/$' | head -n1 | cut -f1 -d '/'"]
            ).decode('utf-8').strip()

            if not extracted_template_name:
                raise Exception("No directory found in template archive")

            return Path(self.templates_dir) / extracted_template_name
        
        except subprocess.CalledProcessError as e:
            print(f"Error extracting template directory: {e}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_template_restore_steps(self, file_path):
        self.print_method_name()
        """
        Return steps for template restore using WZT format.
        """
        return [
            ("Checking Disk Space", lambda: self.check_template_disk_space(file_path)),
            ("Extracting Template File", lambda: self.extract_template_backup(file_path)),
            ("Processing Configuration Files", lambda: self.perform_replacements(self.extract_template_dir(file_path))),
            ("Updating Shortcut List", lambda: self.find_and_save_lnk_files(self.extract_template_dir(file_path))),
            ("Finalizing Template Structure", lambda: self.remove_symlinks_and_create_directories(self.extract_template_dir(file_path))),
            ("Replace symbolic links with directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
            ("Create Wineboot Required file", lambda: self.create_wineboot_required_file(self.extract_prefix_dir(file_path)))
        ]

    def check_template_disk_space(self, file_path):
        self.print_method_name()
        """
        Check disk space in templates directory against backup size.
        """
        try:
            # Get available space in templates directory
            df_output = subprocess.check_output(['df', '--output=avail', str(self.templates_dir)]).decode().splitlines()[1]
            available_space = int(df_output.strip()) * 1024  # Convert KB to bytes

            # Get compressed size
            compressed_size = Path(file_path).stat().st_size

            # Quick check if compressed size is less than 1/4 available space
            if compressed_size * 4 <= available_space:
                print(f"Quick space check passed for template")
                return True

            # Full check with uncompressed size
            uncompressed_size = self.get_total_uncompressed_size(file_path)
            if available_space >= uncompressed_size:
                print(f"Template disk space check passed")
                return True
            
            # Show error if insufficient space
            GLib.idle_add(
                self.show_info_dialog, "Insufficient Space",
                f"Need {uncompressed_size/(1024*1024):.1f}MB, only {available_space/(1024*1024):.1f}MB available."
            )
            return False

        except subprocess.CalledProcessError as e:
            print(f"Disk check error: {e}")
            return False

    def on_template_restore_completed(self):
        self.print_method_name()
        """
        Cleanup after template restore completion.
        """
        self.hide_processing_spinner()
        self.reconnect_open_button()
        self.show_options_for_settings()
        print("Template restore completed successfully")


################ clone template
    def clone_template(self, action=None):
        self.print_method_name()
        """
        Allow the user to clone a template with an editable name suggestion.
        """
        all_templates = [t.name for t in self.templates_dir.iterdir() if t.is_dir()]
        if not all_templates:
            self.show_info_dialog("No Templates Available", "No templates found to clone.")
            return

        dialog = Adw.AlertDialog(
            heading="Clone Template",
            body="Select a template to clone and enter a new name:"
        )

        # Template selection dropdown
        model = Gtk.StringList.new(all_templates)
        dropdown = Gtk.DropDown(model=model)
        dropdown.set_selected(0)

        # Editable name entry with placeholder
        entry = Gtk.Entry()
        entry.set_placeholder_text("Set Template Clone Name")
        entry.set_activates_default(True)
        
        # Connect signals
        dropdown.connect("notify::selected", self.on_template_selected_for_clone, entry, all_templates)
        entry.connect("changed", self.on_clone_name_changed, dropdown, all_templates)

        # Container layout
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(dropdown)
        content_box.append(entry)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")
        dialog.set_extra_child(content_box)

        dialog.connect("response", self.on_clone_template_response, dropdown, entry, all_templates)
        dialog.present(self.window)

    def on_template_selected_for_clone(self, dropdown, _pspec, entry, templates):
        self.print_method_name()
        """Update entry text when template selection changes"""
        selected_index = dropdown.get_selected()
        if 0 <= selected_index < len(templates):
            template_name = templates[selected_index]
            new_name = f"{template_name} (clone)"
            entry.set_text(new_name)
            entry.set_position(len(new_name))  # Move cursor to end

    def on_clone_name_changed(self, entry, dropdown, templates):
        self.print_method_name()
        """Real-time validation of clone name"""
        new_name = entry.get_text().strip()
        dest_path = self.templates_dir / new_name
        
        # Clear previous error styling
        entry.remove_css_class("error")
        
        # Validate new name
        if not new_name:
            entry.add_css_class("error")
        elif dest_path.exists():
            entry.add_css_class("error")

    def on_clone_template_response(self, dialog, response_id, dropdown, entry, templates):
        self.print_method_name()
        if response_id == "ok":
            selected_index = dropdown.get_selected()
            new_name = entry.get_text().strip()

            if 0 <= selected_index < len(templates):
                source_name = templates[selected_index]
                source_path = self.templates_dir / source_name
                dest_path = self.templates_dir / new_name

                # Final validation
                if not new_name:
                    self.show_info_dialog("Invalid Name", "Please enter a name for the clone.")
                    return
                if dest_path.exists():
                    self.show_info_dialog("Error", "A template with this name already exists.")
                    return

                # Start cloning process
                self.show_processing_spinner("Cloning template...")
                threading.Thread(
                    target=self.perform_template_clone,
                    args=(source_path, dest_path),
                    daemon=True
                ).start()

        dialog.close()

    def perform_template_clone(self, source_path, dest_path):
        self.print_method_name()
        """Perform the actual directory copy with error handling"""
        try:
            self.custom_copytree(source_path, dest_path)
            GLib.idle_add(self.show_info_dialog, 
                "Clone Successful", 
                f"Successfully cloned to {dest_path.name}"
            )
        except Exception as e:
            GLib.idle_add(self.show_info_dialog,
                "Clone Error",
                f"An error occurred: {str(e)}"
            )
        finally:
            GLib.idle_add(self.on_template_restore_completed)

########### Create Template
    def create_template(self, action=None):
        self.print_method_name()
        dialog = Adw.AlertDialog(
            heading="Create Template",
            body="Enter a name and select architecture:"
        )
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        entry = Gtk.Entry()
        entry.set_placeholder_text("Template Name")
        content_box.append(entry)
        
        radio_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        win32_radio = Gtk.CheckButton(label="32-bit (win32)")
        win64_radio = Gtk.CheckButton(label="64-bit (win64)")
        win64_radio.set_group(win32_radio)
        win64_radio.set_active(True)
        radio_box.append(win32_radio)
        radio_box.append(win64_radio)
        content_box.append(radio_box)
        
        dialog.set_extra_child(content_box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        
        def on_response(dialog, response):
            self.print_method_name()
            if response == "ok":
                name = entry.get_text().strip()
                if not name:
                    self.show_info_dialog("Invalid Name", "Please enter a valid name.")
                else:
                    arch = "win32" if win32_radio.get_active() else "win64"
                    prefix_dir = self.templates_dir / name
                    self.called_from_settings = True
                    self.initialize_template(prefix_dir, callback=None, arch=arch)

            dialog.close()
        
        dialog.connect("response", on_response)
        dialog.present(self.window)


    def configure_template(self, action=None):
        pass


###################### 0.95























def parse_args():
    WineCharmApp().print_method_name()
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(description="WineCharm GUI application or headless mode for .charm files")
    parser.add_argument('file', nargs='?', help="Path to the .exe, .msi, .charm, .bottle, .prefix, or .wzt file")
    return parser.parse_args()

def main():

    WineCharmApp().print_method_name()
    args = parse_args()

    # Create an instance of WineCharmApp
    app = WineCharmApp()

    # If a file is provided, handle it appropriately
    if args.file:
        file_path = Path(args.file).expanduser().resolve()
        file_extension = file_path.suffix.lower()

        # If it's a .charm file, launch it without GUI
        if file_extension == '.charm':
            try:
                # Load the .charm file data
                with open(file_path, 'r', encoding='utf-8') as file:
                    script_data = yaml.safe_load(file)

                exe_file = script_data.get("exe_file")
                if not exe_file:
                    print("Error: No executable file defined in the .charm script.")
                    sys.exit(1)

                # Prepare to launch the executable
                exe_path = Path(exe_file).expanduser().resolve()
                if not exe_path.exists():
                    print(f"Error: Executable '{exe_path}' not found.")
                    sys.exit(1)

                # Extract additional environment and arguments

                # if .charm file has script_path use it
                wineprefix_path_candidate = script_data.get('script_path')

                if not wineprefix_path_candidate:  # script_path not found
                    # if .charm file has wineprefix in it, then use it
                    wineprefix_path_candidate = script_data.get('wineprefix')
                    if not wineprefix_path_candidate:  # if wineprefix not found
                        wineprefix_path_candidate = file_path  # use the current .charm file's path

                # Resolve the final wineprefix path
                wineprefix = Path(wineprefix_path_candidate).parent.expanduser().resolve()

                env_vars = script_data.get("env_vars", "").strip()
                script_args = script_data.get("args", "").strip()
                runner = script_data.get("runner", "wine")

                # Resolve runner path
                if runner:
                    runner = Path(runner).expanduser().resolve()
                    runner_dir = str(runner.parent.expanduser().resolve())
                    path_env = f'export PATH="{runner_dir}:$PATH"'
                else:
                    runner = "wine"
                    runner_dir = ""  # Or set a specific default if required
                    path_env = ""

                # Prepare the command safely using shlex for quoting
                exe_parent = shlex.quote(str(exe_path.parent.resolve()))
                wineprefix = shlex.quote(str(wineprefix))
                runner = shlex.quote(str(runner))

                # Construct the command parts
                command_parts = []

                # Add path to runner if it exists
                if path_env:
                    command_parts.append(f"{path_env}")

                # Change to the executable's directory
                command_parts.append(f"cd {exe_parent}")

                # Add environment variables if present
                if env_vars:
                    command_parts.append(f"{env_vars}")

                # Add wineprefix and runner
                command_parts.append(f"WINEPREFIX={wineprefix} {runner} {shlex.quote(str(exe_path))}")

                # Process .charm file arguments and paths
                script_args = script_data.get("args", "").strip()
                if script_args:
                    # Expand $WINEPREFIX if present
                    script_args = script_args.replace('$WINEPREFIX', str(wineprefix))
                    args_list, current_arg = [], []
                    for part in script_args.split():
                        if part.startswith('-'):
                            if current_arg:
                                args_list.append(' '.join(current_arg))
                                current_arg = []
                            args_list.append(part)
                        else:
                            current_arg.append(part)
                    if current_arg:
                        args_list.append(' '.join(current_arg))
                    processed_script_args = ' '.join(shlex.quote(arg) for arg in args_list)
                else:
                    processed_script_args = ""

                # Construct the command
                command_parts = []
                if path_env:
                    command_parts.append(path_env)
                command_parts.append(f"cd {exe_parent}")
                if env_vars:
                    command_parts.append(env_vars)
                command_parts.append(f"WINEPREFIX={wineprefix} {runner} {shlex.quote(str(exe_path))} {processed_script_args}")

                # Join all the command parts
                command = " && ".join(command_parts)

                print(f"Executing: {command}")
                subprocess.run(command, shell=True)


                # Exit after headless execution to ensure no GUI elements are opened
                sys.exit(0)

            except Exception as e:
                print(f"Error: Unable to launch the .charm script: {e}")
                sys.exit(1)

        # For .exe, .msi, .bottle, .prefix, or .wzt files, handle via GUI mode
        elif file_extension in ['.exe', '.msi', '.bottle', '.prefix', '.wzt']:
            if app.SOCKET_FILE.exists():
                try:
                    # Send the file to an existing running instance
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.connect(str(app.SOCKET_FILE))
                        message = f"process_file||{args.file}"
                        client.sendall(message.encode())
                        print(f"Sent file path to existing instance: {args.file}")
                    return
                except ConnectionRefusedError:
                    print("No existing instance found, starting a new one.")

            # If no existing instance is running, proceed with normal startup and processing
            app.command_line_file = args.file

        else:
            # Check if it's a supported backup file type
            if file_extension in ['.bottle', '.prefix', '.wzt']:
                app.command_line_file = args.file
            else:
                # Invalid file type, print error and handle accordingly
                print(f"Invalid file type: {file_extension}. Only .exe, .msi, .charm, .bottle, .prefix, or .wzt files are allowed.")

                # If no instance is running, start WineCharmApp and show the error dialog directly
                if not app.SOCKET_FILE.exists():
                    app.start_socket_server()
                    GLib.timeout_add_seconds(1.5, app.show_info_dialog, "Invalid File Type", f"Only .exe, .msi, .charm, .bottle, .prefix, or .wzt files are allowed. You provided: {file_extension}")
                    app.run(sys.argv)

                    # Clean up the socket file
                    if app.SOCKET_FILE.exists():
                        app.SOCKET_FILE.unlink()
                else:
                    # If an instance is running, send the error message to the running instance
                    try:
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                            client.connect(str(app.SOCKET_FILE))
                            message = f"show_dialog||Invalid file type: {file_extension}||Only .exe, .msi, .charm, .bottle, .prefix, or .wzt files are allowed."
                            client.sendall(message.encode())
                        return
                    except ConnectionRefusedError:
                        print("No existing instance found, starting a new one.")

                # Return early to skip further processing
                return

    # Start the socket server and run the application (GUI mode)
    if args.file and file_extension in ['.bottle', '.prefix', '.wzt']:
        app.command_line_file = args.file
    app.start_socket_server()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
