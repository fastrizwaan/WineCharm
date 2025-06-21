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

# Import file operation functions directly
# Add current directory to sys.path for local development
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

try:
    from winecharm import ui, settings, template_manager, runner_manager, single_prefix, restore, backup, winezgui_importer, import_wine_dir, import_game_dir,create_script
except ImportError:
    import ui
    import settings
    import template_manager
    import runner_manager
    import single_prefix
    import restore
    import backup
    import winezgui_importer
    import import_wine_dir
    import import_game_dir
    import create_script
    
class WineCharmApp(Adw.Application):
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
        self.version = "0.99.3"
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
        self.script_ui_data = {}
        
        # Register the SIGINT signal handler
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.script_buttons = {}
        self.current_clicked_row = None  # Initialize current clicked row

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




        # Runner cache file
        self.runner_cache_file = self.winecharmdir / "runner_cache.yaml"
        self.runner_data = None  # Will hold the runner data after fetching


        # Set keyboard accelerators
        self.set_accels_for_action("win.search", ["<Ctrl>f"])
        self.set_accels_for_action("win.open", ["<Ctrl>o"])
        self.set_accels_for_action("win.on_kill_all_clicked", ["<Ctrl>k"])
        self.set_accels_for_action("win.toggle_view", ["<Ctrl>v"])
        self.set_accels_for_action("win.back", ["<Ctrl>BackSpace"])

        self.count = 0
        self.winezgui_prefixes_dir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineZGUI/data/winezgui/Prefixes")).resolve()

