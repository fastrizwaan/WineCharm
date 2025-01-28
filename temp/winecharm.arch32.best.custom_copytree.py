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
from pathlib import Path
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

from datetime import datetime, timedelta
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango  # Add Pango here

class WineCharmApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.fastrizwaan.WineCharm', flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None  # Initialize window as None
        Adw.init()
        
        # Move the global variables to instance attributes
        self.debug = False
        self.version = "0.96"
        
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

        # Initialize other attributes that might be missing
        self.selected_script = None
        self.selected_script_name = None
        self.selected_row = None
        self.spinner = None
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

        self.current_operation = None  # 'backup' or 'installation'
        self.open_button_handler_id = None
        
        # Register the SIGINT signal handler
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.script_buttons = {}
        self.current_clicked_row = None  # Initialize current clicked row
        self.hamburger_actions = [
            ("🛠️ Settings...", self.show_options_for_settings),
            ("🛠 Customize Template...", self.customize_template_components),
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

    def ensure_directory_exists(self, directory):
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
        print("Settings action triggered")
        # You can add code here to open a settings window or dialog.

    def find_matching_processes(self, exe_name_pattern):
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

        # Optionally, clear the running processes dictionary
        self.running_processes.clear()
        GLib.timeout_add_seconds(0.5, self.load_script_list)

    def on_help_clicked(self, action=None, param=None):
        print("Help action triggered")
        # You can add code here to show a help dialog or window.

    def on_about_clicked(self, action=None, param=None):
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
        self.quit()


    def get_default_icon_path(self):
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
        self.script_list = {}
        self.load_script_list()
        self.create_script_list()
        self.single_prefix = False
        self.load_settings()
        print(f"Single Prefix: {self.single_prefix}")

        # Unified template initialization logic
        def initialize_template_if_needed(template_path, arch, single_prefix_dir=None):
            if not template_path.exists():
                print(f"Initializing {arch} template...")
                self.initialize_template(template_path, self.on_template_initialized, arch=arch)
                return True
            elif self.single_prefix and single_prefix_dir and not single_prefix_dir.exists():
                print(f"Copying {arch} template to single prefix...")
                self.copy_template(single_prefix_dir)
            return False

        # Determine which templates need initialization based on settings
        arch_templates = [
            (self.arch == 'win32', self.default_template_win32, 'win32', self.single_prefix_dir_win32),
            (True, self.default_template_win64, 'win64', self.single_prefix_dir_win64)  # Always check win64
        ]

        needs_initialization = False
        for check, template, arch, single_dir in arch_templates:
            if check and not self.single_prefix:
                needs_initialization |= initialize_template_if_needed(template, arch, single_dir)

        # Set dynamic variables if no initialization needed 
        if not needs_initialization:
            self.set_dynamic_variables()
            if self.command_line_file:
                print("Processing command-line file after UI initialization")
                self.process_cli_file_later(self.command_line_file)

        # Common post-init tasks
        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        
        self.check_running_processes_on_startup()
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
        self.flowbox.remove_all()
        self.create_required_directories()
        self.initializing_template = True
        self.stop_processing = False
        self.current_arch = arch  # Store current architecture
        
        # Disconnect open button handler
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_init_clicked)
        
        # Architecture-specific steps
        steps = [
            ("Initializing wineprefix", 
            f"WINEARCH={arch} WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
            ("Replace symbolic links with directories", 
            lambda: self.remove_symlinks_and_create_directories(template_dir)),
            #("Installing corefonts", 
            #f"WINEPREFIX='{template_dir}' winetricks -q corefonts"),
            ("Installing openal", 
            f"WINEPREFIX='{template_dir}' winetricks -q openal"),
            #("Installing vkd3d", 
            #f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
            #("Installing dxvk", 
            #f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
        ]
        
        # Set total steps and initialize progress UI
        self.total_steps = len(steps)
        self.show_processing_spinner(f"Initializing {arch} Template...")

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
        
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.search_button.set_sensitive(True)
        self.view_toggle_button.set_sensitive(True)
        
        if self.open_button_handler_id is not None:
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)

        print("Template initialization completed and UI updated.")
        self.show_initializing_step("Initialization Complete!")
        self.mark_step_as_done("Initialization Complete!")
        GLib.timeout_add_seconds(0.5, self.create_script_list)
        
        # Check if there's a command-line file to process after initialization
        if self.command_line_file:
            print("Processing command-line file after template initialization")
            self.process_cli_file_later(self.command_line_file)
            self.command_line_file = None  # Reset after processing

        self.set_dynamic_variables()
    
    def process_cli_file_later(self, file_path):
        # Use GLib.idle_add to ensure this runs after the main loop starts
        GLib.idle_add(self.show_processing_spinner, "hello world")
        GLib.idle_add(self.process_cli_file, file_path)

    def set_open_button_label(self, text):
        box = self.open_button.get_child()
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Label):
                child.set_label(text)
            elif isinstance(child, Gtk.Image):
                child.set_visible(False if text == "Initializing" else True)
            child = child.get_next_sibling()

    def show_initializing_step(self, step_text):
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
            step_icon = self.spinner = Gtk.Spinner()
            step_label = Gtk.Label(label=step_text)
            step_label.set_halign(Gtk.Align.START)
            step_label.set_hexpand(True)
            
            step_box.append(step_icon)
            step_box.append(step_label)
            self.spinner.start()

            
            # Add to flowbox
            flowbox_child = Gtk.FlowBoxChild()
            flowbox_child.set_child(step_box)
            self.flowbox.append(flowbox_child)
            
            # Store reference
            self.step_boxes.append((step_box, step_icon, step_label))

    def mark_step_as_done(self, step_text):
        """
        Mark a step as completed in the flowbox
        """
        if hasattr(self, 'step_boxes'):
            for step_box, step_icon, step_label in self.step_boxes:
                if step_label.get_text() == step_text:
                    step_box.remove(step_icon)
                    done_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                    step_box.prepend(done_icon)
                    break

    def check_required_programs(self):
        if shutil.which("flatpak-spawn"):
            return []
            
        # List of supported terminals
        terminal_options = [
            'ptyxis',
            'gnome-terminal',
            'konsole',
            'xfce4-terminal'
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
        """Save current settings to the Settings.yaml file."""
        settings = {
            'template': self.replace_home_with_tilde_in_path(str(self.template)),
            'arch': self.arch,
            'runner': self.replace_home_with_tilde_in_path(str(self.settings.get('runner', ''))),
            'wine_debug': "WINEDEBUG=fixme-all DXVK_LOG_LEVEL=none",
            'env_vars': '',
            'icon_view': self.icon_view,
            'single-prefix': self.single_prefix
        }

        try:
            with open(self.settings_file, 'w') as settings_file:
                yaml.dump(settings, settings_file, default_flow_style=False, indent=4)
            print(f"Settings saved to {self.settings_file} with content:\n{settings}")
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
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
            self.single_prefix = settings.get('single-prefix', False)
            return settings

        # If no settings file, return an empty dictionary
        return {}
        
    def set_open_button_icon_visible(self, visible):
        box = self.open_button.get_child()
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Image):
                child.set_visible(visible)
            child = child.get_next_sibling()
            
    def on_activate(self, *args):
        if not self.window:
            self.window = Adw.ApplicationWindow(application=self)
        self.window.present()

 

    def handle_sigint(self, signum, frame):
        if self.SOCKET_FILE.exists():
            self.SOCKET_FILE.unlink()
        self.quit()

    def create_main_window(self):

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Wine Charm")
        self.window.set_default_size(480, 640)
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
        self.vbox.set_margin_top(3)
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
        self.open_button.set_size_request(-1, 36)  # Set height to 36 pixels
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
        self.vbox.append(self.open_button)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_size_request(-1, 36)
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

        if self.icon_view:
            self.flowbox.set_max_children_per_line(8)
        else:
            self.flowbox.set_max_children_per_line(4)

        self.flowbox.set_homogeneous(True)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.scrolled.set_child(self.flowbox)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.window.add_controller(key_controller)

        GLib.timeout_add_seconds(0.5, self.create_script_list)

    def create_sort_actions(self):
        """
        Create a single sorting action for the sorting options in the Sort submenu.
        """
        # Use 's' to denote that the action expects a string type parameter
        sort_action = Gio.SimpleAction.new("sort", GLib.VariantType('s'))
        sort_action.connect("activate", self.on_sort)
        self.window.add_action(sort_action)


    def on_sort(self, action, param):
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
        sorted_scripts = sorted(self.script_list.items(), key=lambda x: x[1].get(key, '').lower() if isinstance(x[1].get(key, ''), str) else x[1].get(key, ''), reverse=reverse)
        self.script_list = {key: value for key, value in sorted_scripts}
        GLib.idle_add(self.create_script_list)

    def create_open_actions(self):
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
        wineprefix = Path(self.winecharmdir)  # Replace with the actual wineprefix path
        print(f"Opening file manager for {wineprefix}")
        command = ["xdg-open", str(wineprefix)]
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening file manager: {e}")

    def open_terminal_winecharm(self, action, param):
        wineprefix = Path(self.winecharmdir).expanduser().resolve()

        print(f"Opening terminal for {wineprefix}")

        self.ensure_directory_exists(wineprefix)

        if shutil.which("flatpak-spawn"):
            command = [
                "wcterm", "bash", "--norc", "-c",
                (
                    rf'export PS1="[\u@\h:\w]\\$ "; '
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
        search_term = entry.get_text().lower()
        self.filter_script_list(search_term)

    def on_search_entry_changed(self, entry):
        search_term = entry.get_text().lower()
        # Check if we're in settings view
        if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
            self.populate_settings_options(search_term)
        elif hasattr(self, 'script_options_flowbox') and self.script_options_flowbox.get_parent() is not None:
            self.populate_script_options(search_term)  # Only pass search term
        else:
            self.filter_script_list(search_term)

    def filter_script_list(self, search_term):
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
        for script_key, script_data in self.script_list.items():
            # Resolve the script path, executable name, and get the progname
            script_path = Path(script_data['script_path']).expanduser().resolve()
            exe_name = Path(script_data['exe_file']).expanduser().resolve().name
            progname = script_data.get('progname', '').lower()  # Fallback to empty string if 'progname' is missing
            
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
                    self.update_ui_for_running_process(script_key, row, self.running_processes)

        if not found_match:
            print(f"No matches found for search term: {search_term}")


    def on_open_button_clicked(self, button):
        self.open_file_dialog()

    def open_file_dialog(self):
        file_dialog = Gtk.FileDialog.new()
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        filter_model.append(self.create_file_filter())
        file_dialog.set_filters(filter_model)
        file_dialog.open(self.window, None, self.on_open_file_dialog_response)

    def create_file_filter(self):
        file_filter = Gtk.FileFilter()
        file_filter.set_name("EXE and MSI files")
        file_filter.add_mime_type("application/x-ms-dos-executable")
        file_filter.add_pattern("*.exe")
        file_filter.add_pattern("*.msi")
        return file_filter

    def on_open_file_dialog_response(self, dialog, result):
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
        """
        Process CLI file in a background thread with proper Path handling
        """
        try:
            print(f"Processing CLI file in thread: {file_path}")
            file_path = Path(file_path) if not isinstance(file_path, Path) else file_path
            abs_file_path = file_path.resolve()
            print(f"Resolved absolute CLI file path: {abs_file_path}")

            if not abs_file_path.exists():
                print(f"File does not exist: {abs_file_path}")
                return

            # Perform the heavy processing here
            self.create_yaml_file(str(abs_file_path), None)

        except Exception as e:
            print(f"Error processing file in background: {e}")
        finally:
            if self.initializing_template:
                pass  # Keep showing spinner
            else:
                GLib.idle_add(self.hide_processing_spinner)
            
            GLib.timeout_add_seconds(0.5, self.create_script_list)

    def on_back_button_clicked(self, button):
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

        # Restore the script list
        self.create_script_list()

        
    def wrap_text_at_20_chars(self):
        text="Speedpro Installer Setup"
        if len(text) < 20:
            return text

        # Find the position of the first space or hyphen after 21 characters
        wrap_pos = -1
        for i in range(12, len(text)):
            if text[i] in [' ', '-']:
                wrap_pos = i + 1
                break

        # If no space or hyphen is found, wrap at 21 chars
        if wrap_pos == -1:
            wrap_pos = 21

        # Insert newline at the found position
        # text[start with 21 chars] + "\n" + text[middle 21 chars] + "\n" + text[end 21 chars] 
        return text[:wrap_pos] + "\n" + text[wrap_pos:] + "\n" + text[wrap_pos]


    def wrap_text_at_20_chars(self, text):
        if len(text) <= 20:
            # If text is already short enough, assign it all to label1
            label1 = text
            label2 = ""
            label3 = ""
            return label1, label2, label3

        # Find the position of the first space or hyphen for the first split
        wrap_pos1 = -1
        for i in range(12, min(21, len(text))):  # Wrap at or before 20 characters
            if text[i] in [' ', '-']:
                wrap_pos1 = i + 1
                break
        if wrap_pos1 == -1:
            wrap_pos1 = 21  # Default wrap at 21 if no space or hyphen found

        # Find the position of the second split for the next 20 chars
        wrap_pos2 = -1
        for i in range(wrap_pos1 + 12, min(wrap_pos1 + 21, len(text))):
            if text[i] in [' ', '-']:
                wrap_pos2 = i + 1
                break
        if wrap_pos2 == -1:
            wrap_pos2 = min(wrap_pos1 + 21, len(text))

        # Split the text into three parts
        label1 = text[:wrap_pos1].strip()
        label2 = text[wrap_pos1:wrap_pos2].strip()
        label3 = text[wrap_pos2:].strip()

        # If label3 is longer than 18 characters, truncate and add '...'
        if len(label3) > 18:
            label3 = label3[:18] + "..."
            
        return label1, label2, label3
        
    def find_charm_files(self, prefixdir=None):
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
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            return None
            
        if self.open_button.get_parent():
            self.vbox.remove(self.open_button)

        self.launch_button = Gtk.Button()
        self.launch_button.set_size_request(450, 36)

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
            self.launch_button.set_size_request(450, 36)
            
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
        # Clear the flowbox
        self.flowbox.remove_all()

        # Rebuild the script list
        self.script_ui_data = {}  # Use script_data to hold all script-related data

        # Iterate over self.script_list
        for script_key, script_data in self.script_list.items():
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
        """
        Creates a row for a given script in the UI, including the play and options buttons.

        Args:
            script_key (str): The unique key for the script (e.g., sha256sum).
            script_data (dict): Data associated with the script.

        Returns:
            Gtk.Overlay: The overlay containing the row UI.
        """
        script = Path(script_data['script_path']).expanduser()

        # Create the main button for the row
        button = Gtk.Button()
        button.set_hexpand(True)
        button.set_halign(Gtk.Align.FILL)
        button.add_css_class("flat")
        button.add_css_class("normal-font")

        # Extract the program name or fallback to the script stem
        label_text, label2_text, label3_text = "", "", ""
        label_text = script_data.get('progname', '').replace('_', ' ') or script.stem.replace('_', ' ')

        # Create an overlay to add play and options buttons
        overlay = Gtk.Overlay()
        overlay.set_child(button)

        if self.icon_view:
            # Icon view mode: Larger icon size and vertically oriented layout
            icon = self.load_icon(script, 64, 64)
            icon_image = Gtk.Image.new_from_paintable(icon)
            button.set_size_request(64, 64)
            icon_image.set_pixel_size(64)
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

            # Create a box to hold both buttons in vertical orientation
            buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

            # Apply text wrapping logic for the label
            label1, label2, label3 = self.wrap_text_at_20_chars(label_text)
            label = Gtk.Label(label=label1)
            if label2:
                label2 = Gtk.Label(label=label2)
            if label3:
                label3 = Gtk.Label(label=label3)
        else:
            # Non-icon view mode: Smaller icon size and horizontally oriented layout
            icon = self.load_icon(script, 32, 32)
            icon_image = Gtk.Image.new_from_paintable(icon)
            button.set_size_request(450, 36)
            icon_image.set_pixel_size(32)
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

            # Create a box to hold both buttons in horizontal orientation
            buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            # Use a single line label for non-icon view
            label = Gtk.Label(label=label_text)
            label.set_xalign(0)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label2 = Gtk.Label(label="")
            label3 = Gtk.Label(label="")

        # Set up the label and icon in the button
        hbox.append(icon_image)
        hbox.append(label)
        if self.icon_view and label2:
            hbox.append(label2)
        if self.icon_view and label3:
            hbox.append(label3)

        button.set_child(hbox)

        # Apply bold styling to the label if the script is new
        if script.stem in self.new_scripts:
            label.set_markup(f"<b>{label.get_text()}</b>")
            if label2:
                label2.set_markup(f"<b>{label2.get_text()}</b>")

            if label3:
                label3.set_markup(f"<b>{label3.get_text()}</b>")
            
        buttons_box.set_margin_end(6)  # Adjust this value to prevent overlapping

        # Play button
        play_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        play_button.set_tooltip_text("Play")
        play_button = Gtk.Button(
            label="Launch",
            icon_name="media-playback-start-symbolic",
            #css_classes=["suggested-action"],
        )
        play_button.set_size_request(60, 36)
        play_button.set_visible(False)  # Initially hidden
        buttons_box.append(play_button)

        # Options button
        options_button = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        options_button.set_tooltip_text("Options")
        options_button.set_size_request(60, 36)
        options_button.set_visible(False)  # Initially hidden
        buttons_box.append(options_button)

        # Add the buttons box to the overlay
        overlay.add_overlay(buttons_box)
        buttons_box.set_halign(Gtk.Align.END)
        buttons_box.set_valign(Gtk.Align.CENTER)

        # **Store references in self.script_ui_data**
        self.script_ui_data[script_key] = {
            'row': overlay,  # The overlay that contains the row UI
            'play_button': play_button,  # The play button for the row
            'options_button': options_button,  # The options button
            'highlighted': False,  # Initially not highlighted
            'is_running': False,  # Not running initially
            'is_clicked_row': False,
            'script_path': script
        }

        # Connect the play button to toggle the script's running state
        play_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, play_button, overlay))

        # Connect the options button to show the script's options
        options_button.connect("clicked", lambda btn: self.show_options_for_script(self.script_ui_data[script_key], overlay, script_key))

        # Event handler for button click (handles row highlighting)
        button.connect("clicked", lambda *args: self.on_script_row_clicked(script_key))

        return overlay
       
    def show_buttons(self, play_button, options_button):
        play_button.set_visible(True)
        options_button.set_visible(True)

    def hide_buttons(self, play_button, options_button):
        if play_button is not None:
            play_button.set_visible(False)
        if options_button is not None:
            options_button.set_visible(False)

    def on_script_row_clicked(self, script_key):
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
            play_button.set_tooltip_text("Stop")
            row.add_css_class("highlighted")
            print(f"Script {script_key} is running. Setting play button to 'Stop' and adding 'highlighted'.")
        else:
            # If the script is not running and not clicked, reset play button and highlight
            if not is_clicked:
                self.set_play_stop_button_state(play_button, False)
                play_button.set_tooltip_text("Play")
                row.remove_css_class("highlighted")
                print(f"Script {script_key} is not running. Setting play button to 'Play' and removing 'highlighted'.")

            # If the script is not running but clicked, ensure it stays highlighted in blue
            if is_clicked and not is_running:
                row.add_css_class("blue")
                print(f"Preserving 'blue' highlight for clicked but not running script_key: {script_key}")

    def set_play_stop_button_state(self, button, is_playing):
        if is_playing:
            button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
            button.set_tooltip_text("Stop")
        else:
            button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
            button.set_tooltip_text("Play")

    def update_row_highlight(self, row, highlight):
        if highlight:
            row.add_css_class("highlighted")
        else:
            #row.remove_css_class("blue")
            row.remove_css_class("highlighted")

    def find_and_remove_wine_created_shortcuts(self):
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
        # Get UI elements for the script
        print(f"--> I'm called by {script_key}")
        ui_state = self.script_ui_data.get(script_key)
        if not ui_state:
            print(f"No script data found for script_key: {script_key}")
            return

        row = ui_state.get('row')
        play_button = ui_state.get('play_button')
        options_button = ui_state.get('options_button')
        is_clicked = ui_state.get('is_clicked_row', False)

        # Handle wineprefix and process linked files if necessary
        process_info = self.running_processes.pop(script_key, None)
        
        # Initialize variables
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
                    self.create_scripts_for_lnk_files(wineprefix)
                    self.find_and_remove_wine_created_shortcuts()

        # Only proceed if exe_name and exe_parent_name are defined
        if exe_name and exe_parent_name:
            # Check if any processes with the same exe_name and exe_parent_name are still running
            is_still_running = False
            new_pid = None
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    proc_cmdline = proc.info['cmdline'] or []

                    # Check if process name matches the target executable name
                    if proc_name.lower() == exe_name.lower() or any(exe_name.lower() in arg.lower() for arg in proc_cmdline):
                        # Extract parent directory names from command-line arguments
                        for arg in proc_cmdline:
                            if exe_name.lower() in arg.lower():
                                proc_exe_path = Path(arg)
                                proc_exe_parent_name = proc_exe_path.parent.name

                                # Compare parent directory names
                                if proc_exe_parent_name == exe_parent_name:
                                    # Process matches
                                    is_still_running = True
                                    new_pid = proc.pid
                                    break
                        if is_still_running:
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            if is_still_running:
                # The process has respawned or is still running
                # Re-add to running_processes with the new PID under the same script_key
                self.running_processes[script_key] = {
                    "process": None,
                    "wineprefix": process_info.get("wineprefix") if process_info else None,
                    "runner": process_info.get("runner") if process_info else None,
                    "row": row,
                    "script": script if process_info else None,
                    "exe_name": exe_name,
                    "exe_parent_name": exe_parent_name,
                    "pid": new_pid,  # Update with the new PID
                    "unique_id": unique_id
                }
                print(f"Process with exe_name {exe_name} and parent directory '{exe_parent_name}' is still running (respawned).")

                # Start monitoring the new process
                threading.Thread(target=self.monitor_external_process, args=(script_key, new_pid), daemon=True).start()

                # Update UI elements
                ui_state['is_running'] = True

                if row:
                    self.update_row_highlight(row, True)
                    row.add_css_class("highlighted")

                if play_button:
                    self.set_play_stop_button_state(play_button, True)
                    play_button.set_tooltip_text("Stop")

                # Maintain the clicked state if it was clicked
                if is_clicked:
                    row.add_css_class("blue")
                    self.show_buttons(play_button, options_button)
                    print(f"Maintaining 'blue' highlight and buttons for script_key: {script_key}")

                return  # Exit early since we have re-added the process under the same script_key

        # No matching process found; reset UI elements
        # Update UI elements
        if row:
            # Remove both 'highlighted' and 'blue' classes
            row.remove_css_class("highlighted")
            row.remove_css_class("blue")

        if play_button:
            self.set_play_stop_button_state(play_button, False)
            play_button.set_tooltip_text("Play")

        # Reset the launch button if it exists
        if self.launch_button:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
            self.launch_button.set_tooltip_text("Play")

        # Hide play and options buttons
        if options_button:
            self.hide_buttons(play_button, options_button)

        # Reset the 'is_clicked_row' state
        ui_state['is_clicked_row'] = False
        ui_state['is_running'] = False

        # Check if there are any remaining running processes
        if not self.running_processes:
            print("All processes ended.")

        # Revert the runner to default
        self.runner_to_use = None

        # Call check_running_processes_on_startup to update UI
        self.check_running_processes_on_startup()

    def launch_script(self, script_key, play_stop_button, row):
        # Reload the script data from the .charm file
        script_data = self.reload_script_data_from_charm(script_key)
        if not script_data:
            print("Error: Script data could not be reloaded.")
            self.handle_ui_error(
                play_stop_button, row,
                "Script Error", "Failed to reload script data.", "Script Error"
            )
            return None

        self.debug = True  # Enable debugging

        # Generate a unique ID for the process
        unique_id = str(uuid.uuid4())
        env = os.environ.copy()
        env['WINECHARM_UNIQUE_ID'] = unique_id

        exe_file = Path(script_data.get('exe_file', '')).expanduser().resolve()
        wineprefix = Path(script_data.get('script_path', '')).parent.expanduser().resolve()
        env_vars = script_data.get('env_vars', '')

        try:
            # Get the runner from the script data
            runner_path = self.get_runner(script_data)
        except Exception as e:
            print(f"Error getting runner: {e}")
            self.handle_ui_error(
                play_stop_button, row,
                "Runner Error", f"Failed to get runner. Error: {e}",
                "Runner Error"
            )
            return

        # Check if the executable file exists
        if not exe_file.exists():
            self.handle_ui_error(
                play_stop_button, row,
                "Executable Not Found", str(exe_file),
                "Exe Not Found"
            )
            return

        # Prepare the log file and command to execute
        log_file_path = Path(wineprefix) / f"{exe_file.stem}.log"
        command = [
            "sh", "-c", 
            (
            f"cd {shlex.quote(str(exe_file.parent))} && "
            f"{env_vars} "
            f"WINEPREFIX={shlex.quote(str(wineprefix))} "
            f"{shlex.quote(str(runner_path))} "
            f"{shlex.quote(exe_file.name)}"
            )
        ]

        if self.debug:
            print(f"Launch command: {command}")

        try:
            # Launch the process
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
                    "script": Path(script_data['script_path']),
                    "exe_file": exe_file,
                    "exe_name": exe_file.name,
                    "runner": str(runner_path),
                    "wineprefix": str(wineprefix)
                }
                
                # Set the current runner for all the following scripts which will be created by this script's exe_file
                self.runner_to_use = runner_path

                self.set_play_stop_button_state(play_stop_button, True)
                self.update_row_highlight(row, True)
                play_stop_button.set_tooltip_text("Stop")

                ui_state = self.script_ui_data.get(script_key)
                if ui_state:
                    ui_state['is_running'] = True

                threading.Thread(target=self.monitor_process, args=(script_key,), daemon=True).start()
                GLib.timeout_add_seconds(5, self.get_child_pid_async, script_key)

        except Exception as e:
            error_message = f"Error launching script: {e}"
            print(error_message)
            traceback_str = traceback.format_exc()
            with open(log_file_path, 'a') as log_file:
                log_file.write(f"\n{error_message}\n{traceback_str}\n")

            # Show the error to the user via an info dialog
            GLib.idle_add(
                self.handle_ui_error,
                play_stop_button, row,
                "Launch Error", f"Failed to launch the script. Error: {e}",
                "Launch Failed"
            )
            GLib.idle_add(
                self.show_info_dialog,
                "Launch Error",
                f"Failed to launch the script. Error: {e}"
            )

    def get_runner(self, script_data):
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
        """
        Updates the UI to reflect an error state and shows an info dialog.
        """
        GLib.idle_add(self.update_row_highlight, row, False)
        GLib.idle_add(play_stop_button.add_css_class, "red")
        GLib.idle_add(play_stop_button.set_child, Gtk.Image.new_from_icon_name("action-unavailable-symbolic"))
        GLib.idle_add(play_stop_button.set_tooltip_text, tooltip)
        GLib.timeout_add_seconds(0.5, self.show_info_dialog, title, message)


    def reload_script_data_from_charm(self, script_key):
        script_data = self.script_list.get(script_key)
        if not script_data:
            print(f"Error: Script with key {script_key} not found in script_list.")
            return None

        script_path = Path(script_data.get('script_path', '')).expanduser().resolve()

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
        # Create the main error message dialog
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            modal=True,
            heading=title,
            body=message
        )

        # Add buttons to the main dialog
        dialog.add_response("show_log", "Show Log")
        dialog.add_response("close", "Close")

        # Set default and close responses
        dialog.set_default_response("close")
        dialog.set_close_response("close")

        # Variable to store the log content
        log_content = ""

        # Load the log content asynchronously
        def load_log_content():
            nonlocal log_content
            try:
                with open(log_file_path, 'r') as log_file:
                    log_content = log_file.read()
            except Exception as e:
                log_content = f"Failed to load log: {e}"

        threading.Thread(target=load_log_content, daemon=True).start()

        # Function to show a separate dialog with the log content
        def show_log_dialog():
            # Create a new dialog for the log content
            log_dialog = Adw.MessageDialog(
                transient_for=self.window,
                modal=True,
                heading="Log Content",
                body=""
            )

            # Create a ScrolledWindow for the log content
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled_window.set_min_content_width(640)
            scrolled_window.set_min_content_height(480)

            # Create a TextView to display the log content
            log_view = Gtk.TextView()
            log_view.set_editable(False)  # Make it read-only
            log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            scrolled_window.set_child(log_view)

            # Load the log content into the TextView
            GLib.idle_add(lambda: log_view.get_buffer().set_text(log_content))

            # Add the ScrolledWindow to the log dialog
            log_dialog.set_extra_child(scrolled_window)

            # Add a close button to the log dialog
            log_dialog.add_response("close", "Close")
            log_dialog.set_default_response("close")
            log_dialog.set_close_response("close")

            # Show the log dialog
            log_dialog.present()

        # Handle responses from the main dialog
        def on_response(dialog, response):
            if response == "show_log":
                show_log_dialog()  # Show the log content in a new dialog
            else:
                dialog.close()  # Close the main dialog

        # Connect the response handler to the main dialog
        dialog.connect("response", on_response)

        # Show the main dialog
        dialog.present()

    def monitor_process(self, script_key):
        process_info = self.running_processes.get(script_key)
        if not process_info:
            return

        process = process_info.get("process")
        if not process:
            return

        process.wait()  # Wait for the process to complete
        return_code = process.returncode

        # Check if the process was manually stopped
        manually_stopped = process_info.get("manually_stopped", False)

        # Update the UI in the main thread
        GLib.idle_add(self.process_ended, script_key)

        if return_code != 0 and not manually_stopped:
            # Handle error code 2 (cancelled by the user) gracefully
            if return_code == 2:
                print("Process was cancelled by the user.")
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
        try:
            proc = psutil.Process(pid)
            proc.wait()  # Wait for the process to terminate
        except psutil.NoSuchProcess:
            pass
        finally:
            # Process has ended; update the UI in the main thread
            GLib.idle_add(self.process_ended, script_key)

    def check_running_processes_on_startup(self):
        for script_key, script_data in self.script_list.items():
            wineprefix = Path(script_data['script_path']).parent.expanduser().resolve()
            target_exe_path = Path(script_data['exe_file']).expanduser().resolve()
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
                            "script": Path(script_data['script_path']),
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
                        play_button.set_tooltip_text("Play")

    def monitor_multiple_processes(self, script_key, pids):
        try:
            procs = [psutil.Process(pid) for pid in pids if psutil.pid_exists(pid)]
            psutil.wait_procs(procs)
        except Exception as e:
            print(f"Error monitoring processes for script_key {script_key}: {e}")
        finally:
            # Processes have ended; update the UI in the main thread
            GLib.idle_add(self.process_ended, script_key)

       
    def update_ui_for_running_script_on_startup(self, script_key):
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
            play_button.set_tooltip_text("Stop")
            ui_state['is_running'] = True  # Ensure is_running is set

            
