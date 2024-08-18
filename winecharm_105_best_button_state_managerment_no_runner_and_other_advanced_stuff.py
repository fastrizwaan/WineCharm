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

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango  # Add Pango here


version = "0.77+2"
# Constants
winecharmdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm")).resolve()
prefixes_dir = winecharmdir / "Prefixes"
templates_dir = winecharmdir / "Templates"
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
        super().__init__(application_id='io.github.fastrizwaan.WineCharm')
        Adw.init()
        self.connect("activate", self.on_activate)
        self.connect("startup", self.on_startup)

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

        # Register the SIGINT signal handler
        signal.signal(signal.SIGINT, self.handle_sigint)

        self.hamburger_actions = [
            ("🛠️ Settings...", self.on_settings_clicked),
            ("☠️ Kill all...", self.on_kill_all_clicked),
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
                background-color: rgba(111, 111, 111, 0.15); 
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

        # Signal handler for cleanup
        signal.signal(signal.SIGINT, self.handle_sigint)

    def on_settings_clicked(self, action=None, param=None):
        print("Settings action triggered")
        # You can add code here to open a settings window or dialog.

    def on_kill_all_clicked(self, action=None, param=None):

        try:
            # Get the PID of the WineCharm application
            winecharm_pid_output = subprocess.check_output(["pgrep", "-aif", do_not_kill]).decode()
            winecharm_pid_lines = winecharm_pid_output.splitlines()
            winecharm_pids = [int(line.split()[0]) for line in winecharm_pid_lines]

            try:
                # Get the list of all Wine exe processes
                wine_exe_output = subprocess.check_output(["pgrep", "-aif", r"\.exe"]).decode()
                wine_exe_lines = wine_exe_output.splitlines()

                # Extract PIDs and reverse the list to kill child processes first
                pids = []
                for line in wine_exe_lines:
                    columns = line.split()
                    pid = int(columns[0])
                    if pid != 1 and pid not in winecharm_pids:  # Skip PID 1 and WineCharm PIDs
                        pids.append(pid)
                pids.reverse()

                # Kill the processes
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                        print(f"Terminated process with PID: {pid}")
                    except ProcessLookupError:
                        print(f"Process with PID {pid} not found")
                    except PermissionError:
                        print(f"Permission denied to kill PID: {pid}")
            except subprocess.CalledProcessError:
                print("No matching Wine exe processes found.")

        except subprocess.CalledProcessError as e:
            print(f"Error retrieving process list: {e}")

        # Optionally, clear the running processes dictionary
        self.running_processes.clear()
        
        self.check_running_processes_and_update_buttons()
#        self.create_script_list()
        print("All Wine exe processes killed except PID 1 and WineCharm processes")

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
        print("Quit action triggered")
        self.quit()

    def update_script_button_state(self, script_stem):
        row = self.find_row_by_script_stem(script_stem)
        if row:
            play_button = row.get_child()
            exe_file, _, _, _ = self.extract_yaml_info(Path(script_stem))
            exe_name = Path(exe_file).name
            
            # Check if the script is running
            if exe_name in self.running_processes:
                play_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
                play_button.set_child(play_icon)
                play_button.set_tooltip_text("Stop")
                row.add_css_class("highlighted")
            else:
                play_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
                play_button.set_child(play_icon)
                play_button.set_tooltip_text("Play")
                row.remove_css_class("highlighted")


    def load_icon(self, script):
        icon_name = script.stem + ".png"
        icon_dir = script.parent
        icon_path = icon_dir / icon_name
        default_icon_path = self.get_default_icon_path()

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon_path), 32, 32)
            return Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(default_icon_path), 32, 32)
                return Gdk.Texture.new_for_pixbuf(pixbuf)
            except Exception:
                return None

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

    def on_activate(self, app):
        self.window.present()
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("enter", self.on_focus_in)
        focus_controller.connect("leave", self.on_focus_out)
        self.window.add_controller(focus_controller)

    def on_focus_in(self, controller):
        self.monitoring_active = True
        self.start_monitoring()

        # Recheck processes and update the UI
        self.check_running_processes_and_update_buttons()

    def on_focus_out(self, controller):
        self.monitoring_active = False

    def start_monitoring(self):
        if not hasattr(self, '_monitoring_id'):
            self._monitoring_id = GLib.timeout_add_seconds(2, self.check_running_processes_and_update_buttons)

    def stop_monitoring(self):
        if hasattr(self, '_monitoring_id'):
            GLib.source_remove(self._monitoring_id)
            delattr(self, '_monitoring_id')

    def handle_sigint(self, signum, frame):
        if SOCKET_FILE.exists():
            SOCKET_FILE.unlink()
        self.quit()

    def quit_app(self, action=None, param=None):
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

        self.search_button = Gtk.ToggleButton()
        search_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        self.search_button.set_child(search_icon)
        self.search_button.connect("toggled", self.on_search_button_clicked)
        self.search_button.add_css_class("flat")
        self.headerbar.pack_start(self.search_button)

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

        self.button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.button_box.set_halign(Gtk.Align.CENTER)
        open_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
        open_label = Gtk.Label(label="Open")

        self.button_box.append(open_icon)
        self.button_box.append(open_label)

        self.open_button = Gtk.Button()
        self.open_button.set_child(self.button_box)
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
        #self.scrolled.add_css_class("flowbox-background")

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_halign(Gtk.Align.FILL)
        self.flowbox.set_max_children_per_line(4)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_vexpand(True)
        self.flowbox.set_hexpand(True)
        self.scrolled.set_child(self.flowbox)

        self.window.present()

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
                self.show_processing_spinner("Processing...")
                threading.Thread(target=self.process_file, args=(file_path,)).start()
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")
        finally:
            self.window.set_visible(True)
        
    def on_back_button_clicked(self, button):
        print("Back button clicked")

        # Restore the script list
        self.create_script_list()
        

        # Reset the header bar title and visibility of buttons
        self.window.set_title("Wine Charm")
        self.headerbar.set_title_widget(None)
        self.menu_button.set_visible(True)
        self.search_button.set_visible(True)
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
        self.flowbox.remove_all()
        self.script_buttons = {}

        scripts = self.find_python_scripts()
        for script in scripts:
            row = self.create_script_row(script)
            if row:
                self.flowbox.append(row)
                self.script_buttons[script.stem] = row

    def create_script_row(self, script):
        exe_file, _, _, _ = self.extract_yaml_info(script)
        exe_name = Path(exe_file).name

        button = Gtk.Button()
        button.set_hexpand(True)
        button.set_halign(Gtk.Align.FILL)
        button.add_css_class("flat")
        button.add_css_class("normal-font")
        button.set_size_request(390, 36)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button.set_child(hbox)

        icon = self.load_icon(script)
        icon_image = Gtk.Image.new_from_paintable(icon)
        icon_image.set_pixel_size(32)
        hbox.append(icon_image)

        label_text = script.stem.replace("_", " ")
        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        label.set_hexpand(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        hbox.append(label)

        if script.stem in self.new_scripts:
            label.set_markup(f"<b>{label.get_text()}</b>")

        button.label = label

        button.connect("clicked", lambda btn: self.show_options_for_script(script, button))

        # Store the button in the dictionary using exe_name as the key
        self.script_buttons[exe_name] = button

        return button

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

    def show_options_for_script(self, script, row):
        self.main_frame.set_child(Gtk.Label(label=f"Options for {script.stem}"))
        self.replace_open_button_with_launch(script, row)
        self.update_script_button_state(script.stem)

    def replace_open_button_with_launch(self, script, row):
        if self.open_button.get_parent():
            self.vbox.remove(self.open_button)

        self.launch_button = Gtk.Button()
        self.launch_button.set_size_request(390, 36)

        exe_file, _, _, _ = self.extract_yaml_info(script)
        exe_name = Path(exe_file).name

        if exe_name in self.running_processes:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
            self.launch_button.set_tooltip_text("Stop")
        else:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
            self.launch_button.set_tooltip_text("Play")

        self.launch_button.set_child(launch_icon)
        self.launch_button.connect("clicked", lambda btn: self.toggle_play_stop(script, self.launch_button, row))

        # Store the exe_name associated with this launch button
        self.launch_button_exe_name = exe_name

        self.vbox.prepend(self.launch_button)
        self.launch_button.set_visible(True)


    def toggle_play_stop(self, script, play_stop_button, row):
        exe_file, _, _, _ = self.extract_yaml_info(script)
        exe_name = Path(exe_file).name

        if exe_name in self.running_processes:
            self.terminate_script(script)
            play_stop_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
            play_stop_button.set_tooltip_text("Play")
            row.remove_css_class("highlighted")
        else:
            self.launch_script(script, play_stop_button, row)

    def launch_script(self, script, play_stop_button, row):
        exe_file, wineprefix, progname, script_args = self.extract_yaml_info(script)
        exe_name = Path(exe_file).name

        command = f"cd {shlex.quote(str(Path(exe_file).parent))} && WINEPREFIX={shlex.quote(str(wineprefix))} wine {shlex.quote(str(exe_name))} {script_args}"

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                preexec_fn=os.setsid,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.running_processes[exe_name] = {"row": row, "script": script, "exe_name": exe_name, "pid": process.pid}

            play_stop_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
            play_stop_button.set_tooltip_text("Stop from launch_script")
            row.add_css_class("highlighted")

        except Exception as e:
            print(f"Error launching script: {e}")


    def terminate_script(self, script):
        exe_file, _, _, _ = self.extract_yaml_info(script)
        exe_name = Path(exe_file).name

        if exe_name in self.running_processes:
            process_info = self.running_processes[exe_name]
            pid = process_info.get("pid")

            try:
                if pid:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                del self.running_processes[exe_name]
            except Exception as e:
                print(f"Error terminating script {script}: {e}")


    def check_running_processes_and_update_buttons(self):
        if not self.monitoring_active:
                self.stop_monitoring()
                return False
        try:
            # Retrieve running processes
            pgrep_output = subprocess.check_output(["pgrep", "-aif", r"\.exe"]).decode().splitlines()

            current_running_processes = {}
            for script in self.find_python_scripts():
                exe_file, _, _, _ = self.extract_yaml_info(script)
                exe_name = Path(exe_file).name

                matching_processes = [line for line in pgrep_output if exe_name in line]

                if matching_processes:
                    for process in matching_processes:
                        pid = int(process.split()[0])
                        command_line = process.split(None, 1)[1]

                        if exe_name in command_line:
                            row = self.find_row_by_exe_name(exe_name)
                            if row:
                                current_running_processes[exe_name] = {"row": row, "script": script, "exe_name": exe_name, "pid": pid}

                                if exe_name not in self.running_processes:
                                    self.running_processes[exe_name] = current_running_processes[exe_name]

                                row.add_css_class("highlighted")

                                # Only update the launch button if it belongs to this script
                                if self.launch_button and self.launch_button_exe_name == exe_name:
                                    self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
                                    self.launch_button.set_tooltip_text("Stop")

                else:
                    self.process_ended(exe_name)

            self.cleanup_ended_processes(current_running_processes)

        except subprocess.CalledProcessError as e:
            pass

        return True

    def cleanup_ended_processes(self, current_running_processes):
        if not self.monitoring_active:
                self.stop_monitoring()
                return False
        for exe_name, process_info in list(self.running_processes.items()):
            if exe_name not in current_running_processes:
                row = process_info["row"]
                if row:
                    row.remove_css_class("highlighted")
                if self.launch_button:
                    self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                    self.launch_button.set_tooltip_text("Play")
                del self.running_processes[exe_name]

        self.running_processes = current_running_processes

    def handle_no_processes_found(self):
        for script_key, process_info in self.running_processes.items():
            row = process_info["row"]
            if row:
                row.remove_css_class("highlighted")
            if self.launch_button:
                print("Settings play button after highlight in handle_no_processes_found 55555")
                self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                self.launch_button.set_tooltip_text("Shifa Play")
                        # Process the lnk files after the process has ended
            script_path = process_info.get("script")
            print(f"script_path: {script_path}")
            if script_path and script_path.exists():
                wineprefix = self.extract_yaml_info(script_path)[1]
                if wineprefix:
                    wineprefix_path = Path(wineprefix)  # Convert wineprefix to a Path object
                    # Run the script creation in a background thread to avoid blocking the main process
                    #self.create_scripts_for_lnk_files(wineprefix_path)
                    print("Launching create_scripts_for_lnk_files...")
                    #threading.Thread(target=self.create_scripts_for_lnk_files, args=(wineprefix_path,)).start()
                    self.create_scripts_for_lnk_files(wineprefix_path)
        self.running_processes.clear()

    def find_row_by_exe_name(self, exe_name):
        return self.script_buttons.get(exe_name)

    def generate_script_key(self, script):
        return hashlib.sha256(str(script).encode()).hexdigest()

    def extract_yaml_info(self, script):
        if not script.exists():
            raise FileNotFoundError(f"Script file not found: {script}")
        with open(script, 'r') as file:
            try:
                data = yaml.safe_load(file)
            except yaml.YAMLError as e:
                print(f"Error loading YAML file {script}: {e}")
                data = {}
        return (
            str(Path(data.get('exe_file', '')).expanduser().resolve()), 
            str(Path(data.get('wineprefix', '')).expanduser().resolve()), 
            data.get('progname', ''), 
            data.get('args', '')
        )


    def create_yaml_file(self, exe_path, prefix_dir=None, use_exe_name=False):
        exe_file = Path(exe_path).resolve()
        exe_name = exe_file.stem
        exe_no_space = exe_name.replace(" ", "_")

        sha256_hash = hashlib.sha256()
        with open(exe_file, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        sha256sum = sha256_hash.hexdigest()[:10]

        if prefix_dir is None:
            prefix_dir = prefixes_dir / f"{exe_no_space}-{sha256sum}"
            if not prefix_dir.exists():
                if default_template.exists():
                    self.copy_template(prefix_dir)
                else:
                    prefix_dir.mkdir(parents=True, exist_ok=True)
                    print(f"Created prefix directory: {prefix_dir}")

        wineprefix_name = prefix_dir.name

        product_cmd = [
            'exiftool', shlex.quote(str(exe_file))
        ]

        product_output = self.run_command(" ".join(product_cmd))
        if product_output is None:
            print(f"Error: Failed to retrieve product name for {exe_file}")
            productname = exe_no_space
        else:
            productname_match = re.search(r'Product Name\s+:\s+(.+)', product_output)
            productname = productname_match.group(1).strip() if productname_match else exe_no_space

        if use_exe_name or "setup" in exe_name.lower() or "install" in exe_name.lower():
            progname = exe_name
        elif use_exe_name or "setup" in productname.lower() or "install" in productname.lower():
            progname = productname
        else:
            progname = productname if productname and not any(char.isdigit() for char in productname) and productname.isascii() else exe_no_space

        yaml_data = {
            'exe_file': str(exe_file).replace(str(Path.home()), "~"),
            'wineprefix': str(prefix_dir).replace(str(Path.home()), "~"),
            'progname': progname,
            'args': "",
            'sha256sum': sha256_hash.hexdigest()
        }
        
        yaml_file_path = prefix_dir / f"{progname.replace(' ', '_')}.charm"
        with open(yaml_file_path, 'w') as yaml_file:
            yaml.dump(yaml_data, yaml_file)

        icon_path = self.extract_icon(exe_file, prefix_dir, exe_no_space, progname)
        self.create_desktop_entry(progname, yaml_file_path, icon_path, prefix_dir)

        self.add_or_update_script_row(yaml_file_path)
        self.create_script_list()


    def add_or_update_script_row(self, script_path):
        script_name = script_path.stem.replace("_", " ")
        existing_row = None

        for row in self.flowbox:
            box = row.get_child()
            if box:
                label_widget = box.get_first_child().get_next_sibling()
                if label_widget and label_widget.get_text() == script_name:
                    existing_row = row
                    break

        if existing_row:
            self.flowbox.remove(existing_row)

        new_row = self.create_script_row(script_path)
        self.flowbox.insert(new_row, 0)

    def extract_icon(self, exe_file, wineprefix, exe_no_space, progname):
        icon_path = wineprefix / f"{progname.replace(' ', '_')}.png"
        ico_path = tempdir / f"{exe_no_space}.ico"

        try:
            tempdir.mkdir(parents=True, exist_ok=True)

            bash_cmd = f"""
            wrestool -x -t 14 {shlex.quote(str(exe_file))} > {shlex.quote(str(ico_path))} 2>/dev/null
            icotool -x {shlex.quote(str(ico_path))} -o {shlex.quote(str(tempdir))} 2>/dev/null
            """
            try:
                subprocess.run(bash_cmd, shell=True, executable='/bin/bash', check=True)
            except subprocess.CalledProcessError as e:
                print(f"Warning: Command failed with error {e.returncode}, but continuing.")

            png_files = sorted(tempdir.glob(f"{exe_no_space}*.png"), key=lambda x: x.stat().st_size, reverse=True)
            if png_files:
                best_png = png_files[0]
                shutil.move(best_png, icon_path)

        finally:
            for file in tempdir.glob(f"{exe_no_space}*"):
                file.unlink()
            tempdir.rmdir()

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
        
        product_name_map = {}
        
        for exe_file in exe_files:
            product_name = self.get_product_name(exe_file)
            if product_name:
                if product_name not in product_name_map:
                    product_name_map[product_name] = []
                product_name_map[product_name].append(exe_file)
            else:
                self.create_yaml_file(exe_file, wineprefix)
        
        for product_name, exe_files in product_name_map.items():
            for exe_file in exe_files:
                if len(exe_files) > 1:
                    self.create_yaml_file(exe_file, wineprefix, use_exe_name=True)
                else:
                    self.create_yaml_file(exe_file, wineprefix, use_exe_name=False)

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
        #self.monitoring_active = True
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

        # Replace the previous 'options' list with this simplified version
        options = [
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

            # Simplified connect statement
            options_flowbox.append(option_button)

            option_button.connect(
                "clicked",
                lambda btn, cb=callback, sc=script, ob=option_button:
                self.callback_wrapper(cb, sc, ob)
            )

        # Set the header bar title to the script's icon and name
        self.headerbar.set_title_widget(self.create_icon_title_widget(script))
        self.menu_button.set_visible(False)
        self.search_button.set_visible(False)

        # Ensure the back button is added and visible
        if self.back_button.get_parent() is None:
            self.headerbar.pack_start(self.back_button)
        self.back_button.set_visible(True)

        # Remove the "Open" button
        self.open_button.set_visible(False)

        # Replace the "Open" button with the "Launch" button
        self.replace_open_button_with_launch(script, row)

        # Call update_execute_button_icon only after options_listbox is set up
        self.update_execute_button_icon(script)
        self.selected_row = None

    def open_terminal(self, script, *args):
        wineprefix = Path(script).parent
        print(f"Opening terminal for {wineprefix}")
        if not wineprefix.exists():
            wineprefix.mkdir(parents=True, exist_ok=True)

        if shutil.which("flatpak-spawn"):
            command = [
                "flatpak-spawn",
                "--host",
                "gnome-terminal",
                "--wait",
                "--",
                "flatpak",
                "--filesystem=host",
                "--filesystem=~/.var/app",
                "--command=bash",
                "run",
                "io.github.fastrizwaan.WineCharm",
                "--norc",
                "-c",
                rf'export PS1="[\u@\h:\w]\\$ "; export WINEPREFIX={shlex.quote(str(wineprefix))}; cd {shlex.quote(str(wineprefix))}; exec bash --norc -i'
            ]
        else:
            command = [
                "gnome-terminal",
                "--wait",
                "--",
                "bash",
                "--norc",
                "-c",
                rf'export PS1="[\u@\h:\w]\\$ "; export WINEPREFIX={shlex.quote(str(wineprefix))}; cd {shlex.quote(str(wineprefix))}; exec bash --norc -i'
            ]
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening terminal: {e}")

    def install_dxvk_vkd3d(self, script, button):
        wineprefix = script.parent
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

    def create_icon_title_widget(self, script):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        icon = self.load_icon(script)
        icon_image = Gtk.Image.new_from_paintable(icon)
        icon_image.set_pixel_size(24)
        hbox.append(icon_image)

        label = Gtk.Label(label=f"<b>{script.stem.replace('_', ' ')}</b>")
        label.set_use_markup(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        hbox.append(label)

        return hbox
        
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
            if rename:
                _, _, progname, _ = self.extract_yaml_info(script)
                entry = Gtk.Entry()
                entry.set_text(progname)
            else:
                exe_file, wineprefix, progname, script_args = self.extract_yaml_info(script)
                entry = Gtk.Entry()
                entry.set_text(script_args or "-opengl -SkipBuildPatchPrereq")
            
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
                ok_button.connect("clicked", lambda btn: self.on_ok_rename_button_clicked(parent, button, entry, script))
            else:
                ok_button.connect("clicked", lambda btn: self.on_ok_button_clicked(parent, button, entry, script))

    def show_processing_spinner(self, message="Processing..."):
        self.spinner = Gtk.Spinner()
        self.spinner.start()
        self.button_box.append(self.spinner)

        box = self.open_button.get_child()
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Image):
                child.set_visible(False)
            elif isinstance(child, Gtk.Label):
                child.set_label(message)
            child = child.get_next_sibling()

    def hide_processing_spinner(self):
        if self.spinner:
            self.spinner.stop()
            self.button_box.remove(self.spinner)

        box = self.open_button.get_child()
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Image):
                child.set_visible(True)
            elif isinstance(child, Gtk.Label):
                child.set_label("Open...")
            child = child.get_next_sibling()

    def process_file(self, file_path):
        try:
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

    def process_ended(self, exe_name):
        if not self.monitoring_active:
                self.stop_monitoring()
                return False
        process_info = self.running_processes.get(exe_name)

        if process_info:
            row = process_info.get("row")
            if row:
                row.remove_css_class("highlighted")

            if self.launch_button:
                self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                self.launch_button.set_tooltip_text("Play")

            script_path = process_info.get("script")
            if script_path and script_path.exists():
                wineprefix = self.extract_yaml_info(script_path)[1]
                if wineprefix:
                    wineprefix_path = Path(wineprefix)
                    self.create_scripts_for_lnk_files(wineprefix_path)
            
            if exe_name in self.running_processes:
                del self.running_processes[exe_name]




    def copy_template(self, prefix_dir):
        try:
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





######## Refine

    def on_focus_in(self, controller):
        self.monitoring_active = True
        
        # Start monitoring again
        self.start_monitoring()

        # Recheck processes and update the UI
        self.check_running_processes_and_update_buttons()

        # Ensure any ended processes are cleaned up
        current_running_processes = {}

        try:
            pgrep_output = subprocess.check_output(["pgrep", "-aif", r"\.exe"]).decode().splitlines()
        except subprocess.CalledProcessError as e:
            # If pgrep returns a non-zero exit status, it means no processes were found
            pgrep_output = []

        for script in self.find_python_scripts():
            exe_file, _, _, _ = self.extract_yaml_info(script)
            exe_name = Path(exe_file).name

            matching_processes = [line for line in pgrep_output if exe_name in line]

            if matching_processes:
                for process in matching_processes:
                    pid = int(process.split()[0])
                    command_line = process.split(None, 1)[1]

                    if exe_name in command_line:
                        row = self.find_row_by_exe_name(exe_name)
                        if row:
                            current_running_processes[exe_name] = {"row": row, "script": script, "exe_name": exe_name, "pid": pid}
                            row.add_css_class("highlighted")

                            # Update the launch button if it belongs to this script
                            if self.launch_button and self.launch_button_exe_name == exe_name:
                                self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
                                self.launch_button.set_tooltip_text("Stop")

        # Clean up ended processes
        self.cleanup_ended_processes(current_running_processes)






















###################################################################################################





###################################################################################################




def main():
    app = WineCharmApp()
    app.run(None)

if __name__ == "__main__":
    main()