##################### Import Methods from files #####################
        # Define method mappings
        module_methods = {
            ui: [
                'create_main_window',
                'add_keyboard_actions',
                'create_sort_actions',
                'on_search_button_clicked',
                'populate_script_options',
                'on_key_pressed',
                'on_search_entry_activated',
                'on_search_entry_changed',
                'filter_script_list',
                'update_ui_for_running_process',
                'on_open_button_clicked',
                'open_file_dialog',
                'create_file_filter',
                'on_open_file_dialog_response',
                'on_back_button_clicked',
                'open_filemanager_winecharm',
                'open_terminal_winecharm',
                'setup_accelerator_context',
                'remove_accelerator_context',
                'restore_open_button',
            ],
            settings: [
                'on_settings_clicked',
                'load_settings',
                'save_settings',
                'set_dynamic_variables',
                'replace_open_button_with_settings', 
                'show_options_for_settings',
                'populate_settings_options',
            ],
            template_manager: [
                'initialize_template', 'on_template_initialized',
                'copy_template',
                'on_cancel_template_init_clicked',
                'on_cancel_template_init_dialog_response',
                'cleanup_cancelled_template_init',
                'reset_ui_after_template_init',
                'get_template_arch',
                'set_default_template',
                'delete_template',
                'import_template',
                'on_import_template_response',
                'process_template_import',
                'verify_template_source',
                'clean_template_files',
                'handle_template_import_error',
                'on_import_template_directory_completed',
                'backup_template',
                'on_backup_template_response',
                'create_template_backup',
                'connect_cancel_button_for_template_backup',
                'on_cancel_template_backup_clicked',
                'on_cancel_template_backup_dialog_response',
                'cleanup_cancelled_template_backup',
                'restore_template_from_backup',
                'on_restore_template_file_dialog_response',
                'restore_template_tar_zst',
                'extract_template_backup',
                'extract_template_dir',
                'get_template_restore_steps',
                'check_template_disk_space',
                'on_template_restore_completed',
                'clone_template',
                'on_template_selected_for_clone',
                'on_clone_name_changed',
                'on_clone_template_response',
                'perform_template_clone',
                'create_template',
                'configure_template',
            ],
            runner_manager: [
                'get_runner',
                'update_runner_path_in_script',
                'change_runner',
                'on_change_runner_response',
                'get_valid_runners',
                'validate_runner',
                'on_download_runner_clicked',
                'on_runner_download_complete',
                'get_system_wine',
                'show_no_runners_available_dialog',
                'set_default_runner',
                '_on_dropdown_factory_setup',
                '_on_dropdown_factory_bind',
                'on_set_default_runner_response',
                'on_download_runner_clicked_default',
                'on_runner_download_complete_default_runner',
                'maybe_fetch_runner_urls',
                'cache_is_stale',
                'fetch_runner_urls_from_github',
                'parse_runner_data',
                'get_runner_category',
                'save_runner_data_to_cache',
                'load_runner_data_from_cache',
                'on_settings_download_runner_clicked',
                'on_download_runner_response',
                'download_runners_thread',
                'download_and_extract_runner',
                'delete_runner',
                'on_delete_runner_response',
                'backup_runner',
                'on_backup_runner_response',
                'create_runner_backup',
                'restore_runner',
                'extract_runner_archive',
                'archive_contains_wine',
                'import_runner',
                'on_import_runner_response',
                'process_runner_import',
                'verify_runner_source',
                'verify_runner_binary',
                'set_runner_permissions',
                'handle_runner_import_error',
                'on_import_runner_directory_completed',
                'refresh_runner_list',
                'show_confirm_dialog',
            ],
            single_prefix: [
                'single_prefix_mode',
                'handle_prefix_mode_change',
                'finalize_prefix_mode_change',
            ],
            backup: [
                'show_backup_prefix_dialog',
                'on_backup_prefix_dialog_response',
                'on_backup_prefix_completed',
                '_complete_backup_ui_update',
                'backup_prefix',
                'create_backup_archive',
                'connect_open_button_with_backup_cancel',
                'cleanup_cancelled_backup',
                'on_cancel_backup_clicked',
                'on_cancel_backup_dialog_response',
                'get_directory_size',
                'create_bottle',
                'on_create_bottle_completed',
                '_complete_bottle_creation_ui_update',
                'create_bottle_selected',
                'show_create_bottle_dialog',
                'on_create_bottle_dialog_response',
                'create_bottle_archive',
                'connect_open_button_with_bottling_cancel',
                'cleanup_cancelled_bottle',
                '_reset_ui_state',
                'on_backup_confirmation_response',
                'create_bottle_archive',
                'on_cancel_bottle_clicked',
                'on_cancel_bottle_dialog_response',
                'backup_existing_directory',
            ],
            restore: [
                'restore_from_backup',
                'get_total_uncompressed_size',
                'restore_check_disk_space_and_uncompressed_size',
                'on_restore_file_dialog_response',
                'restore_prefix_bottle_wzt_tar_zst',
                'get_restore_steps',
                'get_wzt_restore_steps',
                'create_wineboot_required_file',
                'perform_replacements',
                'replace_strings_in_files',
                'is_binary_file',
                'process_sh_files',
                'load_and_fix_yaml',
                'create_charm_file',
                'extract_infofile_path_from_sh',
                'find_sh_files',
                'find_and_save_lnk_files',
                'parse_info_file',
                'add_charm_files_to_script_list',
                'on_restore_completed',
                'extract_backup',
                '_kill_current_process',
                'extract_prefix_dir',
                'check_disk_space_and_show_step',
                'check_disk_space_quick',
                'connect_open_button_with_restore_backup_cancel',
                'on_cancel_restore_backup_clicked',
                'on_cancel_restore_backup_dialog_response',
            ],
            winezgui_importer: [
                'process_winezgui_sh_files',
            ],
            import_wine_dir: [
                'rename_and_merge_user_directories',
                'merge_directories',
                'on_import_wine_directory_clicked',
                'on_import_directory_response',
                'import_wine_directory',
                'on_import_wine_directory_completed',
                'copy_wine_directory',
                'show_import_wine_directory_overwrite_confirmation_dialog',
                'on_import_wine_directory_overwrite_response',
                'on_cancel_import_wine_direcotory_dialog_response',
                'on_cancel_import_wine_directory_clicked',
                'connect_open_button_with_import_wine_directory_cancel',
                'handle_import_cancellation',
                'handle_import_error',
                'cleanup_backup',
                'cleanup_cancelled_import',
                'disconnect_open_button',
                'reconnect_open_button',
                'create_scripts_for_exe_files',
                'find_exe_files',
                'process_reg_files',
                'custom_copytree',
            ],
            import_game_dir: [
                'import_game_directory',
                'copy_game_directory',
                'on_import_game_directory_completed',
                'update_exe_file_path_in_script',
                'get_do_not_bundle_directories',
                'has_enough_disk_space',
                ],
            create_script: [
                'determine_progname',
                'create_yaml_file',
                'extract_icon',
                'track_all_lnk_files',
                'find_lnk_files',
                'add_lnk_file_to_processed',
                'is_lnk_file_processed',
                'create_scripts_for_lnk_files',
                'extract_exe_files_from_lnk',
            ],
        }

        # Bind methods to self
        for module, methods in module_methods.items():
            for method_name in methods:
                if hasattr(module, method_name):
                    setattr(self, method_name, getattr(module, method_name).__get__(self, WineCharmApp))         
                