############################### 1050 - 1682 ########################################

    def update_running_processes(self, current_running_processes):
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
        script_data = self.script_list.get(script_key)
        if script_data:
            return script_data
        else:
            print(f"Warning: Script with key {script_key} not found in script_list.")
            return {}

    def determine_progname(self, productname, exe_no_space, exe_name):
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
            return productname + ' Setup'
        elif "setup" in productname.lower() or "install" in productname.lower():
            return productname
        else:
            # Fallback to product name or executable name without spaces if productname contains numbers or is non-ascii
            return productname if productname and not any(char.isdigit() for char in productname) and productname.isascii() else exe_no_space


    def create_yaml_file(self, exe_path, prefix_dir=None, use_exe_name=False):
        # If the launch script has a different runner use that runner
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

        # Check if a script with the same sha256sum already exists
        script_key = sha256_hash.hexdigest()
        if script_key in self.script_list:
            # Remove the existing .charm file and its entry from the script list
            existing_script_path = Path(self.script_list[script_key]['script_path']).expanduser().resolve()
            if existing_script_path.exists():
                existing_script_path.unlink()  # Remove the existing file
                print(f"Removed existing charm file: {existing_script_path}")

            # Remove the entry from script_list
            #del self.script_list[script_key]
            #print(f"Removed old script_key {script_key} from script_list")
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
                    self.copy_template(prefix_dir, template_to_use)
            else:
                # Create new unique prefix per executable
                prefix_dir = self.prefixes_dir / f"{exe_no_space}-{sha256sum[:10]}"
                if not prefix_dir.exists():
                    template_to_use = self.default_template_win32 if self.arch == 'win32' else self.default_template_win64
                    if template_to_use.exists():
                        self.copy_template(prefix_dir, template_to_use)
                    else:
                        self.ensure_directory_exists(prefix_dir)

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

        # Prepare YAML data
        yaml_data = {
            'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
            'script_path': self.replace_home_with_tilde_in_path(str(yaml_file_path)),
            'wineprefix': self.replace_home_with_tilde_in_path(str(prefix_dir)),
            'progname': progname,
            'args': "",
            'sha256sum': sha256_hash.hexdigest(),
            'runner': runner_to_use,
            'wine_debug': "WINEDEBUG=fixme-all DXVK_LOG_LEVEL=none",  # Set a default or allow it to be empty
            'env_vars': ""  # Initialize with an empty string or set a default if necessary
        }

        # Write the new YAML file
        with open(yaml_file_path, 'w') as yaml_file:
            yaml.dump(yaml_data, yaml_file, default_flow_style=False, width=1000)

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

    def find_lnk_files(self, wineprefix):
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
            yaml.dump(found_lnk_files, file, default_flow_style=False, width=1000)

    def is_lnk_file_processed(self, wineprefix, lnk_file):
        found_lnk_files_path = wineprefix / "found_lnk_files.yaml"
        if found_lnk_files_path.exists():
            with open(found_lnk_files_path, 'r') as file:
                found_lnk_files = yaml.safe_load(file) or []
                return lnk_file.name in found_lnk_files
        return False

    def create_scripts_for_lnk_files(self, wineprefix):
        lnk_files = self.find_lnk_files(wineprefix)
        
        exe_files = self.extract_exe_files_from_lnk(lnk_files, wineprefix)
        
        product_name_map = {}  # Key: product_name, Value: list of exe_files
        
        for exe_file in exe_files:
            exe_name = exe_file.stem  # Extract the name of the executable
            product_name = self.get_product_name(exe_file) or exe_name  # Use exe_name if no product name is found
            
            if product_name not in product_name_map:
                product_name_map[product_name] = []
            
            product_name_map[product_name].append(exe_file)  # Group exe files under the same product_name
        
        # Create YAML files based on the product_name_map
        for product_name, exe_files in product_name_map.items():
            
            if len(exe_files) > 1:
                # Multiple exe files with the same product_name, use exe_name for differentiation
                for exe_file in exe_files:
                    self.create_yaml_file(exe_file, wineprefix, use_exe_name=True)
            else:
                # Only one exe file, use the product_name for the YAML file
                self.create_yaml_file(exe_files[0], wineprefix, use_exe_name=False)

        # After create_yaml_file is finished, re-create the script list    
        #GLib.timeout_add_seconds(0.5, self.create_script_list)



    def extract_exe_files_from_lnk(self, lnk_files, wineprefix):
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
            d.close()
            if callback is not None:
                callback()

        dialog.connect("response", on_response)
        dialog.present(self.window)

        
    def reverse_process_reg_files(self, wineprefix):
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
            f"\\\\users\\\\{current_username}": f"\\\\users\\\\%USERNAME%",
            f"\\\\home\\\\{current_username}": f"\\\\home\\\\%USERNAME%",
            f'"USERNAME"="{current_username}"': f'"USERNAME"="%USERNAME%"'
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


