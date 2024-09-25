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

from datetime import datetime

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango  # Add Pango here

debug = True
version = "0.95"
# Constants
winecharmdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm")).resolve()
prefixes_dir = winecharmdir / "Prefixes"
templates_dir = winecharmdir / "Templates"
runners_dir = winecharmdir / "Runners"
default_template = templates_dir / "WineCharm-win64"

applicationsdir = Path(os.path.expanduser("~/.local/share/applications")).resolve()
tempdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/tmp")).resolve()
iconsdir = Path(os.path.expanduser("~/.local/share/icons")).resolve()
do_not_kill = "bin/winecharm"

SOCKET_FILE = winecharmdir / "winecharm_socket"

# These need to be dynamically updated:
runner = ""  # which wine
wine_version = ""  # runner --version
template = ""  # default: WineCharm-win64 ; #if not found in settings.yaml at winecharm directory add default_template
arch = ""  # default: win64 ; # #if not found in settings.yaml at winecharm directory add win64


class WineCharmApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.fastrizwaan.WineCharm', flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None  # Initialize window as None
        Adw.init()
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
        self.tempdir = tempdir
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
        tempdir =  winecharm_data_dir / "tmp"
        winecharmdir = winecharm_data_dir / "winecharm"
        prefixes_dir = winecharmdir / "Prefixes"
        templates_dir = winecharmdir / "Templates"
        runners_dir = winecharmdir / "Runners"

        directories = [winecharmdir, prefixes_dir, templates_dir, runners_dir, tempdir]

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

            # Iterate over all processes using psutil
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    # Process information
                    pid = proc.info['pid']
                    proc_name = proc.info['name']
                    proc_exe = proc.info['exe']
                    proc_cmdline = proc.info['cmdline']
                    
                    # Build command string for matching (similar to pgrep)
                    command = " ".join(proc_cmdline) if proc_cmdline else proc_name
                    
                    # Check if this is a WineCharm process (using do_not_kill pattern)
                    if do_not_kill in command:
                        winecharm_pids.append(pid)
                    # Check if this is a .exe process and exclude PID 1 (system process)
                    elif exe_name_pattern in command.lower() and pid != 1:
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
        self.create_script_list()

    def on_help_clicked(self, action=None, param=None):
        print("Help action triggered")
        # You can add code here to show a help dialog or window.

    def on_about_clicked(self, action=None, param=None):
        about_dialog = Adw.AboutWindow(
            transient_for=self.window,
            application_name="WineCharm",
            application_icon="io.github.fastrizwaan.WineCharm",
            version=f"{version}",
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
        self.load_script_list()
        self.create_script_list()
        self.check_running_processes_and_update_buttons()
        
        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        else:
            if not default_template.exists():
                self.initialize_template(default_template, self.on_template_initialized)
            else:
                self.set_dynamic_variables()
                # Process the command-line file if the template already exists
                if self.command_line_file:
                    print("Template exists. Processing command-line file after UI initialization.")
                    self.process_cli_file_later(self.command_line_file)

        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("enter", self.on_focus_in)
        focus_controller.connect("leave", self.on_focus_out)
        self.window.add_controller(focus_controller)

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
            ("Installing vkd3d",        f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
            ("Installing dxvk",         f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
            ("Installing corefonts",    f"WINEPREFIX='{template_dir}' winetricks -q corefonts"),
            ("Installing openal",       f"WINEPREFIX='{template_dir}' winetricks -q openal"),
            #("Installing vcrun2005",    f"WINEPREFIX='{template_dir}' winetricks -q vcrun2005"),
            #("Installing vcrun2019",    f"WINEPREFIX='{template_dir}' winetricks -q vcrun2019"),
        ]

        def initialize():
            for step_text, command in steps:
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
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
        self.create_script_list()
        
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
        child = self.flowbox.get_first_child()
        while child:
            button = child.get_child()
            if button.label.get_text() == step_text:
                button.checkbox.set_active(True)
                button.add_css_class("normal-font")
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
        global runner, wine_version, template, arch
        runner = subprocess.getoutput('which wine')
        wine_version = subprocess.getoutput(f"{runner} --version")
        template = "WineCharm-win64" if not (winecharmdir / "settings.yml").exists() else self.load_settings().get('template', "WineCharm-win64")
        arch = "win64" if not (winecharmdir / "settings.yml").exists() else self.load_settings().get('arch', "win64")

    def load_settings(self):
        settings_file_path = winecharmdir / "settings.yml"
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

    def on_focus_in(self, controller):
        if self.monitoring_active:
            return  # Prevent multiple activations

        #print("Focus In")
        self.count = 0
        self.monitoring_active = True
        self.start_monitoring()
        self.check_running_processes_and_update_buttons()
        current_running_processes = self.get_running_processes()
        self.cleanup_ended_processes(current_running_processes)
        #print(" - - - current_running_processes - - -  on_focus_in - - - ")
        #print(current_running_processes)

    def on_focus_out(self, controller):
        self.monitoring_active = False

    def start_monitoring(self, delay=2):
        self.stop_monitoring()  # Ensure the old monitoring is stopped before starting a new one
        self._monitoring_id = GLib.timeout_add_seconds(delay, self.check_running_processes_and_update_buttons)

    def stop_monitoring(self):
        if hasattr(self, '_monitoring_id') and self._monitoring_id is not None:
            try:
                if GLib.source_remove(self._monitoring_id):
                    #print(f"Monitoring source {self._monitoring_id} removed.")
                    self._monitoring_id = None
            except ValueError:
                #print(f"Warning: Attempted to remove a non-existent or already removed source ID {self._monitoring_id}")
                self._monitoring_id = None

    def handle_sigint(self, signum, frame):
        if SOCKET_FILE.exists():
            SOCKET_FILE.unlink()
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

        app_icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        app_icon_box.set_margin_start(10)
        app_icon = Gtk.Image.new_from_icon_name("io.github.fastrizwaan.WineCharm")
        app_icon.set_pixel_size(18)  # Set icon size to 18
        app_icon_box.append(app_icon)
        self.headerbar.pack_start(app_icon_box)

        # Back button
        self.back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.back_button.add_css_class("flat")
        self.back_button.set_visible(False)  # Hide it initially
        self.back_button.connect("clicked", self.on_back_button_clicked)
        self.headerbar.pack_start(self.back_button)

        # Search button
        self.search_button = Gtk.ToggleButton()
        search_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        self.search_button.set_child(search_icon)
        self.search_button.connect("toggled", self.on_search_button_clicked)
        self.search_button.add_css_class("flat")
        self.headerbar.pack_start(self.search_button)

        # Icon/List view toggle button
        self.view_toggle_button = Gtk.ToggleButton()
        icon_view_icon = Gtk.Image.new_from_icon_name("view-grid-symbolic")
        list_view_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        self.view_toggle_button.set_child(icon_view_icon if self.icon_view else list_view_icon)
        self.view_toggle_button.add_css_class("flat")
        self.view_toggle_button.set_tooltip_text("Toggle Icon/List View")
        self.view_toggle_button.connect("toggled", self.on_view_toggle_button_clicked)
        self.headerbar.pack_start(self.view_toggle_button)

        self.menu_button = Gtk.MenuButton()
        menu_icon = Gtk.Image.new_from_icon_name("open-menu-symbolic")
        self.menu_button.set_child(menu_icon)
        self.menu_button.add_css_class("flat")
        self.menu_button.set_tooltip_text("Menu")
        self.headerbar.pack_end(self.menu_button)

        menu = Gio.Menu()
        for label, action in self.hamburger_actions:
            menu.append(label, f"app.{action.__name__}")
            action_item = Gio.SimpleAction.new(action.__name__, None)
            action_item.connect("activate", action)
            self.add_action(action_item)

        self.menu_button.set_menu_model(menu)

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

        self.create_script_list()

    def create_menu_model(self):
        menu = Gio.Menu()
        for label, action in self.hamburger_actions:
            menu.append(label, f"app.{action.__name__}")
            action_item = Gio.SimpleAction.new(action.__name__, None)
            action_item.connect("activate", action)
            self.add_action(action_item)
        return menu

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
            search_term (str): The term to search for within script names.
        """
        # Normalize the search term for case-insensitive matching
        search_term = search_term.lower()
        
        # Clear the existing flowbox to prepare for the filtered scripts
        self.flowbox.remove_all()
        
        # Flag to check if any scripts match the search term
        found_match = False
        
        # Iterate over all scripts in self.script_list using script_key and script_data
        for script_key, script_data in self.script_list.items():
            # Resolve the script path and executable name
            script_path = Path(script_data['script_path']).expanduser().resolve()
            exe_name = Path(script_data['exe_file']).expanduser().resolve().name
            
            # Debugging output (optional)
            print(f"Filtering script: {script_path} with key: {script_key}")
            
            # Check if the search term is present in the script's stem (file name without extension)
            if search_term in script_path.stem.lower():
                found_match = True
                
                # Create a script row. Ensure that create_script_row accepts script_key and script_data
                row = self.create_script_row(script_key, script_data)
                
                # Append the created row to the flowbox for display
                self.flowbox.append(row)
                
                # If the script is currently running, update the UI to reflect its running state
                if script_key in self.running_processes:
                    self.update_ui_for_running_process(script_key, row, self.running_processes)
        
        # Optionally, show a message if no scripts match the search term
        if not found_match:
            self.show_info_dialog("No Results", "No scripts match your search criteria.")


    def on_open_button_clicked(self, button):
        self.open_file_dialog()

    def open_file_dialog(self):
        file_dialog = Gtk.FileDialog.new()
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        filter_model.append(self.create_file_filter())
        file_dialog.set_filters(filter_model)
        file_dialog.open(self.window, None, self.on_file_dialog_response)

    def create_file_filter(self):
        file_filter = Gtk.FileFilter()
        file_filter.set_name("EXE and MSI files")
        file_filter.add_mime_type("application/x-ms-dos-executable")
        file_filter.add_pattern("*.exe")
        file_filter.add_pattern("*.msi")
        return file_filter

    def on_file_dialog_response(self, dialog, result):
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

    def on_back_button_clicked(self, button):
        #print("Back button clicked")

        # Restore the script list
        GLib.idle_add(self.create_script_list)

        # Reset the header bar title and visibility of buttons
        self.window.set_title("Wine Charm")
        self.headerbar.set_title_widget(None)
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

        self.check_running_processes_and_update_buttons()
        
    def restore_open_button(self):
        if not self.open_button.get_parent():
            self.vbox.prepend(self.open_button)
        self.open_button.set_visible(True)

                    
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
        
    def create_script_list(self):
        # Clear the flowbox
        self.flowbox.remove_all()

        # Rebuild the script list
        self.script_data_two = {}  # Use script_data to hold all script-related data

        # Iterate over self.script_list
        for script_key, script_info in self.script_list.items():
            row = self.create_script_row(script_key, script_info)
            if row:
                self.flowbox.append(row)

            # After row creation, highlight if the process is running
            if script_key in self.running_processes:
                self.update_row_highlight(row, True)
                self.script_data_two[script_key]['highlighted'] = True
            else:
                self.update_row_highlight(row, False)
                self.script_data_two[script_key]['highlighted'] = False


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

        # **Store references in self.script_data_two**
        self.script_data_two[script_key] = {
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
        options_button.connect("clicked", lambda btn: self.show_options_for_script(self.script_data_two[script_key], overlay, script_key))

        # Event handler for button click (handles row highlighting)
        button.connect("clicked", lambda *args: self.on_script_row_clicked(button, play_button, options_button))

        return overlay

       
    def show_buttons(self, play_button, options_button):
        play_button.set_visible(True)
        options_button.set_visible(True)

    def hide_buttons(self, play_button, options_button):
        if play_button is not None:
            play_button.set_visible(False)
        if options_button is not None:
            options_button.set_visible(False)

    def on_script_row_clicked(self, button, play_button, options_button):
        """
        Handles the click event on a script row. Manages row highlighting and play/stop button state
        using the `is_clicked_row` property within `script_data_two`.

        Args:
            button (Gtk.Button): The button associated with the script row.
            play_button (Gtk.Button): The play button inside the script row.
            options_button (Gtk.Button): The options button inside the script row.
        """

        # Retrieve the script key associated with the clicked button
        script_key = None
        for key, info in self.script_data_two.items():
            if info['row'] == button.get_parent():  # Assuming 'row' is the parent of the button
                script_key = key
                break

        # If no script_key was found, exit the function early
        if not script_key:
            print("No script_key associated with this button.")
            return

        # Update `is_clicked_row` for all script rows, marking only the current one as True
        for key, data in self.script_data_two.items():
            if key == script_key:
                data['is_clicked_row'] = True  # Mark the current row as clicked
            else:
                data['is_clicked_row'] = False  # Unmark all other rows

        # Iterate over all script buttons and update the UI based on `is_clicked_row`
        for key, data in self.script_data_two.items():
            row_button = data['row']
            row_play_button = data['play_button']
            row_options_button = data['options_button']

            if data['is_clicked_row']:
                # Set this row as clicked: highlight it and show the play/stop buttons
                row_button.add_css_class("blue")
                self.show_buttons(row_play_button, row_options_button)
            else:
                # Set this row as not clicked: remove highlight and hide buttons
                row_button.remove_css_class("blue")
                self.hide_buttons(row_play_button, row_options_button)

        # Check if the script is running and update the play button and row highlight accordingly
        if self.script_data_two[script_key]['is_running']:
            # Script is running: set play button to 'Stop' and add 'highlighted' class to the row
            self.set_play_stop_button_state(play_button, True)
            play_button.set_tooltip_text("Stop")
            button.add_css_class("highlighted")  # Ensure 'highlighted' for running scripts
            print(f"Script {script_key} is running. Setting play button to 'Stop' and adding 'highlighted'.")
        else:
            # Script is not running: set play button to 'Play' and remove 'highlighted' class from the row
            self.set_play_stop_button_state(play_button, False)
            play_button.set_tooltip_text("Play")
            button.remove_css_class("highlighted")  # Remove 'highlighted' if not running
            print(f"Script {script_key} is not running. Setting play button to 'Play' and removing 'highlighted'.")






    def find_row_by_script_stem(self, script_stem):
        script_label = script_stem.replace('_', ' ')
        return self.script_buttons.get(script_label)

    def find_python_scripts(self):
        scripts = []
        for root, dirs, files in os.walk(prefixes_dir):
            depth = root[len(str(prefixes_dir)):].count(os.sep)
            if depth >= 2:
                dirs[:] = []  # Prune the search space
                continue
            scripts.extend([Path(root) / file for file in files if file.endswith(".charm")])
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
            row.remove_css_class("blue")
            row.remove_css_class("highlighted")

    def toggle_play_stop(self, script_key, play_stop_button, row):
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            print(f"No script data found for script_key: {script_key}")
            return

        exe_file = Path(script_data['exe_file']).expanduser().resolve()
        script = Path(script_data['script_path']).resolve()
        progname = script_data['progname']
        script_args = script_data['args']
        runner = script_data['runner'] or "wine"
        
        wineprefix = script.parent.resolve()
        
        # Check if the script is already running
        if script_key in self.running_processes:
            self.terminate_script(script_key)
            self.set_play_stop_button_state(play_stop_button, False)
            self.update_row_highlight(row, False)

            # Ensure overlay buttons are hidden when the process ends
            if self.current_clicked_row:
                button, play_button, options_button = self.current_clicked_row
                self.hide_buttons(play_button, options_button)
                self.set_play_stop_button_state(play_button, False)  # Reset play button to "Play"
                self.current_clicked_row = None
                button.remove_css_class("highlighted")
                button.remove_css_class("blue")
        else:
            self.launch_script(script_key, play_stop_button, row)
            self.set_play_stop_button_state(play_stop_button, True)


    def process_ended(self, script_key):


        # Get the process information for the given script_key
        script_info = self.script_data_two.get(script_key)
        if not script_info:
            print(f"No script data found for script_key: {script_key}")
            return

        # Retrieve row, play_button, and options_button from script_data_two
        row = script_info.get('row')
        play_button = script_info.get('play_button')
        options_button = script_info.get('options_button')

        # If the row exists, remove any highlights (un-highlight the row)
        if row:
            row.remove_css_class("highlighted")
            row.remove_css_class("blue")
            #print(f"Un-highlighted row for script_key: {script_key}")

        # Hide the play and options buttons
        if play_button and options_button:
            self.hide_buttons(play_button, options_button)
            self.set_play_stop_button_state(play_button, False)  # Reset play button to 'Play'
            #print(f"Play and options buttons hidden for script_key: {script_key}")

        # Reset script_data_two's is_running flag for this script
        script_info['is_running'] = False

        # Check if the script was the currently clicked row
        if self.current_clicked_row:
            current_button, current_play_button, current_options_button = self.current_clicked_row

            # If the current clicked row matches the script, un-highlight it and hide buttons
            if current_button == row:
                self.hide_buttons(current_play_button, current_options_button)
                current_button.remove_css_class("blue")
                self.current_clicked_row = None
                #print(f"Current clicked row reset for script_key: {script_key}")

        # Update the launch button state if the script was launched from it
        if self.launch_button and getattr(self, 'launch_button_exe_name', None) == script_key:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
            self.launch_button.set_tooltip_text("Play")
           # print(f"Launch button reset for script_key: {script_key}")

        # Handle the wineprefix and process linked files (if applicable)
        process_info = self.running_processes.get(script_key)
        if process_info:
            script_path = process_info.get("script")
            if script_path and script_path.exists():
                wineprefix = Path(script_path).parent  # Use the parent directory as the wineprefix
                print(f"Processing wineprefix: {wineprefix}")
                if wineprefix:
                    self.create_scripts_for_lnk_files(wineprefix)

        # Remove the script from the running processes
        if script_key in self.running_processes:
            del self.running_processes[script_key]
            print(f"Removed {script_key} from running_processes")

        # If no more running processes exist, reset all UI elements
        if not self.running_processes:
            self.reset_all_ui_elements()
            #print("All processes ended. Resetting all UI elements.")

    def reset_all_ui_elements(self):
        """
        Resets all UI elements (row highlights, button states) to their default state.
        """
        # Reset row highlights and button states for all scripts in script_data_two
        for script_key, script_info in self.script_data_two.items():
            row = script_info.get('row')
            play_button = script_info.get('play_button')
            options_button = script_info.get('options_button')

            # Reset row highlight (remove 'highlighted' and 'blue' classes)
            if row:
                self.update_row_highlight(row, False)  # Un-highlight the row
                row.remove_css_class("blue")  # Remove 'blue' if it's applied
                row.remove_css_class("highlighted")  # Ensure 'highlighted' is also removed
                script_info['highlighted'] = False  # Update the script info state
                script_info['is_clicked_row'] = False  # Mark it as not clicked

            # Hide play and options buttons
            if play_button and options_button:
                self.hide_buttons(play_button, options_button)

            # Reset the play button state to "Play"
            if play_button:
                self.set_play_stop_button_state(play_button, False)

        # Reset the launch button if it exists
        if self.launch_button:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
            self.launch_button.set_tooltip_text("Play")

        # Clear the currently clicked row information
        #self.current_clicked_row = None
        #print("All UI elements reset to default state.")


        
    def launch_script(self, script_key, play_stop_button, row):
        script_data = self.script_list.get(script_key)
        if not script_data:
            return None
        
        exe_file = Path(script_data.get('exe_file', '')).expanduser().resolve()
        script = Path(script_data.get('script_path', '')).expanduser().resolve()
        progname = script_data.get('progname', '')
        script_args = script_data.get('args', '')
        script_key = script_data.get('sha256sum', script_key)
        env_vars = script_data.get('env_vars', '')
        wine_debug = script_data.get('wine_debug', '')
        exe_name = Path(exe_file).name
        wineprefix = Path(script_data.get('script_path', '')).parent.expanduser().resolve()
        runner = script_data.get('runner', 'wine')
        if runner:
            runner = Path(runner).expanduser().resolve()
            runner_dir = runner.parent.resolve()
            path_env = f'export PATH={runner_dir}:$PATH'
        else:
            runner = "wine"
            runner_dir = ""  # Or set a specific default if required
            path_env = ""
            
        # shlex quote for bash
        exe_parent = shlex.quote(str(exe_file.parent.resolve()))
        wineprefix = shlex.quote(str(wineprefix))
        runner = shlex.quote(str(runner))
        runner_dir = shlex.quote(str(runner_dir))
        exe_name = shlex.quote(str(exe_name))
        
        if debug:
            print("--------------------- launch_script_data ------------------")
            print(f"exe_file = {exe_file}\nscript = {script}\nprogname = {progname}")
            print(f"script_args = {script_args}\nscript_key = {script_key}")
            print(f"env_vars = {env_vars}\nwine_debug = {wine_debug}")
            print(f"exe_name = {exe_name}\nwineprefix = {wineprefix}")
            print("runner = {runner}\nrunner_dir = {runner_dir}")
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



        #Logging stderr to {log_file_path}")
        log_file_path = Path(wineprefix) / f"{script.stem}.log"

        # Will be set in Settings
        if wine_debug == "disabled":
            wine_debug = "WINEDEBUG=-all DXVK_LOG_LEVEL=none"

        # If exe_file not found then show info
        if not Path(exe_file).exists():
            GLib.idle_add(play_stop_button.set_child, Gtk.Image.new_from_icon_name("action-unavailable-symbolic"))
            GLib.idle_add(play_stop_button.set_tooltip_text, "Exe Not Found")
            play_stop_button.add_css_class("red")
            self.show_info_dialog("Exe Not found", str(Path(exe_file)))
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
        if debug:
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
                    stderr=log_file  # Redirect stderr to the log file
                )

                self.running_processes[script_key] = {
                    "row": row,
                    "script": script,
                    "exe_name": exe_name,
                    "pids": [process.pid],
                    "wineprefix": wineprefix
                }
                self.set_play_stop_button_state(play_stop_button, True)
                self.update_row_highlight(row, True)
                GLib.timeout_add_seconds(5, self.get_child_pid_async, script_key, exe_name, wineprefix)

        except Exception as e:
            print(f"Error launching script: {e}")
        if debug:
            print(f"launched self.running_processes[script_key]: {self.running_processes[script_key]}")
            print("-------------------Launch Script's self.running_processes--------------------")
            print(self.running_processes)
            print("------------------/Launch Script's self.running_processes--------------------")
            
            
    def get_child_pid_async(self, script_key, exe_name, wineprefix):
        # Run get_child_pid in a separate thread
        if script_key not in self.running_processes:
            print("Process already ended, nothing to get child PID for")
            self.launching_another_from_same_prefix = False
            return False

        process_info = self.running_processes[script_key]
        pid = process_info.get('pid')
        script = process_info.get('script')
        wineprefix = Path(process_info.get('wineprefix')).expanduser().resolve()

        # Replacing Extract YAML info with script_data
        script_data = self.script_list.get(script_key)
        if not script_data:
            return None

        script_key = script_data.get('sha256sum', script_key)        
        exe_file = Path(script_data.get('exe_file', '')).expanduser().resolve()        
        exe_name = Path(exe_file).name
        unix_exe_dir_name = exe_file.parent.name
        wineprefix = Path(script_data.get('script_path', '')).parent.expanduser().resolve()
        
        runner = script_data.get('runner', 'wine')
        if runner:
            runner = Path(runner).expanduser().resolve()
            runner_dir = runner.parent.resolve()
            path_env = f'export PATH={runner_dir}:$PATH'
        else:
            runner = "wine"
            runner_dir = ""  # Or set a specific default if required
            path_env = ""
        
        
        exe_name = shlex.quote(str(exe_name))
        runner_dir = shlex.quote(str(runner_dir))


        def run_get_child_pid():
            try:
                print("---------------------------------------------")
                print(f"Looking for child processes of: {exe_name}")

                # Prepare command to filter processes using winedbg
                if path_env:
                    winedbg_command_with_grep = (
                    f"export PATH={shlex.quote(str(runner_dir))}:$PATH;"
                    f"WINEPREFIX={wineprefix} winedbg --command 'info proc' | "
                    f"grep -A9 \"{exe_name}\" | grep -v 'grep' | grep '_' | "
                    f"grep -v 'start.exe'    | grep -v 'winedbg.exe' | grep -v 'conhost.exe' | "
                    f"grep -v 'explorer.exe' | grep -v 'services.exe' | grep -v 'rpcss.exe' | "
                    f"grep -v 'svchost.exe'   | grep -v 'plugplay.exe' | grep -v 'winedevice.exe' | "
                    f"cut -f2- -d '_' | tr \"'\" ' '"
                    )
                else:
                    winedbg_command_with_grep = (
                    f"WINEPREFIX={wineprefix} winedbg --command 'info proc' | "
                    f"grep -A9 \"{exe_name}\" | grep -v 'grep' | grep '_' | "
                    f"grep -v 'start.exe'    | grep -v 'winedbg.exe' | grep -v 'conhost.exe' | "
                    f"grep -v 'explorer.exe' | grep -v 'services.exe' | grep -v 'rpcss.exe' | "
                    f"grep -v 'svchost.exe'   | grep -v 'plugplay.exe' | grep -v 'winedevice.exe' | "
                    f"cut -f2- -d '_' | tr \"'\" ' '"
                    )
                if debug:    
                    print("---------run_get_child_pid's winedbg_command_with_grep---------------")
                    print(winedbg_command_with_grep)
                    print("--------/run_get_child_pid's winedbg_command_with_grep---------------")
            
                winedbg_output_filtered = subprocess.check_output(winedbg_command_with_grep, shell=True, text=True).strip().splitlines()
                if debug:    
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
                    if debug:    
                        print("--------- run_get_child_pid's pgrep_command ---------------")
                        print(f"{pgrep_command}")
                        print("---------/run_get_child_pid's pgrep_command ---------------")
                        pgrep_output = subprocess.check_output(pgrep_command, shell=True, text=True).strip()
                        child_pids.update(pgrep_output.splitlines())
                        
                    if debug:    
                        print("--------- run_get_child_pid's pgrep_output ---------------")
                        print(f"{pgrep_output}")
                        print("---------/run_get_child_pid's pgrep_output ---------------")
                        
                    if debug:    
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

        # After completing the task, reset the flag
        self.launching_another_from_same_prefix = False
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
        # Get process info for the script using the script_key
        process_info = self.running_processes.get(script_key)

        if not process_info:
            print(f"No running process found for script_key: {script_key}")
            return

        # Extract relevant information from process_info
        script = process_info.get('script')
        wineprefix = Path(process_info.get('wineprefix')).expanduser().resolve()
        runner = process_info.get('runner', 'wine')
        pids = process_info.get("pids", [])
        exe_name = process_info.get('exe_name')

        print(f"Terminating script {script_key} with wineprefix {wineprefix}, runner {runner}, and PIDs: {pids}")

        wineprefix_process_count = 0

        # Count how many processes are using the same wineprefix
        for proc_info in self.running_processes.values():
            if Path(proc_info['wineprefix']).expanduser().resolve() == wineprefix:
                wineprefix_process_count += 1
                print(f"Process running from {wineprefix}: {proc_info}")

        existing_running_script = any(Path(proc_info['script']).expanduser().resolve() == script for proc_info in self.running_processes.values())
        
        print(f"Number of processes with the same wineprefix: {wineprefix_process_count}")

        try:
            if wineprefix_process_count == 1 and existing_running_script:
                runner_dir = Path(runner).parent
                command = f"export PATH={shlex.quote(str(runner_dir))}:$PATH; WINEPREFIX={shlex.quote(str(wineprefix))} wineserver -k"
                print("=======wineserver -k==========")
                print("=======wineserver -k==========")
                print("=======wineserver -k==========")
                print(f"Running command: {command}")
                subprocess.run(command, shell=True, check=True)
                print(f"Successfully killed using wineserver -k")

            
            # Case 2: If wineserver -k fails or there are multiple processes, handle manually
            print("======= Killing processes manually ==========")
            self.kill_processes_by_name(exe_name, script_key)

            # Remove the script from running_processes after termination
            if script_key in self.running_processes:
                del self.running_processes[script_key]

            # Reset UI for the row associated with the script
            row = process_info.get("row")
            if row:
                self.update_row_highlight(row, False)

            # Ensure the play/stop button is reset if it was clicked for this script
            if self.current_clicked_row and self.current_clicked_row[0] == row:
                play_button, options_button = self.current_clicked_row[1], self.current_clicked_row[2]
                self.set_play_stop_button_state(play_button, False)
                self.hide_buttons(play_button, options_button)
                self.current_clicked_row = None

        except Exception as e:
            print(f"Error terminating script {script_key}: {e}")

        print(f"Termination complete for script {script_key}")

    def kill_processes_by_name(self, exe_name, script_key):
        """Kill all processes matching the given exe_name."""
        print(f"Looking for all processes with the name: {exe_name}")
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Kill processes with matching exe_name
                if proc.info['name'].lower() == exe_name.lower():
                    print(f"Terminating process {proc.info['pid']} with name {proc.info['name']}")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def is_process_running(self, pid):
        """Check if a process with the given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


    def kill_processes_individually(self, pids, script_key):
        """Kill each process by PID."""
        for pid in pids:
            if self.is_process_running(pid):
                try:
                    print(f"Terminating PID {pid}")
                    os.kill(pid, signal.SIGKILL)  # Send SIGKILL to the process
                    print(f"Successfully terminated process {pid} for script {script_key}")
                except ProcessLookupError:
                    print(f"Process with PID {pid} not found, may have already exited.")
                except PermissionError:
                    print(f"Permission denied to kill process with PID {pid}.")
            else:
                print(f"Process with PID {pid} is no longer running.")
        print(f"All specified PIDs terminated for {script_key}")


    def check_running_processes_and_update_buttons(self):
        current_running_processes = self.get_running_processes()
        self.cleanup_ended_processes(current_running_processes)

        for script_key, process_info in self.running_processes.items():
            script_info = self.script_data_two.get(script_key)
            if script_info:
                row = script_info.get('row')
                if row and row.get_parent():
                    self.update_ui_for_running_process(script_key, row, current_running_processes)

        if not current_running_processes:
            self.stop_monitoring()

    def get_running_processes(self):
        current_running_processes = {}
        exe_name_count = {}

        # Count occurrences of each exe_name
        for script_key, script_data in self.script_list.items():
            exe_name = Path(script_data['exe_file']).expanduser().resolve().name
            exe_name_count[exe_name] = exe_name_count.get(exe_name, 0) + 1

        try:
            # Get all running .exe processes with their command lines
            pgrep_output = subprocess.check_output(["pgrep", "-aif", "\\.exe"]).decode().splitlines()

            # Filter out any processes that match do_not_kill
            pgrep_output = [line for line in pgrep_output if do_not_kill not in line]
            
            for script_key, script_data in self.script_list.items():
                #print("=======================================================")
                #print(f"{script_data}")
                script = Path(script_data['script_path'])
                exe_name = Path(script_data['exe_file']).name
                unix_exe_dir_name = Path(script_data['exe_file']).parent.name
                wineprefix = Path(script).parent

                # Quote paths and command parts to prevent issues with spaces
                #wineprefix = Path(script).parent
                #exe_name = shlex.quote(str(exe_name))
                #wineprefix = shlex.quote(str(wineprefix))
                
                # Check if exe_name has duplicates
                is_duplicate = exe_name_count[exe_name] > 1

                # Find matching processes
                if is_duplicate:
                    matching_processes = [
                        (int(line.split()[0]), line.split(None, 1)[1]) for line in pgrep_output
                        if exe_name in line and unix_exe_dir_name in line and int(line.split()[0]) != 1
                    ]
                else:
                    matching_processes = [
                        (int(line.split()[0]), line.split(None, 1)[1]) for line in pgrep_output
                        if exe_name in line and int(line.split()[0]) != 1
                    ]

                # If the process is still running
                if matching_processes:
                    for pid, cmd in matching_processes:
                        row_info = self.script_buttons.get(script_key)
                        if row_info:
                            row = row_info.get("row")
                            if row:
                                if script_key not in current_running_processes:
                                    current_running_processes[script_key] = {
                                        "row": row,
                                        "script": script,
                                        "exe_name": exe_name,
                                        "pids": [],
                                        "command": cmd,
                                        "wineprefix": wineprefix
                                    }
                                if pid not in current_running_processes[script_key]["pids"]:
                                    current_running_processes[script_key]["pids"].append(pid)

                # If no matching process is found, mark it as ended
                else:
                    self.process_ended(script_key)

        except subprocess.CalledProcessError:
            pgrep_output = []
            self.stop_monitoring()
            self.count = 0

        # Merge new running processes with existing ones
        for script_key, process_info in current_running_processes.items():
            if script_key in self.running_processes:
                # Merge PIDs to avoid duplicates
                current_pids = set(self.running_processes[script_key].get("pids", []))
                current_pids.update(process_info["pids"])
                self.running_processes[script_key]["pids"] = list(current_pids)
            else:
                self.running_processes[script_key] = process_info

        return self.running_processes



        
    def update_ui_for_running_process(self, script_key, row, current_running_processes):
        """
        Update the UI to reflect the state of a running process.
        
        Args:
            script_key (str): The sha256sum used as a unique identifier for the script.
            row (Gtk.Widget): The corresponding row widget in the UI.
            current_running_processes (dict): A dictionary containing details of the current running processes.
        """
        # Get the script info from script_data_two
        script_info = self.script_data_two.get(script_key)
        if not script_info:
            print(f"No script data found for script_key: {script_key}")
            return

        # Check if the script is running
        if script_key not in current_running_processes:
            # Script is not running, remove 'highlighted' class
            self.update_row_highlight(row, False)
            row.remove_css_class("highlighted")
            row.remove_css_class("blue")
            script_info['is_running'] = False
            print(f"Removed 'highlighted' from row for script_key: {script_key}")
        else:
            # Script is running, ensure the 'highlighted' class is added
            self.update_row_highlight(row, True)
            #row.remove_css_class("blue")  # Ensure 'blue' is removed
            row.add_css_class("highlighted")  # Add 'highlighted' for running scripts
            script_info['is_running'] = True
            print(f"Added 'highlighted' to row for script_key: {script_key}")

        # Update the play/stop button if the script is currently clicked
        if script_info.get('is_clicked_row', False):
            play_button = script_info.get('play_button')
            options_button = script_info.get('options_button')
            if play_button and options_button:
                self.show_buttons(play_button, options_button)
                self.set_play_stop_button_state(play_button, True)
                print(f"Updated play/stop button for script_key: {script_key}")

        # Update the launch button state if it matches the script_key
        if self.launch_button and getattr(self, 'launch_button_exe_name', None) == script_key:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
            self.launch_button.set_tooltip_text("Stop")
            print(f"Updated launch button for script_key: {script_key}")


    def cleanup_ended_processes(self, current_running_processes):
        print("- - - current_running_processes - - -  cleanup_ended_processes - - -")
        print(current_running_processes)
        for script_key in list(self.running_processes.keys()):
            if script_key not in current_running_processes:
                self.process_ended(script_key)

        if not current_running_processes:
            print(" - - "*50)
            print("Calling self.reset_all_ui_elements()")
            self.reset_all_ui_elements()


    def find_row_by_script_key(self, script_key):
        return self.script_buttons.get(script_key)

    def extract_yaml_info(self, script_key):
        #print(f" ===== > script key = {script_key}")
        script_data = self.script_list.get(script_key)
        print(f"===== > script_data = {script_data}")
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

        # Handle prefix directory
        if prefix_dir is None:
            prefix_dir = prefixes_dir / f"{exe_no_space}-{sha256sum}"
            if not prefix_dir.exists():
                if default_template.exists():
                    self.copy_template(prefix_dir)
                else:
                    self.ensure_directory_exists(prefix_dir)

        wineprefix_name = prefix_dir.name

        # Extract product name using exiftool
        product_cmd = [
            'exiftool', shlex.quote(str(exe_file))
        ]
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

        with open(yaml_file_path, 'w') as yaml_file:
            yaml.dump(yaml_data, yaml_file, default_flow_style=False, width=1000)

        # Extract icon and create desktop entry
        icon_path = self.extract_icon(exe_file, prefix_dir, exe_no_space, progname)
        self.create_desktop_entry(progname, yaml_file_path, icon_path, prefix_dir)

        # Add the new script data directly to self.script_list
        self.script_list[sha256_hash.hexdigest()] = yaml_data

        self.new_scripts.add(yaml_file_path.stem)
        print("#"*100)
        print(self.new_scripts)
        print(yaml_file_path.stem)

        # Add or update script row in UI
        # Add the new script data to the top of self.script_list
        self.script_list = {sha256_hash.hexdigest(): yaml_data, **self.script_list}

#        self.add_or_update_script_row(sha256_hash.hexdigest(), yaml_data)
        GLib.idle_add(self.create_script_list)




    def add_or_update_script_row(self, script_key, script_data):
        """
        Add a new script row to the flowbox or update an existing one.
        
        Args:
            script_key (str): The unique key for the script (e.g., sha256sum).
            script_data (dict): Data associated with the script.
        """
        self.flowbox.remove_all()
        # Create the row using the newly added script data
        row = self.create_script_row(script_key, script_data)

        # Append or prepend the row to the flowbox
        if row:
            self.flowbox.append(row)

        # Highlight the row if the script is running
        if script_key in self.running_processes:
            self.update_row_highlight(row, True)
            self.script_data_two[script_key]['highlighted'] = True
        else:
            self.update_row_highlight(row, False)
            self.script_data_two[script_key]['highlighted'] = False

        # Update the icon for the row after the script is added
        self.update_script_row_icon(script_key)



    def update_script_row_icon(self, script_key):
        """
        Update the icon for a specific script row once the icon is available.
        
        Args:
            script_key (str): The unique key for the script (e.g., sha256sum).
        """
        script_info = self.script_data_two.get(script_key)
        if not script_info:
            return

        row = script_info.get('row')
        script_path = Path(script_info.get('script_path')).expanduser()
        icon_path = script_path.with_suffix(".png")  # Assuming the icon is saved as a .png file

        # Check if the icon exists and update the UI
        if icon_path.exists():
            # Load the icon and update the row
            icon = self.load_icon(script_path, 64, 64)
            button = row.get_child()  # Assuming the button is the child of the overlay
            hbox = button.get_child()  # Get the HBox inside the button
            icon_image = hbox.get_first_child()  # Get the first child (the icon image)
            icon_image.set_from_paintable(icon)
            print(f"Updated icon for script: {script_key}")
        else:
            print(f"Icon not found for script: {script_key}")

    def xadd_or_update_script_row(self, script_key, script_data):
        script_info = self.script_data_two.get(script_key)
        if not script_info:
            return

        row = script_info.get('row')
        script_path = Path(script_info.get('script_path')).expanduser()
        script_name = script_path.stem.replace("_", " ")

        # Clear the existing rows
        self.flowbox.remove_all()

        # Recreate the script list
        self.create_script_list()
        self.update_script_row_icon(script_key)
        # Update the icon for the row after the script is added

    def update_script_row(self, row, script_key, script_data):
        """
        Update the contents of an existing script row.

        Args:
            row (Gtk.Widget): The row to update.
            script_data (dict): The updated data for the script.
        """
        # Assuming the row has a button with a label and an icon
        button = row.get_child()  # Assuming the button is the child of the row (Overlay)
        hbox = button.get_child()  # Assuming hbox is the child of the button (inside the overlay)

        # Update the label with the new script data
        label_text = script_data.get('progname', '').replace('_', ' ') or Path(script_data['script_path']).stem.replace('_', ' ')
        
        # Assuming the label is the second child of the hbox
        label = hbox.get_first_child().get_next_sibling()  # Get the label after the icon in the hbox
        if isinstance(label, Gtk.Label):
            label.set_text(label_text)

        # Update any other necessary elements of the row, such as play and options buttons
        play_button = self.script_data_two[script_data['sha256sum']].get('play_button')
        options_button = self.script_data_two[script_data['sha256sum']].get('options_button')

        # Set button states based on whether the script is running
        if script_data['sha256sum'] in self.running_processes:
            self.set_play_stop_button_state(play_button, True)  # Set to "Stop"
            play_button.set_tooltip_text("Stop")
        else:
            self.set_play_stop_button_state(play_button, False)  # Set to "Play"
            play_button.set_tooltip_text("Play")

        # If necessary, update tooltips, icon, and any other button-related properties
        # You can add further updates here as required.
        self.update_script_row_icon(script_key)
        
    def add_or_update_script_row(self, script_key, script_data):
        """
        Add a new script row to the flowbox or update an existing one.
        
        Args:
            script_key (str): The unique key for the script (e.g., sha256sum).
            script_data (dict): Data associated with the script.
        """
        # Check if the script row already exists in self.script_data_two
        existing_script_info = self.script_data_two.get(script_key)

        if existing_script_info:
            # If the row exists, update it instead of appending a new one
            row = existing_script_info.get('row')
            self.update_script_row(row, script_key, script_data)
        else:
            # Create the row using the newly added script data
            row = self.create_script_row(script_key, script_data)

            # Prepend the row to the flowbox if it's new
            if row:
                self.flowbox.prepend(row)

        # Highlight the row if the script is running
        if script_key in self.running_processes:
            self.update_row_highlight(row, True)
            self.script_data_two[script_key]['highlighted'] = True
        else:
            self.update_row_highlight(row, False)
            self.script_data_two[script_key]['highlighted'] = False

        # Update the icon for the row after the script is added
        self.update_script_row_icon(script_key)

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
        
        dialog = Adw.MessageDialog.new(self.window)
        dialog.set_heading(title)
        dialog.set_body(message)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    def create_backup_archive(self, wineprefix, backup_path):
        # Prepare the tar command
        tar_command = [
            'tar',
            '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
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


    def backup_prefix(self, script, backup_path):
        wineprefix = Path(script).parent

        try:
            # Step 3: Reverse `process_reg_files` changes
            self.reverse_process_reg_files(wineprefix)

            # Step 4: Create the backup archive using `tar` with `zstd` compression
            self.create_backup_archive(wineprefix, backup_path)

            # Notify the user that the backup is complete
            GLib.timeout_add_seconds(1, self.show_info_dialog, "Backup Complete", f"Backup saved to {backup_path}")

        except Exception as e:
            print(f"Error during backup: {e}")
            GLib.idle_add(self.show_info_dialog, "Backup Failed", str(e))
            

        finally:
            # Step 5: Re-apply the `process_reg_files` changes
            self.process_reg_files(wineprefix)


    def on_backup_dialog_response(self, dialog, response, script):
        if response == Gtk.ResponseType.OK:
            backup_file = dialog.get_file()
            if backup_file:
                backup_path = backup_file.get_path()
                print(f"Backup will be saved to: {backup_path}")
                # Proceed to backup
                threading.Thread(target=self.backup_prefix, args=(script, backup_path)).start()
        dialog.destroy()

    def show_backup_prefix_dialog(self, script, button):
        # Step 1: Suggest the backup file name
        default_backup_name = f"{script.stem} prefix backup.tar.zst"

        # Create a dialog to get the backup file name and target directory
        dialog = Gtk.FileChooserDialog(
            title="Select Backup Location",
            action=Gtk.FileChooserAction.SAVE,
            transient_for=self.window,
            modal=True
        )
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Save", Gtk.ResponseType.OK
        )

        # Set the default backup file name
        dialog.set_current_name(default_backup_name)

        # Show the dialog and connect the response handler
        dialog.connect("response", self.on_backup_dialog_response, script)
        dialog.present()

    def restore_from_backup(self, action=None, param=None):
        # Step 1: Show open file dialog to select a .tar.zst file
        self.create_required_directories()

        dialog = Gtk.FileChooserDialog(
            title="Select Backup File",
            transient_for=self.window,
            modal=True,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)

        # Set the file filter to only show .tar.zst files
        filter_tar_zst = Gtk.FileFilter()
        filter_tar_zst.set_name("Compressed Backup Files (*.tar.zst)")
        filter_tar_zst.add_pattern("*.tar.zst")
        dialog.add_filter(filter_tar_zst)  # Updated method to add the filter

        def on_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                # Use `get_file()` to get the selected file in GTK 4, but handle it differently
                selected_file = dialog.get_file()
                if selected_file:
                    file_path = selected_file.get_path()  # Correctly use `get_path()` method from the file object
                    print(f"Selected file: {file_path}")
                    
                    # Start a thread for the extraction process to avoid freezing the UI
                    threading.Thread(target=self.perform_restore, args=(file_path,)).start()

            dialog.close()

        dialog.connect("response", on_response)
        dialog.show()

    def perform_restore(self, file_path):
        # Perform the extraction in a separate thread
        try:
            # Step 2: Extract the prefix name from the .tar.zst file
            extracted_prefix_name = subprocess.check_output(
                ['tar', '-tf', file_path],
                universal_newlines=True
            ).splitlines()[0].split('/')[0]
            extracted_prefix_dir = Path(prefixes_dir) / extracted_prefix_name

            print(f"Extracted prefix name: {extracted_prefix_name}")
            print(f"Extracting to: {extracted_prefix_dir}")

            # Step 3: Extract the archive to prefixes_dir
            subprocess.run(
                ['tar', '-I', 'zstd -T0', '-xf', file_path, '-C', prefixes_dir],
                check=True
            )

            # Step 4: Process the extracted registry files
            self.process_reg_files(extracted_prefix_dir)

            # Step 5: Update the script list
            GLib.idle_add(self.create_script_list)  # Schedule to run in the main thread

            # Step 6: Show a dialog confirming the extraction is complete
            GLib.idle_add(self.show_info_dialog, "Restore Complete", f"Backup extracted to {extracted_prefix_dir}")

        except Exception as e:
            print(f"Error extracting backup: {e}")
            GLib.idle_add(self.show_info_dialog, "Error", f"Failed to restore backup: {str(e)}")



    def show_options_for_script(self, script_info, row, script_key):
        """
        Display the options for a specific script.
        
        Args:
            script_info (dict): Information about the script stored in script_data_two.
            row (Gtk.Widget): The row UI element where the options will be displayed.
            script_key (str): The unique key for the script (should be sha256sum or a unique identifier).
        """
        # Get the script path from script_info
        script = Path(script_info['script_path'])  # Get the script path from script_info

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
            ("Delete Wineprefix", "edit-delete-symbolic", self.show_delete_confirmation),
            ("Delete Shortcut", "edit-delete-symbolic", self.show_delete_shortcut_confirmation),
            ("Wine Arguments", "preferences-system-symbolic", self.show_wine_arguments_entry),
            ("Rename Shortcut", "text-editor-symbolic", self.show_rename_shortcut_entry),
            ("Change Icon", "applications-graphics-symbolic", self.show_change_icon_dialog),
            ("Backup Prefix", "document-save-symbolic", self.show_backup_prefix_dialog),  # New option
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
        self.replace_open_button_with_launch(script_info, row, script_key)
        self.update_execute_button_icon(script_info)
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
        script = Path(script_data['script_path'])
        progname = script_data['progname']
        script_args = script_data['args']
        runner = script_data['runner'] or "wine"
        script_key = script_data['sha256sum']  # Use sha256sum as the key
        env_vars = script_data.get('env_vars', '')   # Ensure env_vars is initialized if missing
        wine_debug = script_data.get('wine_debug')
        exe_name = Path(exe_file).name
        
        
        #wineprefix = Path(script).parent
        wineprefix = Path(script_data['script_path']).parent.expanduser().resolve()



        #yaml_info = self.extract_yaml_info(script)
        #progname = script_data.get('progname')
        #script_args = script_data.get('args')
        #runner = yaml_info['runner'] or "wine"
        #script_key = yaml_info['sha256sum']  # Use sha256sum as the key
        #env_vars = yaml_info.get('env_vars', '')  # Ensure env_vars is initialized if missing
        #wine_debug = yaml_info.get('wine_debug', '')
        #exe_name = exe_file.name

        # Ensure the runner path is valid and resolve it
        runner = Path(runner).expanduser().resolve() if runner else Path("wine")
        runner_dir = runner.parent.resolve()

        print(" - - - - - runner_dir - - - - - ")
        print(runner)
        print(runner_dir)
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
            
    def show_delete_confirmation(self, script, button):
        """
        Show an Adw.MessageDialog to confirm the deletion of the Wine prefix.
        
        Args:
            script: The script that contains information about the Wine prefix.
            button: The button that triggered the deletion request.
        """
        wineprefix = Path(script).parent

        # Create a confirmation dialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,  # Assuming self.window is the main application window
            title="Delete Wine Prefix",
            body=f"Are you sure you want to delete the Wine prefix for {wineprefix.name}?"
        )
        
        # Add the "Delete" and "Cancel" buttons
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")
        
        # Show the dialog and connect the response signal
        dialog.connect("response", self.on_delete_confirmation_response, wineprefix)

        # Present the dialog (use present instead of show to avoid deprecation warning)
        dialog.present()


    def on_delete_confirmation_response(self, dialog, response_id, wineprefix):
        """
        Handle the response from the delete confirmation dialog.
        
        Args:
            dialog: The Adw.MessageDialog instance.
            response_id: The ID of the response clicked by the user.
            wineprefix: The path to the Wine prefix that is potentially going to be deleted.
        """
        if response_id == "delete":
            # Perform the deletion of the Wine prefix
            try:
                if wineprefix.exists() and wineprefix.is_dir():
                    shutil.rmtree(wineprefix)
                    print(f"Deleted Wine prefix: {wineprefix}")
                    
                    # Remove the script/row associated with this Wine prefix
                    script_key = self.get_script_key_from_wineprefix(wineprefix)
                    if script_key in self.script_list:
                        del self.script_list[script_key]
                        print(f"Removed script {script_key} from script_list")
                    else:
                        print(f"Script not found in script_list for Wine prefix: {wineprefix}")

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

    def get_script_key_from_wineprefix(self, wineprefix):
        """
        Retrieve the script_key for a given Wine prefix.
        
        Args:
            wineprefix: The path to the Wine prefix.
            
        Returns:
            The corresponding script_key from script_list, if found.
        """
        for script_key, script_info in self.script_list.items():
            script_path = Path(script_info['script_path'])
            if script_path.parent == wineprefix:
                return script_key
        return None


    def show_delete_shortcut_confirmation(self, script, button):
        """
        Show an Adw.MessageDialog to confirm the deletion of the shortcut.
        
        Args:
            script: The script that contains information about the shortcut.
            button: The button that triggered the deletion request.
        """
        shortcut_file = Path(script)

        # Create a confirmation dialog
        dialog = Adw.MessageDialog(
            modal=True,
            transient_for=self.window,  # Assuming self.window is the main application window
            title="Delete Shortcut",
            body=f"Are you sure you want to delete the shortcut for {shortcut_file.name}?"
        )
        
        # Add the "Delete" and "Cancel" buttons
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")
        
        # Show the dialog and connect the response signal
        dialog.connect("response", self.on_delete_shortcut_confirmation_response, shortcut_file)

        # Present the dialog (use present instead of show to avoid deprecation warning)
        dialog.present()

    def on_delete_shortcut_confirmation_response(self, dialog, response_id, shortcut_file):
        """
        Handle the response from the delete shortcut confirmation dialog.
        
        Args:
            dialog: The Adw.MessageDialog instance.
            response_id: The ID of the response clicked by the user.
            shortcut_file: The path to the shortcut that is potentially going to be deleted.
        """
        if response_id == "delete":
            # Perform the deletion of the shortcut
            try:
                if shortcut_file.exists() and shortcut_file.is_file():
                    shortcut_file.unlink()  # Delete the shortcut file
                    print(f"Deleted shortcut: {shortcut_file}")
                    
                    # Remove the script/row associated with this shortcut
                    script_key = self.get_script_key_from_shortcut(shortcut_file)
                    if script_key in self.script_list:
                        del self.script_list[script_key]
                        print(f"Removed script {script_key} from script_list")
                    else:
                        print(f"Script not found in script_list for shortcut: {shortcut_file}")

                    # Trigger the back button to return to the previous view
                    self.on_back_button_clicked(None)
                else:
                    print(f"Shortcut file does not exist: {shortcut_file}")
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
        for script_key, script_info in self.script_list.items():
            script_path = Path(script_info['script_path'])
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
        script_data = self.script_list.get(script_key)
        
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
                script_info = self.extract_yaml_info(script_key)
                script_info['args'] = new_args

                # Update the in-memory representation
                self.script_list[script_key]['args'] = new_args

                # Get the script path from the script info
                script_path = Path(script_info['script_path'])

                # Write the updated info back to the YAML file
                with open(script_path, 'w') as file:
                    yaml.dump(script_info, file, default_flow_style=False, width=1000)

                print(f"Updated Wine arguments for {script_path}: {new_args}")

                ## Optionally refresh the script list or UI to reflect the changes
                ##self.create_script_list()

            except Exception as e:
                print(f"Error updating Wine arguments for {script_key}: {e}")

        else:
            print("Wine arguments modification canceled")

        # Close the dialog
        dialog.close()



    def show_rename_shortcut_entry(self, script, button):
        self.replace_button_with_entry_overlay(script, "New Shortcut Name:", button, rename=True)

    def show_change_icon_dialog(self, script, option_button, button):
        file_dialog = Gtk.FileDialog.new()
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Image and Executable files")
        file_filter.add_mime_type("image/png")
        file_filter.add_mime_type("image/svg+xml")
        file_filter.add_mime_type("application/x-ms-dos-executable")
        file_filter.add_pattern("*.exe")
        file_filter.add_pattern("*.msi")

        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        filter_model.append(file_filter)
        file_dialog.set_filters(filter_model)

        file_dialog.open(self.window, None, lambda dlg, res: self.on_change_icon_response(dlg, res, script))

    def on_change_icon_response(self, dialog, result, script):
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = file.get_path()
                suffix = Path(file_path).suffix.lower()
                if suffix in [".png", ".svg"]:
                    self.change_icon(script, file_path)
                elif suffix in [".exe", ".msi"]:
                    self.extract_and_change_icon(script, file_path)
                # Update the icon in the title bar
                self.headerbar.set_title_widget(self.create_icon_title_widget(script))
        except GLib.Error as e:
            print(f"An error occurred: {e}")

    def change_icon(self, script, new_icon_path):
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            return None    
        script_path = Path(script_data['script_path'])
        icon_path = script_path.with_suffix(".png")
        backup_icon_path = icon_path.with_suffix(".bak")

        if icon_path.exists():
            shutil.move(icon_path, backup_icon_path)

        shutil.copy(new_icon_path, icon_path)
        self.create_script_list()

    def extract_and_change_icon(self, script, exe_path):
        script_path = Path(script_data['script_path'])
        icon_path = script_path.with_suffix(".png")
        backup_icon_path = icon_path.with_suffix(".bak")

        if icon_path.exists():
            shutil.move(icon_path, backup_icon_path)

        extracted_icon_path = self.extract_icon(exe_path, script_path.parent, script_path.stem, script_path.stem)
        if extracted_icon_path:
            shutil.move(extracted_icon_path, icon_path)
        self.create_script_list()



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

    def replace_button_with_overlay(self, script, confirmation_text, action_type, button):
        # Ensure button is a valid GTK button object
        if button is None or not hasattr(button, 'get_parent'):
            raise ValueError("Invalid button object passed to replace_button_with_overlay.")
        
        parent = button.get_parent()

        # Check if the parent is a valid Gtk.FlowBoxChild
        if isinstance(parent, Gtk.FlowBoxChild):
            # Create an overlay and a confirmation box
            overlay = Gtk.Overlay()

            confirmation_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            confirmation_box.set_valign(Gtk.Align.START)
            confirmation_box.set_halign(Gtk.Align.FILL)
            confirmation_box.set_margin_start(10)

            # Add the confirmation label to the confirmation box
            confirmation_label = Gtk.Label(label=confirmation_text)
            confirmation_box.append(confirmation_label)

            # Create and style the "Yes" button (destructive action)
            yes_button = Gtk.Button()
            yes_button_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            yes_button.set_child(yes_button_icon)
            yes_button.add_css_class("destructive-action")

            # Create and style the "No" button (suggested action)
            no_button = Gtk.Button()
            no_button_icon = Gtk.Image.new_from_icon_name("window-close-symbolic")
            no_button.set_child(no_button_icon)
            no_button.add_css_class("suggested-action")

            # Append buttons to the confirmation box
            confirmation_box.append(yes_button)
            confirmation_box.append(no_button)

            # Set the confirmation box as the child of the overlay
            overlay.set_child(confirmation_box)

            # Replace the parent widget's child with the overlay
            parent.set_child(overlay)

            # Connect signals to the "Yes" and "No" buttons
            yes_button.connect("clicked", self.on_confirm_action, script, action_type, parent, button)
            no_button.connect("clicked", self.on_cancel_button_clicked, parent, button)

        else:
            raise ValueError("The button's parent is not a Gtk.FlowBoxChild.")


    def replace_button_with_entry_overlay(self, script, prompt_text, button, rename=False):
        parent = button.get_parent()

        if isinstance(parent, Gtk.FlowBoxChild):
            # Create the overlay and the entry box
            overlay = Gtk.Overlay()

            entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            entry_box.set_halign(Gtk.Align.FILL)
            entry_box.set_valign(Gtk.Align.CENTER)
            entry_box.set_margin_start(10)

            entry_label = Gtk.Label(label=prompt_text)
            entry_box.append(entry_label)

            # Get the current name for renaming or arguments for pre-filling the entry
            yaml_info = self.extract_yaml_info(script)
            if rename:
                entry = Gtk.Entry()
                entry.set_text(yaml_info['progname'])
            else:
                entry = Gtk.Entry()
                entry.set_text(yaml_info['args'] or "-opengl -SkipBuildPatchPrereq")
            
            entry.select_region(0, -1)  # Select all the text in the entry
            entry.set_hexpand(True)
            entry_box.append(entry)

            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            ok_button = Gtk.Button()
            ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            ok_button.set_child(ok_icon)

            cancel_button = Gtk.Button()
            cancel_icon = Gtk.Image.new_from_icon_name("window-close-symbolic")
            cancel_button.set_child(cancel_icon)

            button_box.append(cancel_button)
            button_box.append(ok_button)

            entry_box.append(button_box)

            overlay.set_child(entry_box)
            parent.set_child(overlay)

            # Connect cancel and ok button actions
            cancel_button.connect("clicked", self.on_cancel_button_clicked, parent, button)
            if rename:
                ok_button.connect("clicked", lambda btn: self.on_ok_rename_button_clicked(entry.get_text().strip(), script))
            else:
                ok_button.connect("clicked", lambda btn: self.on_ok_button_clicked(entry.get_text().strip(), script))

    def on_ok_rename_button_clicked(self, new_name, script):
        script_path = Path(script_data['script_path'])
        yaml_info = self.extract_yaml_info(script)
        
        old_progname = yaml_info['progname']
        old_icon_name = f"{old_progname.replace(' ', '_')}.png"
        new_icon_name = f"{new_name.replace(' ', '_')}.png"
        
        # Update the YAML information
        yaml_info['progname'] = new_name
        
        try:
            # Write the updated info back to the YAML file
            with open(script_path, 'w') as file:
                yaml.dump(yaml_info, file, default_flow_style=False, width=1000)
            
            # Rename the icon file if it exists
            icon_path = script_path.parent / old_icon_name
            if icon_path.exists():
                new_icon_path = script_path.parent / new_icon_name
                icon_path.rename(new_icon_path)
                print(f"Renamed icon from {old_icon_name} to {new_icon_name}")
            
            # Rename the .charm file
            new_script_path = script_path.with_stem(new_name.replace(' ', '_'))
            script_path.rename(new_script_path)
            print(f"Renamed script from {script_path} to {new_script_path}")
            
            # Update the UI
            self.create_script_list()
            
        except Exception as e:
            print(f"Error renaming script or icon: {e}")
        
        # Go back to the previous view
        self.on_back_button_clicked(None)

    def on_ok_button_clicked(self, new_args, script):
        try:
            # Update the script with the new arguments
            script_info = self.extract_yaml_info(script)
            script_info['args'] = new_args
            
            # Write the updated info back to the YAML file
            with open(script, 'w') as file:
                yaml.dump(script_info, file, default_flow_style=False, width=1000)
            
            # Update the UI or whatever is necessary
            self.create_script_list()

        except Exception as e:
            print(f"Error updating script arguments: {e}")
            

    def process_file(self, file_path):
        try:
            print("process_file")
            abs_file_path = str(Path(file_path).resolve())
            print(f"Resolved absolute file path: {abs_file_path}")  # Debugging output

            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return

            self.create_yaml_file(abs_file_path, None)
            self.create_script_list()
        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            print("hide_processing_spinner")
            GLib.idle_add(self.hide_processing_spinner)

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

    def get_play_button_from_row(self, row):
        """
        Helper method to retrieve the play button from a script row.
        Assumes that the play button is one of the children in the row.
        """
        for child in row.get_children():
            if isinstance(child, Gtk.Button) and child.get_tooltip_text() == "Play" or child.get_tooltip_text() == "Stop":
                return child
        return None


    def copy_template(self, prefix_dir):
        try:
            if self.initializing_template:
                 print(f"Template is being initialized, skipping copy_template!!!!")
                 return
            print(f"Copying default template to {prefix_dir}")
            shutil.copytree(default_template, prefix_dir, symlinks=True)
        except shutil.Error as e:
            for src, dst, err in e.args[0]:
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                else:
                    print(f"Skipping {src} -> {dst} due to error: {err}")
        except Exception as e:
            print(f"Error copying template: {e}")

    def create_desktop_entry(self, progname, script_path, icon_path, wineprefix):
        return; # do not create
        desktop_file_content = f"""[Desktop Entry]
    Name={progname}
    Type=Application
    Exec=wine '{script_path}'
    Icon={icon_path if icon_path else 'wine'}
    Keywords=winecharm; game; {progname};
    NoDisplay=false
    StartupNotify=true
    Terminal=false
    Categories=Game;Utility;
    """
        desktop_file_path = wineprefix / f"{progname}.desktop"
        
        try:
            # Write the desktop entry to the specified path
            with open(desktop_file_path, "w") as desktop_file:
                desktop_file.write(desktop_file_content)

            # Create a symlink to the desktop entry in the applications directory
            symlink_path = applicationsdir / f"{progname}.desktop"
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            symlink_path.symlink_to(desktop_file_path)

            # Create a symlink to the icon in the icons directory if it exists
            if icon_path:
                icon_symlink_path = iconsdir / f"{icon_path.name}"
                if icon_symlink_path.exists() or icon_symlink_path.is_symlink():
                    icon_symlink_path.unlink(missing_ok=True)
                icon_symlink_path.symlink_to(icon_path)

            print(f"Desktop entry created: {desktop_file_path}")
        except Exception as e:
            print(f"Error creating desktop entry: {e}")

    def start_socket_server(self):
        def server_thread():
            socket_dir = SOCKET_FILE.parent

            # Ensure the directory for the socket file exists
            self.create_required_directories()

            # Remove existing socket file if it exists
            if SOCKET_FILE.exists():
                SOCKET_FILE.unlink()
            
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(SOCKET_FILE))
                server.listen()
                while True:
                    conn, _ = server.accept()
                    with conn:
                        message = conn.recv(1024).decode()
                        if message:
                            cwd, file_path = message.split("||")
                            base_path = Path(cwd)
                            pattern = file_path.split("/")[-1]
                            directory = "/".join(file_path.split("/")[:-1])
                            search_path = base_path / directory

                            if not search_path.exists():
                                print(f"Directory does not exist: {search_path}")
                                continue

                            abs_file_paths = list(search_path.glob(pattern))
                            if abs_file_paths:
                                for abs_file_path in abs_file_paths:
                                    if abs_file_path.exists():
                                        print(f"Resolved absolute file path: {abs_file_path}")
                                        GLib.idle_add(self.process_cli_file, str(abs_file_path))
                                    else:
                                        print(f"File does not exist: {abs_file_path}")
                            else:
                                print(f"No files matched the pattern: {file_path}")

        threading.Thread(target=server_thread, daemon=True).start()

    def initialize_app(self):
        if not hasattr(self, 'window') or not self.window:
            # Call the startup code
            self.create_main_window()
            self.create_script_list()
            self.check_running_processes_and_update_buttons()
            
            missing_programs = self.check_required_programs()
            if missing_programs:
                self.show_missing_programs_dialog(missing_programs)
            else:
                if not default_template.exists():
                    self.initialize_template(default_template, self.on_template_initialized)
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
            self.create_script_list()
        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            if self.initializing_template:
                pass  # Keep showing spinner
            else:
                GLib.timeout_add_seconds(1, self.hide_processing_spinner)


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
               # self.show_info_dialog("Invalid File Type", "Only .exe and .msi files are supported.")
                GLib.timeout_add_seconds(1, self.show_info_dialog, "Invalid File Type", "Only .exe and .msi files are supported.")
                self.command_line_file = None
                return False

    def load_icon(self, script, x, y):
        
        icon_name = script.stem + ".png"
        icon_dir = script.parent
        icon_path = icon_dir / icon_name
        default_icon_path = self.get_default_icon_path()

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
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        icon = self.load_icon(script, 24, 24)
        if icon:
            icon_image = Gtk.Image.new_from_paintable(icon)
            icon_image.set_pixel_size(24)
            hbox.append(icon_image)

        label = Gtk.Label(label=f"<b>{script.stem.replace('_', ' ')}</b>")
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

    def on_import_wine_directory_clicked(self):
        pass
    
