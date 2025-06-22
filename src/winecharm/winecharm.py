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
    from winecharm import (
        ui,
        settings,
        template_manager,
        runner_manager,
        single_prefix,
        restore,
        backup,
        winezgui_importer,
        import_wine_dir,
        import_game_dir,
        create_script,
        check_required_programs,
        set_wine_arch,
        script_options,
        save_load_users_dir
    )
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
    import check_required_programs
    import set_wine_arch
    import script_options
    import save_load_users_dir

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
        self.version = "0.99.4"
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
            check_required_programs: [
                'check_required_programs',
                'show_missing_programs_dialog',
            ],
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
                'create_script_list',
                'create_script_row',
                'toggle_overlay_buttons',
                'show_buttons',
                'hide_buttons',
                'on_script_row_clicked',
                'set_play_stop_button_state',
                'update_row_highlight',
                'replace_open_button_with_launch',
                'replace_launch_button',
                'on_view_toggle_button_clicked',
                'show_processing_spinner',
                'hide_processing_spinner',
                'disable_open_button',
                'enable_open_button',
                'set_open_button_icon_visible',
                'set_open_button_label',
                'show_initializing_step',
                'mark_step_as_done',
                'on_cancel_button_clicked',
                'show_info_dialog',
                'update_ui_for_running_script_on_startup',
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
                'revert_open_button',
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
            set_wine_arch: [
                'set_wine_arch',
            ],
            script_options: [
                'show_options_for_script',
                'show_log_file',
                'open_terminal',
                'open_filemanager',
                'open_script_file',
                'run_other_exe',
                'on_run_other_exe_response',
                'set_environment_variables',
                'on_env_vars_dialog_response',
                'validate_environment_variables',
                'rename_prefix_directory',
                'show_rename_dialog',
                'on_rename_prefix_dialog_response',
                'update_charm_files_with_new_prefix',
                'update_script_data_references',
                'wine_config',
                'wine_registry_editor',
                'show_script_about',
                'get_directory_size_for_about',
                'add_desktop_shortcut',
                'on_add_desktop_shortcut_response',
                'remove_desktop_shortcut',
                'on_remove_desktop_shortcut_response',
                'show_delete_wineprefix_confirmation',
                'on_delete_wineprefix_confirmation_response',
                'show_delete_shortcut_confirmation',
                'on_delete_shortcuts_response',
                'get_script_key_from_shortcut',
                'show_wine_arguments_entry',
                'on_wine_arguments_dialog_response',
                'show_rename_shortcut_entry',
                'on_show_rename_shortcut_dialog_response',
                'rename_script_and_icon',
                'show_change_icon_dialog',
                'on_change_icon_response',
                'clear_icon_cache_for_script',
                'change_icon',
                'extract_and_change_icon',
                'reset_shortcut_confirmation',
                'on_reset_shortcut_confirmation_response',
                'reset_shortcut',
                'callback_wrapper',
                'update_execute_button_icon',
                'run_winetricks_script',
            ],
            save_load_users_dir: [
                'show_save_user_dirs_dialog',
                'on_directory_dialog_response',
                'on_add_directory',
                'show_save_file_dialog',
                'on_save_user_dirs_dialog_response',
                'save_user_dirs',
                'show_load_user_dirs_dialog',
                'on_load_user_dirs_dialog_response',
                'confirm_restore',
                'load_user_dirs',
                'is_valid_directory',
                'show_error_dialog',

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



        if not self.template:
            self.template = getattr(self, f'default_template_{self.arch}')
            self.template = self.expand_and_resolve_path(self.template)

        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        else:
            if not self.template.exists():
                # If template doesn't exist, initialize it
                self.initialize_template(self.template, self.on_template_initialized, new=True)
            else:
                # Template already exists, set dynamic variables
                self.set_dynamic_variables()
                # Process command-line file immediately if it exists
                if self.command_line_file:
                    print("Template exists. Processing command-line file after UI initialization.")
                    # Use a small delay to ensure UI is ready
                    GLib.timeout_add_seconds(0.5, self.process_cli_file_later, self.command_line_file)
                
                
        # After loading scripts and building the UI, check for running processes
        self.load_script_list()
        self.create_script_list()        
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

       


            





    def extract_yaml_info(self, script_key):
        self.print_method_name()
        script_data = self.script_list.get(script_key)
        if script_data:
            return script_data
        else:
            print(f"Warning: Script with key {script_key} not found in script_list.")
            return {}





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
