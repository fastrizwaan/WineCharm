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

from datetime import datetime

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
        self.version = "0.94"
        
        # Paths and directories
        self.winecharmdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm")).resolve()
        self.prefixes_dir = self.winecharmdir / "Prefixes"
        self.templates_dir = self.winecharmdir / "Templates"
        self.runners_dir = self.winecharmdir / "Runners"
        self.default_template = self.templates_dir / "WineCharm-win64"
        
        self.applicationsdir = Path(os.path.expanduser("~/.local/share/applications")).resolve()
        self.tempdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/tmp")).resolve()
        self.iconsdir = Path(os.path.expanduser("~/.local/share/icons")).resolve()
        self.do_not_kill = "bin/winecharm"
        
        self.SOCKET_FILE = self.winecharmdir / "winecharm_socket"

        # Variables that need to be dynamically updated
        self.runner = ""  # which wine
        self.wine_version = ""  # runner --version
        self.template = ""  # default: WineCharm-win64, if not found in settings.yaml
        self.arch = ""  # default: win
                
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
        # Register the SIGINT signal handler
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.script_buttons = {}
        self.current_clicked_row = None  # Initialize current clicked row
        self.hamburger_actions = [
            ("🛠️ Settings...", self.on_settings_clicked),
            ("☠️ Kill all...", self.on_kill_all_clicked),
            ("🍾 Restore...", self.restore_from_backup),
            ("📂 Import Wine Directory", self.on_import_wine_directory_clicked),
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
        GLib.timeout_add_seconds(0.5, self.create_script_list)

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
        # Clear or initialize the script list
        self.script_list = {}
        self.load_script_list()
        self.create_script_list()
        #self.check_running_processes_and_update_buttons()
        
        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        else:
            if not self.default_template.exists():
                self.initialize_template(self.default_template, self.on_template_initialized)
            else:
                self.set_dynamic_variables()
                # Process the command-line file if the template already exists
                if self.command_line_file:
                    print("Template exists. Processing command-line file after UI initialization.")
                    self.process_cli_file_later(self.command_line_file)
        # After loading scripts and building the UI, check for running processes
        self.check_running_processes_on_startup()
        
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
        self.create_required_directories()
        self.initializing_template = True
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)

        self.spinner = Gtk.Spinner()
        self.spinner.start()
        self.open_button_box.append(self.spinner)

        self.set_open_button_label("Initializing...")
        self.set_open_button_icon_visible(False)  # Hide the open-folder icon
        self.search_button.set_sensitive(False)  # Disable the search button
        self.view_toggle_button.set_sensitive(False)
        self.ensure_directory_exists(template_dir)

        steps = [
            ("Initializing wineprefix", f"WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
            ("Replace symbolic links with directories", lambda: self.remove_symlinks_and_create_directories(template_dir)),
            ("Installing corefonts",    f"WINEPREFIX='{template_dir}' winetricks -q corefonts"),
            ("Installing openal",       f"WINEPREFIX='{template_dir}' winetricks -q openal"),
            ("Installing vkd3d",        f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
            ("Installing dxvk",         f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
            #("Installing vcrun2005",    f"WINEPREFIX='{template_dir}' winetricks -q vcrun2005"),
            #("Installing vcrun2019",    f"WINEPREFIX='{template_dir}' winetricks -q vcrun2019"),
        ]

        def initialize():
            for step_text, command in steps:
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    if callable(command):
                        # If the command is a callable, invoke it directly
                        command()
                    else:
                        # Run the command in the shell
                        subprocess.run(command, shell=True, check=True)
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except subprocess.CalledProcessError as e:
                    print(f"Error initializing template: {e}")
                    break
            GLib.idle_add(callback)

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


    def process_cli_file_later(self, file_path):
        # Use GLib.idle_add to ensure this runs after the main loop starts
        GLib.idle_add(self.show_processing_spinner)
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
        button = Gtk.Button()
        button.set_size_request(390, 36)
        button.add_css_class("flat")
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        checkbox = Gtk.CheckButton()
        label = Gtk.Label(label=step_text)
        label.set_xalign(0)
        hbox.append(checkbox)
        hbox.append(label)
        button.set_child(hbox)
        button.checkbox = checkbox
        button.label = label
        self.flowbox.append(button)
        button.set_visible(True)
        self.flowbox.queue_draw()  # Ensure the flowbox redraws itself to show the new button

    def mark_step_as_done(self, step_text):
        """
        Mark the step as done by updating the UI with a checkmark.
        """
        child = self.flowbox.get_first_child()
        while child:
            button = child.get_child()
            if isinstance(button, Gtk.Button):  # Ensure you're working with a Gtk.Button
                label = button.get_child().get_last_child()  # Access the label inside the button
                if isinstance(label, Gtk.Label) and label.get_text() == step_text:
                    checkbox = button.get_first_child().get_first_child()  # Access the checkbox inside the button
                    if isinstance(checkbox, Gtk.CheckButton):
                        checkbox.set_active(True)  # Mark the checkbox as checked
                    button.add_css_class("normal-font")  # Optionally update the style
                    break
            child = child.get_next_sibling()

        self.flowbox.queue_draw()  # Ensure the flowbox redraws itself to update the checkbox status

    def check_required_programs(self):
        if shutil.which("flatpak-spawn"):
            return []

        required_programs = [
            'exiftool',
            'wine',
            'winetricks',
            'wrestool',
            'icotool',
            'pgrep',
            'gnome-terminal',
            'xdg-open'
        ]
        missing_programs = [prog for prog in required_programs if not shutil.which(prog)]
        return missing_programs

    def show_missing_programs_dialog(self, missing_programs):
        dialog = Gtk.Dialog(transient_for=self.window, modal=True)
        dialog.set_title("Missing Programs")
        dialog.set_default_size(300, 200)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        dialog.set_child(box)

        label = Gtk.Label(label="The following required programs are missing:")
        box.append(label)

        for prog in missing_programs:
            prog_label = Gtk.Label(label=prog)
            prog_label.set_halign(Gtk.Align.START)
            box.append(prog_label)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda w: dialog.close())
        box.append(close_button)

        dialog.present()
        
    def set_dynamic_variables(self):
        # Set instance attributes instead of globals
        self.runner = subprocess.getoutput('which wine')
        self.wine_version = subprocess.getoutput(f"{self.runner} --version")
        
        # Check if settings.yml exists and set the template and arch accordingly
        settings_file = self.winecharmdir / "settings.yml"
        if settings_file.exists():
            settings = self.load_settings()  # Assuming load_settings() returns a dictionary
            self.template = settings.get('template', "WineCharm-win64")
            self.arch = settings.get('arch', "win64")
        else:
            self.template = "WineCharm-win64"
            self.arch = "win64"


    def load_settings(self):
        settings_file_path = self.winecharmdir / "settings.yml"
        if settings_file_path.exists():
            with open(settings_file_path, 'r') as settings_file:
                return yaml.safe_load(settings_file)
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
        self.window.set_default_size(420, 560)
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

        self.menu_button.set_menu_model(menu)

        # Add other existing options in the hamburger menu
        for label, action in self.hamburger_actions:
            menu.append(label, f"win.{action.__name__}")
            action_item = Gio.SimpleAction.new(action.__name__, None)
            action_item.connect("activate", action)
            self.window.add_action(action_item)

        # Create actions for sorting options
        self.create_sort_actions()

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

        
    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.search_button.set_active(False)

    def on_search_button_clicked(self, button):
        if self.search_active:
            self.vbox.remove(self.search_entry_box)
            self.vbox.prepend(self.open_button)
            self.search_active = False
            self.filter_script_list("")  # Reset the list to show all scripts
        else:
            self.vbox.remove(self.open_button)
            self.vbox.prepend(self.search_entry_box)
            self.search_entry.grab_focus()
            self.search_active = True

    def on_search_entry_activated(self, entry):
        search_term = entry.get_text().lower()
        self.filter_script_list(search_term)

    def on_search_entry_changed(self, entry):
        search_term = entry.get_text().lower()
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
                self.show_processing_spinner("Processing...")

                # Start a background thread to process the file
                threading.Thread(target=self.process_cli_file_in_thread, args=(file_path,)).start()

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
        #print("Back button clicked")


        # Reset the header bar title and visibility of buttons
        self.headerbar.set_title_widget(self.title_box)
        self.menu_button.set_visible(True)
        self.search_button.set_visible(True)
        self.view_toggle_button.set_visible(True)
        self.back_button.set_visible(False)

        # Remove the "Launch" button if it exists
        if hasattr(self, 'launch_button') and self.launch_button.get_parent():
            self.vbox.remove(self.launch_button)
            self.launch_button = None

        # Restore the "Open" button
        if not self.open_button.get_parent():
            self.vbox.prepend(self.open_button)
        self.open_button.set_visible(True)

        # Ensure the correct child is set in the main_frame
        if self.main_frame.get_child() != self.scrolled:
            self.main_frame.set_child(self.scrolled)

        # Restore the script list
        self.create_script_list()
        #self.check_running_processes_and_update_buttons()
        
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
        self.launch_button.set_size_request(390, 36)

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
            button.set_size_request(390, 36)
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
        play_button.set_visible(False)  # Initially hidden
        buttons_box.append(play_button)

        # Options button
        options_button = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        options_button.set_tooltip_text("Options")
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
            script = process_info.get("script")
            exe_name = process_info.get("exe_name")
            exe_parent_name = process_info.get("exe_parent_name")
            unique_id = process_info.get("unique_id")
            if script and script.exists():
                wineprefix = script.parent
                print(f"Processing wineprefix: {wineprefix}")
                if wineprefix:
                    self.create_scripts_for_lnk_files(wineprefix)

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

        # Call check_running_processes_on_startup to update UI
        self.check_running_processes_on_startup()

    def launch_script(self, script_key, play_stop_button, row):
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
        #print("*"*100)
        #print(wineprefix)
        runner = script_data.get('runner', 'wine')
        if runner:
            runner = Path(runner).expanduser().resolve()
            runner_dir = str(runner.parent.expanduser().resolve())
            path_env = f'export PATH="{runner_dir}:$PATH"'
        else:
            runner = "wine"
            runner_dir = ""  # Or set a specific default if required
            path_env = ""

        #Logging stderr to {log_file_path}")
        log_file_path = Path(wineprefix) / f"{script.stem}.log"
            
        # shlex quote for bash
        exe_parent = shlex.quote(str(exe_file.parent.resolve()))
        wineprefix = shlex.quote(str(wineprefix))
        #print("="*100)
        #print(wineprefix)
        #print(wineprefix.strip("'"))
        runner = shlex.quote(str(runner))
        runner_dir = shlex.quote(str(runner_dir))
        exe_name = shlex.quote(str(exe_name))
        
        if self.debug:
            print("--------------------- launch_script_data ------------------")
            print(f"exe_file = {exe_file}\nscript = {script}\nprogname = {progname}")
            print(f"script_args = {script_args}\nscript_key = {script_key}")
            print(f"env_vars = {env_vars}\nwine_debug = {wine_debug}")
            print(f"exe_name = {exe_name}\nwineprefix = {wineprefix}")
            print(f"runner = {runner}\nrunner_dir = {runner_dir}")
            print(f"log_file_path = {log_file_path}")
            print("---------------------/launch_script_data ------------------")

        # Check if any process with the same wineprefix is already running
        self.launching_another_from_same_prefix = False
        wineprefix_process_count = 0
       
        for process_info in self.running_processes.values():
            if Path(process_info['wineprefix']) == wineprefix:
                wineprefix_process_count += 1

        # Set self.launching_another_from_same_prefix if >1 process shares the wineprefix.
        if wineprefix_process_count > 1:
            self.launching_another_from_same_prefix = True
        else:
            self.launching_another_from_same_prefix = False

        # Will be set in Settings
        if wine_debug == "disabled":
            wine_debug = "WINEDEBUG=-all DXVK_LOG_LEVEL=none"

        # If exe_file not found then show info
        if not Path(exe_file).exists():
            GLib.idle_add(play_stop_button.set_child, Gtk.Image.new_from_icon_name("action-unavailable-symbolic"))
            GLib.idle_add(play_stop_button.set_tooltip_text, "Exe Not Found")
            play_stop_button.add_css_class("red")
            GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Exe Not found", str(Path(exe_file)))
            return
        else:
            play_stop_button.remove_css_class("red")

        # Command to launch
        if path_env:
            command = (f"{path_env}; cd {exe_parent} && "
                       f"{wine_debug} {env_vars} WINEPREFIX={wineprefix} "
                       f"{runner} {exe_name} {script_args}" )
        else:
            command = (f"cd {exe_parent} && "
                       f"{wine_debug} {env_vars} WINEPREFIX={wineprefix} "
                       f"{runner} {exe_name} {script_args}" )
        if self.debug:
            print(f"----------------------Launch Command--------------------")
            print(f"{command}")
            print(f"--------------------------------------------------------")
            print("")
            
        try:
            with open(log_file_path, 'w') as log_file:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    preexec_fn=os.setsid,
                    stdout=subprocess.DEVNULL,
                    stderr=log_file,
                    env=env
                )

                self.running_processes[script_key] = {
                    "process": process,
                    "unique_id": unique_id,
                    "pgid": os.getpgid(process.pid),  # Get the process group ID
                    "row": row,
                    "script": script,
                    "exe_file": exe_file,
                    "exe_name": exe_name.strip("'"),
                    "runner": runner.strip("'"),
                    "wineprefix": wineprefix.strip("'")
                }

                print("."*100)
                print(f"""
                process = {process}
                unique_id = {unique_id}
                pgid = {os.getpgid(process.pid)}
                row = {row}
                script = {script}
                exe_file = {exe_file}
                exe_name = {exe_name}
                runner = {runner}
                wineprefix = {wineprefix}
                """)
                # Update UI
                self.set_play_stop_button_state(play_stop_button, True)
                self.update_row_highlight(row, True)
                play_stop_button.set_tooltip_text("Stop")
                ui_state = self.script_ui_data.get(script_key)
                if ui_state:
                    ui_state['is_running'] = True

                # Start a thread to monitor the process
                threading.Thread(target=self.monitor_process, args=(script_key,), daemon=True).start()
    
                # Call get_child_pid_async after a delay to ensure that child processes have time to start
                GLib.timeout_add_seconds(5, self.get_child_pid_async, script_key)

        except Exception as e:
            print(f"Error launching script: {e}")
            
    def monitor_process(self, script_key):
        process_info = self.running_processes.get(script_key)
        if not process_info:
            return

        process = process_info.get("process")
        if not process:
            return

        # Wait for the process to complete
        process.wait()

        # Process has ended; update the UI in the main thread
        GLib.idle_add(self.process_ended, script_key)


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
        exe_name = script = process_info.get('exe_name')

        runner = process_info.get('runner', 'wine')
        

        if runner:
            runner = Path(runner).expanduser().resolve()
            runner_dir = str(runner.parent.expanduser().resolve())
            path_env = f'export PATH="{runner_dir}:$PATH"'
        else:
            runner = "wine"
            runner_dir = ""  # Or set a specific default if required
            path_env = ""
        
        
        exe_name = shlex.quote(str(exe_name))
        runner_dir = shlex.quote(str(runner_dir))

        print("="*100)
        print(f"runner = {runner}")
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
                        
                    if self.debug:    
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

        unique_id = process_info.get("unique_id")
        wineprefix = process_info.get("wineprefix")
        runner = process_info.get("runner") or "wine"  # Ensure runner is not None
        runner_dir = Path(runner).expanduser().resolve().parent
        pids = process_info.get("pids", [])  # Get the list of PIDs

        if unique_id:
            # Existing logic to terminate processes using unique_id
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
            # Terminate all PIDs
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f"Successfully sent SIGTERM to process with PID {pid}")
                except Exception as e:
                    print(f"Error sending SIGTERM to process with PID {pid}: {e}")

            # Wait for a short time to see if the processes terminate
            #time.sleep(1)
            for pid in pids:
                if psutil.pid_exists(pid):
                    # If the process is still running, send SIGKILL
                    try:
                        os.kill(pid, signal.SIGKILL)
                        print(f"Successfully sent SIGKILL to process with PID {pid}")
                    except Exception as e:
                        print(f"Error sending SIGKILL to process with PID {pid}: {e}")
        else:
            print(f"No PIDs found to terminate for script_key: {script_key}")
            # Fallback to wineserver -k to terminate all processes in the Wine prefix
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

        # Remove the script from running_processes
        self.running_processes.pop(script_key, None)

        # Update the UI
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
        if prefix_dir is None:
            prefix_dir = self.prefixes_dir / f"{exe_no_space}-{sha256sum}"
            if not prefix_dir.exists():
                if self.default_template.exists():
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
            'exe_file': str(exe_file).replace(str(Path.home()), "~"),
            'script_path': str(yaml_file_path).replace(str(Path.home()), "~"), 
            'wineprefix': str(prefix_dir).replace(str(Path.home()), "~"),
            'progname': progname,
            'args': "",
            'sha256sum': sha256_hash.hexdigest(),
            'runner': "",
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
            for file in files:
                file_path = Path(root) / file

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


    def show_info_dialog(self, title, message):
        if self.window is None:
            print(f"Cannot show dialog: window is not available.")
            return

        # Create an instance of AdwAlertDialog
        dialog = Adw.AlertDialog()
        
        # Set the title and message for the alert dialog
        dialog.set_heading(title)
        dialog.set_body(message)

        # Add an "OK" button as a response
        dialog.add_response("ok", "OK")

        # Set the default response and close response to "ok"
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")

        # Connect the response signal to destroy the dialog
        dialog.connect("response", lambda d, r: d.destroy())

        # Present the dialog attached to the parent window
        dialog.present(self.window)
        
    def create_backup_archive(self, wineprefix, backup_path):
        # Get the current username from the environment
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")

        # Escape the wineprefix name for the transform pattern to handle special characters
        #escaped_prefix_name = re.escape(wineprefix.name)

        # Prepare the transform pattern to rename the user's directory to '%USERNAME%'
        # The pattern must be expanded to include anything under the user's folder
        #transform_pattern = f"s|{escaped_prefix_name}/drive_c/users/{current_username}|{escaped_prefix_name}/drive_c/users/%USERNAME%|g"

        # Prepare the tar command with --transform option
        tar_command = [
            'tar',
            '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
            '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",  # Rename the directory and its contents
            '-cf', backup_path,
            '-C', str(wineprefix.parent),
            wineprefix.name
        ]

        print(f"Running backup command: {' '.join(tar_command)}")

        # Execute the tar command
        result = subprocess.run(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            raise Exception(f"Backup failed: {result.stderr}")

        print(f"Backup archive created at {backup_path}")


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


    def backup_prefix(self, script, script_key, backup_path):
        """
        Backs up the Wine prefix in a stepwise manner, indicating progress via spinner and label updates.
        """
        wineprefix = Path(script).parent

        # Step 1: Disconnect the UI elements and initialize the spinner
        self.disconnect_open_button()
        self.set_open_button_label("Exporting...")
        self.show_processing_spinner("Preparing backup...")

        # Get the user's home directory to replace with `~`
        usershome = os.path.expanduser('~')
        find_replace_pairs = {usershome: '~'}
        user = os.getenv('USER')
        #home_to_userhome = {user: "%USERNAME%"}
        #userhome_to_home = {"%USERNAME%": user}
        # Step 2: Define the steps for the backup process
        def perform_backup_steps():
            steps = [
                (f"Replace \"{usershome}\" with '~' in script files", lambda: self.replace_strings_in_specific_files(wineprefix, find_replace_pairs)),
                ("Reverting user-specific .reg changes", lambda: self.reverse_process_reg_files(wineprefix)),
                ("Creating backup archive", lambda: self.create_backup_archive(wineprefix, backup_path)),
                ("Re-applying user-specific .reg changes", lambda: self.process_reg_files(wineprefix)),
            ]
            
            for step_text, step_func in steps:
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    # Execute the step
                    step_func()
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    print(f"Error during step '{step_text}': {e}")
                    GLib.idle_add(self.show_info_dialog, "Backup Failed", f"Error during '{step_text}': {str(e)}")
                    break

            # Step 3: Once all steps are completed, reset the UI
            GLib.idle_add(self.on_backup_prefix_completed, script_key, backup_path)

        # Step 4: Run the backup steps in a separate thread to keep the UI responsive
        threading.Thread(target=perform_backup_steps).start()

    def on_backup_prefix_completed(self, script_key,backup_path):
        """
        Called when the backup process is complete. Updates the UI accordingly.
        """
        # Reset the button label and remove the spinner
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.reconnect_open_button()
        self.hide_processing_spinner()
        
        # Notify the user that the backup is complete
        self.show_info_dialog("Backup Complete", f"Backup saved to {backup_path}")
        print("Backup process completed successfully.")
       # GLib.idle_add(self.show_options_for_script, self.script_data, self.selected_row, self.current_script_key)
        # Iterate over all script buttons and update the UI based on `is_clicked_row`
        for key, data in self.script_ui_data.items():
            row_button = data['row']
            row_play_button = data['play_button']
            row_options_button = data['options_button']
        self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)

    def show_backup_prefix_dialog(self, script, script_key, button):
        # Step 1: Suggest the backup file name
        default_backup_name = f"{script.stem} prefix backup.tar.zst"

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


    def restore_from_backup(self, action=None, param=None):
        # Step 1: Create required directories (if needed)
        self.create_required_directories()

        # Step 2: Create a new Gtk.FileDialog instance
        file_dialog = Gtk.FileDialog.new()

        # Step 3: Create file filters for .tar.zst and .wzt files
        file_filter_combined = Gtk.FileFilter()
        file_filter_combined.set_name("Backup Files (*.tar.zst, *.wzt)")
        file_filter_combined.add_pattern("*.tar.zst")
        file_filter_combined.add_pattern("*.wzt")

        file_filter_tar = Gtk.FileFilter()
        file_filter_tar.set_name("Compressed Backup Files (*.tar.zst)")
        file_filter_tar.add_pattern("*.tar.zst")

        file_filter_wzt = Gtk.FileFilter()
        file_filter_wzt.set_name("Winezgui Backup Files (*.wzt)")
        file_filter_wzt.add_pattern("*.wzt")

        # Step 4: Set the filters on the dialog
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        
        # Add the combined filter as the default option
        filter_model.append(file_filter_combined)

        # Add individual filters for .tar.zst and .wzt files
        filter_model.append(file_filter_tar)
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

                # Check the file extension to determine whether it's a .tar.zst or .wzt file
                if file_path.endswith(".tar.zst"):
                    self.restore_tar_zst_backup(file_path)
                elif file_path.endswith(".wzt"):
                    self.restore_wzt_backup(file_path)

        except GLib.Error as e:
            # Handle errors, such as dialog cancellation
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")

    def restore_tar_zst_backup(self, file_path):
        """
        Restore from a .tar.zst backup file.
        """
        # Clear the flowbox and show a progress spinner
        GLib.idle_add(self.flowbox.remove_all)
        self.show_processing_spinner(f"Restoring from {Path(file_path).name}")
        self.disconnect_open_button()

        # Start a thread to restore from the backup (process the file in steps)
        self.perform_restore_steps(file_path)

    def restore_wzt_backup(self, file_path):
        """
        Restore from a .wzt backup file in steps, showing progress for each step.
        """
        # Clear the flowbox and show a progress spinner
        GLib.idle_add(self.flowbox.remove_all)
        self.show_processing_spinner(f"Extracting WZT from {Path(file_path).name}")
        self.disconnect_open_button()

        # Start the WZT extraction process in steps
        self.perform_wzt_restore_steps(file_path)


    def perform_wzt_restore_steps(self, wzt_file):
        """
        Perform the WZT extraction process in steps, showing progress for each.
        """
        steps = [
            ("Checking Disk Space", lambda: self.check_disk_space_and_show_step(wzt_file)),
            ("Extracting WZT Backup File", lambda: self.extract_wzt_file(wzt_file)),
            ("Performing Replacements", lambda: self.perform_replacements(self.extract_prefix_dir(wzt_file))),
            ("Processing Shell Files", lambda: self.process_sh_files(self.extract_prefix_dir(wzt_file))),
            ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(wzt_file))),
            ("Renaming and merging user directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(wzt_file))),
            ("Finding and Saving LNK Files", lambda: self.find_and_save_lnk_files(self.extract_prefix_dir(wzt_file))),
        ]

        def perform_steps():
            for step_text, step_func in steps:
                # Queue the UI update safely in the main thread
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    # Perform the restore step and check the result
                    result = step_func()
                    if result is False:
                        # Stop further steps if a step fails
                        print(f"Step '{step_text}' failed, aborting restore process.")
                        break

                    # Mark the step as done in the main thread
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    print(f"Error during step '{step_text}': {e}")
                    GLib.idle_add(self.show_info_dialog, "Error", f"Failed during step '{step_text}': {str(e)}")
                    break

            # Once complete, update the UI in the main thread
            GLib.idle_add(self.on_restore_completed)

        # Start the restore process in a new thread
        threading.Thread(target=perform_steps).start()



    def extract_wzt_file(self, wzt_file):
        """
        Extract the .wzt file to the Wine prefixes directory and process the files.
        """
        extract_dir = Path(self.prefixes_dir)                           
        extract_dir.mkdir(parents=True, exist_ok=True)
        user = os.getenv('USER')
        
        try:
            # Extract the first directory (prefix) inside the WZT archive
            wzt_prefix = subprocess.check_output(
                ["bash", "-c", f"tar -tf '{wzt_file}' | grep '/$' | head -n1 | cut -f1 -d '/'"]
            ).decode('utf-8').strip()
            
            if not wzt_prefix:
                raise Exception("Unable to determine WZT prefix directory")

            extracted_wzt_prefix = extract_dir / wzt_prefix
            
            # Extract the entire WZT archive into the correct prefix directory
            subprocess.run(
                ["tar", "-xvf", wzt_file, "-C", extract_dir, "--transform", f"s|XOUSERXO|{user}|g"],
                check=True
            )
            
            # Perform replacements, process .sh files, and find .lnk files
            GLib.idle_add(self.show_initializing_step, f"Performing user related replacements...")
            self.perform_replacements(extracted_wzt_prefix)
            GLib.idle_add(self.mark_step_as_done, f"Performing user related replacements...")

            GLib.idle_add(self.show_initializing_step, f"Processing WineZGUI script files...")
            self.process_sh_files(extracted_wzt_prefix)
            GLib.idle_add(self.mark_step_as_done, f"Processing WineZGUI script files...")
            
            GLib.idle_add(self.show_initializing_step, f"Search lnk files and append to found list...")
            self.find_and_save_lnk_files(extracted_wzt_prefix)
            GLib.idle_add(self.mark_step_as_done, f"Search lnk files and append to found list...")
            
            # Mark extraction as complete
            self.on_extraction_complete(success=True, message=f"Extracted all files to {extracted_wzt_prefix}")
            self.extracted_dir = extracted_wzt_prefix  # Update the extracted directory reference
        except subprocess.CalledProcessError as e:
            print(f"Error extracting file: {e}")
            self.on_extraction_complete(success=False, message=f"Error extracting file: {e}")
        except Exception as e:
            print(f"Error: {e}")
            self.on_extraction_complete(success=False, message=f"Error: {e}")

    def on_extraction_complete(self, success, message):
        """
        Handle the completion of the extraction process.
        """
        GLib.idle_add(self.hide_processing_spinner)
        GLib.idle_add(self.reconnect_open_button)

        if success:
            print(message)
            # Perform any UI updates necessary after a successful extraction
            GLib.idle_add(self.show_info_dialog, "Extraction Completed", message)
        else:
            print(f"Extraction failed: {message}")
            GLib.idle_add(self.show_info_dialog, "Extraction Error", message)

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
            "XOWINEEXEXO": "/app/bin/wine",
            "XOWINEVERXO": "wine-9.0",
        }

        self.replace_strings_in_files(directory, find_replace_pairs)
        
        
    def replace_strings_in_specific_files(self, directory, find_replace_pairs):
        # Define the patterns of the files you want to modify
        file_patterns = ["*.charm", "*.yaml", "*.yml", "*.txt", "*.desktop", "*.sh"]

        # Collect all the files matching the patterns
        files_to_modify = []
        for pattern in file_patterns:
            files_to_modify.extend(glob.glob(os.path.join(directory, pattern)))

        for file_path in files_to_modify:
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

                # Replace strings based on the provided dictionary
                for find, replace in find_replace_pairs.items():
                    content = content.replace(find, replace)

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                print(f"Replacements applied to file: {file_path}")
            except (UnicodeDecodeError, FileNotFoundError, PermissionError) as e:
                print(f"Skipping file: {file_path} ({e})")

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

            info_file_path = variables.get('INFOFILE')
            if info_file_path:
                info_file_path = os.path.join(os.path.dirname(sh_file), info_file_path)
                if os.path.exists(info_file_path):
                    try:
                        info_data = self.parse_info_file(info_file_path)
                        runner = info_data.get('Runner', '')
                        args = info_data.get('Args', '')

                        yml_path = sh_file.replace('.sh', '.charm')
                        self.create_charm_file({
                            'exe_file': exe_file,
                            'progname': progname,
                            'sha256sum': sha256sum,
                            'runner': runner,
                            'args': args,
                        }, yml_path)

                        # Add the new script data directly to self.script_list
                        self.new_scripts.add(Path(yml_path).stem)
                        print(f"Created {yml_path}")
                        created_charm_files = True  # Mark that at least one .charm file was created

                    except Exception as e:
                        print(f"Error parsing INFOFILE {info_file_path}: {e}")
                else:
                    print(f"INFOFILE {info_file_path} not found")
            else:
                print(f"No INFOFILE found in {sh_file}")

        # If no .charm files were created, proceed to create scripts for .lnk and .exe files
        if not created_charm_files:
            print(f"No .charm files created. Proceeding to create scripts for .lnk and .exe files in {directory}")
            self.create_scripts_for_lnk_files(directory)
            print(f"Scripts created for .lnk files in {directory}")

            self.create_scripts_for_exe_files(directory)
            print(f"Scripts created for .exe files in {directory}")


    def create_charm_file(self, info_data, yml_path):
        # Print to confirm the function is being executed
        print(f"Creating .charm file at path: {yml_path}")

        # Prepare the data to be written
        exe_file = info_data.get('exe_file', '')
        progname = info_data.get('progname', '')
        args = info_data.get('args', '')
        sha256sum = info_data.get('sha256sum', '')
        runner = info_data.get('runner', '')

        # Debugging: Print values before writing
        print(f"exe_file: {exe_file}")
        print(f"progname: {progname}")
        print(f"args: {args}")
        print(f"sha256sum: {sha256sum}")
        print(f"runner: {runner}")

        # Manually write the actual content to the file
        try:
            with open(yml_path, 'w') as yml_file:
                yml_file.write(f"exe_file: '{exe_file}'\n")
                yml_file.write(f"progname: '{progname}'\n")
                yml_file.write(f"args: '{args}'\n")
                yml_file.write(f"sha256sum: '{sha256sum}'\n")
                yml_file.write(f"runner: '{runner}'\n")
            print(f"Actual content written to {yml_path}")
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
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.reconnect_open_button()
        self.hide_processing_spinner()

        # Restore the script list in the flowbox
        GLib.idle_add(self.create_script_list)

        print("Restore process completed and script list restored.")

    def extract_backup(self, file_path):
        """
        Extract the .tar.zst backup to the Wine prefixes directory.
        """
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")
        # Step 2: Extract the prefix name from the .tar.zst file
        extracted_prefix_name = subprocess.check_output(
            ['tar', '-tf', file_path],
            universal_newlines=True
        ).splitlines()[0].split('/')[0]
        extracted_prefix_dir = Path(self.prefixes_dir) / extracted_prefix_name

        print(f"Extracted prefix name: {extracted_prefix_name}")
        print(f"Extracting to: {extracted_prefix_dir}")

        # Step 3: Extract the archive to self.prefixes_dir
        subprocess.run(
            ['tar', '-I', 'zstd -T0', '-xf', file_path, '-C', self.prefixes_dir, "--transform", f"s|%USERNAME%|{current_username}|g"],
            check=True
        )

        return extracted_prefix_dir  # Return the extracted directory

    def extract_prefix_dir(self, file_path):
        """
        Return the extracted prefix directory for the backup file.
        This method ensures that only the first directory is returned, not individual files.
        """
        try:
            # Extract only directories by filtering those that end with '/'
            extracted_prefix_name = subprocess.check_output(
                ["bash", "-c", f"tar -tf '{file_path}' | grep '/$' | head -n1 | cut -f1 -d '/'"]
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


    def perform_restore_steps(self, file_path):
        """
        Perform the restore process in steps, showing progress for each.
        """
        steps = [
            ("Checking Uncompressed Size", lambda: self.check_disk_space_and_show_step(file_path)),
            ("Extracting Backup File", lambda: self.extract_backup(file_path)),
            ("Processing Registry Files", lambda: self.process_reg_files(self.extract_prefix_dir(file_path))),
            ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
            ("Renaming and merging user directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(file_path))),
            ("Add Shortcuts to Script List", lambda: self.add_charm_files_to_script_list(self.extract_prefix_dir(file_path))),

        ]
        #for wzt restore
#            ("Create Exe Shortcuts", lambda: self.create_scripts_for_exe_files(self.extract_prefix_dir(file_path)))
        def perform_steps():
            for step_text, step_func in steps:
                # Queue the UI update safely in the main thread
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    # Perform the restore step and check the result
                    result = step_func()
                    if result is False:
                        # Stop further steps if a step fails
                        print(f"Step '{step_text}' failed, aborting restore process.")
                        break

                    # Mark the step as done in the main thread
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    print(f"Error during step '{step_text}': {e}")
                    GLib.idle_add(self.show_info_dialog, "Error", f"Failed during step '{step_text}': {str(e)}")
                    break

            # Once complete, update the UI in the main thread
            GLib.idle_add(self.on_restore_completed)

        # Start the restore process in a new thread
        threading.Thread(target=perform_steps).start()



    def check_disk_space_and_show_step(self, file_path):
        """
        Check available disk space and the uncompressed size of the backup file, showing this as a step.
        """
        # Update the UI to indicate that disk space is being checked
        #GLib.idle_add(self.show_initializing_step, "Checking Available Disk Space")

        # Perform the disk space and uncompressed size check
        enough_space, available_space, uncompressed_size = self.check_disk_space_and_uncompressed_size(self.prefixes_dir, file_path)

        if not enough_space:
            # Show warning about disk space
            GLib.idle_add(self.show_info_dialog, "Insufficient Disk Space",
                          f"The uncompressed size of the backup is {uncompressed_size / (1024 * 1024):.2f} MB, "
                          f"but only {available_space / (1024 * 1024):.2f} MB is available. Please free up space.")
            return False  # Return False to indicate failure and prevent further steps

        # If enough space, update the UI and log the success
        GLib.idle_add(self.show_initializing_step, f"Uncompressed size check passed: {uncompressed_size / (1024 * 1024):.2f} MB")
        print(f"Uncompressed size check passed: {uncompressed_size / (1024 * 1024)} MB")
        GLib.idle_add(self.mark_step_as_done, f"Uncompressed size check passed: {uncompressed_size / (1024 * 1024):.2f} MB")
        return True  # Return True to indicate success

    def show_options_for_script(self, ui_state, row, script_key):
        """
        Display the options for a specific script.
        
        Args:
            ui_state (dict): Information about the script stored in script_data_two.
            row (Gtk.Widget): The row UI element where the options will be displayed.
            script_key (str): The unique key for the script (should be sha256sum or a unique identifier).
        """
        # Get the script path from ui_state
        script = Path(ui_state['script_path'])  # Get the script path from ui_state

        # Ensure the search button is toggled off and the search entry is cleared
        self.search_button.set_active(False)
        self.main_frame.set_child(None)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)

        options_flowbox = Gtk.FlowBox()
        options_flowbox.set_valign(Gtk.Align.START)
        options_flowbox.set_halign(Gtk.Align.FILL)
        options_flowbox.set_max_children_per_line(4)
        options_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        options_flowbox.set_vexpand(True)
        options_flowbox.set_hexpand(True)
        scrolled_window.set_child(options_flowbox)

        self.main_frame.set_child(scrolled_window)

        # Initialize or replace self.options_listbox with the current options_flowbox
        self.options_listbox = options_flowbox

        # Options list
        options = [
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
            ("Save Wine User Directories", "document-save-symbolic", self.show_save_user_dirs_dialog),
            ("Load Wine User Directories", "document-revert-symbolic", self.show_load_user_dirs_dialog),
            ("Reset Shortcut", "view-refresh-symbolic", self.reset_shortcut_confirmation),
            ("Add Desktop Shortcut", "user-bookmarks-symbolic", self.add_desktop_shortcut),
            ("Remove Desktop Shortcut", "action-unavailable-symbolic", self.remove_desktop_shortcut),
            ("Import Game Directory", "folder-download-symbolic", self.import_game_directory)
        ]

        for label, icon_name, callback in options:
            option_button = Gtk.Button()
            option_button.set_size_request(390, 36)
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

            options_flowbox.append(option_button)

            # Enable or disable the "Show log" button based on log file existence and size
            if label == "Show log":
                log_file_path = script.parent / f"{script.stem}.log"
                if not log_file_path.exists() or log_file_path.stat().st_size == 0:
                    option_button.set_sensitive(False)

            # Ensure the correct button (`btn`) is passed to the callback
            option_button.connect(
                "clicked",
                lambda btn, cb=callback, sc=script, sk=script_key: self.callback_wrapper(cb, sc, sk, btn)
            )

        # Use `script` as a Path object for `create_icon_title_widget`
        self.headerbar.set_title_widget(self.create_icon_title_widget(script))

        self.menu_button.set_visible(False)
        self.search_button.set_visible(False)
        self.view_toggle_button.set_visible(False)

        if self.back_button.get_parent() is None:
            self.headerbar.pack_start(self.back_button)
        self.back_button.set_visible(True)

        self.open_button.set_visible(False)
        self.replace_open_button_with_launch(ui_state, row, script_key)
        self.update_execute_button_icon(ui_state)
        self.selected_row = None



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

#        yaml_info = self.extract_yaml_info(script)
#        exe_name = Path(yaml_info['exe_file'])
        #exe_name = Path(script_data['exe_file'])
        #script = Path(script_data['script_path'])
        #wineprefix = Path(script).parent
        #exe_name_quoted = shlex.quote(str(exe_name))
        #wineprefix = shlex.quote(str(wineprefix))
        #exe_file = Path(script_data['exe_file']).expanduser().resolve()
        #wineprefix = Path(script).parent.resolve()

        exe_file = Path(script_data['exe_file']).expanduser().resolve()
        #script = Path(script_data['script_path'])
        progname = script_data['progname']
        script_args = script_data['args']
        runner = script_data['runner'] or "wine"
        script_key = script_data['sha256sum']  # Use sha256sum as the key
        env_vars = script_data.get('env_vars', '')   # Ensure env_vars is initialized if missing
        wine_debug = script_data.get('wine_debug')
        exe_name = Path(exe_file).name
        
        
        #wineprefix = Path(script).parent
#        wineprefix = Path(script_data['script_path']).parent.expanduser().resolve()



        #yaml_info = self.extract_yaml_info(script)
        #progname = script_data.get('progname')
        #script_args = script_data.get('args')
        #runner = yaml_info['runner'] or "wine"
        #script_key = yaml_info['sha256sum']  # Use sha256sum as the key
        #env_vars = yaml_info.get('env_vars', '')  # Ensure env_vars is initialized if missing
        #wine_debug = yaml_info.get('wine_debug', '')
        #exe_name = exe_file.name

        # Ensure the wineprefix, runner path is valid and resolve it
        script = Path(script_data['script_path']).expanduser().resolve()
        wineprefix = Path(script_data['script_path']).parent.expanduser().resolve()
        runner = Path(runner).expanduser().resolve() if runner else Path("wine")
        runner_dir = runner.parent.resolve()

        #print(" - - - - - runner_dir - - - - - ")
        #print(runner)
        #print(runner_dir)
        print(f"Opening terminal for {wineprefix}")

        self.ensure_directory_exists(wineprefix)

        if shutil.which("flatpak-spawn"):
            command = [
                "wcterm",
                "bash",
                "--norc",
                "-c",
                rf'export PS1="[\u@\h:\w]\\$ "; export WINEPREFIX={shlex.quote(str(wineprefix))}; export PATH={shlex.quote(str(runner_dir))}:$PATH; cd {shlex.quote(str(wineprefix))}; exec bash --norc -i'
            ]
        else:
            command = [
                "gnome-terminal",
                "--wait",
                "--",
                "bash",
                "--norc",
                "-c",
                rf'export PS1="[\u@\h:\w]\\$ "; export WINEPREFIX={shlex.quote(str(wineprefix))}; export PATH={shlex.quote(str(runner_dir))}:$PATH; cd {shlex.quote(str(wineprefix))}; exec bash --norc -i'
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
        wineprefix = Path(script).parent
        print(f"Opening file manager for {wineprefix}")
        command = ["xdg-open", str(script)]
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





    def update_execute_button_icon(self, script):
        for child in self.options_listbox:
            box = child.get_child()
            widget = box.get_first_child()
            while widget:
                if isinstance(widget, Gtk.Button) and widget.get_tooltip_text() == "Run or stop the script":
                    play_stop_button = widget
                    if script.stem in self.running_processes:
                        play_stop_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
                        play_stop_button.set_tooltip_text("Stop")
                    else:
                        play_stop_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                        play_stop_button.set_tooltip_text("Run or stop the script")
                widget = widget.get_next_sibling()

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

    def copy_template(self, prefix_dir):
        try:
            if self.initializing_template:
                 print(f"Template is being initialized, skipping copy_template!!!!")
                 return
            print(f"Copying default template to {prefix_dir}")
            shutil.copytree(self.default_template, prefix_dir, symlinks=True)
        except shutil.Error as e:
            for src, dst, err in e.args[0]:
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                else:
                    print(f"Skipping {src} -> {dst} due to error: {err}")
        except Exception as e:
            print(f"Error copying template: {e}")

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
                if not self.default_template.exists():
                    self.initialize_template(self.default_template, self.on_template_initialized)
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


    def show_processing_spinner(self, message="Processing..."):
        if not self.spinner:
            self.spinner = Gtk.Spinner()
            self.spinner.start()
            self.open_button_box.append(self.spinner)

            box = self.open_button.get_child()
            child = box.get_first_child()
            while child:
                if isinstance(child, Gtk.Image):
                    child.set_visible(False)
                elif isinstance(child, Gtk.Label):
                    child.set_label(message)
                child = child.get_next_sibling()

    def hide_processing_spinner(self):
        print("hide_processing_spinner")
        if self.spinner and self.spinner.get_parent() == self.open_button_box:
            self.spinner.stop()
            self.open_button_box.remove(self.spinner)
            self.spinner = None  # Ensure the spinner is set to None
            
        box = self.open_button.get_child()
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Image):
                child.set_visible(True)
            elif isinstance(child, Gtk.Label):
                child.set_label("Open")
            child = child.get_next_sibling()

        print("Spinner hidden.")

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
        self.icon_view = button.get_active()

        # Update the icon for the toggle button
        icon_view_icon = Gtk.Image.new_from_icon_name("view-grid-symbolic")
        list_view_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        button.set_child(icon_view_icon if self.icon_view else list_view_icon)
        
        if self.icon_view:
            self.flowbox.set_max_children_per_line(8)
        else:
            self.flowbox.set_max_children_per_line(4)
        # Recreate the script list with the new view
        self.create_script_list()


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
                        # Clear the flowbox for non-existing directories
                        GLib.idle_add(self.flowbox.remove_all)
                        
                        # Proceed with copying if the directory doesn't exist
                        threading.Thread(target=self.import_wine_directory, args=(directory, dest_dir)).start()
                else:
                    print(f"Invalid directory selected: {directory}")
                    GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Invalid Directory", "The selected directory does not appear to be a valid Wine directory.")
        
        except GLib.Error as e:
            # Handle any errors that occurred during folder selection
            print(f"An error occurred: {e}")
        finally:
            print("renaming and merging other user directories")
            self.remove_symlinks_and_create_directories(dest_dir)
            self.rename_and_merge_user_directories(dest_dir)

        print("FileDialog operation complete.")

    def on_import_wine_directory_completed(self):
        """
        Called when the import process is complete. Updates UI, restores scripts, and resets the open button.
        """
        # Reconnect open button and reset its label
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.reconnect_open_button()
        self.hide_processing_spinner()

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
        # Don't clear the flowbox here — only clear it after the user selects "Overwrite"
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,
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
            # No need to restore the script list as it wasn't cleared

    def import_wine_directory(self, src, dst):
        """
        Import the Wine directory in steps: copy the directory, process registry files, and create scripts for executables.
        """
        steps = [
            ("Copying Wine directory", lambda: self.custom_copytree(src, dst)),
            ("Processing registry files", lambda: self.process_reg_files(dst)),
            ("Creating scripts for .exe files", lambda: self.create_scripts_for_exe_files(dst)),
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
            
            # Re-enable UI elements and restore the script list after the import process
            GLib.idle_add(self.on_import_wine_directory_completed)

        threading.Thread(target=perform_import_steps).start()




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

        self.set_open_button_label("Importing...")
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

    def load_script_list(self, prefixdir=None):
        """
        Loads all .charm files from the specified directory (or the default self.prefixes_dir)
        into the self.script_list dictionary.
        
        Args:
            prefixdir (str or Path, optional): The directory to search for .charm files.
                                               Defaults to self.prefixes_dir.
        """
        # Use the specified prefix directory, or default to self.prefixes_dir
        if prefixdir is None:
            prefixdir = self.prefixes_dir
        
        # Find all .charm files in the directory
        scripts = self.find_charm_files(prefixdir)

        # Process each .charm file
        for script_file in scripts:
            try:
                # Open the original script file to read its content
                with open(script_file, 'r') as f:
                    # Load the YAML data from the .charm file
                    script_data = yaml.safe_load(f)

                    # Ensure script_data is a dictionary
                    if not isinstance(script_data, dict):
                        print(f"Warning: Invalid format in {script_file}, skipping.")
                        continue

                    # Flag to track if any changes are needed
                    updated = False

                    # Replace any paths in the script data with '~' if applicable
                    for key, value in script_data.items():
                        if isinstance(value, str) and value.startswith(os.getenv("HOME")):
                            new_value = self.replace_home_with_tilde_in_path(value)
                            if new_value != value:
                                script_data[key] = new_value
                                updated = True  # Mark that an update is needed

                    # If updates are needed, rewrite the file with updated paths
                    if updated:
                        with open(script_file, 'w') as f:
                            yaml.safe_dump(script_data, f)
                        print(f"Updated script file: {script_file}")

                    # Add the updated or original script path with '~' in script_data for internal use
                    script_data['script_path'] = self.replace_home_with_tilde_in_path(str(script_file))
                    
                    # Add modification time (mtime) to script_data
                    script_data['mtime'] = script_file.stat().st_mtime

                    # Use 'sha256sum' as the key in script_list
                    script_key = script_data.get('sha256sum')
                    if script_key:
                        if prefixdir == self.prefixes_dir:
                            self.script_list[script_key] = script_data
                        else:  # Add the scripts from a single prefix to the top
                            self.script_list = {script_key: script_data, **self.script_list}
                    else:
                        print(f"Warning: Script {script_file} missing 'sha256sum'. Skipping.")

            except yaml.YAMLError as yaml_err:
                print(f"YAML error in {script_file}: {yaml_err}")
            except Exception as e:
                print(f"Error loading script {script_file}: {e}")

        # Print the total number of loaded scripts
        print(f"Loaded {len(self.script_list)} scripts.")


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
                '-C', str(users_dir.parent),  # Change directory to parent of 'users'
                'users'  # Archive the 'users' directory
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
                '-C', str(wineprefix / "drive_c")  # Extract in the drive_c directory
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
        self.show_processing_spinner(f"Importing {exe_path.name}")

        # Copy the game directory in a new thread and update script_path
        threading.Thread(target=self.copy_game_directory, args=(exe_path, exe_name, game_dir, script_path)).start()

    def has_enough_disk_space(self, source, destination):
        # Get the size of the source directory
        source_size = sum(f.stat().st_size for f in source.glob('**/*') if f.is_file())

        # Get the available free space in the destination directory
        destination_free_space = shutil.disk_usage(destination).free

        # Check if destination has enough space for the source
        return destination_free_space > source_size

    def copy_game_directory(self, src, exe_name, dst, script_path):
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
            ("Updating Script Path", lambda: self.update_script_path(script_path, dst_path / exe_name))
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

            GLib.idle_add(self.on_import_wine_directory_completed)

        threading.Thread(target=perform_import_steps).start()



    def update_script_path(self, script_path, new_exe_file):
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