##### BACKUP PREFIX
    def show_backup_prefix_dialog(self, script, script_key, button):
        self.stop_processing = False
        wineprefix = Path(script).parent
        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = self.expand_and_resolve_path(script_data['exe_file'])
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
            # Handle any errors, such as cancellation
            print(f"An error occurred: {e}")

    def on_backup_prefix_completed(self, script_key, backup_path):
        """
        Called when the backup process is complete. Updates the UI safely.
        """
        try:
            GLib.idle_add(self._complete_backup_ui_update, script_key, backup_path)
        except Exception as e:
            print(f"Error scheduling backup completion UI update: {e}")
            self.show_info_dialog("Warning", "Backup completed but there was an error updating the UI")

    def _complete_backup_ui_update(self, script_key, backup_path):
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
        """
        Connect cancel handler to the open button for backup process
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_backup_clicked, script_key)
        
        self.set_open_button_icon_visible(False)

    def cleanup_cancelled_backup(self, script, script_key):
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
        """
        Handle cancel button click during backup
        """
        dialog = Adw.MessageDialog.new(
            self.window,
            "Cancel Backup",
            "Do you want to cancel the backup process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Backup")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_backup_dialog_response, script_key)
        dialog.present()

    def on_cancel_backup_dialog_response(self, dialog, response, script_key):
        """
        Handle cancel dialog response for backup
        """
        if response == "cancel":
            self.stop_processing = True
        dialog.close()

##### /BACKUP PREFIX xx

    def show_options_for_script(self, ui_state, row, script_key):
        """
        Display the options for a specific script with search functionality.
        """
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
            ("Show log", "document-open-symbolic", self.show_log_file),
            ("Open Terminal", "utilities-terminal-symbolic", self.open_terminal),
            ("Install dxvk vkd3d", "emblem-system-symbolic", self.install_dxvk_vkd3d),
            ("Open Filemanager", "system-file-manager-symbolic", self.open_filemanager),
            ("Edit Script File", "text-editor-symbolic", self.open_script_file),
            ("Delete Wineprefix", "user-trash-symbolic", self.show_delete_wineprefix_confirmation),
            ("Delete Shortcut", "edit-delete-symbolic", self.show_delete_shortcut_confirmation),
            ("Wine Arguments", "preferences-system-symbolic", self.show_wine_arguments_entry),
            ("Rename Shortcut", "text-editor-symbolic", self.show_rename_shortcut_entry),
            ("Change Icon", "applications-graphics-symbolic", self.show_change_icon_dialog),
            ("Backup Prefix", "document-save-symbolic", self.show_backup_prefix_dialog),
            ("Create Bottle", "package-x-generic-symbolic", self.create_bottle_selected),
            ("Save Wine User Dirs", "document-save-symbolic", self.show_save_user_dirs_dialog),
            ("Load Wine User Dirs", "document-revert-symbolic", self.show_load_user_dirs_dialog),
            ("Reset Shortcut", "view-refresh-symbolic", self.reset_shortcut_confirmation),
            ("Add Desktop Shortcut", "user-bookmarks-symbolic", self.add_desktop_shortcut),
            ("Remove Desktop Shortcut", "action-unavailable-symbolic", self.remove_desktop_shortcut),
            ("Import Game Directory", "folder-download-symbolic", self.import_game_directory),
            ("Run Other Exe", "system-run-symbolic", self.run_other_exe),
            ("Environment Variables", "preferences-system-symbolic", self.set_environment_variables),
            ("Change Runner", "preferences-desktop-apps-symbolic", self.change_runner),
            ("Rename Prefix Directory", "folder-visiting-symbolic", self.rename_prefix_directory),
            ("Wine Config (winecfg)", "preferences-system-symbolic", self.wine_config),
            ("Registry Editor (regedit)", "dialog-password-symbolic", self.wine_registry_editor)

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
                option_button.set_size_request(150, 36)
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

        exe_file = self.expand_and_resolve_path(script_data['exe_file'])
        exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_path = exe_file.parent
        exe_name = exe_file.name

        runner = self.expand_and_resolve_path(script_data['runner'])

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
        """
        Called when the bottle creation process is complete. Schedules UI updates safely.
        """
        try:
            GLib.idle_add(self._complete_bottle_creation_ui_update, script_key, backup_path)
        except Exception as e:
            print(f"Error scheduling bottle creation UI update: {e}")
            self.show_info_dialog("Warning", "Bottle created but there was an error updating the UI")

    def _complete_bottle_creation_ui_update(self, script_key, backup_path):
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
        if response_id == "continue":
            dialog.close()
            self.show_create_bottle_dialog(script, script_key)
        else:
            return

    def create_bottle_selected(self, script, script_key, button):
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
            dialog = Adw.MessageDialog.new(
            self.window,
            "Large Game Directory",
            f"The game directory size is {directory_size_gb}GB. Do you want to continue?"
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("continue", "Continue")
            dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        #dialog.connect("response", perform_backup_steps, script, script_key, backup_path)
            dialog.connect("response", self.on_backup_confirmation_response, script, script_key)
            dialog.present()
            print("----------------------------------------------------------")
        else:
            self.show_create_bottle_dialog(script, script_key)

    def show_create_bottle_dialog(self, script, script_key):

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
            # Handle any errors, such as cancellation
            print(f"An error occurred: {e}")

    def create_bottle_archive(self, script_key, wineprefix, backup_path):
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

        exe_file = Path(script_data['exe_file']).expanduser().resolve()
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

        exe_file = Path(script_data['exe_file']).expanduser().resolve()
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
        """
        Connect cancel handler to the open button
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_bottle_clicked, script_key)
        
        #if not hasattr(self, 'spinner') or not self.spinner:
        #    self.spinner = Gtk.Spinner()
        #    self.spinner.start()
        #    self.open_button_box.append(self.spinner)

        #self.set_open_button_label("Cancel")
        self.set_open_button_icon_visible(False)

    def cleanup_cancelled_bottle(self, script, script_key):
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
        """
        Handle cancel button click
        """
        dialog = Adw.MessageDialog.new(
            self.window,
            "Cancel Bottle Creation",
            "Do you want to cancel the bottle creation process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Creation")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_bottle_dialog_response, script_key)
        dialog.present()

    def on_cancel_bottle_dialog_response(self, dialog, response, script_key):
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
        log_file_path = Path(script.parent) / f"{script.stem}.log"
        if log_file_path.exists() and log_file_path.stat().st_size > 0:
            try:
                subprocess.run(["xdg-open", str(log_file_path)], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error opening log file: {e}")


    def open_terminal(self, script, script_key, *args):
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            return None

        exe_file = Path(script_data['exe_file']).expanduser().resolve()
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
        script = Path(script_data['script_path']).expanduser().resolve()
        wineprefix = Path(script_data['script_path']).parent.expanduser().resolve()

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
        wineprefix = Path(script).parent
        self.run_winetricks_script("vkd3d dxvk", wineprefix)
        self.create_script_list()

    def open_filemanager(self, script, script_key, *args):
        wineprefix = Path(script).parent
        print(f"Opening file manager for {wineprefix}")
        command = ["xdg-open", str(wineprefix)]
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening file manager: {e}")

    def open_script_file(self, script, script_key, *args):
        """
        Open the file manager to show the script's location.
        """
        wineprefix = Path(script).parent
        print(f"Opening file manager for {wineprefix}")
        
        # Ensure we're using the updated script path
        script_data = self.script_list.get(script_key)
        if script_data:
            script_path = Path(script_data['script_path']).expanduser().resolve()
        else:
            print(f"Error: Script key {script_key} not found in script_list.")
            return
        
        command = ["xdg-open", str(script_path)]
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening file manager: {e}")

            
    def show_delete_wineprefix_confirmation(self, script, button):
        """
        Show an Adw.MessageDialog to confirm the deletion of the Wine prefix.
        
        Args:
            script: The script that contains information about the Wine prefix.
            button: The button that triggered the deletion request.
        """
        wineprefix = Path(script).parent

        # Get all charm files associated with the wineprefix
        charm_files = list(wineprefix.rglob("*.charm"))

        # Create a confirmation dialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,  # Assuming self.window is the main application window
            title="Delete Wine Prefix",
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
        dialog.present()


    def on_delete_wineprefix_confirmation_response(self, dialog, response_id, wineprefix):
        """
        Handle the response from the delete Wine prefix confirmation dialog.
        
        Args:
            dialog: The Adw.MessageDialog instance.
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



    def get_script_keys_from_wineprefix(self, wineprefix):
        """
        Retrieve the list of script_keys for a given Wine prefix.
        
        Args:
            wineprefix: The path to the Wine prefix.
            
        Returns:
            A list of script_keys corresponding to the given wineprefix.
        """
        script_keys = []
        for script_key, script_data in self.script_list.items():
            script_path = Path(script_data['script_path']).expanduser().resolve()
            if script_path.parent == wineprefix:
                script_keys.append(script_key)
        return script_keys


    def show_delete_shortcut_confirmation(self, script, script_key, button, *args):
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
        wine_prefix_dir = Path(script_data['script_path']).parent.expanduser().resolve()
        script_path = Path(script_data['script_path']).expanduser().resolve()


        # Fetch the list of charm files only in the specific Wine prefix directory
        charm_files = list(wine_prefix_dir.rglob("*.charm"))

        # If there are no charm files, show a message
        if not charm_files:
            self.show_info_dialog("No Shortcuts", f"No shortcuts are available for deletion in {wine_prefix_dir}.")
            return

        # Create a new dialog for selecting shortcuts
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            title="Delete Shortcuts",
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
        dialog.present()


    def on_delete_shortcuts_response(self, dialog, response_id, checkbox_dict):
        """
        Handle the response from the delete shortcut dialog.
        
        Args:
            dialog: The Adw.MessageDialog instance.
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
        """
        Retrieve the script_key for a given shortcut file.
        
        Args:
            shortcut_file: The path to the shortcut.
            
        Returns:
            The corresponding script_key from script_list, if found.
        """
        for script_key, script_data in self.script_list.items():
            script_path = Path(script_data['script_path']).expanduser().resolve()
            if script_path == shortcut_file:
                return script_key
        return None

    def show_wine_arguments_entry(self, script, script_key, *args):
        """
        Show an Adw.MessageDialog to allow the user to edit Wine arguments.

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
            script_path = Path(script_data['script_path']).expanduser().resolve()
        else:
            print(f"Error: Script key {script_key} not found in script_list.")
            return
        
        #script = Path(script_data['script_path'])
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

        # Create an Adw.MessageDialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,  # Assuming self.window is the main application window
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
        dialog.present()


    def on_wine_arguments_dialog_response(self, dialog, response_id, entry, script_key):
        """
        Handle the response from the Wine arguments dialog.
        
        Args:
            dialog: The Adw.MessageDialog instance.
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
                script_path = Path(script_data['script_path']).expanduser().resolve()

                # Write the updated info back to the YAML file
                with open(script_path, 'w') as file:
                    yaml.dump(script_data, file, default_flow_style=False, width=1000)

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
        """
        Show an Adw.MessageDialog to allow the user to rename a shortcut.

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
            script_path = Path(script_data['script_path']).expanduser().resolve()
        else:
            print(f"Error: Script key {script_key} not found in script_list.")
            return

        # Get the current name of the shortcut
        current_name = script_data.get('progname')
        if not current_name:  # In case the current name is missing
            current_name = "New Shortcut"

        # Create an Adw.MessageDialog for renaming
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,  # Assuming self.window is the main application window
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
        dialog.present()

    def on_show_rename_shortcut_dialog_response(self, dialog, response_id, entry, script_key):
        """
        Handle the response from the Rename Shortcut dialog.

        Args:
            dialog: The Adw.MessageDialog instance.
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
                script_path = Path(script_data['script_path']).expanduser().resolve()

                print("*"*100)
                print("writing script_path = {script_path}")

                # Rename the .charm file and associated icon
                new_script_path = self.rename_script_and_icon(script_path, old_progname, new_name)
                
                # Write the updated info back to the YAML file
                with open(new_script_path, 'w') as file:
                    script_data['script_path'] = str(new_script_path).replace(str(Path.home()), "~")
                    yaml.dump(script_data, file, default_flow_style=False, width=1000)
                    
                # Ensure that script_data still contains the same sha256sum
                existing_sha256sum = script_data.get('sha256sum')

                # Extract icon and create desktop entry
                exe_file = Path(script_data['exe_file'])  # Assuming exe_file exists in script_data
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
        # Ensure we're using the updated script path
        script_data = self.script_list.get(script_key)
        if script_data:
            script_path = Path(script_data['script_path']).expanduser().resolve()
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


    def change_icon(self, script_path, new_icon_path):
        script_path = Path(script_path)
        icon_path = script_path.with_suffix(".png")
        backup_icon_path = icon_path.with_suffix(".bak")

        if icon_path.exists():
            shutil.move(icon_path, backup_icon_path)

        shutil.copy(new_icon_path, icon_path)
        
        

    def extract_and_change_icon(self, script_path, exe_path):
        script_path = Path(script_path)
        icon_path = script_path.with_suffix(".png")
        backup_icon_path = icon_path.with_suffix(".bak")

        if icon_path.exists():
            shutil.move(icon_path, backup_icon_path)

        extracted_icon_path = self.extract_icon(exe_path, script_path.parent, script_path.stem, script_path.stem)
        if extracted_icon_path:
            shutil.move(extracted_icon_path, icon_path)
            
    def reset_shortcut_confirmation(self, script, script_key, button=None):
        script_data = self.script_list.get(script_key)
        if script_data:
            exe_file = Path(script_data.get('exe_file'))

        # Create a confirmation dialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,  # Assuming self.window is the main application window
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
        dialog.present()


    def on_reset_shortcut_confirmation_response(self, dialog, response_id, script_key):
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
        exe_file = Path(script_data['exe_file']).expanduser().resolve()
        wineprefix = script_data.get('wineprefix')
        script =  Path(script_data['script_path']).expanduser().resolve()
        if wineprefix is None:
            wineprefix = script.parent  # Use script's parent directory if wineprefix is not provided
        else:
            wineprefix = Path(wineprefix).expanduser().resolve()

        script_path = Path(script_data.get('script_path')).expanduser().resolve()

        script_path = Path(script_data.get('script_path')).expanduser().resolve()

        
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
            script_path = Path(script_data.get('script_path')).expanduser().resolve()
            self.headerbar.set_title_widget(self.create_icon_title_widget(script_path))



    def callback_wrapper(self, callback, script, script_key, button=None, *args):
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
        command = f"WINEPREFIX={shlex.quote(str(wineprefix))} winetricks {script_name}"
        try:
            subprocess.run(command, shell=True, check=True)
            print(f"Successfully ran {script_name} in {wineprefix}")
        except subprocess.CalledProcessError as e:
            print(f"Error running winetricks script {script_name}: {e}")

    def process_file(self, file_path):
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
        # Restore the original button as the child of the FlowBoxChild
        parent.set_child(original_button)
        original_button.set_sensitive(True)

    def run_command(self, command):
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
        drive_c = Path(wineprefix) / "drive_c"
        for root, dirs, files in os.walk(drive_c):
            for file in files:
                if file.lower() == exe_name.lower():
                    return Path(root) / file
        return None

    def get_product_name(self, exe_file):
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
        if source_template is None:
            source_template = self.template
        source_template = Path(source_template)
        dest_dir = Path(dest_dir)
        
        if source_template.exists():
            shutil.copytree(source_template, dest_dir, symlinks=True, dirs_exist_ok=True)
            print(f"Copied template {source_template} to {dest_dir}")
        else:
            print(f"Template {source_template} does not exist. Creating empty prefix.")
            self.ensure_directory_exists(dest_dir)

    def create_desktop_entry(self, progname, script_path, icon_path, wineprefix, category = "Game"):
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
        def server_thread():
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
                                GLib.idle_add(self.process_cli_file, file_path)

        # Run the server in a separate thread
        threading.Thread(target=server_thread, daemon=True).start()


    def initialize_app(self):
        if not hasattr(self, 'window') or not self.window:
            # Call the startup code
            self.create_main_window()
            self.create_script_list()
            #self.check_running_processes_and_update_buttons()
            
            missing_programs = self.check_required_programs()
            if missing_programs:
                self.show_missing_programs_dialog(missing_programs)
            else:
                if not self.default_template.exists() and not self.single_prefix:
                    self.initialize_template(self.default_template, self.on_template_initialized)
                if not self.default_template.exists() and self.single_prefix:
                    self.initialize_template(self.default_template, self.on_template_initialized)
                    self.copy_template(self.single_prefixes_dir)
                elif self.default_template.exists() and not self.single_prefixes_dir.exists() and self.single_prefix:
                    self.copy_template(self.single_prefixes_dir)
                else:
                    self.set_dynamic_variables()



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


    def show_processing_spinner(self, label_text):
        """
        Initialize progress tracking UI for any step-based process
        """
        # Clear the open button box
        while self.open_button_box.get_first_child():
            self.open_button_box.remove(self.open_button_box.get_first_child())
        
        # Create and add progress bar to the open button
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text(label_text)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_size_request(420, -1)
        self.open_button_box.append(self.progress_bar)
        
        # Clear the flowbox for showing steps
        self.flowbox.remove_all()
        
        # Create a list to store steps
        self.step_boxes = []
        
        # Disable UI elements during processing
        self.search_button.set_sensitive(False)
        self.view_toggle_button.set_sensitive(False)

    def hide_processing_spinner(self):
        """
        Restore UI state after process completion with safe widget removal
        """
        try:
            # Safely remove children from open_button_box
            if hasattr(self, 'open_button_box'):
                child = self.open_button_box.get_first_child()
                while child:
                    next_child = child.get_next_sibling()
                    self.open_button_box.remove(child)
                    child = next_child
            
            # Safely restore original button content
            if hasattr(self, 'open_button_box'):
                open_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
                open_label = Gtk.Label(label="Open")
                self.open_button_box.append(open_icon)
                self.open_button_box.append(open_label)
            
            # Safely re-enable UI elements
            if hasattr(self, 'search_button'):
                self.search_button.set_sensitive(True)
            if hasattr(self, 'view_toggle_button'):
                self.view_toggle_button.set_sensitive(True)
            
            # Clear step tracking safely
            if hasattr(self, 'step_boxes'):
                self.step_boxes = []
                
        except Exception as e:
            print(f"Error in hide_processing_spinner: {e}")

    def on_open(self, app, files, *args):
        # Ensure the application is fully initialized
        print("1. on_open method called")
        
        # Initialize the application if it hasn't been already
        self.initialize_app()
        print("2. self.initialize_app initiated")
        
        # Present the window as soon as possible
        GLib.idle_add(self.window.present)
        print("3. self.window.present() Complete")
        
        # Check if the command_line_file exists and is either .exe or .msi
        if self.command_line_file:
            print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
            print(self.command_line_file)
            
            file_extension = Path(self.command_line_file).suffix.lower()
            if file_extension in ['.exe', '.msi']:
                print(f"Processing file: {self.command_line_file} (Valid extension: {file_extension})")
                print("Trying to process file inside on template initialized")

                GLib.idle_add(self.show_processing_spinner)
                self.process_cli_file(self.command_line_file)
            else:
                print(f"Invalid file type: {file_extension}. Only .exe or .msi files are allowed.")
                GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Invalid File Type", "Only .exe and .msi files are supported.")
                self.command_line_file = None
                return False
        self.check_running_processes_on_startup()
        
    def load_icon(self, script, x, y):
        
        icon_name = script.stem + ".png"
        icon_dir = script.parent
        icon_path = icon_dir / icon_name
        default_icon_path = self.get_default_icon_path()

#        print(f"""
#        script = {script}
#        script.stem = {script.stem}
#        script.stem + '.png' = 
#        icon_name = {icon_name}
#        """)
        try:
            # Load the icon at a higher resolution
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon_path), 128, 128)
            # Scale down to the desired size
            scaled_pixbuf = pixbuf.scale_simple(x, y, GdkPixbuf.InterpType.BILINEAR)
            return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
        except Exception:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(default_icon_path), 128, 128)
                scaled_pixbuf = pixbuf.scale_simple(x, y, GdkPixbuf.InterpType.BILINEAR)
                return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
            except Exception:
                return None


                
    def create_icon_title_widget(self, script):
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


    def on_view_toggle_button_clicked(self, button):
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


    def rename_and_merge_user_directories(self, wineprefix):
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
        # Create a new Gtk.FileDialog for selecting a directory
        file_dialog = Gtk.FileDialog.new()

        # Set the action to select a folder (in GTK 4, it's done by default via FileDialog)
        file_dialog.set_modal(True)

        # Open the dialog to select a folder (async operation)
        file_dialog.select_folder(self.window, None, self.on_import_directory_response)

        print("FileDialog presented for importing Wine directory.")

    def on_import_directory_response(self, dialog, result):
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
                    self.disconnect_open_button()

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
            # Handle any errors that occurred during folder selection
            print(f"An error occurred: {e}")

        print("FileDialog operation complete.")

    def on_import_wine_directory_completed(self):
        """
        Called when the import process is complete. Updates UI, restores scripts, and resets the open button.
        """
        # Reconnect open button and reset its label
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        
        self.hide_processing_spinner()

        # This will disconnect open_button handler, use this then reconnect the open
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)

        self.reconnect_open_button()
        self.load_script_list()
        # Restore the script list in the flowbox
        GLib.idle_add(self.create_script_list)

        print("Wine directory import completed and script list restored.")

    def copy_wine_directory(self, src, dst):
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
        """
        Show a confirmation dialog asking the user whether to overwrite the existing directory.
        """
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            heading="Overwrite Existing Directory?",
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
        dialog.present()


    def on_import_wine_directory_overwrite_response(self, dialog, response_id, src, dest_dir):
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
        """
        Handle cancel button click
        """
        dialog = Adw.MessageDialog.new(
            self.window,
            "Cancel Bottle Creation",
            "Do you want to cancel the bottle creation process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Creation")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_import_wine_direcotory_dialog_response)
        dialog.present()


    def connect_open_button_with_import_wine_directory_cancel(self):
        """
        Connect cancel handler to the open button
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_import_wine_directory_clicked)
        
        self.set_open_button_icon_visible(False)


    def import_wine_directory(self, src, dst):
        """
        Import the Wine directory with improved safety and rollback capability.
        Args:
            src: Source directory path (Path object)
            dst: Destination directory path (Path object)
        """
        self.stop_processing = False
        
        # Generate backup directory name with timestamp
        backup_dir = dst.parent / f"{dst.name}_backup_{int(time.time())}"
        
        # Clear the flowbox and initialize progress UI
        GLib.idle_add(self.flowbox.remove_all)
        
        steps = [
            ("Backing up existing directory", lambda: self.backup_existing_directory(dst, backup_dir)),
            ("Copying Wine directory", lambda: self.custom_copytree(src, dst)),
            ("Processing registry files", lambda: self.process_reg_files(dst)),
            ("Performing Replacements", lambda: self.perform_replacements(dst)),
            ("Creating scripts for .exe files", lambda: self.create_scripts_for_exe_files(dst)),
        ]
        
        # Set total steps and initialize progress UI
        self.total_steps = len(steps)
        self.show_processing_spinner("Importing Wine Directory...")
        self.connect_open_button_with_import_wine_directory_cancel()

        def perform_import_steps():
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
                    except Exception as e:
                        print(f"Error during step '{step_text}': {e}")
                        GLib.idle_add(lambda: self.handle_import_error(dst, backup_dir, f"An error occurred during '{step_text}': {e}"))
                        return

                if not self.stop_processing:
                    # Success - remove the backup
                    self.cleanup_backup(backup_dir)
                    GLib.idle_add(self.on_import_wine_directory_completed)
                    
            except Exception as e:
                print(f"Error during import process: {e}")
                GLib.idle_add(lambda: self.handle_import_error(dst, backup_dir, f"Import failed: {e}"))

        threading.Thread(target=perform_import_steps).start()

    def backup_existing_directory(self, dst, backup_dir):
        """
        Safely backup the existing directory if it exists.
        """
        if dst.exists():
            try:
                dst.rename(backup_dir)
                print(f"Created backup of existing directory: {backup_dir}")
            except Exception as e:
                raise Exception(f"Failed to create backup: {e}")

    def handle_import_cancellation(self, dst, backup_dir):
        """
        Handle import cancellation by restoring from backup.
        """
        try:
            if dst.exists():
                shutil.rmtree(dst)
                print(f"Removed incomplete import directory: {dst}")
            
            if backup_dir.exists():
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
        """
        Disconnect the open button's handler and update its label to "Importing...".
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
        
        if not hasattr(self, 'spinner') or not self.spinner:  # Ensure spinner is not created multiple times
            self.spinner = Gtk.Spinner()
            self.spinner.start()
            self.open_button_box.append(self.spinner)

        if self.spinner:
            self.spinner.stop()
            self.open_button_box.remove(self.spinner)
            self.spinner = None 

        #self.set_open_button_label("Importing...")
        self.set_open_button_icon_visible(False)  # Hide the open-folder icon
        print("Open button disconnected and spinner shown.")

    def reconnect_open_button(self):
        """
        Reconnect the open button's handler and reset its label.
        """
        if self.open_button_handler_id is not None:
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
        
        if self.spinner:
            self.spinner.stop()
            self.open_button_box.remove(self.spinner)
            self.spinner = None  # Ensure the spinner reference is cleared

        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        print("Open button reconnected and UI reset.")
        
    def create_scripts_for_exe_files(self, wineprefix):
        exe_files = self.find_exe_files(wineprefix)
        for exe_file in exe_files:
            self.create_yaml_file(exe_file, wineprefix, use_exe_name=True)
            
        GLib.timeout_add_seconds(0.5, self.create_script_list)

    def find_exe_files(self, wineprefix):
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
        """
        Custom recursive copy function that ensures no overwriting of files or symlinks.
        Args:
            src (str): The source directory path.
            dst (str): The destination directory path.
        """
        self.ensure_directory_exists(dst)  # Ensure the destination directory exists

        # Iterate over all items in the source directory
        for item in os.listdir(src):
            s = os.path.join(src, item)  # Source item path
            d = os.path.join(dst, item)  # Destination item path

            # If the item is a symlink, replicate the symlink in the destination
            if os.path.islink(s):
                linkto = os.readlink(s)
                # Create a symlink in the destination pointing to the same location as the source
                if not os.path.exists(d):  # Avoid overwriting existing symlinks
                    try:
                        os.symlink(linkto, d)
                    except FileExistsError:
                        print(f"Symlink already exists: {d}, skipping.")
                else:
                    # Log or print a message if the symlink already exists
                    print(f"Skipping existing symlink: {d}")

            # If the item is a directory, call custom_copytree recursively
            elif os.path.isdir(s):
                self.custom_copytree(s, d)

            # If the item is a file, copy it only if it doesn't already exist
            elif os.path.isfile(s):
                if not os.path.exists(d):  # Only copy if the file does not exist
                    try:
                        shutil.copy2(s, d)
                    except FileExistsError:
                        print(f"File already exists: {d}, skipping.")
                else:
                    # Optional: Print a message or log that the file already exists and is being skipped
                    print(f"Skipping existing file: {d}")

    def custom_copytree(self, src, dst, progress_range=(0.0, 1.0)):
        """Custom copy implementation with progress tracking"""
        try:
            # Ensure progress bar exists
            GLib.idle_add(self.show_processing_spinner, "Copying files...")
            
            # Calculate progress scale factors
            range_start, range_end = progress_range
            range_span = range_end - range_start
            
            # Count files first for progress calculation
            count_process = subprocess.Popen(
                ['find', str(src), '-type', 'f', '-printf', '%P\n'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            out, err = count_process.communicate()
            if count_process.returncode != 0:
                raise Exception(f"File count failed: {err.decode()}")
                
            total_files = len(out.decode().splitlines()) or 1  # Prevent division by zero

            # Create parent directory if needed
            dst_path = Path(dst)
            dst_path.mkdir(parents=True, exist_ok=True)

            # Start copy process
            def preexec():
                os.setpgrp()

            copy_process = subprocess.Popen(
                ['cp', '-a', f'{src}/.', str(dst)],
                preexec_fn=preexec,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=True
            )

            # Store process for cancellation
            with self.process_lock:
                self.current_process = copy_process

            # Progress monitoring thread
            def monitor_progress():
                nonlocal total_files
                while copy_process.poll() is None and not self.stop_processing:
                    try:
                        current_count = sum(1 for _ in dst_path.rglob('*') if _.is_file())
                        progress = range_start + (current_count / total_files * range_span)
                        if hasattr(self, 'progress_bar'):
                            GLib.idle_add(self.progress_bar.set_fraction, min(progress, 0.99))
                            GLib.idle_add(self.progress_bar.set_text,
                                        f"Copying {current_count}/{total_files} files")
                    except Exception as e:
                        print(f"Progress update error: {e}")
                    time.sleep(0.2)

            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.start()

            # Wait for completion
            while copy_process.poll() is None:
                if self.stop_processing:
                    self._kill_process_group(copy_process.pid)
                    raise Exception("Copy cancelled by user")
                time.sleep(0.1)

            # Final progress update
            if hasattr(self, 'progress_bar'):
                GLib.idle_add(self.progress_bar.set_fraction, range_end)
                GLib.idle_add(self.progress_bar.set_text, f"Copied {total_files} files")

            # Verify result
            if copy_process.returncode != 0:
                err = copy_process.stderr.read()
                raise Exception(f"Copy failed: {err}")

            return True

        except Exception as e:
            print(f"Copy error: {e}")
            if dst_path.exists():
                shutil.rmtree(dst_path, ignore_errors=True)
            raise
        finally:
            with self.process_lock:
                self.current_process = None
            if 'monitor_thread' in locals():
                monitor_thread.join()
            GLib.idle_add(self.hide_processing_spinner)


                
    def disable_open_button(self):
        if self.open_button:
            self.open_button.set_sensitive(False)
        print("Open button disabled.")

    def enable_open_button(self):
        if self.open_button:
            self.open_button.set_sensitive(True)
        print("Open button enabled.")

    def replace_home_with_tilde_in_path(self, path_str):
        """Replace the user's home directory with '~' in the given path string."""
        user_home = os.getenv("HOME")
        if path_str.startswith(user_home):
            return path_str.replace(user_home, "~", 1)
        return path_str

    def expand_and_resolve_path(self, path):
        """Expand '~' to the home directory and resolve the absolute path."""
        return Path(path).expanduser().resolve()
        
    def load_script_list(self, prefixdir=None):
        """
        Loads all .charm files from the specified directory (or the default self.prefixes_dir)
        into the self.script_list dictionary.

        Args:
            prefixdir (str or Path, optional): The directory to search for .charm files.
                                               Defaults to self.prefixes_dir.
        """
        if prefixdir is None:
            prefixdir = self.prefixes_dir

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
                if 'sha256sum' not in script_data or script_data['sha256sum'] == None :
                    should_generate_hash = True

                if should_generate_hash:
                    if 'exe_file' in script_data or script_data['exe_file']:
                        # Generate hash from exe_file if it exists
                        exe_path = Path(script_data['exe_file']).expanduser().resolve()
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

                # Add modification time (mtime) to script_data
                script_data['mtime'] = script_file.stat().st_mtime

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
        """
        Show a dialog with checkboxes to allow the user to select shortcuts for desktop creation.
        
        Args:
            script: The script that contains information about the shortcut.
            script_key: The unique identifier for the script in the script_list.
        """
        # Ensure we're using the updated script path from the script_data
        script_data = self.script_list.get(script_key)
        if not script_data:
            print(f"Error: Script key {script_key} not found in script_list.")
            return

        # Extract the Wine prefix directory associated with this script
        wine_prefix_dir = Path(script_data['script_path']).parent.expanduser().resolve()
        script_path = Path(script_data['script_path']).expanduser().resolve()

        # Fetch the list of charm files only in the specific Wine prefix directory
        charm_files = list(wine_prefix_dir.rglob("*.charm"))

        # If there are no charm files, show a message
        if not charm_files:
            self.show_info_dialog("No Shortcuts", f"No shortcuts are available for desktop creation in {wine_prefix_dir}.")
            return

        # Create a new dialog for selecting shortcuts
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            title="Create Desktop Shortcuts",
            body=f"Select the shortcuts you want to create for {wine_prefix_dir.name}:"
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

        # Add a label for the category selection
        category_label = Gtk.Label(label="Select Category:")
        category_label.set_xalign(0)
        vbox.append(category_label)

        # Create a ComboBoxText widget for selecting categories
        category_combo = Gtk.ComboBoxText()
        categories = [
            "AudioVideo", "Audio", "Video", "Development", "Education",
            "Game", "Graphics", "Network", "Office", "Science",
            "Settings", "System", "Utility"
        ]
        for category in categories:
            category_combo.append_text(category)

        # Set default selection to "Game"
        category_combo.set_active(categories.index("Game"))
        vbox.append(category_combo)

        # Add the vertical box to the dialog
        dialog.set_extra_child(vbox)

        # Add "Create" and "Cancel" buttons
        dialog.add_response("create", "Create")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")

        # Connect the response signal to handle desktop shortcut creation
        dialog.connect("response", self.on_add_desktop_shortcut_response, checkbox_dict, category_combo)

        # Present the dialog
        dialog.present()

    def on_add_desktop_shortcut_response(self, dialog, response_id, checkbox_dict, category_combo):
        """
        Handle the response from the create desktop shortcut dialog.
        
        Args:
            dialog: The Adw.MessageDialog instance.
            response_id: The ID of the response clicked by the user.
            checkbox_dict: Dictionary mapping checkboxes to charm files.
            category_combo: The ComboBoxText widget for selecting the category.
        """
        if response_id == "create":
            # Get the selected category from the combo box
            selected_category = category_combo.get_active_text()

            # Iterate through the checkboxes and create shortcuts for selected files
            for checkbox, charm_file in checkbox_dict.items():
                if checkbox.get_active():  # Check if the checkbox is selected
                    try:
                        # Load the script data to create the desktop shortcut
                        script_key = self.get_script_key_from_shortcut(charm_file)
                        script_data = self.script_list.get(script_key)

                        if not script_data:
                            print(f"Error: Script data for {charm_file} not found.")
                            continue

                        progname = script_data.get('progname', '')
                        script_path = Path(script_data['script_path']).expanduser().resolve()
                        wineprefix = Path(script_data['script_path']).parent.expanduser().resolve()
                        icon_name = script_path.stem + ".png"
                        icon_dir = script_path.parent
                        icon_path = icon_dir / icon_name

                        # Create the desktop entry using the existing method, including the selected category
                        self.create_desktop_entry(progname, script_path, icon_path, wineprefix, selected_category)
                        print(f"Desktop shortcut created for: {charm_file}")

                    except Exception as e:
                        print(f"Error creating desktop shortcut for {charm_file}: {e}")

            # Notify the user of successful shortcut creation
            self.show_info_dialog("Shortcut Created", "Desktop shortcuts created successfully.")

        else:
            print("Shortcut creation canceled")

        # Close the dialog
        dialog.close()


    def remove_desktop_shortcut(self, script, script_key, *args):
        """
        Show a dialog with checkboxes to allow the user to select desktop shortcuts for deletion.

        Args:
            script: The script that contains information about the shortcut.
            script_key: The unique identifier for the script in the script_list.
        """
        # Ensure we're using the updated script path from the script_data
        script_data = self.script_list.get(script_key)
        if not script_data:
            print(f"Error: Script key {script_key} not found in script_list.")
            return

        # Extract the Wine prefix directory associated with this script
        wine_prefix_dir = Path(script_data['script_path']).parent.expanduser().resolve()
        script_path = Path(script_data['script_path']).expanduser().resolve()

        # Fetch the list of desktop files in the specific Wine prefix directory
        desktop_files = list(wine_prefix_dir.glob("*.desktop"))

        # If there are no desktop shortcut files, show a message
        if not desktop_files:
            self.show_info_dialog("No Desktop Shortcuts", f"No desktop shortcuts are available for deletion in {wine_prefix_dir}.")
            return

        # Create a new dialog for selecting desktop shortcuts
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            title="Delete Desktop Shortcuts",
            body=f"Select the desktop shortcuts you want to delete for {wine_prefix_dir.name}:"
        )

        # A dictionary to store the checkboxes and corresponding desktop files
        checkbox_dict = {}

        # Create a vertical box to hold the checkboxes
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Iterate through the desktop files and create checkboxes with icons and labels
        for desktop_file in desktop_files:
            # Create the icon and title widget (icon + label) for each desktop file
            desktop_script_file = desktop_file.with_suffix(".charm")
            icon_title_widget = self.create_icon_title_widget(desktop_script_file)

            # Create a horizontal box to hold the checkbox and the icon/label widget
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            # Create a checkbox for each desktop shortcut
            checkbox = Gtk.CheckButton()
            hbox.append(checkbox)

            # Append the icon and title widget (icon + label)
            hbox.append(icon_title_widget)

            # Add the horizontal box (with checkbox and icon+label) to the vertical box
            vbox.append(hbox)

            # Store the checkbox and associated file in the dictionary
            checkbox_dict[checkbox] = desktop_file

        # Add the vertical box to the dialog
        dialog.set_extra_child(vbox)

        # Add "Delete" and "Cancel" buttons
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")

        # Connect the response signal to handle desktop shortcut deletion
        dialog.connect("response", self.on_remove_desktop_shortcut_response, checkbox_dict)

        # Present the dialog
        dialog.present()


    def on_remove_desktop_shortcut_response(self, dialog, response_id, checkbox_dict):
        """
        Handle the response from the delete desktop shortcut dialog.

        Args:
            dialog: The Adw.MessageDialog instance.
            response_id: The ID of the response clicked by the user.
            checkbox_dict: Dictionary mapping checkboxes to desktop files.
        """
        if response_id == "delete":
            # Iterate through the checkboxes and delete selected files
            for checkbox, desktop_file in checkbox_dict.items():
                if checkbox.get_active():  # Check if the checkbox is selected
                    try:
                        if desktop_file.exists():
                            # Delete the desktop file
                            desktop_file.unlink()
                            print(f"Deleted desktop shortcut: {desktop_file}")

                            # Find and delete the symbolic link in the applications directory
                            symlink_path = self.applicationsdir / f"winecharm_{desktop_file.stem}.desktop"
                            if symlink_path.exists() or symlink_path.is_symlink():
                                symlink_path.unlink()
                                print(f"Removed symlink: {symlink_path}")

                        else:
                            print(f"Desktop shortcut file does not exist: {desktop_file}")
                    except Exception as e:
                        print(f"Error deleting desktop shortcut: {e}")
        else:
            print("Deletion canceled")

        # Close the dialog
        dialog.close()

########################
    def show_save_user_dirs_dialog(self, script, script_key, button):
        default_backup_name = f"{script.stem}_user_dirs_backup.tar.zst"

        file_dialog = Gtk.FileDialog.new()
        file_dialog.set_initial_name(default_backup_name)

        file_dialog.save(self.window, None, lambda dlg, res: self.on_save_user_dirs_dialog_response(dlg, res, script, script_key))

    def on_save_user_dirs_dialog_response(self, dialog, result, script, script_key):
        try:
            backup_file = dialog.save_finish(result)
            if backup_file:
                backup_path = backup_file.get_path()
                print(f"Backup will be saved to: {backup_path}")

                # Start the backup process in a separate thread
                threading.Thread(target=self.save_user_dirs, args=(script, script_key, backup_path)).start()

        except GLib.Error as e:
            print(f"An error occurred while saving the backup: {e}")

    def save_user_dirs(self, script, script_key, backup_path):
        wineprefix = Path(script).parent

        # Define the user's directory in Wineprefix (usually found at drive_c/users)
        users_dir = wineprefix / "drive_c" / "users"

        if not users_dir.exists():
            print(f"Error: User directories not found in Wineprefix {wineprefix}.")
            return

        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            print("Error: Unable to determine the current username.")
            return

        try:
            # Backup command with zstd compression and path transformation
            tar_command = [
                'tar', '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
                '--transform', f"s|{current_username}|%USERNAME%|g",  # Rename directory
                '-cf', backup_path,
                '-C', str(users_dir),  # Change directory to parent of 'users'
                '.'  # Archive all directories in the 'users' directory
            ]

            print(f"Running backup command: {' '.join(tar_command)}")
            result = subprocess.run(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                raise Exception(f"Backup failed: {result.stderr}")

            print(f"Backup archive created at {backup_path}")
            GLib.idle_add(self.show_info_dialog, "Saved", f"User directory Saved to {backup_path}")
        except Exception as e:
            print(f"Error during backup: {e}")




    def show_load_user_dirs_dialog(self, script, script_key, button):
        # Create a Gtk.FileDialog instance for loading the file
        file_dialog = Gtk.FileDialog.new()

        # Set filter to only allow tar.zst files
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Backup Files (*.tar.zst)")
        file_filter.add_pattern("*.tar.zst")

        # Create a Gio.ListStore to hold the file filter (required by Gtk.FileDialog)
        filter_list_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_list_store.append(file_filter)

        # Set the filters on the file dialog
        file_dialog.set_filters(filter_list_store)

        # Open the dialog asynchronously to select the file to load
        file_dialog.open(self.window, None, lambda dlg, res: self.on_load_user_dirs_dialog_response(dlg, res, script, script_key))


    def on_load_user_dirs_dialog_response(self, dialog, result, script, script_key):
        try:
            backup_file = dialog.open_finish(result)
            if backup_file:
                backup_path = backup_file.get_path()
                print(f"Backup will be loaded from: {backup_path}")

                # Start the load process in a separate thread
                threading.Thread(target=self.load_user_dirs, args=(script, script_key, backup_path)).start()

        except GLib.Error as e:
            print(f"An error occurred while loading the backup: {e}")

    def load_user_dirs(self, script, script_key, backup_path):
        wineprefix = Path(script).parent
        users_dir = wineprefix / "drive_c" / "users"
        if not wineprefix.exists():
            print(f"Error: Wineprefix not found at {wineprefix}.")
            return

        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            print("Error: Unable to determine the current username.")
            return
            

        try:
            # Extraction command
            tar_command = [
                'tar', '-I', 'zstd -d',  # Decompress with zstd
                '-xf', backup_path,
                '--transform', f"s|%USERNAME%|{current_username}|g",
                '--transform', f"s|XOUSERXO|{current_username}|g",
                '-C', str(wineprefix / "drive_c" / "users")  # Extract in the drive_c directory
            ]
            print(f"Running load command: {' '.join(tar_command)}")
            result = subprocess.run(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                raise Exception(f"Restore failed: {result.stderr}")

            print(f"Backup loaded from {backup_path}")
            
            GLib.idle_add(self.show_info_dialog, "Loaded", f"User directory extracted to {backup_path}")

        except Exception as e:
            print(f"Error during restore: {e}")

########################
    def import_game_directory(self, script, script_key, *args):
        script_data = self.script_list.get(script_key)
        if not script_data:
            print(f"Error: Script key {script_key} not found in script_list.")
            return

        # Extract exe_file and wineprefix from script_data
        exe_file = Path(script_data['exe_file']).expanduser().resolve()
        script_path = Path(script_data['script_path']).expanduser().resolve()
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
        source_size = sum(f.stat().st_size for f in source.glob('**/*') if f.is_file())
        destination_free_space = shutil.disk_usage(destination.parent).free
        return destination_free_space > source_size



########### 
    def run_other_exe(self, script, script_key, *args):
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
        script_data = self.script_list.get(script_key)
        if not script_data:
            return None

        unique_id = str(uuid.uuid4())
        env = os.environ.copy()
        env['WINECHARM_UNIQUE_ID'] = unique_id

        exe_file = Path(script_data.get('exe_file', '')).expanduser().resolve()
        script = Path(script_data.get('script_path', '')).expanduser().resolve()
        progname = script_data.get('progname', '')
        script_args = script_data.get('args', '')
        script_key = script_data.get('sha256sum', script_key)
        env_vars = script_data.get('env_vars', '')
        wine_debug = script_data.get('wine_debug', '')
        exe_name = Path(exe_file).name
        wineprefix = Path(script_data.get('script_path', '')).parent.expanduser().resolve()

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
            print(f"Error running EXE: {e}")

    def set_environment_variables(self, script, script_key, *args):
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
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,  # Assuming self.window is the main application window
            title="Set Environment Variables",
            body="Modify the environment variables for this script (X=Y;Z=W format):"
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
        dialog.present()


    def on_env_vars_dialog_response(self, dialog, response_id, entry, script_key):
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
                script_path = Path(script_data['script_path']).expanduser().resolve()
                with open(script_path, 'w') as file:
                    yaml.dump(script_data, file, default_flow_style=False, width=1000)

                print(f"Updated environment variables for {script_path}: {new_env_vars}")
            else:
                print(f"Invalid environment variables format: {new_env_vars}")
                self.show_info_dialog("Invalid Environment Variables", "Please use the correct format: X=Y;Z=W.")

        else:
            print("Environment variable modification canceled")

        # Close the dialog
        dialog.close()


    def validate_environment_variables(self, env_vars):
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
        """
        Display a dialog to change the runner for the given script.
        """
        # Store the current script and key for reuse
        self.selected_script = script
        self.selected_script_key = script_key

        # Gather valid runners
        all_runners = self.get_valid_runners(self.runners_dir, is_bundled=False)

        # Check for prefix-specific runners
        wineprefix = Path(script).parent
        prefix_runners_dir = wineprefix / "Runner"
        all_runners.extend(self.get_valid_runners(prefix_runners_dir, is_bundled=True))

        # Add System Wine to the list if available
        system_wine_display, _ = self.get_system_wine()
        if system_wine_display:
            all_runners.insert(0, (system_wine_display, ""))  # Empty string for System Wine

        # If no runners are available, show the "no runners" dialog
        if not all_runners:
            self.show_no_runners_available_dialog()
            return

        # Get the runner from the script file
        script_data = self.script_list.get(script_key, {})
        runner_from_script = script_data.get('runner', '')
        runner_from_script = os.path.expanduser(runner_from_script)
        runner_from_script = os.path.abspath(runner_from_script)

        # Build the list of runner paths in all_runners
        runner_paths_in_list = [os.path.abspath(os.path.expanduser(runner_path)) for _, runner_path in all_runners]

        # Check if runner_from_script is in runner_paths_in_list
        if runner_from_script and runner_from_script not in runner_paths_in_list:
            # Try to validate runner_from_script
            if self.validate_runner(runner_from_script):
                # Create a display name for this runner
                runner_dir = os.path.dirname(os.path.dirname(runner_from_script))
                runner_name = os.path.basename(runner_dir)
                runner_display_name = f"{runner_name} (from script)"
                # Append it to all_runners
                all_runners.append((runner_display_name, runner_from_script))
                runner_paths_in_list.append(runner_from_script)
            else:
                print(f"Runner specified in script not found or invalid: {runner_from_script}")

        # Now, create the MessageDialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            heading="Change Runner",
            body="Select a runner for the script:"
        )

        # Create a horizontal box for the ComboBox and download icon
        runner_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Create a ComboBoxText and populate with runners
        runner_combo = Gtk.ComboBoxText()
        # Keep track of runner paths corresponding to combo box indices
        combo_runner_paths = []
        for display_name, runner_path in all_runners:
            runner_combo.append_text(display_name)
            combo_runner_paths.append(os.path.abspath(os.path.expanduser(runner_path)))

        # Find the index corresponding to runner_from_script
        selected_index = 0  # default to first item
        for index, runner_path in enumerate(combo_runner_paths):
            if runner_path == runner_from_script:
                selected_index = index
                break

        runner_combo.set_active(selected_index)
        runner_combo.set_hexpand(True)

        # Create a download icon button
        download_button = Gtk.Button()
        download_icon = Gtk.Image.new_from_icon_name("emblem-downloads-symbolic")
        download_button.set_child(download_icon)
        download_button.set_tooltip_text("Download Runner")
        download_button.connect("clicked", lambda btn: self.on_download_runner_clicked(dialog))

        # Add the ComboBox and download button to the hbox
        runner_hbox.append(runner_combo)
        runner_hbox.append(download_button)

        # Create a vertical box and add the runner_hbox
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(runner_hbox)

        # Set the content of the dialog
        dialog.set_extra_child(content_box)

        # Add responses (buttons)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        # Connect response and present the dialog
        dialog.connect("response", self.on_change_runner_response, runner_combo, all_runners, script_key)
        dialog.present()


    def on_change_runner_response(self, dialog, response_id, runner_combo, all_runners, script_key):
        """
        Handle the response when the user selects a runner or cancels the dialog.
        """
        if response_id == "ok":
            selected_index = runner_combo.get_active()
            if selected_index < 0:
                print("No runner selected.")
                dialog.close()
                return

            new_runner_display, new_runner_path = all_runners[selected_index]
            print(f"Selected new runner: {new_runner_display} -> {new_runner_path}")

            # Set to an empty string if System Wine is selected
            new_runner_value = '' if new_runner_display.startswith("System Wine") else new_runner_path
            script_data = self.script_list.get(script_key, {})
            script_data['runner'] = self.replace_home_with_tilde_in_path(new_runner_value)

            script_path = Path(script_data['script_path']).expanduser().resolve()
            try:
                with open(script_path, 'w') as file:
                    yaml.dump(script_data, file, default_flow_style=False, width=1000)
                print(f"Runner for {script_path} updated to {new_runner_display}")
            except Exception as e:
                print(f"Error updating runner: {e}")
        else:
            print("Runner change canceled.")

        dialog.close()


    def get_valid_runners(self, runners_dir, is_bundled=False):
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
        """
        Show a dialog when no runners are available, prompting the user to download one.
        """
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            heading="No Runners Available",
            body="No runners were found. Please download a runner to proceed."
        )

        download_button = Gtk.Button(label="Download Runner")
        download_button.connect("clicked", lambda btn: self.on_download_runner_clicked_default(dialog))

        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda btn: dialog.close())

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.append(cancel_button)
        button_box.append(download_button)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(button_box)

        dialog.set_extra_child(content_box)
        dialog.present()

        
    def rename_prefix_directory(self, script, script_key, *args):
        """
        Show a dialog to allow the user to rename the Wine prefix directory.

        :param script_key: The unique key for identifying the script.
        """
        # Retrieve script data using the script key
        script_data = self.script_list.get(script_key)
        
        # Debug: Print all keys to identify possible mismatches
        if script_data is None:
            print(f"Error: Script key {script_key} not found in script_list.")
            print("Available script keys:", list(self.script_list.keys()))
            return

        # Get the current Wine prefix path
        wineprefix = Path(script_data.get('wineprefix')).expanduser().resolve()
        if not wineprefix.exists():
            print(f"Error: Wine prefix directory '{wineprefix}' does not exist.")
            return

        # Create a dialog to prompt the user for the new directory name
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            title="Rename Wine Prefix",
            body=f"Enter a new name for the Wine prefix directory:\n(Current: {wineprefix.name})"
        )

        # Create an entry field with the current directory name
        entry = Gtk.Entry()
        entry.set_text(wineprefix.name)

        # Add the entry field to the dialog
        dialog.set_extra_child(entry)

        # Add "OK" and "Cancel" buttons
        dialog.add_response("ok", "OK")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")

        # Connect the response signal to handle the user's input
        dialog.connect("response", self.on_rename_prefix_dialog_response, entry, script_key, wineprefix)

        # Present the dialog
        dialog.present()


    def on_rename_prefix_dialog_response(self, dialog, response, entry, script_key, old_wineprefix):
        """
        Handle the user's response to the rename prefix dialog.

        :param dialog: The dialog instance.
        :param response: The user's response (e.g., "ok" or "cancel").
        :param entry: The entry widget containing the new directory name.
        :param script_key: The unique key identifying the script.
        :param old_wineprefix: The original Wine prefix directory path.
        """
        if response != "ok":
            dialog.destroy()
            return

        # Get the new directory name from the entry widget
        new_name = entry.get_text().strip()
        if not new_name or new_name == old_wineprefix.name:
            print("No changes made to the Wine prefix directory name.")
            dialog.destroy()
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
        dialog.destroy()

    def update_charm_files_with_new_prefix(self, new_wineprefix, old_wineprefix):
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
        """
        Update internal script data references related to the old prefix.

        :param script_key: The unique key identifying the script.
        :param new_wineprefix: The new Wine prefix path.
        """
        # Get the script data from script_list
        script_data = self.script_list.get(script_key)
        if script_data:
            old_wineprefix = Path(script_data['wineprefix']).expanduser().resolve()
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
                old_script_filename = Path(script_data['script_path']).name
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

    def set_wine_arch(self, script, script_key, *args):
        print(f"Setting Wine architecture for {script} with script_key {script_key}")
        # Add functionality to set Wine architecture (e.g., 32-bit or 64-bit).

    def wine_config(self, script, script_key, *args):
        script_data = self.script_list.get(script_key)
        if not script_data:
            return None

        unique_id = str(uuid.uuid4())
        env = os.environ.copy()
        env['WINECHARM_UNIQUE_ID'] = unique_id

        exe_file = Path(script_data.get('exe_file', '')).expanduser().resolve()
        script = Path(script_data.get('script_path', '')).expanduser().resolve()
        progname = script_data.get('progname', '')
        script_args = script_data.get('args', '')
        script_key = script_data.get('sha256sum', script_key)
        env_vars = script_data.get('env_vars', '')
        wine_debug = script_data.get('wine_debug', '')
        exe_name = Path(exe_file).name
        wineprefix = Path(script_data.get('script_path', '')).parent.expanduser().resolve()

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
        script_data = self.script_list.get(script_key)
        if not script_data:
            return None

        unique_id = str(uuid.uuid4())
        env = os.environ.copy()
        env['WINECHARM_UNIQUE_ID'] = unique_id

        exe_file = Path(script_data.get('exe_file', '')).expanduser().resolve()
        script = Path(script_data.get('script_path', '')).expanduser().resolve()
        progname = script_data.get('progname', '')
        script_args = script_data.get('args', '')
        script_key = script_data.get('sha256sum', script_key)
        env_vars = script_data.get('env_vars', '')
        wine_debug = script_data.get('wine_debug', '')
        exe_name = Path(exe_file).name
        wineprefix = Path(script_data.get('script_path', '')).parent.expanduser().resolve()

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