##################### / Import Methods from files #####################                
        self.hamburger_actions = [
            ("🛠️ Settings...", self.show_options_for_settings),
            ("☠️ Kill all...", self.on_kill_all_clicked),
            ("🍾 Restore...", self.restore_from_backup),
            ("📥 Import Wine Directory", self.on_import_wine_directory_clicked),
            ("📥 Import WineZGUI Scripts...", self.process_winezgui_sh_files),
            ("❓ Help...", self.on_help_clicked),
            ("📖 About...", self.on_about_clicked),
            ("🚪 Quit...", self.quit_app)
        ]

        self.settings = self.load_settings()  # Add this line
################### / __init__ #################
                
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
        import subprocess
        import shutil
        try:
            if shutil.which("xdg-open") is None:
                raise FileNotFoundError("xdg-open not found on system")
            url = "https://github.com/fastrizwaan/WineCharm/wiki"
            subprocess.run(["xdg-open", url], check=True)
            print(f"Help action triggered: Opened {url}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error opening help URL: {e}")
        
        
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
                # If template doesn't exist, initialize it
                self.initialize_template(self.template, self.on_template_initialized)
                self.process_winezgui_sh_files(suppress_no_scripts_dialog=True) 
            else:
                # Template already exists, set dynamic variables
                self.set_dynamic_variables()
                # Process command-line file immediately if it exists
                if self.command_line_file:
                    print("Template exists. Processing command-line file after UI initialization.")
                    # Use a small delay to ensure UI is ready
                    GLib.timeout_add_seconds(0.5, self.process_cli_file_later, self.command_line_file)
                
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



        

    def process_cli_file_later(self, file_path):
        print("Processing CLI file later: {}".format(file_path))

        if file_path:
            file_extension = Path(file_path).suffix.lower()
            if file_extension in ['.exe', '.msi']:
                print("Valid executable file detected: {}".format(file_path))
                GLib.idle_add(self.show_processing_spinner, "Processing")
                self.process_cli_file_in_thread(file_path)
            elif file_extension in ['.wzt', '.bottle', '.prefix']:
                print("Valid backup file detected: {}".format(file_path))
                GLib.idle_add(self.show_processing_spinner, "Restoring")
                self.restore_prefix_bottle_wzt_tar_zst(file_path)
            else:
                print(f"Invalid file type: {file_extension}. Only .exe or .msi files are allowed.")
                GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Invalid File Type", "Only .exe and .msi files are supported.")
                self.command_line_file = None
                return False

        #self.create_script_list()
        GLib.idle_add(self.create_script_list)
        return False  # Return False to prevent this function from being called again


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





    def is_printable_key(self, keyval):
        """
        Check if the keyval corresponds to a printable character.
        """
        # Convert keyval to unicode character
        char = Gdk.keyval_to_unicode(keyval)
        if char == 0:
            return False
        # Check if the character is printable (alphanumeric, symbols, etc.)
        return chr(char).isprintable() and keyval not in (
            Gdk.KEY_Return, Gdk.KEY_Tab, Gdk.KEY_BackSpace, 
            Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down,
            Gdk.KEY_Control_L, Gdk.KEY_Control_R, Gdk.KEY_Alt_L, 
            Gdk.KEY_Alt_R, Gdk.KEY_Shift_L, Gdk.KEY_Shift_R
        )





    def process_cli_file_in_thread(self, file_path):
        try:
            print(f"Processing CLI file in thread: {file_path}")
            abs_file_path = str(Path(file_path).resolve())
            print(f"Resolved absolute CLI file path: {abs_file_path}")

            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return
            # get runner from settings
            self.load_settings()
            print(self.runner)
            use_runner = str(self.expand_and_resolve_path(self.runner))
            print(use_runner)
            # Perform the heavy processing here
            self.create_yaml_file(abs_file_path, None, runner_override=use_runner)

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
        Finds .charm files efficiently, up to 2 levels deep in both WineCharm and WineZGUI prefix directories.
        Returns a list of Path objects sorted by modification time.
        """
        charm_files = []
        
        # Search in WineCharm's prefixes_dir
        if prefixdir is None or prefixdir == self.prefixes_dir:
            winecharm_dir = Path(self.prefixes_dir).expanduser().resolve()
            if winecharm_dir.exists():
                charm_files.extend(winecharm_dir.glob("*.charm"))
                for subdir in winecharm_dir.iterdir():
                    if subdir.is_dir():
                        charm_files.extend(subdir.glob("*.charm"))

        # Search in WineZGUI's prefixes_dir
        if prefixdir is None or prefixdir == self.winezgui_prefixes_dir:
            winezgui_dir = Path(self.winezgui_prefixes_dir).expanduser().resolve()
            if winezgui_dir.exists():
                charm_files.extend(winezgui_dir.glob("*.charm"))
                for subdir in winezgui_dir.iterdir():
                    if subdir.is_dir():
                        charm_files.extend(subdir.glob("*.charm"))

        # Remove duplicates and sort by modification time (newest first)
        charm_files = list(set(charm_files))
        return sorted(charm_files, key=lambda p: p.stat().st_mtime, reverse=True)


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
        """Create UI rows for scripts efficiently with batch updates, including highlighting."""
        self.flowbox.remove_all()
        
        if not self.script_list:
            return
        
        self.script_ui_data = {}
        
        rows = []
        for script_key, script_data in self.script_list.items():
            row = self.create_script_row(script_key, script_data)
            if row:
                rows.append(row)
                if script_key in self.running_processes:
                    self.update_row_highlight(row, True)
                    self.script_ui_data[script_key]['highlighted'] = True
                    self.script_ui_data[script_key]['is_running'] = True
                else:
                    self.update_row_highlight(row, False)
                    self.script_ui_data[script_key]['highlighted'] = False
                    self.script_ui_data[script_key]['is_running'] = False
        
        for row in rows:
            self.flowbox.append(row)


    def create_script_row(self, script_key, script_data):
        script = Path(str(script_data['script_path'])).expanduser()
        
        # Common title text setup
        title_text = str(script_data.get('progname', script.stem)).replace('_', ' ')
        if script.stem in self.new_scripts:
            title_text = f"<b>{title_text}</b>"

        if self.icon_view:
            # ICON VIEW
            container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            container.add_css_class("rounded-container")
            container.set_size_request(100, 100)
            container.set_hexpand(True)
            #container.set_vexpand(True)
            container.set_halign(Gtk.Align.FILL)
            #container.set_valign(Gtk.Align.FILL)
            # Top: Horizontal box for [options][icon][play]
            top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            top_box.set_hexpand(True)
            top_box.set_vexpand(True)
            #top_box.set_valign(Gtk.Align.CENTER)
            #top_box.set_halign(Gtk.Align.FILL)
            top_box.set_size_request(50,50)
            # Options button (larger, consistent width, initially hidden)
            options_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options")
            options_button.add_css_class("flat")
            options_button.set_size_request(32, -1)  # Consistent width with play button
            options_button.set_hexpand(True)
            options_button.set_margin_start(0)
            options_button.set_margin_end(0)
            options_button.set_margin_top(0)
            options_button.set_margin_bottom(0)
            options_button.set_opacity(0)  # Hidden by default
            options_button.set_sensitive(False)
            #options_button.set_halign(Gtk.Align.FILL)
            #options_button.set_halign(Gtk.Align.FILL)
            top_box.append(options_button)

            # Icon (centered)
            icon = self.load_icon(script, 96, 96, 10)
            icon_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            icon_container.set_hexpand(True)  # Allow icon to expand in the center
            icon_container.set_halign(Gtk.Align.CENTER)
            #icon_container.set_valign(Gtk.Align.CENTER)
            if icon:
                icon_container.add_css_class("rounded-icon")
                icon_image = Gtk.Image.new_from_paintable(icon)
                icon_image.set_pixel_size(96)
                icon_image.set_halign(Gtk.Align.CENTER)
                #icon_image.set_valign(Gtk.Align.CENTER)
                icon_container.append(icon_image)
            else:
                icon_image = Gtk.Image()
                icon_container.append(icon_image)
            icon_container.set_margin_top(0)
            icon_container.set_margin_bottom(1)
            top_box.append(icon_container)

            # Play button (larger, consistent width, initially hidden)
            play_button = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Play")
            play_button.add_css_class("flat")
            #play_button.set_halign(Gtk.Align.FILL)
            play_button.set_size_request(36, -1)  # Consistent width with options button
            play_button.set_opacity(0)  # Hidden by default
            play_button.set_sensitive(False)
            play_button.set_hexpand(True)
            top_box.append(play_button)

            container.append(top_box)

            # Bottom: Label (always visible, ellipsized, color changes with "blue" class)
            label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            label_box.set_halign(Gtk.Align.CENTER)
            #label_box.set_valign(Gtk.Align.FILL)
            main_label = Gtk.Label()
            main_label.set_max_width_chars(18)
            main_label.set_lines(2)
            main_label.set_wrap(True)
            main_label.set_ellipsize(Pango.EllipsizeMode.END)
            #main_label.set_valign(Gtk.Align.FILL)
            main_label.set_markup(title_text)
            main_label.set_tooltip_text(str(script_data.get('progname', script.stem)))
            label_box.append(main_label)


            #label_box.set_size_request(-1, 40)
            label_box.set_opacity(1)  # Always visible
            label_box.set_sensitive(True)  # Always active
            
            container.append(label_box)

            # Store UI data
            self.script_ui_data[script_key] = {
                'row': container,
                'play_button': play_button,
                'options_button': options_button,
                'label_box': label_box,
                'button_box': top_box,
                'label_button_box': None,
                'is_running': False,
                'script_path': script,
                'showing_buttons': False
            }

            # Add click gesture to the icon container
            click = Gtk.GestureClick()
            click.connect("released", lambda gesture, n, x, y: self.toggle_overlay_buttons(script_key))
            icon_container.add_controller(click)

            # Connect button signals
            play_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, btn, container))
            options_button.connect("clicked", lambda btn: self.show_options_for_script(
                self.script_ui_data[script_key], container, script_key))

            return container

        if not self.icon_view:
            # LIST VIEW (unchanged)
            container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            container.add_css_class('rounded-container')

            # Icon (left-aligned)
            script = Path(str(script_data['script_path'])).expanduser()
            title_text = str(script_data.get('progname', script.stem)).replace('_', ' ')
            if script.stem in self.new_scripts:
                title_text = f"<b>{title_text}</b>"
            
            icon = self.load_icon(script, 40, 40, 4)
            if icon:
                icon_container = Gtk.Box()
                icon_container.add_css_class("rounded-icon")
                icon_image = Gtk.Image.new_from_paintable(icon)
                icon_image.set_pixel_size(40)
                icon_image.set_halign(Gtk.Align.CENTER)
                icon_container.append(icon_image)
                icon_container.set_margin_start(6)
            else:
                icon_container = Gtk.Box()
                icon_image = Gtk.Image()
                icon_container.append(icon_image)
                icon_container.set_margin_start(6)
            container.append(icon_container)

            # Container for label or buttons
            label_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            label_button_box.set_hexpand(True)
            label_button_box.set_valign(Gtk.Align.CENTER)

            # Create label_box
            label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            label_box.set_hexpand(True)
            main_label = Gtk.Label()
            main_label.set_hexpand(True)
            main_label.set_halign(Gtk.Align.START)
            main_label.set_wrap(True)
            main_label.set_max_width_chars(25)
            main_label.set_ellipsize(Pango.EllipsizeMode.END)
            main_label.set_markup(title_text)
            label_box.append(main_label)

            # Create button_box
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            button_box.set_hexpand(True)
            box_main_label = Gtk.Label()
            box_main_label.set_markup(title_text)
            box_main_label.set_wrap(True)
            box_main_label.set_max_width_chars(15)
            box_main_label.set_ellipsize(Pango.EllipsizeMode.END)
            
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            
            play_button = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Play")
            play_button.set_size_request(60, -1)
            play_button.set_opacity(1)
            play_button.set_sensitive(True)
            
            options_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options")
            options_button.set_size_request(34, -1)
            options_button.set_opacity(1)
            options_button.set_sensitive(True)
            
            button_box.append(box_main_label)
            button_box.append(spacer)
            button_box.append(play_button)
            button_box.append(options_button)
            button_box.set_margin_end(4)
            button_box.set_size_request(60, 34)
            label_button_box.append(label_box)
            container.append(label_button_box)

            # Store UI data
            self.script_ui_data[script_key] = {
                'row': container,
                'play_button': play_button,
                'options_button': options_button,
                'label_box': label_box,
                'button_box': button_box,
                'label_button_box': label_button_box,
                'is_running': False,
                'script_path': script,
                'showing_buttons': False
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


    def toggle_overlay_buttons(self, script_key):
        # Hide buttons and reset other rows
        for key, ui in self.script_ui_data.items():
            if key != script_key and ui.get('showing_buttons', False):
                if self.icon_view:
                    ui['play_button'].set_opacity(0)
                    ui['play_button'].set_sensitive(False)
                    ui['options_button'].set_opacity(0)
                    ui['options_button'].set_sensitive(False)
                    # Label remains visible, no change needed
                else:
                    ui['label_button_box'].remove(ui['button_box'])
                    ui['label_button_box'].append(ui['label_box'])
                ui['showing_buttons'] = False
                ui['row'].remove_css_class("blue")

        # Toggle the current row
        ui = self.script_ui_data.get(script_key)
        if not ui:
            return

        showing_buttons = ui.get('showing_buttons', False)

        if self.icon_view:
            if showing_buttons:
                # Hide buttons, label stays visible
                ui['play_button'].set_opacity(0)
                ui['play_button'].set_sensitive(False)
                ui['options_button'].set_opacity(0)
                ui['options_button'].set_sensitive(False)
                ui['showing_buttons'] = False
                ui['row'].remove_css_class("blue")
            else:
                # Show buttons, label stays visible
                ui['play_button'].set_opacity(1)
                ui['play_button'].set_sensitive(True)
                ui['options_button'].set_opacity(1)
                ui['options_button'].set_sensitive(True)
                ui['showing_buttons'] = True
                ui['row'].add_css_class("blue")
        else:
            label_button_box = ui['label_button_box']
            if showing_buttons:
                label_button_box.remove(ui['button_box'])
                label_button_box.append(ui['label_box'])
                ui['showing_buttons'] = False
                ui['row'].remove_css_class("blue")
            else:
                label_button_box.remove(ui['label_box'])
                label_button_box.append(ui['button_box'])
                ui['showing_buttons'] = True
                ui['row'].add_css_class("blue")

        # Update play button icon based on running state
        pb = ui['play_button']
        if ui.get("is_running"):
            pb.set_icon_name("media-playback-stop-symbolic")
            pb.set_tooltip_text("Stop")
        else:
            pb.set_icon_name("media-playback-start-symbolic")
            pb.set_tooltip_text("Play")
       
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

        # Handle wineprefix and process linked files if necessary
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

        # Check if process is still running
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

        # Process has ended - reset UI and toggle buttons
        ui_state['is_running'] = False
        if row:
            row.remove_css_class("highlighted")
            # Only remove blue class if buttons aren't showing
            if not ui_state.get('showing_buttons', False):
                row.remove_css_class("blue")

        # Reset play button state
        if play_button:
            self.set_play_stop_button_state(play_button, False)
            play_button.set_icon_name("media-playback-start-symbolic")
            play_button.set_tooltip_text("Play")

        # Handle button visibility based on view type
        if ui_state.get('showing_buttons', False):
            self.toggle_overlay_buttons(script_key)  # Hide buttons and reset to default (label for icon view)
        else:
            # For icon view, ensure buttons stay hidden; for list view, no change needed
            if self.icon_view and play_button and options_button:
                play_button.set_opacity(0)
                play_button.set_sensitive(False)
                options_button.set_opacity(0)
                options_button.set_sensitive(False)
                ui_state['label_box'].set_opacity(1)  # Ensure label is visible
                ui_state['label_box'].set_sensitive(True)
            # List view doesn't need adjustment here since buttons are already hidden by default

        if self.launch_button:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))

        ui_state['is_clicked_row'] = False

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
                    self.window.set_focus(None)


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
            self.window.set_focus(None)



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
            scrolled_window.set_min_content_width(530)
            scrolled_window.set_min_content_height(300)

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
            log_dialog.add_response("copy", "Copy to Clipboard")
            log_dialog.set_default_response("close")
            log_dialog.set_close_response("close")

            # Handle log dialog responses
            def on_log_response(dialog, response):
                self.print_method_name()
                if response == "copy":
                    # Get the text buffer and copy its content to clipboard
                    text_buffer = log_view.get_buffer()
                    start, end = text_buffer.get_bounds()
                    text = text_buffer.get_text(start, end, True)
                    clipboard = self.window.get_clipboard()
                    clipboard.set(text)
                dialog.close()

            # Connect response handler for log dialog
            log_dialog.connect("response", on_log_response)

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





    def extract_yaml_info(self, script_key):
        self.print_method_name()
        script_data = self.script_list.get(script_key)
        if script_data:
            return script_data
        else:
            print(f"Warning: Script with key {script_key} not found in script_list.")
            return {}



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

########################################  delete wineprefix
    def load_icon(self, script, x=24, y=24, radius=3):
        """Load icon for the script with specified dimensions and corner radius."""
        if not hasattr(self, 'icon_cache'):
            self.icon_cache = {}
        
        cache_key = (str(script), x, y)
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]
        
        # USE THIS TO CREATE A HELPER METHOD TO FETCH SCRIPT DATA
        # Find script_data by matching script path
        script_data = next((data for key, data in self.script_list.items() 
                        if Path(str(data['script_path'])).expanduser().resolve() == script), None)
        
        if not script_data:
            print(f"Error: Script data not found for {script}")
            return None
        
        # Get the wineprefix from the script data
        if 'wineprefix' in script_data and script_data['wineprefix']:
            wineprefix = Path(str(script_data['wineprefix'])).expanduser().resolve()
        else:
            # Fallback to the parent directory of script_path if wineprefix is not defined
            wineprefix = script.parent
        # wherever wineprefix = script.parent or similar script.something
        # / USE THIS TO CREATE A HELPER METHOD TO FETCH SCRIPT DATA

        # Get the icon path
        icon_name = script.stem + ".png"
        icon_path = wineprefix / icon_name
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
        #max_children_per_line = 8 if self.icon_view else 4
        #self.flowbox.set_max_children_per_line(max_children_per_line)
        # Recreate the script list with the new view
        self.create_script_list()
        GLib.idle_add(self.save_settings)

############# IMPORT Wine Directory

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
        Load .charm files into self.script_list efficiently using a background thread.
        Handles missing keys, updates files if necessary, and uses sha256sum as the key.

        Args:
            prefixdir (str or Path, optional): The directory to search for .charm files.
                                            Defaults to None, which searches both self.prefixes_dir
                                            and self.winezgui_prefixes_dir.
        """
        def load_in_background():
            temp_script_list = {}
            charm_files = list(self.find_charm_files(prefixdir))

            for charm_file in charm_files:
                if self.stop_processing:
                    return
                try:
                    with open(charm_file, 'r', encoding='utf-8') as f:
                        script_data = yaml.safe_load(f)

                    if not isinstance(script_data, dict):
                        print(f"Warning: Invalid format in {charm_file}, skipping.")
                        continue

                    updated = False
                    required_keys = ['exe_file', 'script_path', 'wineprefix', 'sha256sum']

                    if 'script_path' not in script_data:
                        script_data['script_path'] = self.replace_home_with_tilde_in_path(str(charm_file))
                        updated = True
                        print(f"Warning: script_path missing in {charm_file}. Added default value.")

                    if 'wineprefix' not in script_data or not script_data['wineprefix']:
                        wineprefix = str(Path(charm_file).parent)
                        script_data['wineprefix'] = self.replace_home_with_tilde_in_path(wineprefix)
                        updated = True
                        print(f"Warning: wineprefix missing in {charm_file}. Set to {wineprefix}.")

                    for key in required_keys:
                        if isinstance(script_data.get(key), str) and script_data[key].startswith(os.getenv("HOME")):
                            new_value = self.replace_home_with_tilde_in_path(script_data[key])
                            if new_value != script_data[key]:
                                script_data[key] = new_value
                                updated = True

                    should_generate_hash = False
                    if 'sha256sum' not in script_data or script_data['sha256sum'] is None:
                        should_generate_hash = True

                    if should_generate_hash and 'exe_file' in script_data and script_data['exe_file']:
                        exe_path = Path(str(script_data['exe_file'])).expanduser().resolve()
                        if os.path.exists(exe_path):
                            sha256_hash = hashlib.sha256()
                            with open(exe_path, "rb") as f:
                                for byte_block in iter(lambda: f.read(4096), b""):
                                    sha256_hash.update(byte_block)
                            script_data['sha256sum'] = sha256_hash.hexdigest()
                            updated = True
                            print(f"Generated sha256sum from exe_file in {charm_file}")
                        else:
                            print(f"Warning: exe_file not found, not updating sha256sum for {charm_file}")

                    if updated:
                        with self.file_lock:
                            with open(charm_file, 'w', encoding='utf-8') as f:
                                yaml.dump(script_data, f, default_style="'", default_flow_style=False, width=10000)
                        print(f"Updated script file: {charm_file}")

                    script_data['mtime'] = os.path.getmtime(charm_file)

                    script_key = script_data['sha256sum']
                    temp_script_list[script_key] = script_data

                except yaml.YAMLError as yaml_err:
                    print(f"YAML error in {charm_file}: {yaml_err}")
                except Exception as e:
                    print(f"Error loading {charm_file}: {e}")
                    continue

            GLib.idle_add(self.update_script_list, temp_script_list, prefixdir is None)

        threading.Thread(target=load_in_background, daemon=True).start()

    def update_script_list(self, temp_script_list, clear_existing=True):
        """Update self.script_list and refresh UI in the main thread."""
        self.print_method_name()
        if clear_existing:
            self.script_list = temp_script_list  # Replace the existing list
        else:
            self.script_list = {**temp_script_list, **self.script_list}  # Merge with existing list
        print(f"Loaded {len(self.script_list)} scripts.")
        self.create_script_list()  # Refresh UI after loading

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
        self.dir_list.add_css_class("boxed-list") 
        
        # Load saved directories from .charm file
        script_data = self.extract_yaml_info(script_key)
        saved_dirs = script_data.get('save_dirs', [])
        
        # Track if any valid directories are added
        added_any = False
        if saved_dirs:
            for saved_dir in saved_dirs:
                saved_path = Path(saved_dir).expanduser().resolve()
                # Validate saved directory
                valid, _unused = self.is_valid_directory(saved_path, wineprefix)
                if valid:
                    row = Gtk.ListBoxRow()
                    check = Gtk.CheckButton(label=str(saved_path))
                    check.set_active(True)
                    row.set_child(check)
                    self.dir_list.append(row)
                    added_any = True
        
        # If no valid directories were added, add the default
        if not added_any:
            default_row = Gtk.ListBoxRow()
            default_check = Gtk.CheckButton(label=str(default_dir))
            default_check.set_active(True)
            default_row.set_child(default_check)
            self.dir_list.append(default_row)
        
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







    # Implement placeholders for each setting's callback function

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

######################################################### Initiazlie template and import directory imrpovement






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



##################################################################################### 

        

########################## fix default runner to handle arch difference



    def revert_open_button(self):
        self.print_method_name()
        """
        Cleanup after template restore completion.
        """
        self.hide_processing_spinner()
        self.reconnect_open_button()
        self.show_options_for_settings()
        print("Template created successfully")
    




###################### 0.95




###############

















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
        elif file_extension in ['.exe', '.msi', '.bottle', '.prefix', '.wzt', '.EXE', '.MSI', '.BOTTLE', '.PREFIX', '.WZT']:
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
            if file_extension in ['.bottle', '.prefix', '.wzt', '.WZT', '.BOTTLE', '.PREFIX']:
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
    if args.file and file_extension in ['.bottle', '.prefix', '.wzt', '.WZT', '.BOTTLE', '.PREFIX']:
        app.command_line_file = args.file
    app.start_socket_server()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
