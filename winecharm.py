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

from datetime import datetime

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango  # Add Pango here
#qfrom concurrent.futures import ThreadPoolExecutor

version = "0.91"
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
        tempdir.mkdir(parents=True, exist_ok=True)
        self.tempdir = tempdir
        self.icon_view = False
        # Register the SIGINT signal handler
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.script_buttons = {}
        self.current_clicked_row = None  # Initialize current clicked row
        self.hamburger_actions = [
            ("🛠️ Settings...", self.on_settings_clicked),
            ("☠️ Kill all...", self.on_kill_all_clicked),
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

    def on_settings_clicked(self, action=None, param=None):
        print("Settings action triggered")
        # You can add code here to open a settings window or dialog.

    def on_kill_all_clicked(self, action=None, param=None):
        try:
            # Get the list of all relevant processes, including WineCharm and .exe processes
            all_processes_output = subprocess.check_output(["pgrep", "-aif", "\\.exe|{}".format(do_not_kill)]).decode()
            all_processes_lines = all_processes_output.splitlines()

            winecharm_pids = []
            wine_exe_pids = []

            for line in all_processes_lines:
                pid = int(line.split()[0])
                command = line.split(None, 1)[1]

                if do_not_kill in command:
                    winecharm_pids.append(pid)
                elif ".exe" in command.lower() and pid != 1:  # Ensure PID 1 is not included
                    wine_exe_pids.append(pid)

            wine_exe_pids.reverse()  # Reverse the list to kill child processes first

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

        except subprocess.CalledProcessError as e:
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

        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("enter", self.on_focus_in)
        focus_controller.connect("leave", self.on_focus_out)
        self.window.add_controller(focus_controller)

    def initialize_template(self, template_dir, callback):
        if not template_dir.exists():
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
            template_dir.mkdir(parents=True, exist_ok=True)

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
        self.set_open_button_icon_visible(True)  # Restore the open-folder icon
        self.search_button.set_sensitive(True)  # Enable the search button
        self.view_toggle_button.set_sensitive(True)
        
        if self.open_button_handler_id is not None:
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)

        print("Template initialization completed and UI updated.")
        self.show_initializing_step("Initialization Complete!")
        self.mark_step_as_done("Initialization Complete!")
        self.hide_processing_spinner()
        self.create_script_list()
        
        
        # Check if there's a CLI file to process after initialization
        if  self.command_line_file:
            print("Trying to process file inside on template initialized")
            GLib.idle_add(self.show_processing_spinner)
            self.process_cli_file(self.command_line_file)
            self.command_line_file = None  # Reset after processing
            GLib.timeout_add_seconds(1, self.hide_processing_spinner)


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
            
    def on_activate(self, app):
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
        scripts = self.find_python_scripts()
        self.flowbox.remove_all()
        filtered_scripts = [script for script in scripts if search_term in script.stem.lower()]

        for script in filtered_scripts:
            row = self.create_script_row(script)
            self.flowbox.append(row)

            # Check if the script is currently running and highlight it
            yaml_info = self.extract_yaml_info(script)
            script_key = yaml_info['sha256sum']
            if script_key in self.running_processes:
                self.update_ui_for_running_process(script_key, row, self.running_processes)

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
                self.show_processing_spinner("Processing...")
                
                # Use GLib.idle_add to delay the file processing and allow the UI to update
                threading.Thread(target=self.process_cli_file, args=(file_path,)).start()
                
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")
        finally:
            self.window.set_visible(True)

    def on_back_button_clicked(self, button):
        #print("Back button clicked")

        # Restore the script list
        self.create_script_list()

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

    def create_script_list(self):
        # Clear the flowbox
        self.flowbox.remove_all()

        # Rebuild the script list
        self.script_buttons = {}
        scripts = self.find_python_scripts()

        for script in scripts:
            row = self.create_script_row(script)
            if row:
                self.flowbox.append(row)
                yaml_info = self.extract_yaml_info(script)
                script_key = yaml_info['sha256sum']

                self.script_buttons[script_key] = row

                # Check if the script is running
                if script_key in self.running_processes:
                    row.add_css_class("highlighted")
                else:
                    row.remove_css_class("highlighted")
                    row.remove_css_class("blue")

    def create_script_row(self, script):
        yaml_info = self.extract_yaml_info(script)
        exe_name = Path(yaml_info['exe_file']).name
        script_key = yaml_info['sha256sum']  # Use sha256sum as the key

        button = Gtk.Button()
        button.set_hexpand(True)
        button.set_halign(Gtk.Align.FILL)
        button.add_css_class("flat")
        button.add_css_class("normal-font")

        label_text = script.stem.replace("_", " ")
        label = Gtk.Label(label=label_text)
        label.set_hexpand(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)

        # Create an overlay to add play and options buttons
        overlay = Gtk.Overlay()
        overlay.set_child(button)

        if self.icon_view:
            icon = self.load_icon(script)
            icon_image = Gtk.Image.new_from_paintable(icon)
            button.set_size_request(64, 64)
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            icon_image.set_pixel_size(64)
            # Create a box to hold both buttons
            buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        else:
            icon = self.load_icon_for_list(script)
            icon_image = Gtk.Image.new_from_paintable(icon)
            button.set_size_request(390, 36)
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            icon_image.set_pixel_size(32)
            label.set_xalign(0)
            # Create a box to hold both buttons
            buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        button.set_child(hbox)
        hbox.append(icon_image)
        hbox.append(label)

        if script.stem in self.new_scripts:
            label.set_markup(f"<b>{label.get_text()}</b>")

        button.label = label

        buttons_box.set_margin_end(6)  # Adjust this value to prevent overlapping

        # Play button
        play_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        #play_button.add_css_class("overlay-button")
        play_button.set_tooltip_text("Play")
        play_button.set_visible(False)  # Initially hidden
        buttons_box.append(play_button)

        # Options button
        options_button = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        #options_button.add_css_class("overlay-button")
        options_button.set_tooltip_text("Options")
        options_button.set_visible(False)  # Initially hidden
        buttons_box.append(options_button)

        # Add buttons_box to overlay
        overlay.add_overlay(buttons_box)
        buttons_box.set_halign(Gtk.Align.END)
        buttons_box.set_valign(Gtk.Align.CENTER)

        # Store the button in the dictionary using script_key as the key
        #self.script_buttons[script_key] = button

        # Connect play button to the toggle_play_stop method
        play_button.connect("clicked", lambda btn: self.toggle_play_stop(script, play_button, button))

        # Connect options button to the show_options_for_script method
        options_button.connect("clicked", lambda btn: self.show_options_for_script(script, button))

        # Event handler for button click
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
        # Clear previous overlays
        if self.current_clicked_row:
            prev_button, prev_play_button, prev_options_button = self.current_clicked_row
            self.hide_buttons(prev_play_button, prev_options_button)
            prev_button.remove_css_class("blue")

        # Toggle the highlight class
        if self.current_clicked_row == (button, play_button, options_button):
            self.current_clicked_row = None
            button.remove_css_class("blue")
        else:
            self.current_clicked_row = (button, play_button, options_button)
            button.add_css_class("blue")
            self.show_buttons(play_button, options_button)

        # Retrieve the script key associated with this button
        script_key = None
        for key, row in self.script_buttons.items():
            if row == button.get_parent():  # Assuming row is the parent of the button
                script_key = key
                break

        # Ensure the overlay buttons are hidden when the process ends
        if script_key in self.running_processes:
            self.set_play_stop_button_state(play_button, True)  # Set to "Stop" if running
        else:
            self.set_play_stop_button_state(play_button, False)  # Reset to "Play" otherwise

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

    def replace_open_button_with_launch(self, script, row):
        if self.open_button.get_parent():
            self.vbox.remove(self.open_button)

        self.launch_button = Gtk.Button()
        self.launch_button.set_size_request(390, 36)

        yaml_info = self.extract_yaml_info(script)
        script_key = yaml_info['sha256sum']  # Use sha256sum as the key

        if script_key in self.running_processes:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
            self.launch_button.set_tooltip_text("Stop")
        else:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
            self.launch_button.set_tooltip_text("Play")

        self.launch_button.set_child(launch_icon)
        self.launch_button.connect("clicked", lambda btn: self.toggle_play_stop(script, self.launch_button, row))

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
            row.remove_css_class("highlighted")
            row.remove_css_class("blue")

    def toggle_play_stop(self, script, play_stop_button, row):
        yaml_info = self.extract_yaml_info(script)
        script_key = yaml_info['sha256sum']  # Use sha256sum as the key

        if script_key in self.running_processes:
            self.terminate_script(script_key)  # Pass script_key instead of the entire script path
            self.set_play_stop_button_state(play_stop_button, False)
            self.update_row_highlight(row, False)

            # Ensure the overlay buttons are hidden when the process ends
            if self.current_clicked_row:
                play_button, options_button = self.current_clicked_row[1], self.current_clicked_row[2]
                self.hide_buttons(play_button, options_button)
                self.set_play_stop_button_state(play_button, False)  # Reset the play button to "Play"
                self.current_clicked_row = None
        else:
            self.launch_script(script, play_stop_button, row)
            self.set_play_stop_button_state(play_stop_button, True)
            #self.update_row_highlight(row, True)

    def launch_script(self, script, play_stop_button, row):
        yaml_info = self.extract_yaml_info(script)
        exe_file = yaml_info['exe_file']
        wineprefix = Path(script).parent
        progname = yaml_info['progname']
        script_args = yaml_info['args']
        runner = yaml_info['runner'] or "wine"
        script_key = yaml_info['sha256sum']  # Use sha256sum as the key
        env_vars = yaml_info.get('env_vars', '')  # Ensure env_vars is initialized if missing
        wine_debug = yaml_info.get('wine_debug')
        exe_name = Path(exe_file).name

        if winecharmdir not in Path(runner).parents:
            runner = "wine"

        # Define the log file path based on script name
        log_file_path = wineprefix / f"{script.stem}.log"
        print(f"Logging stderr to {log_file_path}")

        # Handle the special case where wine_debug is "disabled"
        if wine_debug == "disabled":
            wine_debug = "WINEDEBUG=-all DXVK_LOG_LEVEL=none"

        # Quote paths and command parts to prevent issues with spaces
        exe_parent = shlex.quote(str(Path(exe_file).parent))
        wineprefix = shlex.quote(str(wineprefix))
        runner = shlex.quote(runner)
        exe_name = shlex.quote(str(exe_name))

        # Check if the exe_file exists
        if not Path(exe_file).exists():
            # Update the play_stop_button in the main GTK thread
            GLib.idle_add(play_stop_button.set_child, Gtk.Image.new_from_icon_name("action-unavailable-symbolic"))
            GLib.idle_add(play_stop_button.set_tooltip_text, "Exe Not Found")
            play_stop_button.add_css_class("red")
            return
        else:
            play_stop_button.remove_css_class("red")

        command = f"cd {exe_parent} && {wine_debug} {env_vars} WINEPREFIX={wineprefix} {runner} {exe_name} {script_args}"
        print(command)

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
                    "pids": [process.pid]
                }

                self.set_play_stop_button_state(play_stop_button, True)
                
                self.update_row_highlight(row, True)
                
                GLib.timeout_add_seconds(5, self.get_child_pid_async, script_key, exe_name, wineprefix)

        except Exception as e:
            print(f"Error launching script: {e}")

        print(self.running_processes)

    def get_child_pid_async(self, script_key, exe_name, wineprefix):
        # Run get_child_pid in a separate thread
        if script_key not in self.running_processes:
            print("Process already ended, nothing to get child PID for")
            return False
            
        process_info = self.running_processes[script_key]
        pid = process_info.get('pid')
        #xe_name = process_info.get('exe_name')
        script = process_info.get('script')
        wineprefix = Path(process_info['script']).parent
        yaml_info = self.extract_yaml_info(script)
        script_key = yaml_info['sha256sum']
        exe_name = Path(yaml_info['exe_file']).name
        unix_exe_dir_name = Path(yaml_info['exe_file']).parent.name  # Get the parent directory name
        print(yaml_info)
        # Quote paths and command parts to prevent issues with spaces
        wineprefix = Path(script).parent
        exe_name_quoted = shlex.quote(str(exe_name))
        wineprefix = shlex.quote(str(wineprefix))

        
        runner =  yaml_info['runner']
        print(runner)
        runner_dir = Path(runner).parent

    #rf'export PS1="[\u@\h:\w]\\$ "; export WINEPREFIX={shlex.quote(str(wineprefix))}; export PATH={shlex.quote(str(runner_dir))}:$PATH; cd {shlex.quote(str(wineprefix))}; exec bash --norc -i'
        # Use wineprefix along with winedbg to accurately target the process
        #refined_processes = self.get_wine_processes(wineprefix, exe_name)
        #command = f"export PATH={shlex.quote(str(runner_dir))}:$PATH; echo $PATH; which wineserver; WINEPREFIX={shlex.quote(str(wineprefix))} wineserver -k"
        grep_exe_name = exe_name.strip("'")

        # Store exe_name and exe_parent mapped by script_key to handle parent directory matching
        exe_name_info = {}

        for script in self.find_python_scripts():
            yaml_info = self.extract_yaml_info(script)
            exe_name_from_script = Path(yaml_info['exe_file']).name
            exe_parent = Path(yaml_info['exe_file']).parent.name
            script_key_from_script = yaml_info['sha256sum']

            # Store the exe_parent mapped by script_key
            exe_name_info[script_key_from_script] = {
                'exe_name': exe_name_from_script,
                'exe_parent': exe_parent
            }

        def run_get_child_pid():
            try:
                print(f"Looking for child processes of: {exe_name}")

                # Command to get the process information using winedbg
                #winedbg_command = f"WINEPREFIX={wineprefix} winedbg --command 'info proc'"
                #winedbg_output = subprocess.check_output(winedbg_command, shell=True, text=True).strip()

                #print("-----------------------------------------------")
                #print(f"Executed command: {winedbg_command}")
                #print(f"winedbg output:\n{winedbg_output}")
                #print('===============================================')

                # Search for the exe_name in the winedbg output using grep
                winedbg_command_with_grep = (
                    f"export PATH={shlex.quote(str(runner_dir))}:$PATH; echo $PATH;"
                    f"WINEPREFIX={wineprefix} winedbg --command 'info proc' | "
                    f"grep -A9 '{grep_exe_name}' | grep -v 'grep' | grep '_' | "
                    f"grep -v 'start.exe'    | grep -v 'winedbg.exe' | grep -v 'conhost.exe' | "
                    f"grep -v 'explorer.exe' | grep -v 'services.exe' | grep -v 'rpcss.exe' | "
                    f"grep -v 'svchost.exe'   | grep -v 'plugplay.exe' | grep -v 'winedevice.exe' | "
                    f"cut -f2- -d '_' | tr \"'\" ' '"
                )

                # Get the relevant process line from winedbg output
                winedbg_output_filtered = subprocess.check_output(winedbg_command_with_grep, shell=True, text=True).strip().splitlines()
                print(f"Filtered winedbg output: {winedbg_output_filtered}")

                # Retrieve the exe_parent from the info
                exe_parent = exe_name_info.get(script_key, {}).get('exe_parent')
                child_pids = set()

                for filtered_exe in winedbg_output_filtered:
                    filtered_exe = filtered_exe.strip()

                    # pgrep command to find matching processes with exe_parent
                    cleaned_exe_parent_name = exe_parent.replace(r'[', '\\[')
                    cleaned_exe_parent_name = cleaned_exe_parent_name.replace(r']', '\\]')

                    pgrep_command = (
                        f"ps -ax --format pid,command | grep \"{filtered_exe}\" | "
                        f"grep \"{cleaned_exe_parent_name}\" | grep -v 'grep' | sed 's/^ *//g' | cut -f1 -d ' '"
                    )

                    print(f"Running pgrep command: {pgrep_command}")
                    pgrep_output = subprocess.check_output(pgrep_command, shell=True, text=True).strip()

                    # Add all found PIDs to the child_pids set (to avoid duplicates)
                    child_pids.update(pgrep_output.splitlines())

                # If we found child PIDs, pass them to the UI update
                if child_pids:
                    print(f"Found child PIDs: {child_pids}")
                    GLib.idle_add(self.add_child_pids_to_running_processes, script_key, child_pids)
                else:
                    print(f"No child process found for {exe_name}")

            except subprocess.CalledProcessError as e:
                print(f"Error executing command: {e}")
            except ValueError as e:
                print(f"Value error: {e}")

        # Start the background thread
        threading.Thread(target=run_get_child_pid, daemon=True).start()

        # Returning False so GLib.timeout_add_seconds doesn't repeat
        return False

    def add_child_pids_to_running_processes(self, script_key, child_pids):
        # Add the child PIDs to the running_processes dictionary
        if script_key in self.running_processes:
            self.running_processes[script_key]["pids"] = []
            for pid in child_pids:
                self.running_processes[script_key]["pids"].append(int(pid))
                
            #print(f"Updated {script_key} with child PIDs: {self.running_processes[script_key]['pids']}")
        else:
            print(f"Script key {script_key} not found in running processes.")
                        
    def terminate_script(self, script_key):
        process_info = self.running_processes[script_key]
        pid = process_info.get('pid')
        #xe_name = process_info.get('exe_name')
        script = process_info.get('script')
        wineprefix = Path(process_info['script']).parent
        yaml_info = self.extract_yaml_info(script)
        script_key = yaml_info['sha256sum']
        exe_name = Path(yaml_info['exe_file']).name
        unix_exe_dir_name = Path(yaml_info['exe_file']).parent.name  # Get the parent directory name
        print(yaml_info)
        # Quote paths and command parts to prevent issues with spaces
        wineprefix = Path(script).parent
        exe_name_quoted = shlex.quote(str(exe_name))
        wineprefix = shlex.quote(str(wineprefix))

        
        runner =  yaml_info['runner']
        print(runner)
        runner_dir = Path(runner).parent

    #rf'export PS1="[\u@\h:\w]\\$ "; export WINEPREFIX={shlex.quote(str(wineprefix))}; export PATH={shlex.quote(str(runner_dir))}:$PATH; cd {shlex.quote(str(wineprefix))}; exec bash --norc -i'
        # Use wineprefix along with winedbg to accurately target the process
        #refined_processes = self.get_wine_processes(wineprefix, exe_name)
        command = f"export PATH={shlex.quote(str(runner_dir))}:$PATH; echo $PATH; which wineserver; WINEPREFIX={shlex.quote(str(wineprefix))} wineserver -k"
        try:
            subprocess.run(command, shell=True, check=True)
            print(f"Successfully ran {pid} in {wineprefix}")
            del self.running_processes[script_key]
        except subprocess.CalledProcessError as e:
            print(f"Error running winetricks script: {e}")
            
            
        if script_key in self.running_processes:
        
            process_info = self.running_processes[script_key]
            pids = process_info.get("pids", [])

            try:
                for pid in pids:
                    if self.is_process_running(pid):
                        #print(f"Attempting to terminate PID: {pid}")
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                        #print(f"Terminated process {script_key} with PID: {pid}")
                    else:
                        print(f"Process with PID {pid} is no longer running.")

                del self.running_processes[script_key]

                row = process_info["row"]
                self.update_row_highlight(row, False)

            except Exception as e:
                print(f"Error terminating script {script_key}: {e}")


    def is_process_running(self, pid):
        """Check if a process with the given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


    def check_running_processes_and_update_buttons(self):
        if not self.monitoring_active:
            self.stop_monitoring()
            return False

        current_running_processes = self.get_running_processes()
        self.cleanup_ended_processes(current_running_processes)

        # Highlight running processes in the current (possibly filtered) view
        for script_key, process_info in self.running_processes.items():
            row = process_info["row"]
            if row and row.get_parent():  # Check if the row is currently displayed in the flowbox
                self.update_ui_for_running_process(script_key, row, self.running_processes)

        if not current_running_processes or self.count >= 5:
            self.stop_monitoring()
        else:
            self.count += 1

        return False



    def get_running_processes(self):
        current_running_processes = {}
        exe_name_count = {}

        # First, count occurrences of each exe_name
        for script in self.find_python_scripts():
            yaml_info = self.extract_yaml_info(script)
            exe_name = Path(yaml_info['exe_file']).name
            exe_name_count[exe_name] = exe_name_count.get(exe_name, 0) + 1
        try:
            # Get all running .exe processes with their command lines
            pgrep_output = subprocess.check_output(["pgrep", "-aif", "\\.exe"]).decode().splitlines()

            # Filter out any processes that match do_not_kill
            pgrep_output = [line for line in pgrep_output if do_not_kill not in line]

            for script in self.find_python_scripts():
                yaml_info = self.extract_yaml_info(script)
                script_key = yaml_info['sha256sum']
                exe_name = Path(yaml_info['exe_file']).name
                unix_exe_dir_name = Path(yaml_info['exe_file']).parent.name  # Get the parent directory name

                # Quote paths and command parts to prevent issues with spaces
                wineprefix = Path(script).parent
                exe_name_quoted = shlex.quote(str(exe_name))
                wineprefix = shlex.quote(str(wineprefix))


                # Check if exe_name has duplicates
                is_duplicate = exe_name_count[exe_name] > 1

                # Find processes that match the exe_name (and the parent directory name if duplicates exist)
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

                if matching_processes:
                    for pid, cmd in matching_processes:
                        row = self.script_buttons.get(script_key)
                        
                        #print("+++++++++++++++++++++++++++++++++++++++++++++++")
                        #print(script_key, exe_name, wineprefix)
                        # Fetch and update child PIDs asynchronously
                        #GLib.timeout_add_seconds(0.01, self.get_child_pid_async, script_key, exe_name_quoted, wineprefix)
                        if row:
                            if script_key not in current_running_processes:
                                current_running_processes[script_key] = {
                                    "row": row,
                                    "script": script,
                                    "exe_name": exe_name,
                                    "pids": [],
                                    "command": cmd
                                }
                            if pid not in current_running_processes[script_key]["pids"]:
                                current_running_processes[script_key]["pids"].append(pid)
                                
                            if self.launch_button:
                                self.set_play_stop_button_state(self.launch_button, True)
                                
                        else:
                            self.update_row_highlight(row, False)
                else:
                    self.process_ended(script_key)

        except subprocess.CalledProcessError:
            pgrep_output = []
            self.stop_monitoring()
            self.count = 0

        # Merge the new current_running_processes dictionary with the existing self.running_processes dictionary
        for script_key, process_info in current_running_processes.items():
            if script_key in self.running_processes:
                self.running_processes[script_key]["pids"].extend(process_info["pids"])
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
        if script_key not in self.running_processes:
            print(f"REMOVNG HIGHLIGHT to row for script_key: {script_key}")  # Debugging output
            self.running_processes[script_key] = current_running_processes[script_key]
            self.update_row_highlight(row, False)
            
            
        if not row.has_css_class("highlighted"):
            print("check_running_processes_and_update_buttons: highlighting")
            #self.update_row_highlight(row, False)
            self.update_row_highlight(row, True)
            #row.add_css_class("highlighted")
#        else:
#            self.update_row_highlight(row, False)
            # Ensure the overlay buttons are hidden when the process ends

#        # not updating button state from monitoring
#        if self.current_clicked_row:
#            play_button, options_button = self.current_clicked_row[1], self.current_clicked_row[2]
#            #self.hide_buttons(play_button, options_button)
#            self.set_play_stop_button_state(play_button, True)  # Reset the play button to "Play"
##            self.current_clicked_row = None
                            
        # Only update the launch button if it belongs to this script
        if self.launch_button and self.launch_button_exe_name == script_key:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
            self.launch_button.set_tooltip_text("Stop")

    def cleanup_ended_processes(self, current_running_processes):
        for script_key in list(self.running_processes.keys()):
            if script_key not in current_running_processes:
                self.process_ended(script_key)


        for exe_name in list(self.running_processes.keys()):
            if exe_name not in current_running_processes:
                self.process_ended(exe_name)

        # If no more processes are running, reset all UI elements
        if not current_running_processes:
            self.reset_all_ui_elements()

        self.running_processes = current_running_processes

    def find_row_by_script_key(self, script_key):
        return self.script_buttons.get(script_key)

    def extract_yaml_info(self, script):
        if not script.exists():
            raise FileNotFoundError(f"Script file not found: {script}")
        with open(script, 'r') as file:
            try:
                data = yaml.safe_load(file)
            except yaml.YAMLError as e:
                print(f"Error loading YAML file {script}: {e}")
                data = {}
        yaml_info = {
            'exe_file': str(Path(data.get('exe_file', '')).expanduser().resolve()), 
            'wineprefix': str(Path(data.get('wineprefix', '')).expanduser().resolve()), 
            'progname': data.get('progname', ''), 
            'args': data.get('args', ''),
            'runner': data.get('runner', ''),
            'sha256sum': data.get('sha256sum', ''),
            'wine_debug': data.get('wine_debug', '')  # Ensure wine_debug is captured
        }
        return yaml_info


    def create_yaml_file(self, exe_path, prefix_dir=None, use_exe_name=False):
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
                    prefix_dir.mkdir(parents=True, exist_ok=True)
                    #print(f"Created prefix directory: {prefix_dir}")

        wineprefix_name = prefix_dir.name

        # Extract product name using exiftool
        product_cmd = [
            'exiftool', shlex.quote(str(exe_file))
        ]
        product_output = self.run_command(" ".join(product_cmd))
        if product_output is None:
            #print(f"Error: Failed to retrieve product name for {exe_file}")
            productname = exe_no_space
        else:
            productname_match = re.search(r'Product Name\s+:\s+(.+)', product_output)
            productname = productname_match.group(1).strip() if productname_match else exe_no_space

        # Determine program name based on use_exe_name flag
        if use_exe_name:
            progname = exe_name  # Use exe_name if flag is set
        else:
            # Default progname logic with fallback to exe_no_space
            if "setup" in exe_name.lower() or "install" in exe_name.lower():
                progname = productname + ' Setup'
            elif "setup" in productname.lower() or "install" in productname.lower():
                progname = productname
            else:
                progname = productname if productname and not any(char.isdigit() for char in productname) and productname.isascii() else exe_no_space

        # Prepare YAML data
        yaml_data = {
            'exe_file': str(exe_file).replace(str(Path.home()), "~"),
            'progname': progname,
            'args': "",
            'sha256sum': sha256_hash.hexdigest(),
            'runner': "",
            'wine_debug': "WINEDEBUG=fixme-all DXVK_LOG_LEVEL=none",  # Set a default or allow it to be empty
            'env_vars': ""  # Initialize with an empty string or set a default if necessary
        }
        
        # Create YAML file with proper naming
        yaml_file_path = prefix_dir / f"{exe_no_space if use_exe_name else progname.replace(' ', '_')}.charm"
        with open(yaml_file_path, 'w') as yaml_file:
            yaml.dump(yaml_data, yaml_file)


        # Extract icon and create desktop entry
        icon_path = self.extract_icon(exe_file, prefix_dir, exe_no_space, progname)
        self.create_desktop_entry(progname, yaml_file_path, icon_path, prefix_dir)

        # Add or update script row in UI if multi files are being created.
        GLib.idle_add(self.add_or_update_script_row, yaml_file_path)

        
        #self.create_script_list()



    def add_or_update_script_row(self, script_path):
        script_name = script_path.stem.replace("_", " ")

        # Clear the existing rows
        self.flowbox.remove_all()

        # Recreate the script list
        self.create_script_list()

        # No need to call show(), as widgets are visible by default in GTK 4



    def extract_icon(self, exe_file, wineprefix, exe_no_space, progname):
        icon_path = wineprefix / f"{progname.replace(' ', '_')}.png"
        #print(f"------ {wineprefix}")
        ico_path = self.tempdir / f"{exe_no_space}.ico"
       # print(f"-----{ico_path}")
        try:
            self.tempdir.mkdir(parents=True, exist_ok=True)

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
            yaml.dump(found_lnk_files, file, default_flow_style=False)

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

    def show_options_for_script(self, script, row):
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
            ("Delete Wineprefix", "edit-delete-symbolic", self.show_delete_confirmation),
            ("Delete Shortcut", "edit-delete-symbolic", self.show_delete_shortcut_confirmation),
            ("Wine Arguments", "preferences-system-symbolic", self.show_wine_arguments_entry),
            ("Rename Shortcut", "text-editor-symbolic", self.show_rename_shortcut_entry),
            ("Change Icon", "applications-graphics-symbolic", self.show_change_icon_dialog)
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
                log_file_path = Path(script.parent) / f"{script.stem}.log"
                if not log_file_path.exists() or log_file_path.stat().st_size == 0:
                    option_button.set_sensitive(False)
            
            option_button.connect(
                "clicked",
                lambda btn, cb=callback, sc=script, ob=option_button:
                self.callback_wrapper(cb, sc, ob)
            )

        # Set the header bar title to the script's icon and name
        self.headerbar.set_title_widget(self.create_icon_title_widget(script))
        self.menu_button.set_visible(False)
        self.search_button.set_visible(False)
        self.view_toggle_button.set_visible(False)
        
        if self.back_button.get_parent() is None:
            self.headerbar.pack_start(self.back_button)
        self.back_button.set_visible(True)

        self.open_button.set_visible(False)
        self.replace_open_button_with_launch(script, row)
        self.update_execute_button_icon(script)
        self.selected_row = None

    def show_log_file(self, script, *args):
        log_file_path = Path(script.parent) / f"{script.stem}.log"
        if log_file_path.exists() and log_file_path.stat().st_size > 0:
            try:
                subprocess.run(["xdg-open", str(log_file_path)], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error opening log file: {e}")

        




    def open_terminal(self, script, *args):
        yaml_info = self.extract_yaml_info(script)
        exe_file = yaml_info['exe_file']
        wineprefix = Path(script).parent
        progname = yaml_info['progname']
        script_args = yaml_info['args']
        runner = yaml_info['runner'] or "wine"
        script_key = yaml_info['sha256sum']  # Use sha256sum as the key
        env_vars = yaml_info.get('env_vars', '')  # Ensure env_vars is initialized if missing
        wine_debug = yaml_info.get('wine_debug')
        exe_name = Path(exe_file).name
        wineprefix = Path(script).parent

        # If the runner is empty or None, fallback to "wine"
        #runner = runner or "wine"
        
        #if winecharmdir not in Path(runner).parents:
        #    runner = "wine"
            
        runner_dir = Path(runner).parent
        print(" - - - - - runner_dir - - - - - ")
        print(runner)
        print(runner_dir)
        print(f"Opening terminal for {wineprefix}")
        if not wineprefix.exists():
            wineprefix.mkdir(parents=True, exist_ok=True)

        if shutil.which("flatpak-spawn"):

            command = [
                "wcterm",
                "bash",
                "--norc",
                "-c",
                rf'export PS1="[\u@\h:\w]\\$ "; export WINEPREFIX={shlex.quote(str(wineprefix))}; export PATH={shlex.quote(str(runner_dir))}:$PATH; cd {shlex.quote(str(wineprefix))}; exec bash --norc -i'
            ]
            print(command)
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
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening terminal: {e}")

    def install_dxvk_vkd3d(self, script, button):
        wineprefix = Path(script).parent
        self.run_winetricks_script("vkd3d dxvk", wineprefix)
        self.create_script_list()

    def open_filemanager(self, script, *args):
        wineprefix = Path(script).parent
        print(f"Opening file manager for {wineprefix}")
        command = ["xdg-open", str(wineprefix)]
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening file manager: {e}")

    def show_delete_confirmation(self, script, button):
        self.replace_button_with_overlay(script, "Delete Wineprefix?", "wineprefix", button)

    def show_delete_shortcut_confirmation(self, script, button):
        self.replace_button_with_overlay(script, "Delete shortcut?", "shortcut", button)

    def show_wine_arguments_entry(self, script, button):
        yaml_info = self.extract_yaml_info(script)
        self.replace_button_with_entry_overlay(script, "Args:", button)

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
        script_path = Path(script)
        icon_path = script_path.with_suffix(".png")
        backup_icon_path = icon_path.with_suffix(".bak")

        if icon_path.exists():
            shutil.move(icon_path, backup_icon_path)

        shutil.copy(new_icon_path, icon_path)
        self.create_script_list()

    def extract_and_change_icon(self, script, exe_path):
        script_path = Path(script)
        icon_path = script_path.with_suffix(".png")
        backup_icon_path = icon_path.with_suffix(".bak")

        if icon_path.exists():
            shutil.move(icon_path, backup_icon_path)

        extracted_icon_path = self.extract_icon(exe_path, script_path.parent, script_path.stem, script_path.stem)
        if extracted_icon_path:
            shutil.move(extracted_icon_path, icon_path)
        self.create_script_list()

    def callback_wrapper(self, callback, script, button=None, *args):
        # Check the method signature of the callback to determine what to pass
        callback_params = callback.__code__.co_varnames

        # If both 'option_button' and 'button' are expected
        if 'option_button' in callback_params and 'button' in callback_params:
            return callback(script, button, button, *args)
        # If only 'button' is expected
        elif 'button' in callback_params:
            return callback(script, button)
        # If only 'option_button' is expected
        elif 'option_button' in callback_params:
            return callback(script, button)
        # If neither 'button' nor 'option_button' is expected, just pass the script
        else:
            return callback(script)

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
        parent = button.get_parent()

        if isinstance(parent, Gtk.FlowBoxChild):
            # Create the overlay and the confirmation box
            overlay = Gtk.Overlay()

            confirmation_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            confirmation_box.set_valign(Gtk.Align.START)
            confirmation_box.set_halign(Gtk.Align.FILL)
            confirmation_box.set_margin_start(10)
            confirmation_label = Gtk.Label(label=confirmation_text)
            confirmation_box.append(confirmation_label)

            yes_button = Gtk.Button()
            yes_button_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            yes_button.set_child(yes_button_icon)
            yes_button.add_css_class("destructive-action")
            no_button = Gtk.Button()
            no_button_icon = Gtk.Image.new_from_icon_name("window-close-symbolic")
            no_button.set_child(no_button_icon)
            no_button.add_css_class("suggested-action")
            confirmation_box.append(yes_button)
            confirmation_box.append(no_button)

            overlay.set_child(confirmation_box)
            parent.set_child(overlay)

            yes_button.connect("clicked", self.on_confirm_action, script, action_type, parent, button)
            no_button.connect("clicked", self.on_cancel_button_clicked, parent, button)

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
        script_path = Path(script)
        yaml_info = self.extract_yaml_info(script)
        
        old_progname = yaml_info['progname']
        old_icon_name = f"{old_progname.replace(' ', '_')}.png"
        new_icon_name = f"{new_name.replace(' ', '_')}.png"
        
        # Update the YAML information
        yaml_info['progname'] = new_name
        
        try:
            # Write the updated info back to the YAML file
            with open(script_path, 'w') as file:
                yaml.dump(yaml_info, file)
            
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
                yaml.dump(script_info, file)
            
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

    def process_ended(self, script_key):
        process_info = self.running_processes.get(script_key)

        if process_info:
            row = process_info.get("row")
            if row:
                row.remove_css_class("highlighted")
                row.remove_css_class("blue")

            # Ensure the overlay buttons are hidden when the process ends
            if self.current_clicked_row:
                button, play_button, options_button = self.current_clicked_row[0], self.current_clicked_row[1], self.current_clicked_row[2]

                self.hide_buttons(play_button, options_button)
                self.set_play_stop_button_state(play_button, False)  # Reset the play button to "Play"
                self.current_clicked_row = None
                button.remove_css_class("highlighted")
                button.remove_css_class("blue")
                
            # Check if self.launch_button is not None before modifying it
            if self.launch_button and getattr(self, 'launch_button_exe_name', None) == script_key:
                self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                self.launch_button.set_tooltip_text("Play")

            script_path = process_info.get("script")
            if script_path and script_path.exists():
                yaml_info = self.extract_yaml_info(script_path)
                wineprefix = Path(script_path).parent
                if wineprefix:
                    wineprefix_path = Path(wineprefix)
                    self.create_scripts_for_lnk_files(wineprefix_path)


            # Remove the process from the running processes
            if script_key in self.running_processes:
                del self.running_processes[script_key]

            # If there are no more running processes, reset all UI elements
            if not self.running_processes:
                self.reset_all_ui_elements()
           
            
    def reset_all_ui_elements(self):
        # Reset any UI elements that should be updated when no processes are running
        for row in self.script_buttons.values():
            row.remove_css_class("highlighted")
            row.remove_css_class("blue")
        
        if self.launch_button:
            self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
            self.launch_button.set_tooltip_text("Play")


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
            #GLib.idle_add(self.create_script_list)
            #self.create_script_list()
        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            if self.initializing_template:
                pass #keep showing spinner
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
        
        if  self.command_line_file:
            print("Trying to process file inside on template initialized")

            GLib.idle_add(self.show_processing_spinner)
            self.process_cli_file(self.command_line_file)

    def load_icon(self, script):
        icon_name = script.stem + ".png"
        icon_dir = script.parent
        icon_path = icon_dir / icon_name
        default_icon_path = self.get_default_icon_path()

        try:
            # Load the icon at a higher resolution
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon_path), 128, 128)
            # Scale down to the desired size
            scaled_pixbuf = pixbuf.scale_simple(64, 64, GdkPixbuf.InterpType.BILINEAR)
            return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
        except Exception:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(default_icon_path), 128, 128)
                scaled_pixbuf = pixbuf.scale_simple(64, 64, GdkPixbuf.InterpType.BILINEAR)
                return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
            except Exception:
                return None

    def load_icon_for_list(self, script):
        icon_name = script.stem + ".png"
        icon_dir = script.parent
        icon_path = icon_dir / icon_name
        default_icon_path = self.get_default_icon_path()

        try:
            # Load the icon at a higher resolution
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon_path), 128, 128)
            # Scale down to the desired size
            scaled_pixbuf = pixbuf.scale_simple(32, 32, GdkPixbuf.InterpType.BILINEAR)
            return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
        except Exception:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(default_icon_path), 128, 128)
                scaled_pixbuf = pixbuf.scale_simple(32, 32, GdkPixbuf.InterpType.BILINEAR)
                return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
            except Exception:
                return None
                
    def load_icon_for_title(self, script):
        icon_name = script.stem + ".png"
        icon_dir = script.parent
        icon_path = icon_dir / icon_name
        default_icon_path = self.get_default_icon_path()

        try:
            # Load the icon at a higher resolution
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon_path), 128, 128)
            # Scale down to the desired size
            scaled_pixbuf = pixbuf.scale_simple(24, 24, GdkPixbuf.InterpType.BILINEAR)
            return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
        except Exception:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(default_icon_path), 128, 128)
                scaled_pixbuf = pixbuf.scale_simple(24, 24, GdkPixbuf.InterpType.BILINEAR)
                return Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
            except Exception:
                return None

    def create_icon_title_widget(self, script):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        icon = self.load_icon_for_title(script)
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
                    self.show_error_dialog("Invalid Directory", "The selected directory does not appear to be a valid Wine directory.")
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
        os.makedirs(dst, exist_ok=True)
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
                
    def show_error_dialog(self, title, message):
        dialog = Gtk.Window(transient_for=self.window, modal=True, title=title)
        dialog.set_default_size(300, 100)
        dialog.set_deletable(True)

        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_area.set_margin_start(10)
        content_area.set_margin_end(10)
        content_area.set_margin_top(10)
        content_area.set_margin_bottom(10)
        dialog.set_child(content_area)

        label = Gtk.Label(label=message)
        content_area.append(label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_halign(Gtk.Align.END)
        content_area.append(button_box)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda btn: dialog.destroy())
        button_box.append(close_button)

        dialog.present()

    def disable_open_button(self):
        if self.open_button:
            self.open_button.set_sensitive(False)
        print("Open button disabled.")

    def enable_open_button(self):
        if self.open_button:
            self.open_button.set_sensitive(True)
        print("Open button enabled.")
        
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
                    message = f"{os.getcwd()}||{args.file}"
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