#########   ######
    def replace_open_button_with_settings(self):
        # Remove existing click handler from open button
        if hasattr(self, 'open_button_handler_id'):
            self.open_button.disconnect(self.open_button_handler_id)
        
        self.set_open_button_label("Settings")
        self.set_open_button_icon_visible(False)
        # Connect new click handler
        self.open_button_handler_id = self.open_button.connect(
            "clicked",
            lambda btn: print("Settings clicked")
        )

    def restore_open_button(self):
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
        """
        Display the settings options with search functionality using existing search mechanism.
        """
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
            ("Runner Set Default", "preferences-desktop-apps-symbolic", self.set_default_runner),
            ("Runner Download", "emblem-downloads-symbolic", self.on_settings_download_runner_clicked),
            ("Runner Import", "folder-download-symbolic", self.import_runner),
            ("Runner Backup", "document-save-symbolic", self.backup_runner),
            ("Runner Restore", "document-revert-symbolic", self.restore_runner),
            ("Runner Delete", "user-trash-symbolic", self.delete_runner),
            ("Template Set Default", "document-new-symbolic", self.set_default_template),
            ("Template Configure", "preferences-other-symbolic", self.configure_template),
            ("Template Import", "folder-download-symbolic", self.import_template),
            ("Template Clone", "folder-copy-symbolic", self.clone_template),
            ("Template Backup", "document-save-symbolic", self.backup_template),
            ("Template Restore", "document-revert-symbolic", self.restore_template),
            ("Template Delete", "user-trash-symbolic", self.delete_template),
            ("Set Wine Arch", "preferences-system-symbolic", self.set_wine_arch),
            ("Single Prefix Mode", "folder-symbolic", self.single_prefix_mode),
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
                option_button.set_size_request(190, 36)
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
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Single Prefix Mode",
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
            if response == "apply":
                new_state = single_prefix_radio.get_active()
                if new_state != current_state:
                    self.handle_prefix_mode_change(new_state)
            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

    def handle_prefix_mode_change(self, new_state):
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
        if self.single_prefix:
            if not single_dir.exists():
                print("Creating single prefix copy...")
                self.copy_template(single_dir)
        else:
            print("Reverting to multiple prefixes")
            if single_dir.exists():
                print("Cleaning up single prefix directory...")
                shutil.rmtree(single_dir, ignore_errors=True)
