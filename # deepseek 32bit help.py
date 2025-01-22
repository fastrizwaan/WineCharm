# deepseek 32bit help
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
        self.default_template = self.templates_dir / "WineCharm-win64"
        self.default_32bit_template = self.templates_dir / "WineCharm-win32"
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


    def on_startup(self, app):
        self.create_main_window()
        # Clear or initialize the script list
        self.script_list = {}
        self.load_script_list()
        self.create_script_list()
        self.single_prefix = False
        self.load_settings()
        self.arch = "win64"
        print(f"Single Prefix: {self.single_prefix}")
        #self.check_running_processes_and_update_buttons()

        if self.arch == 'win32':
            if not self.default_32bit_template.exists():
                # Pass arch parameter for 32-bit
                self.initialize_template(self.default_32bit_template, 
                                    self.on_template_initialized, 
                                    arch='win32')
        else:  # win64
            if not self.default_template.exists():
                # Pass arch parameter for 64-bit
                self.initialize_template(self.default_template, 
                                    self.on_template_initialized, 
                                    arch='win64')

        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        else:

            if self.arch == 'win32' and not self.default_32bit_template.exists() and not self.single_prefix:
                self.initialize_template(self.default_32bit_template, self.on_template_initialized)
                self.template = self.default_32bit_template
            elif self.arch == 'win32' and not self.default_32bit_template.exists() and self.single_prefix:
                self.initialize_template(self.default_32bit_template, self.on_template_initialized)
                self.template = self.default_32bit_template
                self.copy_template(self.single_prefix_dir_win32)
            elif not self.default_template.exists() and not self.single_prefix:
                self.initialize_template(self.default_template, self.on_template_initialized)
            if not self.default_template.exists() and self.single_prefix:
                self.initialize_template(self.default_template, self.on_template_initialized)
                self.copy_template(self.single_prefix_dir_win64)
            elif self.default_template.exists() and not self.single_prefix_dir_win64.exists() and self.single_prefix:
                self.copy_template(self.single_prefix_dir_win64)
            else:
                self.set_dynamic_variables()
                # Process the command-line file if the template already exists
                if self.command_line_file:
                    print("Template exists. Processing command-line file after UI initialization.")
                    self.process_cli_file_later(self.command_line_file)
        # After loading scripts and building the UI, check for running processes
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

    def initialize_template(self, template_dir, callback):
        """
        Modified template initialization with proper Path handling and interruption support
        """
        template_dir = Path(template_dir) if not isinstance(template_dir, Path) else template_dir
        
        self.create_required_directories()
        self.initializing_template = True
        self.stop_processing = False
        
        # Disconnect open button handler
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_init_clicked)
        
        steps = [
            ("Initializing wineprefix", f"WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
            ("Replace symbolic links with directories", lambda: self.remove_symlinks_and_create_directories(template_dir)),
            ("Installing corefonts", f"WINEPREFIX='{template_dir}' winetricks -q corefonts"),
            ("Installing openal", f"WINEPREFIX='{template_dir}' winetricks -q openal"),
            ("Installing vkd3d", f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
            ("Installing dxvk", f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
        ]
        
        # Set total steps and initialize progress UI
        self.total_steps = len(steps)
        self.show_processing_spinner("Initializing Template...")

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
                        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
                    # Update progress bar only if it exists
                    if hasattr(self, 'progress_bar'):
                        GLib.idle_add(lambda: self.progress_bar.set_fraction(index / self.total_steps))
                    
                except subprocess.CalledProcessError as e:
                    print(f"Error initializing template: {e}")
                    GLib.idle_add(self.cleanup_cancelled_template_init, template_dir)
                    return
                    
            if not self.stop_processing:
                GLib.idle_add(callback)
                GLib.idle_add(self.hide_processing_spinner)
                self.disconnect_open_button()
                GLib.idle_add(self.reset_ui_after_template_init)
        threading.Thread(target=initialize).start()

    def on_template_initialized(self):
        print("Template initialization complete.")
        self.initializing_template = False
        
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
        self.hide_processing_spinner()
        GLib.timeout_add_seconds(0.5, self.create_script_list)
        
        # Check if there's a command-line file to process after initialization
        if self.command_line_file:
            print("Processing command-line file after template initialization")
            self.process_cli_file_later(self.command_line_file)
            self.command_line_file = None  # Reset after processing

        #
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
            self.template = self.expand_and_resolve_path(settings.get('template', self.default_template))
            self.arch = settings.get('arch', "win64")
            self.icon_view = settings.get('icon_view', False)
            self.single_prefix = settings.get('single-prefix', False)
        else:
            self.template = self.expand_and_resolve_path(self.default_template)
            self.arch = "win64"
            self.runner = ""
            self.template = self.default_template  # Set template to the initialized one
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
            self.template = self.expand_and_resolve_path(settings.get('template', self.default_template))
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

        # Handle prefix directory
        if prefix_dir is None and self.single_prefix:
            if not self.single_prefixes_dir.exists():
                self.copy_template(self.single_prefixes_dir)
            prefix_dir = self.single_prefixes_dir 
        elif prefix_dir is None:
            prefix_dir = self.prefixes_dir / f"{exe_no_space}-{sha256sum}"
            if not prefix_dir.exists():
                if self.template.exists() and not prefix_dir.exists():
                    self.copy_template(prefix_dir)
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
        # Create message dialog
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            title="Single Prefix Mode",
            body="Choose prefix mode for new games:\nSingle prefix saves space but makes it harder to backup individual games."
        )

        # Create a vertical box for the radio buttons
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        # Create radio buttons as checkboxes
        single_prefix_radio = Gtk.CheckButton(label="Single Prefix Mode")
        multiple_prefix_radio = Gtk.CheckButton(label="Multiple Prefix Mode")
        
        # Make them behave as radio buttons by setting the group
        multiple_prefix_radio.set_group(single_prefix_radio)
        
        # Set the active radio button based on current setting
        single_prefix_radio.set_active(self.single_prefix)
        multiple_prefix_radio.set_active(not self.single_prefix)
        
        # Add the radio buttons to the box
        vbox.append(single_prefix_radio)
        vbox.append(multiple_prefix_radio)
        
        # Add the box to the dialog
        dialog.set_extra_child(vbox)
        
        # Add response buttons
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", "Apply")
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        
        # Connect the response signal
        dialog.connect("response", lambda dialog, response: self.on_single_prefix_mode_response(
            dialog, response, single_prefix_radio.get_active())
        )
        
        # Present the dialog
        dialog.present()

    def on_single_prefix_mode_response(self, dialog, response_id, is_single_prefix):
        if response_id == "apply":
            # Update the setting
            self.single_prefix = is_single_prefix
            self.save_settings()
            if self.arch == 'win32' and not self.default_32bit_template.exists() and not self.single_prefix:
                self.initialize_template(self.default_32bit_template, self.on_template_initialized)
                self.template = self.default_32bit_template
            elif self.arch == 'win32' and not self.default_32bit_template.exists() and self.single_prefix:
                self.initialize_template(self.default_32bit_template, self.on_template_initialized)
                self.template = self.default_32bit_template
                self.copy_template(self.single_prefix_dir_win32)
            elif not self.default_template.exists() and not self.single_prefix:
                self.initialize_template(self.default_template, self.on_template_initialized)
            elif not self.default_template.exists() and self.single_prefix:
                self.initialize_template(self.default_template, self.on_template_initialized)
                self.copy_template(self.single_prefixes_dir)
            elif self.default_template.exists() and not self.single_prefixes_dir.exists() and self.single_prefix:
                self.copy_template(self.single_prefixes_dir)
            else:
                self.set_dynamic_variables()
            print(f"{'Single' if is_single_prefix else 'Multiple'} Prefix Mode enabled")
        else:
            print("Prefix mode change cancelled")
        
        # Close the dialog
        dialog.close()

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