# import wine directory
    def on_import_wine_directory_clicked(self, action, param):
        dialog = Gtk.FileChooserDialog(
            title="Select Wine Directory",
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            transient_for=self.window,
            modal=True
        )
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Open", Gtk.ResponseType.OK
        )
        dialog.connect("response", self.on_import_directory_response)
        dialog.present()
        print("FileChooserDialog presented for importing Wine directory.")


    def on_import_directory_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            file = dialog.get_file()
            if file:
                directory = file.get_path()
                print(f"Selected directory: {directory}")
                if directory and (Path(directory) / "system.reg").exists():
                    print(f"Valid Wine directory selected: {directory}")
                    self.show_processing_spinner(f"Importing {Path(directory).name}")
                    self.disable_open_button()

                    dest_dir = prefixes_dir / Path(directory).name
                    print(f"Copying Wine directory to: {dest_dir}")
                    threading.Thread(target=self.copy_wine_directory, args=(directory, dest_dir)).start()
                else:
                    print(f"Invalid directory selected: {directory}")
                    #self.show_info_dialog("Invalid Directory", "The selected directory does not appear to be a valid Wine directory.")
                    GLib.timeout_add_seconds(1, self.show_info_dialog, "Invalid Directory", "The selected directory does not appear to be a valid Wine directory.")
        dialog.destroy()
        print("FileChooserDialog destroyed.")

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

    def create_scripts_for_exe_files(self, wineprefix):
        exe_files = self.find_exe_files(wineprefix)
        for exe_file in exe_files:
            self.create_yaml_file(exe_file, wineprefix, use_exe_name=True)

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
            dirs[:] = [d for d in dirs if not fnmatch.fnmatch(d, "windows")]
            for file in files:
                file_path = Path(root) / file
                if any(fnmatch.fnmatch(file, pattern) for pattern in exclude_patterns):
                    continue
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
        self.ensure_directory_exists(dst)
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.islink(s):
                linkto = os.readlink(s)
                os.symlink(linkto, d)
            elif os.path.isdir(s):
                self.custom_copytree(s, d)
            else:
                shutil.copy2(s, d)
                
    def disable_open_button(self):
        if self.open_button:
            self.open_button.set_sensitive(False)
        print("Open button disabled.")

    def enable_open_button(self):
        if self.open_button:
            self.open_button.set_sensitive(True)
        print("Open button enabled.")

    def load_script_list(self):
        """Loads all .charm files into the self.script_list dictionary."""
        self.script_list = {}

        # Find all .charm files
        scripts = []
        for root, dirs, files in os.walk(prefixes_dir):
            depth = root[len(str(prefixes_dir)):].count(os.sep)
            if depth >= 2:
                dirs[:] = []  # Prune the search space
                continue
            scripts.extend([Path(root) / file for file in files if file.endswith(".charm")])

        # Sort the scripts by modification time
        scripts.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # Load each script's data
        for script_file in scripts:
            with open(script_file, 'r') as f:
                try:
                    script_data = yaml.safe_load(f)
                    script_data['script_path'] = str(script_file)
                    script_key = script_data.get('sha256sum')
                    if script_key:
                        self.script_list[script_key] = script_data  # Use sha256sum as the key
                    else:
                        print(f"Warning: Script {script_file} missing 'sha256sum'. Skipping.")
                except Exception as e:
                    print(f"Error loading script {script_file}: {e}")

        print(f"Loaded {len(self.script_list)} scripts.")

                
def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="WineCharm GUI application")
    parser.add_argument('file', nargs='?', help="Path to the .exe or .msi file")
    return parser.parse_args()


def main():
    args = parse_args()

    app = WineCharmApp()

    if args.file:
        if SOCKET_FILE.exists():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(str(SOCKET_FILE))
                    file_extension = Path(args.file).suffix.lower()
                    if not file_extension in ['.exe', '.msi']:
                         print(f"Invalid file type: {file_extension}. Only .exe or .msi files are allowed.")
                         app.show_info_dialog("RIZVAN Invalid file type: {file_extension}", "Only .exe or .msi files are allowed.")
                         return
                         
                    message = f"{os.getcwd()}||{args.file}"
                    print("-=-=-=-=-=-=-=-")
                    print(message)
                    client.sendall(message.encode())
                    print(f"Sent file path to existing instance: {args.file}")
                return
            except ConnectionRefusedError:
                print("No existing instance found, starting a new one.")
        else:
            print("No existing instance found, starting a new one.")

        app.command_line_file = args.file

    app.start_socket_server()

    app.run(sys.argv)

    if SOCKET_FILE.exists():
        SOCKET_FILE.unlink()


if __name__ == "__main__":
    main()