##################### / single prefix mode

    # Implement placeholders for each setting's callback function
    def set_default_runner(self, action=None):
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
        """Setup factory items for the dropdown"""
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_margin_start(6)
        label.set_margin_end(6)
        list_item.set_child(label)

    def _on_dropdown_factory_bind(self, factory, list_item):
        """Bind data to factory items"""
        label = list_item.get_child()
        string_obj = list_item.get_item()
        if string_obj and isinstance(string_obj, Gtk.StringObject):
            label.set_label(string_obj.get_string())

    def on_set_default_runner_response(self, dialog, response_id, runner_dropdown, all_runners):
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

        dialog.close()

    def on_download_runner_clicked_default(self, dialog):
        """
        Handle the "Download Runner" button click from the set_default_runner dialog.
        """
        dialog.close()
        # Start the download process with the appropriate callback
        self.on_settings_download_runner_clicked(callback=self.on_download_complete_default_runner)

    def on_download_complete_default_runner(self):
        """
        Callback method to handle the completion of the runner download.
        Reopens the set_default_runner dialog.
        """
        # Reopen the set_default_runner dialog after the download completes
        self.set_default_runner()



    def maybe_fetch_runner_urls(self):
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
        """
        Save the runner data to the cache file in YAML format.
        """
        try:
            with open(self.runner_cache_file, 'w') as f:
                yaml.dump(runner_data, f)
            print(f"Runner data cached to {self.runner_cache_file}")
        except Exception as e:
            print(f"Error saving runner data to cache: {e}")

    def load_runner_data_from_cache(self):
        """
        Load runner data from the cache file.
        """
        try:
            with open(self.runner_cache_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading runner data from cache: {e}")
            return None
        
    def on_settings_download_runner_clicked(self, callback=None):
        """
        Handle the "Runner Download" option click.
        Use the cached runners loaded at startup, or notify if not available.
        """
        # Ensure runner data is loaded
        if not self.runner_data:
            self.show_info_dialog(
                "Runner data not available",
                "Please try again in a moment or restart the application."
            )
            # Invoke the callback since data is not available
            if callback is not None:
                GLib.idle_add(callback)
            return

        # Get the active window to set as transient parent
        active_window = self.get_active_window() or self.window

        # Create the dialog using Adw.MessageDialog
        dialog = Adw.MessageDialog(
            transient_for=active_window,
            modal=True,
            heading="Download Wine Runner",
            body="Select the runners you wish to download."
        )

        # Create a box for dialog content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.set_margin_top(10)
        content_box.set_margin_bottom(10)
        content_box.set_margin_start(10)
        content_box.set_margin_end(10)
        dialog.set_extra_child(content_box)

        # Labels and ComboBoxes for different Wine categories
        dropdown_data = [
            ("Wine Proton", self.runner_data.get("proton", [])),
            ("Wine Stable", self.runner_data.get("stable", [])),
            ("Wine Devel", self.runner_data.get("devel", [])),
            ("Wine-tkg", self.runner_data.get("tkg", [])),
            ("Wine-WoW64", self.runner_data.get("wow64", []))
        ]

        # Create a dictionary to hold the comboboxes for easy access
        combo_boxes = {}

        for label_text, file_list in dropdown_data:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            label = Gtk.Label(label=label_text)
            label.set_xalign(0)
            label.set_width_chars(12)  # Set fixed width for label alignment
            combo_box = Gtk.ComboBoxText()
            combo_box.append_text("Choose...")  # Default "Choose..." option
            for file in file_list:
                combo_box.append_text(file['name'])  # Add the runner name to the combobox
            combo_box.set_active(0)  # Set default to "Choose..."
            combo_boxes[label_text] = {
                "combo_box": combo_box,
                "file_list": file_list  # Keep track of the original data
            }

            # Add label and combobox to the horizontal box
            hbox.append(label)
            hbox.append(combo_box)

            # Add the hbox to the content box
            content_box.append(hbox)

        # Add buttons to the dialog
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("download", "Download")
        dialog.set_default_response("download")
        dialog.set_close_response("cancel")

        # Present the dialog
        dialog.present()

        # Connect the response signal to handle the dialog's response
        dialog.connect("response", self.on_download_runner_response, combo_boxes, callback)

    def on_download_runner_response(self, dialog, response_id, combo_boxes, callback=None):
        """
        Handle the response from the download runner dialog.
        Only download selected runners (not "Choose...").
        """
        if response_id == "download":
            # Extract selected runners from each combo box
            selected_runners = {}
            for label, data in combo_boxes.items():
                combo_box = data['combo_box']
                file_list = data['file_list']
                selected_runner_name = combo_box.get_active_text()
                if selected_runner_name != "Choose...":  # Only add valid selections
                    # Find the corresponding runner data (name and url) for the selected runner
                    selected_runner = next((runner for runner in file_list if runner['name'] == selected_runner_name), None)
                    if selected_runner:
                        selected_runners[label] = selected_runner

            if selected_runners:
                # Create a progress dialog
                progress_dialog = Adw.MessageDialog(
                    transient_for=self.window,
                    modal=True,
                    heading="Downloading Runners",
                    body=""
                )

                content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                content_box.set_margin_top(10)
                content_box.set_margin_bottom(10)
                content_box.set_margin_start(10)
                content_box.set_margin_end(10)
                progress_dialog.set_extra_child(content_box)

                progress_label = Gtk.Label(label="Starting download...")
                content_box.append(progress_label)

                runner_progress_bar = Gtk.ProgressBar()
                content_box.append(runner_progress_bar)

                total_progress_bar = Gtk.ProgressBar()
                content_box.append(total_progress_bar)

                progress_dialog.present()

                # Start the download in a separate thread, passing the callback
                threading.Thread(
                    target=self.download_runners_thread,
                    args=(selected_runners, progress_dialog, total_progress_bar, runner_progress_bar, progress_label, callback)
                ).start()
            else:
                print("No runners selected for download.")
                # Invoke the callback immediately since no download is needed
                if callback is not None:
                    GLib.idle_add(callback)
        else:
            print("Runner download canceled.")
            # Invoke the callback since the download was canceled
            if callback is not None:
                GLib.idle_add(callback)

        # Close the selection dialog
        dialog.close()


    def download_runners_thread(self, selected_runners, progress_dialog, total_progress_bar, runner_progress_bar, progress_label, callback=None):
        """
        Download selected runners and update progress.
        """
        total_runners = len(selected_runners)
        download_success = True  # Flag to track overall download success

        for idx, (label, runner) in enumerate(selected_runners.items()):
            # Update label with current runner
            GLib.idle_add(progress_label.set_text, f"Downloading {runner['name']}...")

            # Define progress callback for this runner
            def runner_progress_callback(progress):
                GLib.idle_add(runner_progress_bar.set_fraction, progress)

            # Download and extract runner
            try:
                self.download_and_extract_runner(runner['name'], runner['url'], progress_callback=runner_progress_callback)
            except Exception as e:
                download_success = False
                print(f"Error downloading {runner['name']}: {e}")
                GLib.idle_add(self.show_info_dialog, "Download Error", f"Failed to download {runner['name']}: {e}")

            # Reset runner progress bar
            GLib.idle_add(runner_progress_bar.set_fraction, 0.0)

            # Update total progress bar
            total_progress = (idx + 1) / total_runners
            GLib.idle_add(total_progress_bar.set_fraction, total_progress)

        # When done, close the dialog
        GLib.idle_add(progress_dialog.close)
        if download_success:
            GLib.idle_add(
                self.show_info_dialog,
                "Download Complete",
                "The runners have been successfully downloaded and extracted.",
                callback if callback is not None else None
            )
        else:
            GLib.idle_add(
                self.show_info_dialog,
                "Download Incomplete",
                "Some runners failed to download.",
                callback if callback is not None else None
            )

    def download_and_extract_runner(self, runner_name, download_url, progress_callback=None):
        """
        Download and extract the selected runner.
        Args:
            runner_name: The name of the runner.
            download_url: The full URL to download the runner.
            progress_callback: Callback function to update download progress.
        """
        runner_tar_path = self.runners_dir / f"{runner_name}.tar.xz"
        runner_extract_path = self.runners_dir

        # Ensure the runners directory exists
        self.runners_dir.mkdir(parents=True, exist_ok=True)

        def reporthook(block_num, block_size, total_size):
            if progress_callback:
                downloaded = block_num * block_size
                if total_size > 0:
                    percent = downloaded / total_size
                    GLib.idle_add(progress_callback, percent)

        try:
            print(f"Downloading {runner_name} from {download_url}")
            urllib.request.urlretrieve(download_url, runner_tar_path, reporthook)
            print(f"Download complete: {runner_tar_path}")

            # Extract the .tar.xz file
            print(f"Extracting {runner_tar_path} to {runner_extract_path}")
            runner_extract_path.mkdir(exist_ok=True)
            subprocess.run(["tar", "-xf", str(runner_tar_path), "-C", str(runner_extract_path)], check=True)
            print(f"Extraction complete: {runner_extract_path}")

            # Clean up the downloaded .tar.xz file if desired
            runner_tar_path.unlink()
            print(f"Removed downloaded archive: {runner_tar_path}")

        except Exception as e:
            print(f"Error downloading or extracting {runner_name}: {e}")
            raise

        print(f"Runner {runner_name} is ready in {runner_extract_path}")


    def import_runner(self, action=None):
        print("Importing a runner...")
        # Add functionality to import a runner.


    def delete_runner(self, action=None):
        """
        Allow the user to delete a selected runner.
        """

        # Step 1: Gather valid runners from runners_dir
        all_runners = self.get_valid_runners(self.runners_dir, is_bundled=False)
        if not all_runners:
            # If no runners are available, show an information dialog
            self.show_info_dialog("No Runners Available", "No runners found to delete.")
            return

        # Create the MessageDialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            heading="Delete Runner",
            body="Select a runner to delete:"
        )

        # Create the ComboBox for runners
        runner_combo = Gtk.ComboBoxText()
        combo_runner_dirs = []  # Store constructed paths as `runners_dir/{display_name}`

        for display_name, _ in all_runners:
            runner_combo.append_text(display_name)
            # Construct the path as `runners_dir/display_name` and store it
            runner_dir = os.path.join(self.runners_dir, display_name)
            combo_runner_dirs.append(runner_dir)

        runner_combo.set_active(0)
        runner_combo.set_hexpand(True)

        # Add the ComboBox to the content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(runner_combo)

        # Add OK and Cancel buttons to the dialog
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_default_response("delete")
        dialog.set_close_response("cancel")
        dialog.set_extra_child(content_box)

        # Connect the response signal to a deletion handler
        dialog.connect("response", self.on_delete_runner_response, runner_combo, combo_runner_dirs)
        dialog.present()

    def on_delete_runner_response(self, dialog, response, runner_combo, combo_runner_dirs):
        """
        Handle the response from the delete runner dialog.
        """
        dialog.destroy()

        if response != "delete":
            return  # If the user cancels, exit early

        # Get the selected runner directory path
        selected_index = runner_combo.get_active()
        if selected_index < 0:
            self.show_info_dialog("Selection Error", "No runner was selected for deletion.")
            return

        selected_runner_dir = combo_runner_dirs[selected_index]

        # Attempt to delete the runner directory and notify the user
        try:
            # Delete the entire directory and its contents
            if os.path.isdir(selected_runner_dir):
                shutil.rmtree(selected_runner_dir)
            else:
                raise NotADirectoryError(f"{selected_runner_dir} is not a directory.")

            # Notify the user of successful deletion
            self.show_info_dialog("Deletion Successful", f"Runner directory '{selected_runner_dir}' and its contents were deleted successfully.")

        except Exception as e:
            # Handle errors and display error message
            self.show_info_dialog("Deletion Error", f"Error deleting runner directory '{selected_runner_dir}': {e}")


    def set_default_template(self, action=None):
        print("Setting the default template...")
        # Add functionality to set the default template.

    def configure_template(self, action=None):
        print("Configuring the template...")
        # Add functionality to configure the template.

    def import_template(self, action=None):
        print("Importing a template...")
        # Add functionality to import a template.

    def clone_template(self, action=None):
        print("Cloning the template...")
        # Add functionality to clone the template.

    def backup_template(self, action=None):
        print("Backing up the template...")
        # Add functionality to back up the template.

    def restore_template(self, action=None):
        print("Restoring a template from backup...")
        # Add functionality to restore a template.

    def delete_template(self, action=None):
        print("Deleting the template...")
        # Add functionality to delete the template.

    def set_wine_arch(self):
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Set Wine Architecture",
            body="Select the default architecture for new prefixes:"
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        win32_radio = Gtk.CheckButton(label="32-bit (win32)")
        win64_radio = Gtk.CheckButton(label="64-bit (win64)")
        win64_radio.set_group(win32_radio)
        
        current_arch = self.arch
        win32_radio.set_active(current_arch == 'win32')
        win64_radio.set_active(current_arch == 'win64')

        vbox.append(win32_radio)
        vbox.append(win64_radio)
        dialog.set_extra_child(vbox)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def handle_architecture_change(new_arch):
            # Determine paths based on selected architecture
            new_template = self.default_template_win32 if new_arch == 'win32' else self.default_template_win64
            single_prefix_dir = self.single_prefix_dir_win32 if new_arch == 'win32' else self.single_prefix_dir_win64
            
            # Only proceed if architecture actually changed
            if new_arch == self.arch:
                return

            # Update settings first
            self.arch = new_arch
            self.template = new_template
            self.save_settings()
            print(f" => New Template = {new_template}")
            new_template = Path(new_template).expanduser().resolve()
            print(f" => New Template = {new_template}")
            # Check template existence without initializing
            if not new_template.exists():
                print(f"Initializing new {new_arch} template...")
                self.on_back_button_clicked(None)
                self.initialize_template(new_template, 
                                    lambda: self.finalize_arch_change(single_prefix_dir),
                                    arch=new_arch)
            else:
                print(f"Using existing {new_arch} template")
                finalize_arch_change(single_prefix_dir)

        def finalize_arch_change(single_prefix_dir):
            # Handle single prefix copy if needed
            
            if self.single_prefix and not single_prefix_dir.exists():
                print(f"Copying to {single_prefix_dir.name}...")
                self.copy_template(single_prefix_dir)
            self.set_dynamic_variables()
            self.show_options_for_settings()

        def on_response(dialog, response):
            if response == "ok":
                new_arch = 'win32' if win32_radio.get_active() else 'win64'
                if new_arch != current_arch:
                    self.main_frame.set_child(None)
                    #self.show_processing_spinner(f"Configuring {new_arch}...")
                    handle_architecture_change(new_arch)
            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()
        
################
    def backup_runner(self, action=None):
        """
        Allow the user to backup a runner.
        """
        # Gather valid runners from runners_dir
        all_runners = self.get_valid_runners(self.runners_dir, is_bundled=False)

        # If no runners are available, show a message
        if not all_runners:
            self.show_info_dialog("No Runners Available", "No runners found to backup.")
            return

        # Create the MessageDialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
            heading="Backup Runner",
            body="Select a runner to backup:"
        )

        # Create the ComboBox for runners
        runner_combo = Gtk.ComboBoxText()
        combo_runner_paths = []  # Store runner paths corresponding to indices

        for display_name, runner_path in all_runners:
            runner_combo.append_text(display_name)
            combo_runner_paths.append(os.path.abspath(os.path.expanduser(runner_path)))

        runner_combo.set_active(0)
        runner_combo.set_hexpand(True)

        # Add the ComboBox to the content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(runner_combo)

        # Add OK and Cancel buttons to the dialog
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")
        dialog.set_extra_child(content_box)

        dialog.connect("response", self.on_backup_runner_response, runner_combo, combo_runner_paths)
        dialog.present()



    def on_backup_runner_response(self, dialog, response_id, runner_combo, combo_runner_paths):
        if response_id == "ok":
            selected_index = runner_combo.get_active()
            if selected_index < 0:
                print("No runner selected.")
                self.show_info_dialog("No Runner Selected", "Please select a runner to backup.")
                dialog.close()
                return
            runner_path = combo_runner_paths[selected_index]
            runner_name = runner_combo.get_active_text()
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
                try:
                    save_file = dialog.save_finish(result)
                    if save_file:
                        destination_path = save_file.get_path()
                        print(f"Backup destination selected: {destination_path}")
                        # Start the backup process in a separate thread
                        threading.Thread(target=self.create_runner_backup, args=(runner_path, destination_path)).start()
                        self.show_info_dialog("Backup Complete", f"Runner backup saved to {destination_path}.")
                except GLib.Error as e:
                    print(f"An error occurred: {e}")

            # Show the save dialog
            file_dialog.save(self.window, None, on_save_file_dialog_response)
        else:
            print("Backup runner canceled.")

        dialog.close()


    def create_runner_backup(self, runner_path, destination_path):
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
                print(f"An error occurred: {e}")

        # Show the open dialog
        file_dialog.open(self.window, None, on_open_file_dialog_response)

    def extract_runner_archive(self, archive_path):
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
        """
        Handle cancel button click during template initialization
        """
        dialog = Adw.MessageDialog.new(
            self.window,
            "Cancel Initialization",
            "Do you want to cancel the template initialization process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Initialization")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_template_init_dialog_response)
        dialog.present()

    def on_cancel_template_init_dialog_response(self, dialog, response):
        """
        Handle cancel dialog response for template initialization
        """
        if response == "cancel":
            self.stop_processing = True
        dialog.close()

    def cleanup_cancelled_template_init(self, template_dir):
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
        """
        Handle cancel button click during wine directory import
        """
        dialog = Adw.MessageDialog.new(
            self.window,
            "Cancel Import",
            "Do you want to cancel the wine directory import process?"
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Import")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_import_dialog_response)
        dialog.present()

    def on_cancel_import_dialog_response(self, dialog, response):
        """
        Handle cancel dialog response for wine directory import
        """
        if response == "cancel":
            self.stop_processing = True
        dialog.close()

############################################### 4444444444444444444444444 New initialize template

####################### Restore Backup (prefix, bottle, .tar.zst)

    def restore_from_backup(self, action=None, param=None):
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
            # Handle errors, such as dialog cancellation
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")


    def restore_prefix_bottle_wzt_tar_zst(self, file_path):
        """
        Restore from a .prefix or .bottle which is a .tar.zst compressed file.
        """
        self.stop_processing = False
        
        try:
            # Extract prefix name before starting
            extracted_prefix = self.extract_prefix_dir(file_path)
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
                    # Determine the file extension and get the appropriate restore steps
                    if file_path.endswith(".wzt"):
                        restore_steps = self.get_wzt_restore_steps(file_path)
                    else:
                        restore_steps = self.get_restore_steps(file_path)

                    # Perform restore steps
                    for step_text, step_func in restore_steps:
                        if self.stop_processing:
                            # Handle cancellation
                            if backup_dir and backup_dir.exists():
                                if extracted_prefix.exists():
                                    shutil.rmtree(extracted_prefix)
                                shutil.move(str(backup_dir), str(extracted_prefix))
                                print(f"Restored original directory from: {backup_dir}")
                            GLib.idle_add(self.on_restore_completed)
                            #GLib.idle_add(self.show_info_dialog, "Cancelled", "Restore process was cancelled")
                            return

                        GLib.idle_add(self.show_initializing_step, step_text)
                        try:
                            step_func()
                            GLib.idle_add(self.mark_step_as_done, step_text)
                        except Exception as e:
                            print(f"Error during step '{step_text}': {e}")
                            # Handle failure
                            if backup_dir and backup_dir.exists():
                                if extracted_prefix.exists():
                                    shutil.rmtree(extracted_prefix)
                                shutil.move(str(backup_dir), str(extracted_prefix))
                            GLib.idle_add(self.show_info_dialog, "Error", f"Failed during step '{step_text}': {str(e)}")
                            return

                    # If successful, remove backup directory
                    if backup_dir and backup_dir.exists():
                        shutil.rmtree(backup_dir)
                        print(f"Removed backup directory: {backup_dir}")

                    GLib.idle_add(self.on_restore_completed)

                except Exception as e:
                    print(f"Error during restore process: {e}")
                    # Handle failure
                    if backup_dir and backup_dir.exists():
                        if extracted_prefix.exists():
                            shutil.rmtree(extracted_prefix)
                        shutil.move(str(backup_dir), str(extracted_prefix))
                    GLib.idle_add(self.show_info_dialog, "Error", f"Restore failed: {str(e)}")

            # Start the restore process in a new thread
            threading.Thread(target=restore_process).start()

        except Exception as e:
            print(f"Error initiating restore process: {e}")
            GLib.idle_add(self.show_info_dialog, "Error", f"Failed to start restore: {str(e)}")



    def get_restore_steps(self, file_path):
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
        ]

    def get_wzt_restore_steps(self, file_path):
        """
        Return the list of steps for restoring a WZT backup.
        """
        return [
            ("Checking Disk Space", lambda: self.check_disk_space_and_show_step(file_path)),
            ("Extracting WZT Backup File", lambda: self.extract_backup(file_path)),
            ("Performing User Related Replacements", lambda: self.perform_replacements(self.extract_prefix_dir(file_path))),
            ("Processing WineZGUI Script Files", lambda: self.process_sh_files(self.extract_prefix_dir(file_path))),
            ("Search LNK Files and Append to Found List", lambda: self.find_and_save_lnk_files(self.extract_prefix_dir(file_path))),
            ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
            ("Renaming and Merging User Directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(file_path))),
        ]

    def perform_replacements(self, directory):
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
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)

                # Skip binary files
                if self.is_binary_file(file_path):
                    print(f"Skipping binary file: {file_path}")
                    continue

                # Skip files where permission is denied
                if not os.access(file_path, os.R_OK | os.W_OK):
                    print(f"Skipping file: {file_path} (Permission denied)")
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
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                if b'\0' in chunk:
                    return True
        except Exception as e:
            print(f"Could not check file {file_path} ({e})")
        return False
        
    def process_sh_files(self, directory):
        """
        Process all .sh files and convert them to .charm files.
        """
        sh_files = self.find_sh_files(directory)
        created_charm_files = False  # Track whether any .charm file is created

        for sh_file in sh_files:
            variables = self.extract_infofile_path_from_sh(sh_file)
            exe_file = variables.get('EXE_FILE', '')
            progname = variables.get('PROGNAME', '')
            sha256sum = variables.get('CHECKSUM', '')

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

            self.create_scripts_for_exe_files(directory)
            print(f"Scripts created for .exe files in {directory}")

    def load_and_fix_yaml(self, yaml_file_path, filename):
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
        variables = {}
        with open(file_path, 'r') as file:
            for line in file:
                if line.startswith('export '):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].replace('export ', '').strip()
                        value = parts[1].strip().strip('"')
                        variables[key] = value
        return variables
                
    def find_sh_files(self, directory):
        sh_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(".sh"):
                    sh_files.append(os.path.join(root, file))
        return sh_files

    def find_and_save_lnk_files(self, wineprefix):
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
            yaml.dump(updated_lnk_files, file, default_flow_style=False)

        print(f"Saved {len(lnk_files)} .lnk files to {found_lnk_files_path}")
        self.load_script_list(wineprefix)

    def parse_info_file(self, file_path):
        info_data = {}
        with open(file_path, 'r') as file:
            for line in file:
                if ':' in line:
                    key, value = line.split(':', 1)
                    info_data[key.strip()] = value.strip()
        return info_data



    def add_charm_files_to_script_list(self, extracted_prefix_dir):
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
        """
        Called when the restore process is complete. Updates UI, restores scripts, and resets the open button.
        """
        # Reconnect open button and reset its label
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
        self.disconnect_open_button()
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.reconnect_open_button()
        self.hide_processing_spinner()


        # Restore the script list in the flowbox
        GLib.idle_add(self.create_script_list)

        print("Restore process completed and script list restored.")

    def extract_backup(self, file_path):
        """
        Extract the .tar.zst backup to the Wine prefixes directory with proper process management.
        """
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")

        try:
            # Create a new process group
            def preexec_function():
                os.setpgrp()

            # Extract the prefix name from the .tar.zst file
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
            extracted_prefix_name = output.splitlines()[0].split('/')[0]
            extracted_prefix_dir = Path(self.prefixes_dir) / extracted_prefix_name

            print(f"Extracted prefix name: {extracted_prefix_name}")
            print(f"Extracting to: {extracted_prefix_dir}")

            # Extract the archive with process tracking
            extract_process = subprocess.Popen(
                ['tar', '-I', 'zstd -T0', '-xf', file_path, '-C', self.prefixes_dir,
                 "--transform", f"s|XOUSERXO|{current_username}|g", 
                 "--transform", f"s|%USERNAME%|{current_username}|g"],
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
        """
        Return the extracted prefix directory for the backup file.
        This method ensures that only the first directory is returned, not individual files.
        """
        try:
            # Extract only directories by filtering those that end with '/'
            extracted_prefix_name = subprocess.check_output(
                ["bash", "-c", f"tar -tf '{file_path}' | head -n2 | grep '/$' | cut -f1 -d '/'"]
            ).decode('utf-8').strip()

            if not extracted_prefix_name:
                raise Exception("No directory found in the tar archive.")

            # Print the correct path for debugging
            extracted_prefix_path = Path(self.prefixes_dir) / extracted_prefix_name
            print("#" * 100)
            print(extracted_prefix_path)
            
            return extracted_prefix_path
        except subprocess.CalledProcessError as e:
            print(f"Error extracting prefix directory: {e}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None


    def check_disk_space_and_show_step(self, file_path):
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
        """
        Quick check of disk space by comparing compressed file size with available space.
        Only if compressed size is > 1/4 of available space, we need the full uncompressed check.
        
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

            # If compressed file is less than 1/4 of available space, we're safe to proceed
            if compressed_size * 4 <= available_space:
                print(f"Quick check passed - Compressed size: {compressed_size / (1024 * 1024):.2f} MB")
                return True, available_space, compressed_size

            # Otherwise, we need to check the actual uncompressed size
            uncompressed_size = self.get_total_uncompressed_size(file_path)
            return available_space >= uncompressed_size, available_space, uncompressed_size

        except (subprocess.CalledProcessError, OSError) as e:
            print(f"Error checking disk space: {e}")
            return False, 0, 0

    def connect_open_button_with_restore_backup_cancel(self):
        """
        Connect cancel handler to the open button
        """
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_restore_backup_clicked)
        
        self.set_open_button_icon_visible(False)

    def on_cancel_restore_backup_clicked(self, button):
        """
        Handle cancel button click with immediate process termination
        """
        dialog = Adw.MessageDialog.new(
            self.window,
            "Cancel Restoring Backup?",
            "This will immediately stop the extraction process. Any partially extracted files will be cleaned up."
        )
        dialog.add_response("continue", "Continue")
        dialog.add_response("cancel", "Cancel Restore")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_cancel_restore_backup_dialog_response)
        dialog.present()

    def on_cancel_restore_backup_dialog_response(self, dialog, response):
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


########   import interruptible? #################################################################################


    def custom_copytree(self, src, dst):
        """
        Custom copy implementation that can be cancelled and tracks the current process
        """
        try:
            # Create a new process group
            def preexec_function():
                os.setpgrp()

            # Use cp for copying with process tracking
            copy_process = subprocess.Popen(
                ['cp', '-r', str(src) + '/.', str(dst)],
                preexec_fn=preexec_function,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            with self.process_lock:
                self.current_process = copy_process

            while copy_process.poll() is None:
                if self.stop_processing:
                    print("Cancellation requested, terminating copy process...")
                    self._kill_current_process()
                    
                    # Clean up partially copied files
                    if Path(dst).exists():
                        print(f"Cleaning up partially copied files at {dst}")
                        shutil.rmtree(dst, ignore_errors=True)
                    
                    raise Exception("Operation cancelled by user")
                time.sleep(0.1)

            if copy_process.returncode != 0:
                stderr = copy_process.stderr.read().decode() if copy_process.stderr else ""
                raise Exception(f"Copy failed with return code {copy_process.returncode}: {stderr}")

        except Exception as e:
            print(f"Error during copy: {e}")
            raise
        finally:
            with self.process_lock:
                self.current_process = None

    def import_wine_directory(self, src, dst):
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
            ("Creating scripts for .exe files", lambda: self.create_scripts_for_exe_files(dst)),
        ]
        
        self.total_steps = len(steps)
        self.show_processing_spinner("Importing Wine Directory...")
        self.connect_open_button_with_import_wine_directory_cancel()

        def perform_import_steps():
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

    def backup_existing_directory(self, dst, backup_dir):
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


#################3 Replace strings update with interruption

    def replace_strings_in_files(self, directory, find_replace_pairs):
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
                        print(f"Skipping binary file: {file_path}")
                        continue

                    # Skip files where permission is denied
                    if not os.access(file_path, os.R_OK | os.W_OK):
                        print(f"Skipping file: {file_path} (Permission denied)")
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
                        print(f"Skipping file: {file_path} ({e})")
                        continue

        except Exception as e:
            if "Operation cancelled by user" in str(e):
                print("String replacement operation cancelled")
            raise

    def is_binary_file(self, file_path):
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
            print(f"Could not check file {file_path} ({e})")
        return False





################### new initialization winearch related
    def on_startup(self, app):
        self.create_main_window()
        self.script_list = {}
        self.single_prefix = False
        self.load_settings()
        print(f"Single Prefix: {self.single_prefix}")

        # Unified template initialization logic
        def initialize_template_if_needed(template_path, arch, single_prefix_dir=None):
            if not template_path.exists():
                print(f"Initializing {arch} template...")
                self.initialize_template(template_path, self.on_template_initialized, arch=arch)
                return True
            elif self.single_prefix and single_prefix_dir and not single_prefix_dir.exists():
                print(f"Copying {arch} template to single prefix...")
                self.copy_template(single_prefix_dir)
            return False

        # Determine which templates need initialization based on settings
        arch_templates = [
            (self.arch == 'win32', self.default_template_win32, 'win32', self.single_prefix_dir_win32),
            (True, self.default_template_win64, 'win64', self.single_prefix_dir_win64)
        ]

        needs_initialization = False
        for check, template, arch, single_dir in arch_templates:
            if check and not self.single_prefix:
                needs_initialization |= initialize_template_if_needed(template, arch, single_dir)

        # Set dynamic variables if no initialization needed 
        if not needs_initialization:
            self.set_dynamic_variables()
            self.load_script_list()
            self.create_script_list()
            if self.command_line_file:
                print("Processing command-line file after UI initialization")
                self.process_cli_file_later(self.command_line_file)

        # Common post-init tasks (only if no initialization needed)
        if not needs_initialization:
            missing_programs = self.check_required_programs()
            if missing_programs:
                self.show_missing_programs_dialog(missing_programs)
            self.check_running_processes_on_startup()
            threading.Thread(target=self.maybe_fetch_runner_urls).start()

    def show_processing_spinner(self, label_text):
        # Ensure main flowbox is visible
        self.main_frame.set_child(self.scrolled)
        # Clear the open button box and flowbox
        while self.open_button_box.get_first_child():
            self.open_button_box.remove(self.open_button_box.get_first_child())
        self.flowbox.remove_all()
        
        # Add progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text(label_text)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_size_request(420, -1)
        self.open_button_box.append(self.progress_bar)
        
        # Initialize steps
        self.step_boxes = []
        
        # Disable UI elements
        self.search_button.set_sensitive(False)
        self.view_toggle_button.set_sensitive(False)

    def on_template_initialized(self, arch=None):
        print(f"Template initialization complete for {arch if arch else 'default'} architecture.")
        self.initializing_template = False
        if arch:
            self.arch = arch
            self.template = self.default_template_win32 if arch == 'win32' else self.default_template_win64
            self.save_settings()
        
        self.hide_processing_spinner()
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.search_button.set_sensitive(True)
        self.view_toggle_button.set_sensitive(True)
        
        if self.open_button_handler_id is not None:
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)

        # Load and display scripts after initialization
        self.load_script_list()
        self.create_script_list()
        
        # Check for command-line file processing
        if self.command_line_file:
            print("Processing command-line file after template initialization")
            self.process_cli_file_later(self.command_line_file)
            self.command_line_file = None

        self.set_dynamic_variables()
        # Perform post-init tasks if not already done
        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        self.check_running_processes_on_startup()
        threading.Thread(target=self.maybe_fetch_runner_urls).start()








    ######################## 2nd for 
    def on_template_initialized(self, arch=None):
        print(f"Template initialization complete for {arch if arch else 'default'} architecture.")
        self.initializing_template = False
        
        if arch:
            self.arch = arch
            self.template = self.default_template_win32 if arch == 'win32' else self.default_template_win64
            self.save_settings()
        
        # Ensure UI updates happen in main thread
        GLib.idle_add(self.hide_processing_spinner)
        GLib.idle_add(self.set_open_button_label, "Open")
        GLib.idle_add(lambda: self.search_button.set_sensitive(True))
        GLib.idle_add(lambda: self.view_toggle_button.set_sensitive(True))
        
        # Load scripts and update UI 
        GLib.idle_add(self.load_script_list)
        GLib.idle_add(self.create_script_list)  # Refresh flowbox
        
        # Process CLI file if needed
        if self.command_line_file:
            print("Processing command-line file after template initialization")
            GLib.idle_add(self.process_cli_file_later, self.command_line_file)
            self.command_line_file = None

        # Return to settings view if initialized from there
        if hasattr(self, '_return_to_settings_after_init'):
            GLib.idle_add(self.show_options_for_settings)
            del self._return_to_settings_after_init



    def set_wine_arch(self):
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Set Wine Architecture",
            body="Select the default architecture for new prefixes:"
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        win32_radio = Gtk.CheckButton(label="32-bit (win32)")
        win64_radio = Gtk.CheckButton(label="64-bit (win64)")
        win64_radio.set_group(win32_radio)
        
        current_arch = self.arch
        win32_radio.set_active(current_arch == 'win32')
        win64_radio.set_active(current_arch == 'win64')

        vbox.append(win32_radio)
        vbox.append(win64_radio)
        dialog.set_extra_child(vbox)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def handle_architecture_change(new_arch):
            if new_arch == current_arch:
                return

            new_template = self.default_template_win32 if new_arch == 'win32' else self.default_template_win64
            new_template = Path(new_template).expanduser().resolve()
            single_dir = self.single_prefix_dir_win32 if new_arch == 'win32' else self.single_prefix_dir_win64

            # Flag to return to settings after initialization
            self._return_to_settings_after_init = True
            
            # Switch to main view context for initialization progress
            GLib.idle_add(lambda: self.main_frame.set_child(self.scrolled))
            #GLib.idle_add(self.show_processing_spinner, f"Configuring {new_arch}...")
            
            # Disable settings UI during initialization
            GLib.idle_add(self.settings_flowbox.set_sensitive, False)

            def finalize_arch_change():
                try:
                    if self.single_prefix and not single_dir.exists():
                        print(f"Copying to {single_dir.name}...")
                        self.copy_template(single_dir)
                    
                    self.arch = new_arch
                    self.template = new_template
                    self.save_settings()
                    
                    # Return to settings view after completion
                    GLib.idle_add(self.show_options_for_settings)
                    
                except Exception as e:
                    print(f"Architecture change failed: {e}")
                    GLib.idle_add(self.show_error_dialog, "Architecture Change Failed", str(e))
                finally:
                    if hasattr(self, '_return_to_settings_after_init'):
                        del self._return_to_settings_after_init
                    GLib.idle_add(self.settings_flowbox.set_sensitive, True)

            if not new_template.exists():
                print(f"Initializing new {new_arch} template...")
                self.initialize_template(new_template, 
                                    lambda: finalize_arch_change(),
                                    arch=new_arch)
            else:
                print(f"Using existing {new_arch} template")
                finalize_arch_change()

        def on_response(dialog, response):
            if response == "ok":
                new_arch = 'win32' if win32_radio.get_active() else 'win64'
                if new_arch != current_arch:
                    handle_architecture_change(new_arch)
            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()



    def initialize_template(self, template_dir, callback, arch='win64'):
        """
        Modified template initialization with architecture support
        """
        template_dir = Path(template_dir) if not isinstance(template_dir, Path) else template_dir
        self.flowbox.remove_all()
        self.create_required_directories()
        self.initializing_template = True
        self.stop_processing = False
        self.current_arch = arch  # Store current architecture
        
        # Disconnect open button handler
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_init_clicked)
        
        # Architecture-specific steps
        steps = [
            ("Initializing wineprefix", 
            f"WINEARCH={arch} WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
            ("Replace symbolic links with directories", 
            lambda: self.remove_symlinks_and_create_directories(template_dir)),
            #("Installing corefonts", 
            #f"WINEPREFIX='{template_dir}' winetricks -q corefonts"),
            ("Installing openal", 
            f"WINEPREFIX='{template_dir}' winetricks -q openal"),
            #("Installing vkd3d", 
            #f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
            #("Installing dxvk", 
            #f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
        ]
        
        # Set total steps and initialize progress UI
        self.total_steps = len(steps)
        self.show_processing_spinner(f"Initializing {arch} Template...")

        def initialize():
            for index, (step_text, command) in enumerate(steps, 2):
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


    def cleanup_cancelled_template_init(self, template_dir):
        """
        Clean up after template initialization is cancelled, create a basic template,
        and update settings.yml with robust directory handling
        """
        template_dir = Path(template_dir)
        success = False
        max_retries = 3
        retry_delay = 0.5  # seconds

        def remove_readonly(func, path, _):
            """Remove readonly attribute and retry deletion"""
            os.chmod(path, stat.S_IWRITE)
            func(path)

        try:
            # Attempt directory removal with retries
            for attempt in range(max_retries):
                if template_dir.exists():
                    try:
                        shutil.rmtree(template_dir, ignore_errors=False, onerror=remove_readonly)
                        print(f"Successfully removed directory on attempt {attempt+1}")
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise RuntimeError(f"Failed to delete directory after {max_retries} attempts: {str(e)}")
                        print(f"Deletion attempt {attempt+1} failed: {str(e)}")
                        time.sleep(retry_delay)
                        # Flush filesystem changes
                        subprocess.run(["sync"], check=False)

            # Verify directory removal
            if template_dir.exists():
                raise RuntimeError(f"Directory still exists after removal attempts: {template_dir}")

            # Create fresh directory structure
            template_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize basic wineprefix with minimal setup
            basic_steps = [
                ("Creating basic wineprefix", 
                f"WINEARCH={self.arch} WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
                ("Setting up directories", 
                lambda: self.remove_symlinks_and_create_directories(template_dir))
            ]
            
            for step_text, command in basic_steps:
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    if callable(command):
                        command()
                    else:
                        result = subprocess.run(command, shell=True, check=True, 
                                            stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                        if result.returncode != 0:
                            raise RuntimeError(f"Command failed: {command}")
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    raise RuntimeError(f"{step_text} failed: {str(e)}") from e
                    
            print("Successfully initialized basic wineprefix")
            success = True
            
        except Exception as e:
            error_msg = f"Template cleanup failed: {str(e)}"
            print(error_msg)
            GLib.idle_add(
                self.show_info_dialog, 
                "Cleanup Error", 
                f"Could not create basic template:\n{error_msg}"
            )
        finally:
            try:
                # Update settings if directory was created
                if template_dir.exists():
                    self.template = template_dir
                    self.save_settings()
                    print(f"Updated settings with template path: {template_dir}")
                
                self.initializing_template = False
                self.stop_processing = False
                GLib.idle_add(self.reset_ui_after_template_init)
                
                if success:
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Basic Template Created",
                        "A new basic template was created and settings were updated."
                    )
                    
            except Exception as e:
                print(f"Final cleanup error: {str(e)}")
                GLib.idle_add(
                    self.show_info_dialog,
                    "Critical Error",
                    f"Failed to finalize template cleanup: {str(e)}"
                )

##########################

    def clxeanup_cancelled_template_init(self, template_dir):
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



                        











####################### USE BASIC AND USE CUSTOMIZE TEMPLATE
    def customize_template_components(self, *args):
        """Entry point for template customization from settings"""
        current_template = Path(self.template)
        
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Select additional components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            check.set_active(False)
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Install")
        dialog.set_default_response("ok")
        
        def on_response(dialog, response):
            if response == "ok":
                selected = [c for c, cb in checkboxes.items() if cb.get_active()]
                if selected:
                    self.install_template_components(current_template, selected)
            dialog.destroy()
                    
        dialog.connect("response", on_response)
        dialog.present()

    def install_template_components(self, base_template, components):
        """Install additional components to a template copy"""
        try:
            # Create working copy
            temp_dir = base_template.with_name(f"{base_template.name}_customizing")
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            shutil.copytree(base_template, temp_dir)
            
            # Store state for cancellation handling
            self._active_customization_temp = temp_dir
            self._original_template = base_template
            
            # Installation steps
            steps = []
            for component in components:
                steps.append(
                    (f"Installing {component}", 
                    f"WINEPREFIX='{temp_dir}' winetricks -q {component}")
                )
            
            # Show progress UI
            self.total_steps = len(steps)
            self.show_processing_spinner("Customizing Template...")
            
            # Run installation in thread
            threading.Thread(target=self._run_component_steps, args=(steps, temp_dir)).start()
            
        except Exception as e:
            self.cleanup_template_customization(False)
            self.show_info_dialog("Customization Error", f"Failed to start installation: {str(e)}")



    def initialize_template(self, template_dir, callback, arch='win64', basic_only=True):
        """
        Creates a wine template with atomic replacement pattern
        basic_only=True: Only creates base wineprefix (wineboot + directory setup)
        basic_only=False: [Reserved for future component integration]
        """
        template_dir = Path(template_dir)
        temp_dir = template_dir.with_name(f".temp_{template_dir.name}")
        
        self.create_required_directories()
        self.initializing_template = True
        self.stop_processing = False
        self.current_arch = arch

        # Disconnect open button during initialization
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_init_clicked)

        # Basic initialization steps
        steps = [
            ("Creating wineprefix structure", 
            f"WINEARCH={arch} WINEPREFIX='{temp_dir}' WINEDEBUG=-all wineboot -i"),
            ("Configuring directories", 
            lambda: self.remove_symlinks_and_create_directories(temp_dir))
        ]

        self.total_steps = len(steps)
        self.show_processing_spinner(f"Creating {'Basic' if basic_only else 'Full'} Template...")

        def atomic_replace():
            """Atomically replace target with temp directory"""
            try:
                if template_dir.exists():
                    shutil.rmtree(template_dir, ignore_errors=True)
                temp_dir.rename(template_dir)
                return True
            except Exception as e:
                print(f"Atomic replace failed: {str(e)}")
                return False

        def initialize():
            try:
                # Clean existing temp dir
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    
                # Create fresh temp dir
                temp_dir.mkdir(parents=True)

                # Process initialization steps
                for index, (step_text, command) in enumerate(steps, 1):
                    if self.stop_processing:
                        break

                    GLib.idle_add(self.show_initializing_step, step_text)
                    
                    try:
                        if callable(command):
                            command()
                        else:
                            process = subprocess.Popen(
                                command, 
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            
                            # Monitor process with cancellation support
                            while True:
                                if self.stop_processing:
                                    process.terminate()
                                    try:
                                        process.wait(timeout=2)
                                    except subprocess.TimeoutExpired:
                                        process.kill()
                                    break
                                
                                if process.poll() is not None:
                                    break
                                    
                                time.sleep(0.1)

                            if process.returncode not in [0, -15]:  # -15 = SIGTERM
                                raise subprocess.CalledProcessError(
                                    process.returncode, 
                                    command,
                                    output=process.stdout.read().decode(),
                                    stderr=process.stderr.read().decode()
                                )

                        GLib.idle_add(self.mark_step_as_done, step_text)
                        GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                    except Exception as e:
                        if not self.stop_processing:
                            GLib.idle_add(
                                self.show_info_dialog,
                                "Initialization Error",
                                f"Step '{step_text}' failed: {str(e)}"
                            )
                        break

                # Finalize only if not cancelled
                if not self.stop_processing:
                    if atomic_replace():
                        GLib.idle_add(self.on_template_initialized, arch)
                        GLib.idle_add(callback)
                    else:
                        raise RuntimeError("Failed to finalize template replacement")

            except Exception as e:
                GLib.idle_add(
                    self.show_info_dialog,
                    "Initialization Failed",
                    f"Template creation failed: {str(e)}"
                )
            finally:
                # Cleanup temp directory
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                # Final reset
                GLib.idle_add(self.finalize_template_initialization)

        def finalize_template_initialization(self):
            """Clean up initialization state"""
            try:
                self.initializing_template = False
                self.stop_processing = False
                self.hide_processing_spinner()
                
                # Reconnect open button
                if self.open_button_handler_id:
                    self.open_button.disconnect(self.open_button_handler_id)
                self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
                
                # Reset UI
                self.reset_ui_after_template_init()
                
            except Exception as e:
                print(f"Finalization error: {str(e)}")
                GLib.idle_add(
                    self.show_info_dialog,
                    "Cleanup Error",
                    f"Final cleanup failed: {str(e)}"
                )

        # Start the initialization thread
        threading.Thread(target=initialize, daemon=True).start()


############################# customize template improvement
    def customize_template_components(self, *args):
        """Template customization with progress tracking"""
        current_template = Path(self.template)
        
        # Clear UI and setup progress
        self.flowbox.remove_all()
        self.show_processing_spinner("Preparing Customization...")
        
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Select additional components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            check.set_active(False)
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Install")
        dialog.set_default_response("ok")
        
        def on_response(dialog, response):
            if response == "ok":
                selected = [c for c, cb in checkboxes.items() if cb.get_active()]
                if selected:
                    # Show processing UI
                    self.main_frame.set_child(self.scrolled)
                    self.show_processing_spinner("Customizing Template...")
                    
                    # Prepare steps
                    steps = [
                        ("Creating temporary copy", None),  # Special handling
                    ] + [(f"Installing {c}", c) for c in selected]
                    
                    # Start installation process
                    threading.Thread(target=self.install_template_components, 
                                args=(current_template, steps)).start()
            dialog.destroy()
                    
        dialog.connect("response", on_response)
        dialog.present()

    def install_template_components(self, base_template, steps):
        """Install components with progress tracking"""
        try:
            temp_dir = base_template.with_name(f"{base_template.name}_customizing")
            original_dir = base_template

            # Step 1: Create temporary copy
            GLib.idle_add(self.show_initializing_step, steps[0][0])
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            shutil.copytree(base_template, temp_dir)
            GLib.idle_add(self.mark_step_as_done, steps[0][0])
            
            # Process installation steps
            self.total_steps = len(steps)
            
            for index, (step_text, component) in enumerate(steps[1:], 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    process = subprocess.Popen(
                        f"WINEPREFIX='{temp_dir}' winetricks -q {component}",
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    
                    while process.poll() is None:
                        if self.stop_processing:
                            process.terminate()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            break
                        time.sleep(0.1)

                    if process.returncode not in [0, -15]:
                        raise subprocess.CalledProcessError(
                            process.returncode, 
                            f"winetricks {component}",
                            output=process.stdout.read().decode(),
                            stderr=process.stderr.read().decode()
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    if not self.stop_processing:
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Installation Error",
                            f"Failed to install {component}: {str(e)}"
                        )
                    break

            # Finalize
            if not self.stop_processing and temp_dir.exists():
                # Atomic replace
                if original_dir.exists():
                    shutil.rmtree(original_dir)
                temp_dir.rename(original_dir)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed successfully!"
                )
            else:
                self.cleanup_customization(temp_dir)

        except Exception as e:
            GLib.idle_add(
                self.show_info_dialog,
                "Error",
                f"Customization failed: {str(e)}"
            )
            self.cleanup_customization(temp_dir)
        finally:
            GLib.idle_add(self.hide_processing_spinner)
            self.stop_processing = False

    def cleanup_customization(self, temp_dir):
        """Clean up failed/cancelled customization"""
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"Cleanup error: {str(e)}")

#############################
    def install_template_components(self, base_template, components):
        """Install components with native Python copy and progress tracking"""
        temp_dir = None
        original_template = Path(base_template)
        self.stop_processing = False

        try:
            # Setup temporary directory
            temp_dir = original_template.with_name(f"{original_template.name}_customizing")
            steps = [
                ("Creating temporary copy", None),
            ] + [(f"Installing {component}", component) for component in components]

            # Initialize UI
            GLib.idle_add(self.show_processing_spinner, "Customizing Template...")
            GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
            self.total_steps = len(steps)

            # Step 1: Copy template with progress
            GLib.idle_add(self.show_initializing_step, steps[0][0])
            
            def copy_template_with_progress(src, dst):
                """Custom copy with cancellation support"""
                file_count = 0
                for root, dirs, files in os.walk(src):
                    if self.stop_processing:
                        raise RuntimeError("Cancelled")
                    
                    rel_path = os.path.relpath(root, src)
                    dest_dir = os.path.join(dst, rel_path)
                    os.makedirs(dest_dir, exist_ok=True)

                    for file in files:
                        if self.stop_processing:
                            raise RuntimeError("Cancelled")
                            
                        src_file = os.path.join(root, file)
                        dest_file = os.path.join(dest_dir, file)
                        shutil.copy2(src_file, dest_file, follow_symlinks=False)
                        
                        # Update progress every 10 files
                        file_count += 1
                        if file_count % 10 == 0:
                            GLib.idle_add(self.progress_bar.pulse)

            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                copy_template_with_progress(original_template, temp_dir)
                GLib.idle_add(self.mark_step_as_done, steps[0][0])
            except Exception as e:
                print(str(e))
                raise RuntimeError(f"Copy failed: {str(e)}")


            # Process installation steps
            for index, (step_text, component) in enumerate(steps[1:], 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    proc = subprocess.Popen(
                        f"WINEPREFIX='{temp_dir}' winetricks -q {component}",
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )

                    # Monitor process with cancellation
                    while proc.poll() is None:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        time.sleep(0.1)

                    if proc.returncode not in [0, -15]:
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            f"winetricks {component}",
                            output=proc.stdout.read().decode(),
                            stderr=proc.stderr.read().decode()
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    progress = (index + 1) / self.total_steps
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(progress))

                except Exception as e:
                    if not self.stop_processing:
                        error_msg = f"Failed to install {component}: {str(e)}"
                        print(error_msg)
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Installation Error",
                            error_msg
                        )
                    break

            # Finalize if successful
            if not self.stop_processing and temp_dir.exists():
                # Atomic replacement
                if original_template.exists():
                    shutil.rmtree(original_template)
                temp_dir.rename(original_template)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed!"
                )

        except Exception as e:
            GLib.idle_add(
                self.show_info_dialog,
                "Error",
                f"Customization failed: {str(e)}"
            )
        finally:
            # Cleanup resources
            try:
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"Cleanup error: {str(e)}")
            
            GLib.idle_add(self.hide_processing_spinner)
            self.stop_processing = False
            self.initializing_template = False

###################### another
    def inxstall_template_components(self, base_template, components):
        """Install components with native Python copy and progress tracking"""
        temp_dir = None
        original_template = Path(base_template)
        self.stop_processing = False

        try:
            # Setup temporary directory
            temp_dir = original_template.with_name(f"{original_template.name}_customizing")
            
            # Create steps list: copy step + component steps
            steps = [
                ("Creating temporary copy", None),
            ] + [(f"Installing {component}", component) for component in components]  # Ensure components are strings

            # Initialize UI
            GLib.idle_add(self.show_processing_spinner, "Customizing Template...")
            GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
            self.total_steps = len(steps)

            # Step 1: Copy template (handled separately)
            GLib.idle_add(self.show_initializing_step, steps[0][0])
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                shutil.copytree(original_template, temp_dir)
                GLib.idle_add(self.mark_step_as_done, steps[0][0])
            except Exception as e:
                raise RuntimeError(f"Copy failed: {str(e)}")

            # Process winetricks components (steps[1:] are the actual components)
            for index, (step_text, component) in enumerate(steps[1:], 1):  # Start from index 1
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    # Only run winetricks if component is not None (copy step already handled)
                    if component is None:
                        continue  # Skip invalid entries

                    proc = subprocess.Popen(
                        f"WINEPREFIX='{temp_dir}' winetricks -q {component}",
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )

                    # Monitor process with cancellation
                    while proc.poll() is None:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        time.sleep(0.1)

                    if proc.returncode not in [0, -15]:
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            f"winetricks {component}",
                            output=proc.stdout.read().decode(),
                            stderr=proc.stderr.read().decode()
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    progress = (index + 1) / self.total_steps
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(progress))

                except Exception as e:
                    if not self.stop_processing:
                        error_msg = f"Failed to install {component}: {str(e)}"
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Installation Error",
                            error_msg
                        )
                    break

            # Finalize if successful
            if not self.stop_processing and temp_dir.exists():
                if original_template.exists():
                    shutil.rmtree(original_template)
                temp_dir.rename(original_template)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed!"
                )

        except Exception as e:
            GLib.idle_add(
                self.show_info_dialog,
                "Error",
                f"Customization failed: {str(e)}"
            )
        finally:
            # Cleanup resources
            try:
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"Cleanup error: {str(e)}")
            
            GLib.idle_add(self.hide_processing_spinner)
            self.stop_processing = False
            self.initializing_template = False

######################### another 2
    def initialize_template(self, template_dir, callback, arch='win64', basic_only=True):
        """
        Creates a wine template with atomic replacement pattern
        basic_only=True: Only creates base wineprefix (wineboot + directory setup)
        basic_only=False: [Reserved for future component integration]
        """
        template_dir = Path(template_dir)
        temp_dir = template_dir.with_name(f".temp_{template_dir.name}")
        
        self.create_required_directories()
        self.initializing_template = True
        self.stop_processing = False
        self.current_arch = arch

        # Disconnect open button during initialization
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_init_clicked)

        # Basic initialization steps
        steps = [
            ("Creating wineprefix structure", 
            f"WINEARCH={arch} WINEPREFIX='{temp_dir}' WINEDEBUG=-all wineboot -i"),
            ("Configuring directories", 
            lambda: self.remove_symlinks_and_create_directories(temp_dir))
        ]

        self.total_steps = len(steps)
        self.show_processing_spinner(f"Creating {'Basic' if basic_only else 'Full'} Template...")

        def atomic_replace():
            """Atomically replace target with temp directory"""
            try:
                if template_dir.exists():
                    shutil.rmtree(template_dir, ignore_errors=True)
                temp_dir.rename(template_dir)
                return True
            except Exception as e:
                print(f"Atomic replace failed: {str(e)}")
                return False

        def initialize():
            try:
                # Clean existing temp dir
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    
                # Create fresh temp dir
                temp_dir.mkdir(parents=True)

                # Process initialization steps
                for index, (step_text, command) in enumerate(steps, 1):
                    if self.stop_processing:
                        break

                    GLib.idle_add(self.show_initializing_step, step_text)
                    
                    try:
                        if callable(command):
                            command()
                        else:
                            process = subprocess.Popen(
                                command, 
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            
                            # Monitor process with cancellation support
                            while True:
                                if self.stop_processing:
                                    process.terminate()
                                    try:
                                        process.wait(timeout=2)
                                    except subprocess.TimeoutExpired:
                                        process.kill()
                                    break
                                
                                if process.poll() is not None:
                                    break
                                    
                                time.sleep(0.1)

                            if process.returncode not in [0, -15]:  # -15 = SIGTERM
                                raise subprocess.CalledProcessError(
                                    process.returncode, 
                                    command,
                                    output=process.stdout.read().decode(),
                                    stderr=process.stderr.read().decode()
                                )

                        GLib.idle_add(self.mark_step_as_done, step_text)
                        GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                    except Exception as e:
                        if not self.stop_processing:
                            GLib.idle_add(
                                self.show_info_dialog,
                                "Initialization Error",
                                f"Step '{step_text}' failed: {str(e)}"
                            )
                        break

                # Finalize only if not cancelled
                if not self.stop_processing:
                    if atomic_replace():
                        GLib.idle_add(self.on_template_initialized, arch)
                        GLib.idle_add(callback)
                    else:
                        raise RuntimeError("Failed to finalize template replacement")

            except Exception as e:
                print(e)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Initialization Failed",
                    f"Template creation failed: {str(e)}"
                )
            finally:
                # Cleanup temp directory
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                # Final reset
                GLib.idle_add(self.finalize_template_initialization)

        # Start the initialization thread
        threading.Thread(target=initialize, daemon=True).start()

    def finalize_template_initialization(self):
        """Clean up initialization state and reset UI"""
        try:
            self.initializing_template = False
            self.stop_processing = False
            self.hide_processing_spinner()
            
            # Reconnect open button
            if self.open_button_handler_id:
                self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
            
            # Reset UI elements
            self.reset_ui_after_template_init()
            
            # Update dynamic variables
            self.set_dynamic_variables()
            
        except Exception as e:
            print(f"Finalization error: {str(e)}")
            GLib.idle_add(
                self.show_info_dialog,
                "Cleanup Error",
                f"Final cleanup failed: {str(e)}"
            )

    ############################        another 4
    def customize_template_components(self, *args):
        """Template customization with reliable component installation"""
        current_template = Path(self.template)
        
        # Component list with (display name, winetricks component)
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Select additional components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            check.set_active(False)
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Install")
        dialog.set_default_response("ok")
        
        def on_response(dialog, response):
            if response == "ok":
                selected = [c for c, cb in checkboxes.items() if cb.get_active()]
                if selected:
                    self.show_processing_spinner("Customizing Template...")
                    threading.Thread(
                        target=self.install_template_components,
                        args=(current_template, selected)
                    ).start()
            dialog.destroy()
                    
        dialog.connect("response", on_response)
        dialog.present()

    def install_template_components(self, base_template, components):
        """Install components with proper error handling and progress updates"""
        temp_dir = None
        original_template = Path(base_template)
        self.stop_processing = False

        try:
            # Setup temporary directory
            temp_dir = original_template.with_name(f"{original_template.name}_customizing")
            steps = [
                ("Creating temporary copy", None),
            ] + [(f"Installing {component}", component) for component in components]

            # Initialize UI
            GLib.idle_add(self.show_processing_spinner, "Customizing Template...")
            GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
            self.total_steps = len(steps)

            # Step 1: Copy template
            GLib.idle_add(self.show_initializing_step, steps[0][0])
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                shutil.copytree(original_template, temp_dir, symlinks=True, dirs_exist_ok=True)
                GLib.idle_add(self.mark_step_as_done, steps[0][0])
            except Exception as e:
                print(e)
                raise RuntimeError(f"Copy failed: {str(e)}")

            # Process installation steps
            for index, (step_text, component) in enumerate(steps[1:], 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    # Verify component is valid
                    if not component or not isinstance(component, str):
                        raise ValueError(f"Invalid component: {component}")

                    # Run winetricks command
                    cmd = f"WINEPREFIX='{temp_dir}' winetricks -q {component}"
                    print(f"Executing: {cmd}")  # Debug logging
                    
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )

                    # Monitor process with real-time output
                    while True:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        
                        # Read output incrementally
                        stdout_line = proc.stdout.readline()
                        stderr_line = proc.stderr.readline()
                        if stdout_line:
                            print(f"[{component} stdout] {stdout_line.strip()}")
                        if stderr_line:
                            print(f"[{component} stderr] {stderr_line.strip()}")
                        
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)

                    # Check results
                    if proc.returncode not in [0, -15]:
                        stdout, stderr = proc.communicate()
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            cmd,
                            output=stdout,
                            stderr=stderr
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    progress = (index + 1) / self.total_steps
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(progress))

                except Exception as e:
                    if not self.stop_processing:
                        error_msg = f"Failed to install {component}: {str(e)}"
                        print(error_msg)
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Installation Error",
                            error_msg
                        )
                    break

            # Finalize if successful
            if not self.stop_processing and temp_dir.exists():
                if original_template.exists():
                    shutil.rmtree(original_template)
                temp_dir.rename(original_template)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed!"
                )

        except Exception as e:
            print(e)
            GLib.idle_add(
                self.show_info_dialog,
                "Error",
                f"Customization failed: {str(e)}"
            )
        finally:
            # Cleanup resources
            try:
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(e)
                print(f"Cleanup error: {str(e)}")
            
            GLib.idle_add(self.hide_processing_spinner)
            self.stop_processing = False

####################3 4 
    def install_template_components(self, base_template, components):
        """Install components directly into the existing template"""
        self.stop_processing = False
        template_dir = Path(base_template)
        failed = False
        try:
            # Setup steps without copy step
            steps = [(f"Installing {component}", component) for component in components]
            self.total_steps = len(steps)

            # Initialize UI
            GLib.idle_add(self.show_processing_spinner, "Customizing Template...")
            GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))

            # Process installation directly in the template
            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    # Verify component is valid
                    if not component or not isinstance(component, str):
                        raise ValueError(f"Invalid component: {component}")

                    # Run winetricks command directly on the template
                    cmd = f"WINEPREFIX='{template_dir}' winetricks -q {component}"
                    print(f"Executing: {cmd}")
                    
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )

                    # Monitor process with real-time output
                    while True:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        
                        # Read output incrementally
                        stdout_line = proc.stdout.readline()
                        stderr_line = proc.stderr.readline()
                        if stdout_line:
                            print(f"[{component} stdout] {stdout_line.strip()}")
                        if stderr_line:
                            print(f"[{component} stderr] {stderr_line.strip()}")
                        
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)

                    # Check results
                    if proc.returncode not in [0, -15]:
                        stdout, stderr = proc.communicate()
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            cmd,
                            output=stdout,
                            stderr=stderr
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    progress = index / self.total_steps
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(progress))

                except Exception as e:
                    failed = True
                    if not self.stop_processing:
                        error_msg = f"Failed to install {component}: {str(e)}"
                        print(error_msg)
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Installation Error",
                            error_msg
                        )
                        self.create_script_list()
                    break

            if not self.stop_processing and not failed:
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template components updated successfully!"
                )
                self.create_script_list()

        except Exception as e:
            print(e)
            GLib.idle_add(
                self.show_info_dialog,
                "Error",
                f"Customization failed: {str(e)}\nTemplate may be in a modified state."
            )
        finally:
            GLib.idle_add(self.hide_processing_spinner)
            self.stop_processing = False


    def customize_template_components(self, *args):
        """Template customization with reliable component installation"""
        current_template = Path(self.template)
        
        # Component list with (display name, winetricks component)
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Select additional components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            check.set_active(False)
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Install")
        dialog.set_default_response("ok")
        
        def on_response(dialog, response):
            if response == "ok":
                selected = [c for c, cb in checkboxes.items() if cb.get_active()]
                if selected:
                    self.show_processing_spinner("Updating Template...")
                    threading.Thread(
                        target=self.install_template_components,
                        args=(self.template, selected)  # Pass existing template path
                    ).start()
            dialog.destroy()

                    
        dialog.connect("response", on_response)
        dialog.present()

##########################
    def customize_template_components(self, *args):
        """Template customization with installed component detection"""
        current_template = Path(self.template)
        winetricks_log = current_template / "winetricks.log"
        
        # Get installed components from log file
        installed_components = set()
        if winetricks_log.exists():
            with open(winetricks_log, 'r') as f:
                installed_components = {line.strip() for line in f.readlines() if line.strip()}

        # Component list with (display name, winetricks component)
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Already installed components are disabled and checked\nSelect additional components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            
            # Check if component is already installed
            if component in installed_components:
                check.set_active(True)
                check.set_sensitive(False)  # Disable interaction
                check.set_tooltip_text("This component is already installed and cannot be removed")
            else:
                check.set_active(False)
                
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Install")
        dialog.set_default_response("ok")
        
        def on_response(dialog, response):
            if response == "ok":
                # Only select components that aren't already installed
                selected = [c for c, cb in checkboxes.items() 
                        if cb.get_active() and c not in installed_components]
                
                if selected:
                    self.show_processing_spinner("Updating Template...")
                    threading.Thread(
                        target=self.install_template_components,
                        args=(self.template, selected)
                    ).start()
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()


########################### cancellable?
    def install_template_components(self, base_template, components):
        """Install components with backup/restore on cancellation"""
        self.stop_processing = False
        template_dir = Path(base_template)
        temp_backup = None
        failed = False
        
        try:
            # Create temporary backup
            temp_backup = template_dir.with_name(f"{template_dir.name}_backup_{int(time.time())}")
            shutil.copytree(template_dir, temp_backup, symlinks=True, dirs_exist_ok=True)
            
            # Setup steps without copy step
            steps = [(f"Installing {component}", component) for component in components]
            self.total_steps = len(steps)

            # Initialize UI
            GLib.idle_add(self.show_processing_spinner, "Customizing Template...")
            GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
            
            # Change open button to cancel button
            GLib.idle_add(self.set_open_button_label, "Cancel")
            GLib.idle_add(self.set_open_button_icon_visible, False)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_customization_clicked, temp_backup)

            # Process installation directly in the template
            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    # Verify component is valid
                    if not component or not isinstance(component, str):
                        raise ValueError(f"Invalid component: {component}")

                    # Run winetricks command directly on the template
                    cmd = f"WINEPREFIX='{template_dir}' winetricks -q {component}"
                    print(f"Executing: {cmd}")
                    
                    with self.process_lock:
                        self.current_process = subprocess.Popen(
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True
                        )

                    # Monitor process with real-time output
                    while True:
                        if self.stop_processing:
                            with self.process_lock:
                                if self.current_process:
                                    self.current_process.terminate()
                            break
                        
                        # Read output incrementally
                        stdout_line = self.current_process.stdout.readline()
                        stderr_line = self.current_process.stderr.readline()
                        if stdout_line:
                            print(f"[{component} stdout] {stdout_line.strip()}")
                        if stderr_line:
                            print(f"[{component} stderr] {stderr_line.strip()}")
                        
                        if self.current_process.poll() is not None:
                            break
                        time.sleep(0.1)

                    # Check results
                    if self.current_process.returncode not in [0, -15]:
                        stdout, stderr = self.current_process.communicate()
                        raise subprocess.CalledProcessError(
                            self.current_process.returncode,
                            cmd,
                            output=stdout,
                            stderr=stderr
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    progress = index / self.total_steps
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(progress))

                except Exception as e:
                    failed = True
                    if not self.stop_processing:
                        error_msg = f"Failed to install {component}: {str(e)}"
                        print(error_msg)
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Installation Error",
                            error_msg
                        )
                    break

            if not self.stop_processing and not failed:
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template components updated successfully!"
                )
            else:
                # Restore backup if cancelled
                self.restore_template_backup(template_dir, temp_backup)

        except Exception as e:
            print(e)
            self.restore_template_backup(template_dir, temp_backup)
            GLib.idle_add(
                self.show_info_dialog,
                "Error",
                f"Customization failed: {str(e)}\nTemplate has been restored."
            )
        finally:
            # Cleanup backup if successful
            if temp_backup and temp_backup.exists() and not failed and not self.stop_processing:
                shutil.rmtree(temp_backup, ignore_errors=True)
            
            GLib.idle_add(self.hide_processing_spinner)
            self.stop_processing = False
            with self.process_lock:
                self.current_process = None

    def on_cancel_customization_clicked(self, button, temp_backup):
        """Handle cancellation of template customization"""
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Cancel Customization?",
            body="This will restore the template to its original state."
        )
        dialog.add_response("no", "Continue")
        dialog.add_response("yes", "Restore")
        dialog.set_default_response("no")
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)
        
        def on_response(dialog, response):
            if response == "yes":
                self.stop_processing = True
                # Restore will happen in install_template_components finally block
            dialog.destroy()
        
        dialog.connect("response", on_response)
        dialog.present()

    def restore_template_backup(self, template_dir, backup_dir):
        """Restore template from backup with atomic replacement"""
        try:
            if backup_dir and backup_dir.exists():
                # Remove current template
                if template_dir.exists():
                    shutil.rmtree(template_dir, ignore_errors=True)
                
                # Restore from backup
                backup_dir.rename(template_dir)
                print(f"Restored template from backup: {backup_dir}")
                
        except Exception as e:
            print(f"Restoration failed: {str(e)}")
            GLib.idle_add(
                self.show_info_dialog,
                "Restoration Error",
                f"Could not restore template: {str(e)}\nBackup remains at: {backup_dir}"
            )

    def customize_template_components(self, *args):
        """Template customization with backup, restore, and installed component detection"""
        current_template = Path(self.template)
        winetricks_log = current_template / "winetricks.log"
        
        # Create timestamped backup first
        backup_dir = current_template.with_name(f"{current_template.name}_backup_{int(time.time())}")
        try:
            shutil.copytree(current_template, backup_dir, symlinks=True, dirs_exist_ok=True)
        except Exception as e:
            GLib.idle_add(
                self.show_info_dialog,
                "Backup Failed",
                f"Could not create backup: {str(e)}\nCannot proceed with customization."
            )
            return

        # Get installed components from log file
        installed_components = set()
        if winetricks_log.exists():
            with open(winetricks_log, 'r') as f:
                installed_components = {line.strip() for line in f.readlines() if line.strip()}

        # Component list with (display name, winetricks component)
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Already installed components are disabled\nSelect new components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            
            # Set state based on existing installation
            if component in installed_components:
                check.set_active(True)
                check.set_sensitive(False)
                check.set_tooltip_text(f"{name} already installed")
            else:
                check.set_active(False)
                check.set_sensitive(True)
                
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install")
        dialog.set_default_response("install")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "install":
                # Get selected components that aren't already installed
                selected = [c for c, cb in checkboxes.items() 
                        if cb.get_active() and c not in installed_components]
                
                if selected:
                    # Configure UI for installation
                    GLib.idle_add(self.show_processing_spinner, "Customizing Template...")
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
                    GLib.idle_add(self.set_open_button_label, "Cancel")
                    GLib.idle_add(self.set_open_button_icon_visible, False)
                    
                    # Disconnect previous handler and set cancel action
                    if self.open_button_handler_id:
                        self.open_button.disconnect(self.open_button_handler_id)
                    self.open_button_handler_id = self.open_button.connect(
                        "clicked", 
                        self.on_cancel_customization_clicked,
                        backup_dir
                    )
                    
                    # Start installation thread
                    threading.Thread(
                        target=self.install_template_components,
                        args=(current_template, selected, backup_dir),
                        daemon=True
                    ).start()
                else:
                    # No new components selected - clean up backup
                    if backup_dir.exists():
                        shutil.rmtree(backup_dir, ignore_errors=True)
            else:
                # User cancelled dialog - clean up backup
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
            
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def on_cancel_customization_clicked(self, button, backup_dir):
        """Handle cancellation of ongoing customization"""
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Cancel Customization?",
            body="This will restore the template to its previous state."
        )
        dialog.add_response("continue", "Continue Installation")
        dialog.add_response("cancel", "Restore Backup")
        dialog.set_default_response("continue")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_cancel_response(dialog, response):
            if response == "cancel":
                self.stop_processing = True
                # Restore backup
                self.restore_template_backup(Path(self.template), backup_dir)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Restored",
                    "Template has been restored to previous state"
                )
            dialog.destroy()

        dialog.connect("response", on_cancel_response)
        dialog.present()

    def restore_template_backup(self, template_dir, backup_dir):
        """Atomic template restoration from backup"""
        try:
            if backup_dir.exists():
                # Remove current template
                if template_dir.exists():
                    shutil.rmtree(template_dir, ignore_errors=True)
                # Restore backup
                backup_dir.rename(template_dir)
                print(f"Restored template from backup: {backup_dir}")
                return True
            return False
        except Exception as e:
            print(f"Restoration failed: {str(e)}")
            GLib.idle_add(
                self.show_info_dialog,
                "Restoration Error",
                f"Could not restore template: {str(e)}\nBackup remains at: {backup_dir}"
            )
            return False

    def install_template_components(self, template_dir, components, backup_dir):
        """Install components with backup management"""
        self.stop_processing = False
        template_path = Path(template_dir)
        
        try:
            steps = [(f"Installing {component}", component) for component in components]
            self.total_steps = len(steps)

            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )

                    # Monitor process
                    while proc.poll() is None:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        time.sleep(0.1)

                    if proc.returncode not in [0, -15]:
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            cmd,
                            output=proc.stdout.read(),
                            stderr=proc.stderr.read()
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    # Restore backup on any error
                    self.restore_template_backup(template_path, backup_dir)
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Installation Failed",
                        f"Failed to install {component}: {str(e)}\nTemplate has been restored."
                    )
                    return

            if not self.stop_processing:
                # Cleanup backup on success
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template components updated successfully!"
                )

        finally:
            # Final cleanup
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)
            self.stop_processing = False
            if self.open_button_handler_id:
                self.open_button.disconnect(self.open_button_handler_id)


############### another
    def install_template_components(self, template_dir, components, backup_dir):
        """Install components with backup management"""
        self.stop_processing = False
        template_path = Path(template_dir)
        
        try:
            steps = [(f"Installing {component}", component) for component in components]
            self.total_steps = len(steps)

            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )

                    # Monitor process
                    while proc.poll() is None:
                        if self.stop_processing:
                            proc.terminate()
                            try:
                                proc.wait(2)  # Wait for process to terminate
                            except subprocess.TimeoutExpired:
                                pass
                            break
                        time.sleep(0.1)

                    returncode = proc.returncode
                    if returncode not in [0, -15]:
                        # Handle None returncode
                        status = returncode if returncode is not None else "Unknown"
                        output = proc.stdout.read()[:200] + "..." if proc.stdout else ""
                        stderr = proc.stderr.read()[:200] + "..." if proc.stderr else ""
                        
                        raise subprocess.CalledProcessError(
                            returncode if returncode is not None else -1,
                            cmd,
                            output=output,
                            stderr=stderr
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    # Get safe error details
                    error_msg = f"Failed to install {component}: "
                    if isinstance(e, subprocess.CalledProcessError):
                        rc = e.returncode if e.returncode is not None else "Unknown"
                        error_msg += f"Exit code {rc}\nCommand: {e.cmd}\n"
                        if e.stdout: error_msg += f"Output: {e.stdout[:200]}\n"
                        if e.stderr: error_msg += f"Error: {e.stderr[:200]}"
                    else:
                        error_msg += str(e)
                    
                    # Restore backup
                    self.restore_template_backup(template_path, backup_dir)
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Installation Failed",
                        error_msg + "\n\nTemplate has been restored."
                    )
                    return

            if not self.stop_processing:
                # Cleanup backup on success
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template components updated successfully!"
                )

        finally:
            # Final cleanup
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)
            self.stop_processing = False
            if self.open_button_handler_id:
                self.open_button.disconnect(self.open_button_handler_id)



   ################### non laggy
    def customize_template_components(self, *args):
        """Template customization with backup, restore, and installed component detection"""
        current_template = Path(self.template)
        winetricks_log = current_template / "winetricks.log"

        # Get installed components from log file
        installed_components = set()
        if winetricks_log.exists():
            with open(winetricks_log, 'r') as f:
                installed_components = {line.strip() for line in f.readlines() if line.strip()}

        # Component list with (display name, winetricks component)
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Already installed components are disabled\nSelect new components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            
            # Set state based on existing installation
            if component in installed_components:
                check.set_active(True)
                check.set_sensitive(False)
                check.set_tooltip_text(f"{name} already installed")
            else:
                check.set_active(False)
                check.set_sensitive(True)
                
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install")
        dialog.set_default_response("install")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "install":
                # Get selected components that aren't already installed
                selected = [c for c, cb in checkboxes.items() 
                        if cb.get_active() and c not in installed_components]
                
                if selected:
                    # Create backup only when user confirms installation
                    backup_dir = current_template.with_name(f"{current_template.name}_backup_{int(time.time())}")
                    try:
                        # Show backup creation as first step
                        GLib.idle_add(self.show_processing_spinner, "Starting Customization...")
                        GLib.idle_add(self.show_initializing_step, "Creating template backup")
                        shutil.copytree(current_template, backup_dir, symlinks=True, dirs_exist_ok=True)
                        GLib.idle_add(self.mark_step_as_done, "Creating template backup")
                        
                        # Configure UI for installation
                        GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
                        GLib.idle_add(self.set_open_button_label, "Cancel")
                        GLib.idle_add(self.set_open_button_icon_visible, False)
                        
                        # Disconnect previous handler and set cancel action
                        if self.open_button_handler_id:
                            self.open_button.disconnect(self.open_button_handler_id)
                        self.open_button_handler_id = self.open_button.connect(
                            "clicked", 
                            self.on_cancel_customization_clicked,
                            backup_dir
                        )
                        
                        # Start installation thread
                        threading.Thread(
                            target=self.install_template_components,
                            args=(current_template, selected, backup_dir),
                            daemon=True
                        ).start()
                        
                    except Exception as e:
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Backup Failed",
                            f"Could not create backup: {str(e)}\nCannot proceed with customization."
                        )
                        if backup_dir.exists():
                            shutil.rmtree(backup_dir, ignore_errors=True)
                        return
                else:
                    # No new components selected
                    GLib.idle_add(
                        self.show_info_dialog,
                        "No Components Selected",
                        "No new components were selected for installation."
                    )
            else:
                # User cancelled dialog
                pass
            
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()



############### non laggy
    def install_template_components(self, template_dir, components, backup_dir):
        """Install components with visible backup step first"""
        self.stop_processing = False
        template_path = Path(template_dir)
        failed = False
        
        try:
            # Create steps with backup as first step
            steps = [
                ("Creating template backup", None),
            ] + [(f"Installing {component}", component) for component in components]
            
            self.total_steps = len(steps)

            # Process steps
            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                # Show step first before any operations
                GLib.idle_add(self.show_initializing_step, step_text)
                
                if step_text == "Creating template backup":
                    try:
                        # Perform actual backup after showing the step
                        shutil.copytree(template_path, backup_dir, 
                                    symlinks=True, dirs_exist_ok=True)
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        failed = True
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Backup Failed",
                            f"Could not create backup: {str(e)}"
                        )
                        return
                    continue

                # Regular component installation
                try:
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )

                    # Monitor process
                    while proc.poll() is None:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        time.sleep(0.1)

                    if proc.returncode not in [0, -15]:
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            cmd,
                            output=proc.stdout.read(),
                            stderr=proc.stderr.read()
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(
                        (index)/self.total_steps  # Offset by 1 for backup step
                    ))

                except Exception as e:
                    failed = True
                    self.restore_template_backup(template_path, backup_dir)
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Installation Failed",
                        f"Failed to install {component}: {str(e)}\nTemplate restored from backup."
                    )
                    return

            if not self.stop_processing and not failed:
                # Cleanup backup on success
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed successfully!"
                )

        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)
            self.stop_processing = False

    def customize_template_components(self, *args):
        """Updated customization dialog"""
        current_template = Path(self.template)
        winetricks_log = current_template / "winetricks.log"
        
        # Get installed components
        installed_components = set()
        if winetricks_log.exists():
            with open(winetricks_log, 'r') as f:
                installed_components = {line.strip() for line in f.readlines() if line.strip()}

        # Component list
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        # Create dialog
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Already installed components are disabled\nSelect new components to install:"
        )
        
        # Build checkboxes
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            if component in installed_components:
                check.set_active(True)
                check.set_sensitive(False)
                check.set_tooltip_text(f"{name} already installed")
            else:
                check.set_active(False)
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install")
        dialog.set_default_response("install")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "install":
                selected = [c for c, cb in checkboxes.items() 
                        if cb.get_active() and c not in installed_components]
                
                if selected:
                    # Prepare UI
                    GLib.idle_add(self.show_processing_spinner, "Preparing Customization...")
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
                    GLib.idle_add(self.set_open_button_label, "Cancel")
                    GLib.idle_add(self.set_open_button_icon_visible, False)
                    
                    # Generate backup path but don't create it yet
                    backup_dir = current_template.with_name(
                        f"{current_template.name}_backup_{int(time.time())}"
                    )
                    
                    # Start thread with backup path
                    threading.Thread(
                        target=self.install_template_components,
                        args=(current_template, selected, backup_dir),
                        daemon=True
                    ).start()
                    
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()

####################### another non laggy cancel
    def customize_template_components(self, *args):
        """Template customization dialog with full cancellation support"""
        current_template = Path(self.template)
        winetricks_log = current_template / "winetricks.log"
        
        # Get installed components from log file
        installed_components = set()
        if winetricks_log.exists():
            with open(winetricks_log, 'r') as f:
                installed_components = {line.strip() for line in f.readlines() if line.strip()}

        # Component list with (display name, winetricks component)
        components = [
            ("Core Fonts", "corefonts"),
            ("DirectX 9", "dxvk"),
            ("Visual C++ Runtimes", "vcredist"),
            ("DirectShow", "dshow"),
            ("OpenAL", "openal")
        ]
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Customize Template Components",
            body="Already installed components are disabled\nSelect new components to install:"
        )
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        checkboxes = {}
        
        for name, component in components:
            check = Gtk.CheckButton(label=name)
            
            # Set state based on existing installation
            if component in installed_components:
                check.set_active(True)
                check.set_sensitive(False)
                check.set_tooltip_text(f"{name} already installed")
            else:
                check.set_active(False)
                check.set_sensitive(True)
                
            checkboxes[component] = check
            vbox.append(check)
        
        dialog.set_extra_child(vbox)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install")
        dialog.set_default_response("install")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "install":
                # Get selected components that aren't already installed
                selected = [c for c, cb in checkboxes.items() 
                        if cb.get_active() and c not in installed_components]
                
                if selected:
                    # Generate backup path (actual backup happens in thread)
                    backup_dir = current_template.with_name(
                        f"{current_template.name}_backup_{int(time.time())}"
                    )
                    
                    # Configure UI for installation
                    GLib.idle_add(self.show_processing_spinner, "Starting Customization...")
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(0.0))
                    GLib.idle_add(self.set_open_button_label, "Cancel")
                    GLib.idle_add(self.set_open_button_icon_visible, False)
                    
                    # Disconnect previous handler and set cancel action
                    if self.open_button_handler_id:
                        self.open_button.disconnect(self.open_button_handler_id)
                    self.open_button_handler_id = self.open_button.connect(
                        "clicked", 
                        self.on_cancel_customization_clicked,
                        backup_dir
                    )
                    
                    # Start installation thread
                    threading.Thread(
                        target=self.install_template_components,
                        args=(current_template, selected, backup_dir),
                        daemon=True
                    ).start()
                else:
                    GLib.idle_add(
                        self.show_info_dialog,
                        "No Selection",
                        "No new components selected for installation."
                    )
            else:
                # User cancelled component selection dialog
                pass
            
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def on_cancel_customization_clicked(self, button, backup_dir):
        """Handle cancellation of ongoing customization process"""
        if self.current_operation == "backup":
            # Immediate cancellation for backup process
            self.stop_processing = True
            return
        
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Cancel Customization?",
            body="This will restore the template to its previous state.",
            close_response="continue"
        )
        dialog.add_response("continue", "Continue Installation")
        dialog.add_response("cancel", "Restore Backup")
        dialog.set_default_response("continue")
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_dialog_response(dialog, response):
            if response == "cancel":
                # Show restoring feedback immediately
                self.stop_processing = True
                GLib.idle_add(self.show_processing_spinner, "Restoring Template...")
                GLib.idle_add(self.progress_bar.pulse)
                
                # Start restoration in background
                threading.Thread(
                    target=self.restore_template_backup,
                    args=(Path(self.template), backup_dir),
                    daemon=True
                ).start()
            dialog.destroy()

        dialog.connect("response", on_dialog_response)
        dialog.present()

    def restore_template_backup(self, template_dir, backup_dir):
        """Atomic template restoration with UI feedback"""
        try:
            if backup_dir.exists():
                # Remove current template
                if template_dir.exists():
                    shutil.rmtree(template_dir, ignore_errors=True)
                
                # Restore backup
                backup_dir.rename(template_dir)
                
                GLib.idle_add(
                    self.show_info_dialog,
                    "Restoration Complete",
                    "Template has been restored to previous state."
                )
            else:
                GLib.idle_add(
                    self.show_info_dialog,
                    "No Backup Found",
                    "Could not find backup to restore from."
                )
        except Exception as e:
            print(e)
            GLib.idle_add(
                self.show_info_dialog,
                "Restoration Failed",
                f"Could not restore template: {str(e)}\nBackup remains at: {backup_dir}"
            )
        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)
            self.stop_processing = False

    def install_template_components(self, template_dir, components, backup_dir):
        """Main installation process with visible backup step"""
        self.stop_processing = False
        template_path = Path(template_dir)
        
        try:
            # Create steps with backup as first step
            steps = [
                ("Creating template backup", None),
            ] + [(f"Installing {component}", component) for component in components]
            
            self.total_steps = len(steps)

            # Process steps with cancellation checks
            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                # Update UI first
                GLib.idle_add(self.show_initializing_step, step_text)
                
                if step_text == "Creating template backup":
                    try:
                        self.current_operation = "backup"
                        self._cancellable_copy(template_path, backup_dir)
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Backup Failed",
                            f"Could not create backup: {str(e)}"
                        )
                        return
                    finally:
                        self.current_operation = None
                    continue

                # Component installation
                try:
                    self.current_operation = "installation"
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    with self.process_lock:
                        self.current_process = subprocess.Popen(
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True
                        )

                    # Monitor process with cancellation
                    while True:
                        if self.stop_processing:
                            with self.process_lock:
                                if self.current_process:
                                    self.current_process.terminate()
                            break
                        
                        if self.current_process.poll() is not None:
                            break
                        
                        time.sleep(0.1)

                    # Verify results
                    returncode = self.current_process.returncode
                    if returncode not in [0, -15]:
                        output = self.current_process.stdout.read()[:500]
                        error = self.current_process.stderr.read()[:500]
                        raise subprocess.CalledProcessError(
                            returncode,
                            cmd,
                            output=output,
                            stderr=error
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    self.restore_template_backup(template_path, backup_dir)
                    error_msg = "Operation cancelled" if self.stop_processing else f"Failed to install {component}: {str(e)}"
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Cancelled" if self.stop_processing else "Installation Failed",
                        error_msg + "\nTemplate has been restored."
                    )
                    return
                finally:
                    self.current_operation = None

            # Final success
            if not self.stop_processing:
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed successfully!"
                )

        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)
            self.stop_processing = False
            self.current_operation = None
            with self.process_lock:
                self.current_process = None

    def _cancellable_copy(self, src, dst):
        """Custom copy with progress and cancellation support"""
        src = Path(src)
        dst = Path(dst)
        
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
            
        os.makedirs(dst, exist_ok=True)
        
        total_files = sum(len(files) for _, _, files in os.walk(src))
        copied_files = 0
        
        for root, dirs, files in os.walk(src):
            if self.stop_processing:
                raise Exception("Copy cancelled by user")
                
            rel_path = os.path.relpath(root, src)
            dest_dir = os.path.join(dst, rel_path)
            os.makedirs(dest_dir, exist_ok=True)
            
            for file in files:
                if self.stop_processing:
                    raise Exception("Copy cancelled by user")
                    
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                shutil.copy2(src_file, dest_file)
                
                # Update progress every 10 files
                copied_files += 1
                if copied_files % 10 == 0:
                    progress = copied_files / total_files
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(progress))




    def _cancellable_copy(self, src, dst):
        """Custom copy with proper symlink handling and cancellation support"""
        src = Path(src)
        dst = Path(dst)
        
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
            
        os.makedirs(dst, exist_ok=True)
        
        total_files = sum(len(files) for _, _, files in os.walk(src, followlinks=False))
        copied_files = 0
        
        for root, dirs, files in os.walk(src, followlinks=False):
            if self.stop_processing:
                raise Exception("Copy cancelled by user")
                
            rel_path = os.path.relpath(root, src)
            dest_dir = os.path.join(dst, rel_path)
            os.makedirs(dest_dir, exist_ok=True)
            
            # Process directories first to maintain structure
            for dir_name in dirs:
                src_dir = os.path.join(root, dir_name)
                dest_dir_path = os.path.join(dest_dir, dir_name)
                
                if os.path.islink(src_dir):
                    # Handle symlinked directories
                    link_target = os.readlink(src_dir)
                    if os.path.exists(dest_dir_path):
                        shutil.rmtree(dest_dir_path, ignore_errors=True)
                    os.symlink(link_target, dest_dir_path)
                else:
                    # Regular directory
                    os.makedirs(dest_dir_path, exist_ok=True)
            
            # Process files
            for file in files:
                if self.stop_processing:
                    raise Exception("Copy cancelled by user")
                    
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                
                if os.path.islink(src_file):
                    # Handle symlinked files
                    link_target = os.readlink(src_file)
                    if os.path.lexists(dest_file):
                        os.remove(dest_file)
                    os.symlink(link_target, dest_file)
                else:
                    # Regular file copy
                    shutil.copy2(src_file, dest_file, follow_symlinks=False)
                
                # Update progress every 10 files
                copied_files += 1
                if copied_files % 10 == 0:
                    progress = copied_files / total_files
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(progress))

##################3 error fix?
    def install_template_components(self, template_dir, components, backup_dir):
        """Main installation process with proper cancellation error handling"""
        self.stop_processing = False
        template_path = Path(template_dir)
        
        try:
            # Create steps with backup as first step
            steps = [
                ("Creating template backup", None),
            ] + [(f"Installing {component}", component) for component in components]
            
            self.total_steps = len(steps)

            # Process steps with cancellation checks
            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                # Update UI first
                GLib.idle_add(self.show_initializing_step, step_text)
                
                if step_text == "Creating template backup":
                    try:
                        self.current_operation = "backup"
                        self._cancellable_copy(template_path, backup_dir)
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        error_msg = "Backup cancelled" if self.stop_processing else f"Backup failed: {str(e)}"
                        print(error_msg)
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Cancelled" if self.stop_processing else "Backup Failed",
                            error_msgCancelled
                        )
                        return
                    finally:
                        self.current_operation = None
                    continue

                # Component installation
                try:
                    self.current_operation = "installation"
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    with self.process_lock:
                        self.current_process = subprocess.Popen(
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True
                        )

                    # Monitor process with cancellation
                    while True:
                        if self.stop_processing:
                            with self.process_lock:
                                if self.current_process:
                                    self.current_process.terminate()
                            break
                        
                        if self.current_process.poll() is not None:
                            break
                        
                        time.sleep(0.1)

                    # Get safe return code
                    returncode = self.current_process.returncode
                    if returncode not in [0, -15]:
                        # Handle None returncode
                        safe_returncode = returncode if returncode is not None else "Unknown"
                        output = self.current_process.stdout.read()[:500] or "No output"
                        error = self.current_process.stderr.read()[:500] or "No error"
                        
                        raise subprocess.CalledProcessError(
                            returncode if returncode is not None else -1,
                            cmd,
                            output=output,
                            stderr=error
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    # Handle cancellation vs error
                    if self.stop_processing:
                        error_msg = "Customization cancelled by user"
                        title = "Cancelled"
                    else:
                        error_msg = self._format_error(e, component)
                        title = "Installation Failed"
                    
                    self.restore_template_backup(template_path, backup_dir)
                    GLib.idle_add(
                        self.show_info_dialog,
                        title,
                        f"{error_msg}\nTemplate has been restored."
                    )
                    return
                finally:
                    self.current_operation = None

            # Final success
            if not self.stop_processing:
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed successfully!"
                )

        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)
            self.stop_processing = False
            self.current_operation = None
            with self.process_lock:
                self.current_process = None

    def _format_error(self, error, component):
        """Safe error formatting with None handling"""
        if isinstance(error, subprocess.CalledProcessError):
            rc = error.returncode if error.returncode is not None else "Unknown"
            cmd = error.cmd if error.cmd else "Unknown command"
            output = error.stdout if error.stdout else "No output"
            stderr = error.stderr if error.stderr else "No error"
            return (
                f"Failed to install {component}:\n"
                f"Command: {cmd}\n"
                f"Exit code: {rc}\n"
                f"Output: {output[:200]}\n"
                f"Error: {stderr[:200]}"
            )
        return f"Failed to install {component}: {str(error)}"




#################### cancellation at component fix?
    def install_template_components(self, template_dir, components, backup_dir):
        """Install components with robust backup handling"""
        self.stop_processing = False
        template_path = Path(template_dir)
        backup_path = Path(backup_dir)
        
        try:
            # Create steps with backup as first step
            steps = [
                ("Creating template backup", None),
            ] + [(f"Installing {component}", component) for component in components]
            
            self.total_steps = len(steps)

            # Process steps with cancellation checks
            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                # Update UI first
                GLib.idle_add(self.show_initializing_step, step_text)
                
                if step_text == "Creating template backup":
                    try:
                        self.current_operation = "backup"
                        self._cancellable_copy(template_path, backup_path)
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        error_msg = "Backup cancelled" if self.stop_processing else f"Backup failed: {str(e)}"
                        print(error_msg)
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Cancelled" if self.stop_processing else "Backup Failed",
                            error_msg
                        )
                        return
                    finally:
                        self.current_operation = None
                    continue

                # Component installation
                try:
                    self.current_operation = "installation"
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    with self.process_lock:
                        self.current_process = subprocess.Popen(
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True
                        )

                    # Monitor process with cancellation
                    while True:
                        if self.stop_processing:
                            with self.process_lock:
                                if self.current_process:
                                    self.current_process.terminate()
                            break
                        
                        if self.current_process.poll() is not None:
                            break
                        
                        time.sleep(0.1)

                    # Handle process results
                    returncode = self.current_process.returncode
                    if returncode not in [0, -15]:
                        output = self.current_process.stdout.read()[:500] or "No output"
                        error = self.current_process.stderr.read()[:500] or "No error"
                        safe_rc = returncode if returncode is not None else "Unknown"
                        
                        raise subprocess.CalledProcessError(
                            returncode if returncode is not None else -1,
                            cmd,
                            output=output,
                            stderr=error
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    
                    error_msg = self._format_error(e, component)
                    success = self.restore_template_backup(template_path, backup_path)
                    print(error_msg)
                    final_msg = "Template restoration failed" if not success else "Template has been restored"
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Cancelled" if self.stop_processing else "Installation Failed",
                        f"{error_msg}\n{final_msg}"
                    )
                    return
                finally:
                    self.current_operation = None
                    with self.process_lock:
                        self.current_process = None

            # Final cleanup if successful
            if not self.stop_processing and backup_path.exists():
                try:
                    shutil.rmtree(backup_path, ignore_errors=True)
                except Exception as e:
                    print(f"Backup cleanup error: {str(e)}")

            if not self.stop_processing:
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed successfully!"
                )

        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)
            self.stop_processing = False

    def restore_template_backup(self, template_dir, backup_dir):
        """Atomic template restoration with comprehensive error handling"""
        template_path = Path(template_dir)
        backup_path = Path(backup_dir)
        
        try:
            if not backup_path.exists():
                GLib.idle_add(
                    self.show_info_dialog,
                    "Restoration Failed",
                    "Backup directory no longer exists\nOriginal template may be damaged"
                )
                return False

            # Remove existing template if present
            if template_path.exists():
                try:
                    shutil.rmtree(template_path, ignore_errors=True)
                except Exception as e:
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Restoration Failed",
                        f"Could not remove damaged template: {str(e)}"
                    )
                    return False

            try:
                # Atomic rename operation
                backup_path.rename(template_path)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Restoration Complete",
                    "Template successfully restored from backup"
                )
                return True
            except FileNotFoundError:
                GLib.idle_add(
                    self.show_info_dialog,
                    "Restoration Failed",
                    "Backup directory was deleted during operation"
                )
                return False
            except Exception as e:
                GLib.idle_add(
                    self.show_info_dialog,
                    "Restoration Failed",
                    f"Could not restore template: {str(e)}"
                )
                return False

        except Exception as e:
            GLib.idle_add(
                self.show_info_dialog,
                "Critical Error",
                f"Restoration failed: {str(e)}\nManual recovery required"
            )
            return False
        finally:
            # Cleanup UI state
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            GLib.idle_add(self.set_open_button_icon_visible, True)

    def _format_error(self, error, component):
        """Safe error message formatting with None handling"""
        if isinstance(error, subprocess.CalledProcessError):
            rc = error.returncode if error.returncode is not None else "Unknown"
            cmd = error.cmd if error.cmd else "Unknown command"
            output = error.stdout if error.stdout else "No output"
            stderr = error.stderr if error.stderr else "No error"
            
            return (
                f"Failed to install {component}:\n"
                f"• Command: {cmd}\n"
                f"• Exit code: {rc}\n"
                f"• Output: {output[:200]}\n"
                f"• Error: {stderr[:200]}"
            )
        
        if self.stop_processing:
            return "Operation cancelled by user"
            
        return f"Unexpected error installing {component}: {str(error)}"

############# quiet restore, don't give too much errors
    def install_template_components(self, template_dir, components, backup_dir):
        """Install components with simplified cancellation handling"""
        self.stop_processing = False
        template_path = Path(template_dir)
        backup_path = Path(backup_dir)
        
        try:
            steps = [
                ("Creating template backup", None),
            ] + [(f"Installing {component}", component) for component in components]
            
            self.total_steps = len(steps)

            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                if step_text == "Creating template backup":
                    try:
                        self._cancellable_copy(template_path, backup_path)
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        if self.stop_processing:
                            self._show_cancellation_message(backup_path)
                        return
                    continue

                try:
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )

                    while True:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)

                    if proc.returncode not in [0, -15]:
                        # Filter winetricks version warning
                        output = self._filter_winetricks_warnings(proc.stdout.read())
                        error = self._filter_winetricks_warnings(proc.stderr.read())
                        
                        if not self.stop_processing:
                            raise subprocess.CalledProcessError(
                                proc.returncode,
                                cmd,
                                output=output,
                                stderr=error
                            )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    if self.stop_processing:
                        self._show_cancellation_message(backup_path)
                    else:
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Installation Error",
                            f"Failed to install {component}\n{str(e)}"
                        )
                    return

            if not self.stop_processing:
                self._cleanup_backup(backup_path)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed!"
                )

        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            self.stop_processing = False

    def _show_cancellation_message(self, backup_path):
        """Show consistent cancellation message"""
        success = self.restore_template_backup(Path(self.template), backup_path)
        msg = "Customization cancelled - template restored" if success else "Customization cancelled - restoration failed"
        GLib.idle_add(
            self.show_info_dialog,
            "Cancelled",
            msg
        )
        self._cleanup_backup(backup_path)

    def restore_template_backup(self, template_dir, backup_dir):
        """Simplified restoration with error suppression"""
        try:
            template_path = Path(template_dir)
            backup_path = Path(backup_dir)
            
            if backup_path.exists():
                if template_path.exists():
                    shutil.rmtree(template_path, ignore_errors=True)
                backup_path.rename(template_path)
                return True
            return False
        except Exception:
            return False

    def _filter_winetricks_warnings(self, text):
        """Filter out common winetricks version warnings"""
        return '\n'.join(
            line for line in text.split('\n') 
            if "warning: You are running winetricks" not in line
        )

    def _cleanup_backup(self, backup_path):
        """Silent backup cleanup"""
        try:
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
        except Exception:
            pass



####################3 reliable?
    def install_template_components(self, template_dir, components, backup_dir):
        """Install components with atomic backup handling"""
        self.stop_processing = False
        template_path = Path(template_dir)
        backup_path = Path(backup_dir)
        backup_created = False

        try:
            # Create temporary backup directory
            temp_backup = backup_path.with_name(f"{backup_path.name}.tmp")
            
            # Backup as first step
            try:
                GLib.idle_add(self.show_initializing_step, "Creating template backup")
                self._atomic_copy(template_path, temp_backup, backup_path)
                backup_created = True
                GLib.idle_add(self.mark_step_as_done, "Creating template backup")
            except Exception as e:
                if self.stop_processing:
                    GLib.idle_add(
                        self.show_info_dialog,
                        "Cancelled",
                        "Customization cancelled before any changes were made"
                    )
                    return
                raise

            # Installation steps
            steps = [(f"Installing {component}", component) for component in components]
            self.total_steps = len(steps)

            for index, (step_text, component) in enumerate(steps, 1):
                if self.stop_processing:
                    break

                GLib.idle_add(self.show_initializing_step, step_text)
                
                try:
                    cmd = f"WINEPREFIX='{template_path}' winetricks -q {component}"
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )

                    while True:
                        if self.stop_processing:
                            proc.terminate()
                            break
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)

                    if proc.returncode not in [0, -15]:
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            cmd,
                            output=proc.stdout.read(),
                            stderr=proc.stderr.read()
                        )

                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index/self.total_steps))

                except Exception as e:
                    if self.stop_processing:
                        self._show_restoration_message(backup_path)
                    else:
                        self._show_restoration_message(backup_path)
                        GLib.idle_add(
                            self.show_info_dialog,
                            "Error",
                            f"Failed to install {component}"
                        )
                    return

            if not self.stop_processing:
                self._cleanup_backup(backup_path)
                GLib.idle_add(
                    self.show_info_dialog,
                    "Success",
                    "Template customization completed!"
                )

        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.set_open_button_label, "Open")
            self.stop_processing = False
            GLib.idle_add(self.create_script_list)

    def _atomic_copy(self, src, temp_dst, final_dst):
        """Atomic copy with temporary directory"""
        try:
            if temp_dst.exists():
                shutil.rmtree(temp_dst, ignore_errors=True)
                
            shutil.copytree(src, temp_dst, symlinks=True)
            temp_dst.rename(final_dst)
        except Exception as e:
            shutil.rmtree(temp_dst, ignore_errors=True)
            if self.stop_processing:
                raise Exception("Cancelled") from e
            raise

    def _show_restoration_message(self, backup_path):
        """Handle restoration consistently"""
        try:
            if backup_path.exists():
                success = self.restore_template_backup(Path(self.template), backup_path)
                msg = "Template restored successfully" if success else "Restoration failed"
            else:
                msg = "No backup found - original template remains unchanged"
                
            GLib.idle_add(
                self.show_info_dialog,
                "Cancelled",
                f"Customization cancelled - {msg}"
            )
        finally:
            self._cleanup_backup(backup_path)

    def restore_template_backup(self, template_dir, backup_dir):
        """Atomic restoration with error suppression"""
        try:
            template_path = Path(template_dir)
            backup_path = Path(backup_dir)
            
            if backup_path.exists():
                if template_path.exists():
                    shutil.rmtree(template_path, ignore_errors=True)
                backup_path.rename(template_path)
                return True
            return False
        except Exception:
            return False

    def _cleanup_backup(self, backup_path):
        """Silent backup cleanup"""
        try:
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
        except Exception:
            pass




















def parse_args():
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(description="WineCharm GUI application or headless mode for .charm files")
    parser.add_argument('file', nargs='?', help="Path to the .exe, .msi, or .charm file")
    return parser.parse_args()
    
def main():
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

                # Add script arguments if present
                if script_args:
                    command_parts.append(f"{script_args}")

                # Join all the command parts
                command = " && ".join(command_parts)

                print(f"Executing: {command}")
                subprocess.run(command, shell=True)

                # Exit after headless execution to ensure no GUI elements are opened
                sys.exit(0)

            except Exception as e:
                print(f"Error: Unable to launch the .charm script: {e}")
                sys.exit(1)

        # For .exe or .msi files, validate the file type and continue with GUI mode
        elif file_extension in ['.exe', '.msi']:
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
            # Invalid file type, print error and handle accordingly
            print(f"Invalid file type: {file_extension}. Only .exe, .msi, or .charm files are allowed.")
            
            # If no instance is running, start WineCharmApp and show the error dialog directly
            if not app.SOCKET_FILE.exists():
                app.start_socket_server()
                GLib.timeout_add_seconds(1.5, app.show_info_dialog, "Invalid File Type", f"Only .exe, .msi, or .charm files are allowed. You provided: {file_extension}")
                app.run(sys.argv)

                # Clean up the socket file
                if app.SOCKET_FILE.exists():
                    app.SOCKET_FILE.unlink()
            else:
                # If an instance is running, send the error message to the running instance
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.connect(str(app.SOCKET_FILE))
                        message = f"show_dialog||Invalid file type: {file_extension}||Only .exe, .msi, or .charm files are allowed."
                        client.sendall(message.encode())
                    return
                except ConnectionRefusedError:
                    print("No existing instance found, starting a new one.")
            
            # Return early to skip further processing
            return

    # Start the socket server and run the application (GUI mode)
    app.start_socket_server()
    app.run(sys.argv)

    # Clean up the socket file
    if app.SOCKET_FILE.exists():
        app.SOCKET_FILE.unlink()

if __name__ == "__main__":
    main()
