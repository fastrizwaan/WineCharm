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

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango

author = "Mohammed Asif Ali Rizvan"
email = "fast.rizwaan@gmail.com"
copyright = "GNU General Public License (GPLv3+)"
website = "https://github.com/fastrizwaan/WineCharm"
appname = "WineCharm"
version = "0.6+4"
do_not_kill = "bin/winecharm"

# These need to be dynamically updated:
runner = ""  # which wine
wine_version = ""  # runner --version
template = ""  # default: WineCharm-win64 ; #if not found in settings.yaml at winecharm directory add default_template
arch = ""  # default: win64 ; # #if not found in settings.yaml at winecharm directory add win64

winecharmdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm")).resolve()
prefixes_dir = winecharmdir / "Prefixes"
templates_dir = winecharmdir / "Templates"
default_template = templates_dir / "WineCharm-win64"

applicationsdir = Path(os.path.expanduser("~/.local/share/applications")).resolve()
tempdir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WineCharm/data/tmp")).resolve()
iconsdir = Path(os.path.expanduser("~/.local/share/icons")).resolve()

SOCKET_FILE = winecharmdir / "winecharm_socket"

class WineCharmApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.fastrizwaan.WineCharm')
        Adw.init()
        self.connect("activate", self.on_activate)
        self.connect("startup", self.on_startup)
        self.wine_process_running = False
        self.selected_script = None
        self.selected_script_name = None
        self.selected_row = None
        self.spinner = None
        self.new_scripts = set()
        self.initializing_template = False
        self.running_processes = {}
        self.play_stop_handlers = {}
        self.options_listbox = None
        self.search_active = False
        self.command_line_file = None
        self.monitoring_active = True  # Flag to control monitoring

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

    def on_activate(self, app):
        self.window.present()

    def on_shutdown(self, app):
        # Perform any necessary cleanup actions here
        if SOCKET_FILE.exists():
            SOCKET_FILE.unlink()

    def handle_sigint(self, signum, frame):
        print("Received SIGINT. Cleaning up and exiting.")
        if os.path.exists(SOCKET_FILE):
            os.remove(SOCKET_FILE)
        self.quit()


    def quit_app(self, action=None, param=None):
        self.quit()

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
                            # Extract the current working directory and file path
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
                                        print(f"Resolved absolute file path: {abs_file_path}")  # Debugging output
                                        GLib.idle_add(self.process_cli_file, str(abs_file_path))
                                    else:
                                        print(f"File does not exist: {abs_file_path}")
                            else:
                                print(f"No files matched the pattern: {file_path}")

        threading.Thread(target=server_thread, daemon=True).start()

    def process_cli_file_when_ready(self):
        while self.initializing_template:
            time.sleep(1)
        GLib.idle_add(self.process_cli_file, self.command_line_file)

    def process_cli_file(self, file_path):
        self.show_processing_spinner("Processing...")
        threading.Thread(target=self._process_cli_file, args=(file_path,)).start()

    def _process_cli_file(self, file_path):
        print(f"Processing CLI file: {file_path}")
        abs_file_path = str(Path(file_path).resolve())
        print(f"Resolved absolute CLI file path: {abs_file_path}")

        try:
            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return
            self.create_yaml_file(abs_file_path, None)
            GLib.idle_add(self.create_script_list)
        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            GLib.idle_add(self.hide_processing_spinner)

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

    def generate_about_yml(self):
        about_file_path = winecharmdir / "About.yml"
        if about_file_path.exists():
            print(f"{about_file_path} already exists. Skipping generation.")
            return

        about_data = {
            "Application": appname,
            "Version": version,
            "Copyright": copyright,
            "Website": website,
            "Author": author,
            "E-mail": email,
            "Wine_Runner": runner,
            "Wine_Version": wine_version,
            "Template": template,
            "Wine_Arch": arch,
            "WineZGUI_Prefix": str(winecharmdir),
            "Wine_Prefix": str(default_template),
            "Creation_Date": time.strftime("%a %b %d %I:%M:%S %p %Z %Y")
        }

        with open(about_file_path, 'w') as about_file:
            yaml.dump(about_data, about_file, default_flow_style=False)
        print(f"Generated {about_file_path}")

    def generate_settings_yml(self):
        settings_file_path = winecharmdir / "settings.yml"
        if settings_file_path.exists():
            print(f"{settings_file_path} already exists. Skipping generation.")
            return

        settings_data = {
            "arch": arch,
            "template": str(default_template),
            "runner": runner
        }

        with open(settings_file_path, 'w') as settings_file:
            yaml.dump(settings_data, settings_file, default_flow_style=False)
        print(f"Generated {settings_file_path}")



    def update_script_button_state(self, script_stem):
        row = self.find_row_by_script_stem(script_stem)
        if row:
            # Find the play button in the row's button box
            play_button = row.get_first_child()  # Assuming row itself is the button container

            # Update the play button to show a "Stop" icon and tooltip
            play_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
            play_button.set_child(play_icon)
            play_button.set_tooltip_text("Stop")

            # Add the 'highlighted' CSS class to the row
            row.add_css_class("highlighted")

            # Update the label text to include a "*" symbol indicating the script is running
            label = play_button.get_child().get_first_child().get_next_sibling()  # Assuming label is the second child in the box
            if label and isinstance(label, Gtk.Label):
                label_text = label.get_text()
                if not label_text.endswith(" *"):
                    label.set_text(f"{label_text} *")

            # Update the running processes dictionary with the relevant details
            self.running_processes[script_stem] = {
                "proc": None,
                "pid": None,
                "pgid": None,
                "play_button": play_button,
                "play_icon": play_icon,
                "options_button": row.get_first_child(),
                "gear_icon": Gtk.Image.new_from_icon_name("emblem-system-symbolic"),
                "script": next((s for s in self.find_python_scripts() if s.stem == script_stem), None)
            }


    def initialize_template(self, template_dir, callback):
        if not template_dir.exists():
            self.initializing_template = True
            if self.open_button_handler_id is not None:
                self.open_button.disconnect(self.open_button_handler_id)

            self.spinner = Gtk.Spinner()
            self.spinner.start()
            self.button_box.append(self.spinner)

            box = self.open_button.get_child()
            child = box.get_first_child()
            while child:
                if isinstance(child, Gtk.Image):
                    child.set_visible(False)
                elif isinstance(child, Gtk.Label):
                    child.set_label(f"Initializing...")
                child = child.get_next_sibling()

            template_dir.mkdir(parents=True, exist_ok=True)

            def initialize():
                wineboot_cmd = f"WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"
                winetricks_vkd3d = f"WINEPREFIX='{template_dir}' winetricks vkd3d"
                winetricks_dxvk = f"WINEPREFIX='{template_dir}' winetricks dxvk"
                winetricks_corefonts = f"WINEPREFIX='{template_dir}' winetricks corefonts"
                try:
                    subprocess.run(wineboot_cmd, shell=True, check=True)
                    self.remove_symlinks_from_drive_c_users(template_dir)
                    subprocess.run(winetricks_vkd3d, shell=True, check=True)
                    subprocess.run(winetricks_dxvk, shell=True, check=True)
                    subprocess.run(winetricks_corefonts, shell=True, check=True)
                    print(f"Template initialized: {template_dir}")
                except subprocess.CalledProcessError as e:
                    print(f"Error initializing template: {e}")
                finally:
                    GLib.idle_add(callback)

            thread = threading.Thread(target=initialize)
            thread.start()

    def remove_symlinks_from_drive_c_users(self, template_dir):
        users_dir = template_dir / "drive_c" / "users"
        for user_dir in users_dir.iterdir():
            if user_dir.is_dir():
                for item in user_dir.iterdir():
                    if item.is_symlink():
                        target_path = item.resolve()
                        item.unlink()
                        item.mkdir(parents=True, exist_ok=True)
                        print(f"Replaced symlink with directory: {item}")

    def copy_template(self, prefix_dir):
        if not prefix_dir.exists():
            try:
                print(f"Copying default template to {prefix_dir}")
                shutil.copytree(default_template, prefix_dir, symlinks=True)
            except shutil.Error as e:
                for src, dst, err in e.args[0]:
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                    else:
                        print(f"Skipping {src} -> {dst} due to error: {err}")
        else:
            print(f"Prefix directory {prefix_dir} already exists. Skipping copying process.")

    def on_template_initialized(self):
        self.initializing_template = False
        if self.spinner:
            self.spinner.stop()
            self.button_box.remove(self.spinner)
            self.spinner = None

        box = self.open_button.get_child()
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Image):
                child.set_visible(True)
            elif isinstance(child, Gtk.Label):
                child.set_label("Open...")
            child = child.get_next_sibling()

        if self.open_button_handler_id is not None:
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_exe_clicked)

        print("Template initialization completed and UI updated.")

        # Process the CLI file if provided after template initialization
        if self.command_line_file:
            self.process_cli_file(self.command_line_file)


    def check_required_programs(self):
        # Check if flatpak-spawn is available
        if shutil.which("flatpak-spawn"):
            return []

        # Check other required programs if flatpak-spawn is not available
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
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_exe_clicked)
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
        self.update_running_script_buttons()

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


    def on_open_exe_clicked(self, button):
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
            GLib.idle_add(self.create_script_list)
        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            GLib.idle_add(self.hide_processing_spinner)
            
    def create_script_list(self):
        self.flowbox.remove_all()
        scripts = self.find_python_scripts()
        for script in scripts:
            row = self.create_script_row(script)
            self.flowbox.append(row)
            self.toggle_running_button_highlight(script.stem, row)  # Correct arguments


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

    def extract_yaml_info(self, script):
        if not script.exists():
            raise FileNotFoundError(f"Script file not found: {script}")
        with open(script, 'r') as file:
            try:
                data = yaml.safe_load(file)
            except yaml.YAMLError as e:
                print(f"Error loading YAML file {script}: {e}")
                data = {}
        return (str(Path(data.get('exe_file', '')).expanduser().resolve()), 
                str(Path(data.get('wineprefix', '')).expanduser().resolve()), 
                data.get('progname', ''), 
                data.get('args', ''))

# This one is better.
    def extract_icon(self, exe_file, wineprefix, exe_no_space, progname):
        icon_path = wineprefix / f"{progname.replace(' ', '_')}.png"
        #tempdir = Path("/tmp/tempdir")
        ico_path = tempdir / f"{exe_no_space}.ico"

        try:
            # Create the temporary directory
            tempdir.mkdir(parents=True, exist_ok=True)

            # Construct the bash command
            bash_cmd = f"""
            wrestool -x -t 14 {shlex.quote(str(exe_file))} > {shlex.quote(str(ico_path))}
            icotool -x {shlex.quote(str(ico_path))} -o {shlex.quote(str(tempdir))}
            """
            
            # Run the bash command
            result = subprocess.run(bash_cmd, shell=True, executable='/bin/bash', capture_output=True, text=True)
            
            # Check for errors
            if result.returncode != 0:
                print(f"Error: {result.stderr}")
            #    raise subprocess.CalledProcessError(result.returncode, bash_cmd)
            
            # Find the largest PNG file
            png_files = sorted(tempdir.glob(f"{exe_no_space}*.png"), key=lambda x: x.stat().st_size, reverse=True)
            if png_files:
                best_png = png_files[0]
                shutil.move(best_png, icon_path)
            else:
                print("No PNG files extracted from ICO.")
        except subprocess.CalledProcessError as e:
            print(f"Error extracting icon: {e}")
        finally:
            # Clean up temporary files and directory
            for file in tempdir.glob(f"{exe_no_space}*"):
                file.unlink()
            tempdir.rmdir()

        return icon_path if icon_path.exists() else None

    def create_desktop_entry(self, progname, script_path, icon_path, wineprefix):
        desktop_file_content = f"""[Desktop Entry]
Name={progname}
Type=Application
Exec=python3 '{script_path}'
Icon={icon_path if icon_path else 'wine'}
Keywords=winecharm; game; {progname};
NoDisplay=false
StartupNotify=true
Terminal=false
Categories=Game;Utility;
"""
#       desktop_file_path = wineprefix / f"{progname}.desktop"
#       
#       with open(desktop_file_path, "w") as desktop_file:
#           desktop_file.write(desktop_file_content)

#       symlink_path = applicationsdir / f"{progname}.desktop"
#       if symlink_path.exists() or symlink_path.is_symlink():
#           symlink_path.unlink()
#       symlink_path.symlink_to(desktop_file_path)

#       if icon_path:
#           icon_symlink_path = iconsdir / f"{icon_path.name}"
#           if icon_symlink_path.exists() or symlink_path.is_symlink():
#               icon_symlink_path.unlink(missing_ok=True)
#           icon_symlink_path.symlink_to(icon_path)

    def add_or_update_script_row(self, script_path):
        script_name = script_path.stem.replace("_", " ")
        existing_row = None

        # Iterate over the FlowBox's children using their index
        for i in range(self.flowbox.get_max_children_per_line()):
            child = self.flowbox.get_child_at_index(i)
            if not child:
                continue  # If child is None, continue to the next iteration
            box = child.get_child()  # Get the box inside the FlowBoxChild
            if box:
                label_widget = box.get_first_child().get_next_sibling()  # Assuming label is the second child
                if label_widget and label_widget.get_text() == script_name:
                    existing_row = child
                    break

        # If the row already exists, remove it
        if existing_row:
            self.flowbox.remove(existing_row)

        # Add the new row
        new_row = self.create_script_row(script_path)
        self.flowbox.insert(new_row, 0)  # Insert at the top

        # Optionally, highlight new scripts
        self.new_scripts.add(script_path.stem)
        new_row.label.set_markup(f"<b>{new_row.label.get_text()}</b>")

    def embolden_new_scripts(self):
        for row in self.flowbox:
            child = row.get_child()
            if child:
                first_child = child.get_first_child()
                if first_child:
                    label_widget = first_child.get_next_sibling()
                    if label_widget and label_widget.get_text():
                        script_label = label_widget.get_text()
                        if script_label.replace(" ", "_") in self.new_scripts:
                            row.label.set_markup(f"<b>{row.label.get_text()}</b>")

    def show_about_dialog(self, action=None, param=None):
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

    def on_settings_clicked(self, action, param):
        print("Settings action triggered")

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

        print("All Wine exe processes killed except PID 1 and WineCharm processes")

        # Updating script list so that stop buttons become play buttons
        self.create_script_list()

    def on_help_clicked(self, action, param):
        print("Help action triggered")

    def on_about_clicked(self, action, param):
        self.show_about_dialog()

    def quit_app(self, action, param):
        self.quit()

    def find_python_scripts(self):
        scripts = []
        for root, dirs, files in os.walk(prefixes_dir):
            depth = root[len(str(prefixes_dir)):].count(os.sep)
            if depth < 2:
                for file in files:
                    if file.endswith(".charm"):
                        scripts.append(Path(root) / file)
            else:
                dirs[:] = []
        scripts.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return scripts

    def find_exe_path(self, wineprefix, exe_name):
        drive_c = wineprefix / "drive_c"
        for root, dirs, files in os.walk(drive_c):
            for file in files:
                if file.lower() == exe_name.lower():
                    return Path(root) / file
        return None

    def update_running_script_buttons(self):
        for script_stem, process_info in self.running_processes.items():
            row = self.find_row_by_script_stem(script_stem)
            if row:
                #play_button = row.button_box.get_first_child()
                #play_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
                #play_button.set_child(play_icon)
                #play_button.set_tooltip_text("Stop")
                row.add_css_class("highlighted")

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


    def restore_open_button(self):
        if self.open_button.get_parent() is None:
            self.vbox.prepend(self.open_button)
        self.open_button.set_visible(True)

    def find_row_by_script_stem(self, script_stem):
        for row in self.flowbox:
            child = row.get_child()
            if not child:
                continue
            first_child = child.get_first_child()
            if not first_child:
                continue
            label_widget = first_child.get_next_sibling()
            if label_widget and label_widget.get_text():
                label_text = label_widget.get_text()
                if label_text.replace(" ", "_") == script_stem:
                    return row
        return None


    def create_script_row(self, script):
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

        return button




    def stop_script(self, process_info):
        if process_info:
            proc = process_info["proc"]
            pid = process_info["pid"]
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                print(f"Terminated wine process with PID {pid}")
                play_button = process_info["play_button"]
                play_icon = process_info["play_icon"]
                options_button = process_info["options_button"]
                gear_icon = process_info["gear_icon"]
                script = process_info["script"]
                self.reset_buttons(play_button, play_icon, options_button, gear_icon, script)
            except ProcessLookupError as e:
                print(f"Error terminating wine process: {e}")
        else:
            print("No running process found")


    def show_exe_not_found_dialog(self, exe_name, exe_file, script, play_stop_button, button):
        dialog = Gtk.Dialog(
            transient_for=self.window,
            modal=True,
            title=f"{exe_name} not found"
        )
        dialog.set_default_size(300, 150)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        
        label_primary = Gtk.Label(label=f"{exe_name} not found at {Path(exe_file).parent}")
        label_secondary = Gtk.Label(label="Would you like to locate the executable file or cancel the operation?")
        label_primary.set_wrap(True)
        label_secondary.set_wrap(True)
        
        box.append(label_primary)
        box.append(label_secondary)
        
        locate_button = Gtk.Button(label=f"Locate {exe_name}")
        locate_button.connect("clicked", lambda btn: self.locate_exe_file(dialog, exe_file, script, play_stop_button, button))
        box.append(locate_button)
        
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda btn: dialog.close())
        box.append(cancel_button)
        
        dialog.set_child(box)
        dialog.present()

    def locate_exe_file(self, dialog, exe_file, script, play_stop_button, button):
        dialog.close()
        
        file_dialog = Gtk.FileDialog.new()
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        filter_model.append(self.create_file_filter())
        file_dialog.set_filters(filter_model)
        file_dialog.open(self.window, None, lambda dlg, res: self.on_locate_file_dialog_response(dlg, res, exe_file, script, play_stop_button, button))

    def on_locate_file_dialog_response(self, dialog, result, original_exe_file, script, play_stop_button, button):
        wineprefix = self.extract_yaml_info(script)
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = file.get_path()
                if file_path:
                    new_sha256sum = self.calculate_sha256sum(file_path)
                    with open(script, 'r') as file:
                        data = yaml.safe_load(file)
                    original_sha256sum = data.get('sha256sum')
                    
                    if new_sha256sum == original_sha256sum:
                        self.update_exe_file_path(script, file_path)
                        self.toggle_play_stop(script, play_stop_button, button)
                    else:
                        self.show_error_dialog("Error", "The selected file does not match the original executable.")
        except GLib.Error as e:
            print(f"An error occurred: {e}")
        finally:
            self.window.set_visible(True)
            self.create_script_list()

    def update_exe_file_path(self, script, new_file_path):
        with open(script, 'r') as file:
            data = yaml.safe_load(file)
        data['exe_file'] = str(new_file_path).replace(str(Path.home()), "~")
        with open(script, 'w') as file:
            yaml.safe_dump(data, file)
            
    def show_error_dialog(self, title, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title
        )
        dialog.props.secondary_text = message
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()             

    def calculate_sha256sum(self, file_path):
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
                



    def disconnect_play_stop_handler(self, button):
        if button in self.play_stop_handlers:
            handler_id = self.play_stop_handlers.pop(button)
            button.disconnect(handler_id)

    def reset_buttons(self, play_button, play_icon, options_button, gear_icon, script):
        play_button.set_child(play_icon)
        play_button.set_sensitive(True)
        options_button.set_child(gear_icon)
        options_button.set_tooltip_text("Settings")
        self.disconnect_play_stop_handler(play_button)
        self.play_stop_handlers[play_button] = play_button.connect("clicked", lambda btn: self.toggle_play_stop(script, play_button, self.selected_row))

    def select_row(self, button, row):
        self.listbox.select_row(row)

    def on_hover_enter(self, button_box, row):
        if self.selected_row:
            self.selected_row.button_box.set_opacity(0.0)
        button_box.set_opacity(1.0)

    def on_hover_leave(self, button_box, row):
        if row != self.selected_row:
            button_box.set_opacity(0.0)
        if self.selected_row:
            self.selected_row.button_box.set_opacity(1.0)

    def on_script_selected(self, listbox, row):
        if row:
            if self.selected_row:
                self.selected_row.label.set_markup(self.selected_row.label.get_text())
                self.selected_row.button_box.set_opacity(0.0)
            script_label = row.get_child().get_first_child().get_next_sibling().get_text()
            self.selected_script = next((script for script in self.find_python_scripts() if script.stem.replace("_", " ") == script_label), None)
            if self.selected_script:
                self.selected_script_name = self.selected_script.stem
                print(f"Script selected: {self.selected_script_name}")
                row.button_box.set_opacity(1.0)
            row.label.set_markup(f"<b>{row.label.get_text()}</b>")
            self.selected_row = row

    def on_listbox_key_pressed(self, controller, keyval, keycode, state, listbox):
        if keyval == Gdk.KEY_Return:
            selected_row = listbox.get_selected_row()
            if selected_row:
                script_label = selected_row.get_child().get_first_child().get_next_sibling().get_text()
                script = next((script for script in self.find_python_scripts() if script.stem.replace("_", " ") == script_label), None)
                if script:
                    self.show_options_for_script(script, selected_row)

    def reselect_previous_row(self):
        if self.selected_script_name:
            for row in self.flowbox:
                script_label = row.get_child().get_first_child().get_next_sibling().get_text()
                if script_label.replace(" ", "_") == self.selected_script_name:
                    self.selected_row = row
                    break

    def load_icon(self, script):
        icon_name = script.stem + ".png"
        icon_dir = script.parent
        icon_path = icon_dir / icon_name
        default_icon_path = self.get_default_icon_path()

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon_path), 32, 32)
            return Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception:
            #print(f"Icon not found: {icon_name}")
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(default_icon_path), 32, 32)
                return Gdk.Texture.new_for_pixbuf(pixbuf)
            except Exception:
                #print(f"Error loading default icon: {default_icon_path}")
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
        self.headerbar.set_title_widget(self.create_icon_title_widget(script))
        self.menu_button.set_visible(False)
        self.search_button.set_visible(False)

        if self.back_button.get_parent():
            self.headerbar.remove(self.back_button)
        self.headerbar.pack_start(self.back_button)
        self.back_button.set_visible(True)
        self.open_button.set_visible(False)

        # Replace the "Open" button with the "Launch" button
        self.replace_open_button_with_launch(script, row)

        # Call update_execute_button_icon only after options_listbox is set up
        self.update_execute_button_icon(script)
        self.selected_row = None



    def replace_open_button_with_launch(self, script, row):
        # Remove the "Open" button if it exists
        if self.open_button.get_parent():
            self.vbox.remove(self.open_button)

        # Create the "Launch" button with just the icon centered
        self.launch_button = Gtk.Button()
        self.launch_button.set_size_request(390, 36)  # Adjust the size as needed

        # Set the "Launch" icon
        if script.stem in self.running_processes:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
        else:
            launch_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")

        launch_icon.set_halign(Gtk.Align.CENTER)
        launch_icon.set_valign(Gtk.Align.CENTER)
        
        # Set the icon as the only child of the button
        self.launch_button.set_child(launch_icon)

        # Connect the "Launch" button to start the script
        self.launch_button.connect("clicked", lambda btn: self.toggle_play_stop(script, self.launch_button, row))

        # Add the "Launch" button to the top of the vbox
        self.vbox.prepend(self.launch_button)
        self.launch_button.set_visible(True)

    def on_option_button_clicked(self, callback, script, row):
        self.options_listbox.select_row(row)
        callback(script)

    def toggle_play_stop(self, script, play_stop_button, row):
        if script.stem in self.running_processes:
            self.terminate_script(script)
            play_stop_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
            play_stop_button.set_tooltip_text("Play")
            row.remove_css_class("highlighted")
        else:
            self.launch_script(script, play_stop_button, row)
            play_stop_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
            play_stop_button.set_tooltip_text("Stop")
            row.add_css_class("highlighted")

    def toggle_running_button_highlight(self, script_name, row):
        if script_name in self.running_processes:
            row.add_css_class("highlighted")
        else:
            row.remove_css_class("highlighted")



    def terminate_script(self, script):
        print(f"Terminating script: {script}")
        if script.stem in self.running_processes:
            process_info = self.running_processes.pop(script.stem, None)
            if process_info:
                exe_file, wineprefix, _, _ = self.extract_yaml_info(script)
                exe_name_upto_fifteen_chars = Path(exe_file).stem[:15]

                try:
                    # Get the WineCharm application PIDs to exclude them from termination
                    winecharm_pid_output = subprocess.check_output(["pgrep", "-aif", do_not_kill]).decode()
                    winecharm_pid_lines = winecharm_pid_output.splitlines()
                    winecharm_pids = {int(line.split()[0]) for line in winecharm_pid_lines}

                    # Get the PIDs of the processes associated with the Wine script
                    pgrep_output = subprocess.check_output(["pgrep", "-aif", exe_name_upto_fifteen_chars]).decode()
                    pids_to_kill = [int(line.split()[0]) for line in pgrep_output.splitlines()]

                    for pid in pids_to_kill:
                        if pid in winecharm_pids:
                            print(f"Skipping termination of {appname} process with PID: {pid}")
                            continue

                        try:
                            os.kill(pid, signal.SIGKILL)
                            print(f"Terminated PID: {pid}")
                        except ProcessLookupError:
                            continue
                    print(f"Terminated wine process for {script}")

                    # Update the button state after termination
                    self.process_ended(script.stem)

                except subprocess.CalledProcessError:
                    print(f"No processes found for {exe_name_upto_fifteen_chars}")
            else:
                print(f"No running process found for {script}")
        else:
            print(f"No running process found for {script}")


    def process_ended(self, script_stem):
        if script_stem in self.running_processes:
            process_info = self.running_processes.pop(script_stem, None)
            if process_info:
                row = self.find_row_by_script_stem(script_stem)
                print(f"Process ended for script: {script_stem}")
                
                # Create the "Play" icon
                play_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
                play_icon.set_halign(Gtk.Align.CENTER)
                play_icon.set_valign(Gtk.Align.CENTER)
                if hasattr(self, 'launch_button') and self.launch_button is not None:
                    self.launch_button.set_child(play_icon)
                    self.launch_button.set_tooltip_text("Play")
                    
                # After the process ends, call the method to create scripts for .lnk files
                wineprefix = Path(process_info['script'].parent)
                GLib.idle_add(self.create_scripts_for_lnk_files, wineprefix)
                self.create_script_list() # Remove highlight from button




    def update_execute_button_icon(self, script):
        child = self.options_listbox.get_first_child()
        while child:
            if isinstance(child, Gtk.ListBoxRow):
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
            child = child.get_next_sibling()

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
    def open_filemanager(self, script, *args):
        wineprefix = Path(script).parent
        print(f"Opening file manager for {wineprefix}")
        command = ["xdg-open", str(wineprefix)]
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Error opening file manager: {e}")
# BUGGY
    def install_dxvk_vkd3d(self, script, button):
        wineprefix = script.parent
        self.run_winetricks_script("vkd3d dxvk", wineprefix)
        self.create_script_list()
# /BUGGY
    def show_delete_confirmation(self, script, button):
        self.replace_button_with_overlay(script, "Delete Wineprefix?", "wineprefix", button)

    def show_delete_shortcut_confirmation(self, script, button):
        self.replace_button_with_overlay(script, "Delete shortcut?", "shortcut", button)

    def show_wine_arguments_entry(self, script, button):
        self.replace_button_with_entry_overlay(script, "Args:", button)

    def on_cancel_button_clicked(self, button, parent, original_button):
        # Restore the original button as the child of the FlowBoxChild
        parent.set_child(original_button)
        original_button.set_sensitive(True)

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

    def replace_button_with_overlay(self, script, confirmation_text, action_type, button):
        parent = button.get_parent()

        if isinstance(parent, Gtk.FlowBoxChild):
            # Create the overlay and the confirmation box
            overlay = Gtk.Overlay()

            confirmation_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            confirmation_box.set_valign(Gtk.Align.START)
            confirmation_box.set_halign(Gtk.Align.FILL)
            #confirmation_box.set_margin_top(10)
            #confirmation_box.set_margin_bottom(10)
            confirmation_box.set_margin_start(10)
            #confirmation_box.set_margin_end(10)
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


    def on_ok_button_clicked(self, parent, original_button, entry, script):
        # Reset the button before saving the arguments
        parent.set_child(original_button)
        original_button.set_sensitive(True)

        # Now call save_wine_arguments
        self.save_wine_arguments(script, entry.get_text())

    def save_wine_arguments(self, script, args):
        with open(script, 'r') as file:
            data = yaml.safe_load(file)
        data['args'] = args
        with open(script, 'w') as file:
            yaml.safe_dump(data, file)
        print(f"Saved arguments for {script}: {args}")

### Change ICON and Rename Shortcut
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


### Rename Shortcut
    def show_rename_shortcut_entry(self, script, option_button, button):
        self.replace_button_with_entry_overlay(script, "New Shortcut Name:", button, rename=True)


    def on_ok_rename_button_clicked(self, parent, original_button, entry, script):
        # Reset the button before saving the new name
        parent.set_child(original_button)
        original_button.set_sensitive(True)

        # Call rename_shortcut to save the new name
        self.rename_shortcut(script, entry.get_text(), None)

    def rename_shortcut(self, script, new_name, dialog=None):
        script_path = Path(script)
        new_name = new_name.strip().replace(" ", "_")
        new_script_path = script_path.with_name(f"{new_name}.charm")
        old_icon_path = script_path.with_suffix(".png")
        new_icon_path = new_script_path.with_suffix(".png")

        if new_script_path.exists():
            self.show_error_dialog("Error", "A shortcut with the new name already exists.")
            return

        with open(script_path, 'r') as file:
            data = yaml.safe_load(file)
        
        data['progname'] = new_name.replace("_", " ")

        with open(new_script_path, 'w') as file:
            yaml.safe_dump(data, file)

        script_path.unlink()
        if old_icon_path.exists():
            old_icon_path.rename(new_icon_path)
        
        if dialog:
            dialog.close()
        else:
            self.on_back_button_clicked(None)


##NEW

    def on_startup(self, app):
        self.create_main_window()
        self.create_script_list()

        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        else:
            if not default_template.exists():
                self.initialize_template(default_template, self.on_template_initialized)
            else:
                self.set_dynamic_variables()
                if self.command_line_file:
                    self.process_cli_file(self.command_line_file)

        self.generate_about_yml()
        self.generate_settings_yml()

        # Run the check_running_processes_and_update_buttons asynchronously
        self.check_running_processes_and_update_buttons()


    def launch_script(self, script, play_stop_button, row):
        print(f"Launching script {script}")
        exe_file, wineprefix, progname, script_args = self.extract_yaml_info(script)
        exe_dir = Path(exe_file).parent
        exe_name = Path(exe_file).name

        # Check if the exe_file exists
        if not Path(exe_file).exists():
            self.show_exe_not_found_dialog(exe_name, exe_file, script, play_stop_button, play_stop_button)
            return

        command = f"cd {shlex.quote(str(exe_dir))} && WINEPREFIX={shlex.quote(str(wineprefix))} wine {shlex.quote(str(Path(exe_file).name))} {script_args}"

        try:
            # Launch the script using subprocess
            proc = subprocess.Popen(
                command,
                shell=True,
                preexec_fn=os.setsid,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Store the row and script information for later use
            self.running_processes[script.stem] = {"row": row, "script": script, "pid": proc.pid}

            # Immediately update the play button to show that the script is running
            start_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
            play_stop_button.set_child(start_icon)
            play_stop_button.set_tooltip_text("Stop")
            row.add_css_class("highlighted")

            # Start a thread to monitor the process
            threading.Thread(target=self.monitor_process, args=(script.stem, exe_file)).start()

        except Exception as e:
            print(f"Error launching script: {e}")

    def monitor_process(self, script_stem, exe_file):
        exe_name = Path(exe_file).name

        # Get the first 15 characters of the file name with the extension
        exe_name_upto_fifteen_chars = exe_name[:15]

        print(f"Monitoring process for: {exe_name_upto_fifteen_chars}")
        x = 1
        try:
            while True:
#            while x < 10:
                # Get the list of running processes related to the script
                pgrep_output = subprocess.check_output(["pgrep", "-aif", exe_name_upto_fifteen_chars]).decode()
                if not any(exe_name_upto_fifteen_chars in line for line in pgrep_output.splitlines()):
                    # No relevant processes are running, consider the process ended
                    GLib.idle_add(self.process_ended, script_stem)
                    break
                time.sleep(1)  # Wait before checking again
                #x = x + 1
        except subprocess.CalledProcessError:
            # No processes found, consider the process ended
            GLib.idle_add(self.process_ended, script_stem)
            
    def check_running_processes_and_update_buttons(self):
        def update_buttons():
            try:
                # Get the list of running processes with '.exe' in the command line
                running_processes_output = subprocess.check_output(["pgrep", "-aif", r"\.exe"]).decode().splitlines()
                print("Running processes with '.exe':", running_processes_output)

                # Loop through each script and update its state
                for script in self.find_python_scripts():
                    try:
                        exe_file, _, _, _ = self.extract_yaml_info(script)
                        exe_name = Path(exe_file).name  # Keep original casing

                        # Regular expression to match the process name exactly
                        exe_name_pattern = re.compile(r'\b' + re.escape(exe_name) + r'\b', re.IGNORECASE)

                        # Determine if the script is running
                        is_running = any(exe_name_pattern.search(process) for process in running_processes_output)

                        # Find the corresponding row for the script
                        row = self.find_row_by_script_stem(script.stem)

                        if is_running:
                            # If the script is running, ensure it's recorded
                            if script.stem not in self.running_processes:
                                print(f"Script running: {script.stem}  : {exe_name}")
                                self.running_processes[script.stem] = {"row": row, "script": script}
                        else:
                            # If the script is not running, remove it from running processes
                            if script.stem in self.running_processes:
                                print(f"Process ended for script: {script.stem} : {exe_name}")
                                self.running_processes.pop(script.stem)
                                GLib.idle_add(self.create_script_list)

                        # Always update the row highlighting based on the running status
                        if row:  # Ensure row is not None before accessing it
                            self.toggle_running_button_highlight(script.stem, row)

                    except Exception as e:
                        print(f"Error processing script {script}: {e}")

            except subprocess.CalledProcessError:
                print("pgrep: No running processes found")

            return True  # Continue the loop

        # Schedule the update_buttons function to run every 10 seconds
        GLib.timeout_add_seconds(1, update_buttons)
############################
    def on_activate(self, app):
        # Create a focus event controller
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("enter", self.on_focus_in)
        focus_controller.connect("leave", self.on_focus_out)
        self.window.add_controller(focus_controller)


    def on_focus_in(self, controller):
        print("Window focused")
        self.monitoring_active = True
        self.start_monitoring()

    def on_focus_out(self, controller):
        print("Window unfocused")
        self.monitoring_active = False

    def start_monitoring(self):
        # Start the monitoring loop if it's not already running
        if not hasattr(self, '_monitoring_id'):
            self._monitoring_id = GLib.timeout_add_seconds(1, self.check_running_processes_and_update_buttons)

    def stop_monitoring(self):
        # Stop the monitoring loop if it’s running
        if hasattr(self, '_monitoring_id'):
            GLib.source_remove(self._monitoring_id)
            delattr(self, '_monitoring_id')

    def launch_script(self, script, play_stop_button, row):
        print(f"Launching script {script}")
        exe_file, wineprefix, progname, script_args = self.extract_yaml_info(script)
        exe_dir = Path(exe_file).parent
        exe_name = Path(exe_file).name

        # Check if the exe_file exists
        if not Path(exe_file).exists():
            self.show_exe_not_found_dialog(exe_name, exe_file, script, play_stop_button, play_stop_button)
            return

        command = f"cd {shlex.quote(str(exe_dir))} && WINEPREFIX={shlex.quote(str(wineprefix))} wine {shlex.quote(str(Path(exe_file).name))} {script_args}"

        try:
            # Launch the script using subprocess
            proc = subprocess.Popen(
                command,
                shell=True,
                preexec_fn=os.setsid,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Store the row and script information for later use
            self.running_processes[script.stem] = {"row": row, "script": script, "pid": proc.pid}

            # Immediately update the play button to show that the script is running
            start_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
            play_stop_button.set_child(start_icon)
            play_stop_button.set_tooltip_text("Stop")
            row.add_css_class("highlighted")

            # Start a thread to monitor the process
            threading.Thread(target=self.monitor_process, args=(script.stem, exe_file)).start()

        except Exception as e:
            print(f"Error launching script: {e}")

    def monitor_process(self, script_stem, exe_file):
        exe_name = Path(exe_file).name

        # Get the first 15 characters of the file name with the extension
        exe_name_upto_fifteen_chars = exe_name[:15]

        try:
            print(f"Monitoring process for: {exe_name_upto_fifteen_chars}")
            while self.monitoring_active:
                # Get the list of running processes related to the script
                pgrep_output = subprocess.check_output(["pgrep", "-aif", exe_name_upto_fifteen_chars]).decode()
                if not any(exe_name_upto_fifteen_chars in line for line in pgrep_output.splitlines()):
                    # No relevant processes are running, consider the process ended
                    GLib.idle_add(self.process_ended, script_stem)
                    break
                time.sleep(1)  # Wait before checking again
        except subprocess.CalledProcessError:
            # No processes found, consider the process ended
            GLib.idle_add(self.process_ended, script_stem)

    def check_running_processes_and_update_buttons(self):
        if not self.monitoring_active:
            self.stop_monitoring()
            return False  # Stop the loop if not active

        try:
            # Get the list of running processes with '.exe' in the command line
            running_processes_output = subprocess.check_output(["pgrep", "-aif", r"\.exe"]).decode().splitlines()
           # print("Running processes with '.exe':", running_processes_output)

            # Loop through each script and update its state
            for script in self.find_python_scripts():
                try:
                    exe_file, _, _, _ = self.extract_yaml_info(script)
                    exe_name = Path(exe_file).name  # Keep original casing

                    # Regular expression to match the process name exactly
                    exe_name_pattern = re.compile(r'\b' + re.escape(exe_name) + r'\b', re.IGNORECASE)

                    # Determine if the script is running
                    is_running = any(exe_name_pattern.search(process) for process in running_processes_output)

                    # Find the corresponding row for the script
                    row = self.find_row_by_script_stem(script.stem)

                    if is_running:
                        # If the script is running, ensure it's recorded
                        if script.stem not in self.running_processes:
                            print(f"Script running: {script.stem}  : {exe_name}")
                            self.running_processes[script.stem] = {"row": row, "script": script}
                    else:
                        # If the script is not running, remove it from running processes
                        if script.stem in self.running_processes:
                            print(f"Process ended for script: {script.stem} : {exe_name}")
                            self.running_processes.pop(script.stem)
                            GLib.idle_add(self.create_script_list)

                    # Always update the row highlighting based on the running status
                    if row:  # Ensure row is not None before accessing it
                        self.toggle_running_button_highlight(script.stem, row)

                except Exception as e:
                    print(f"Error processing script {script}: {e}")

        except subprocess.CalledProcessError:
            print("pgrep: No running processes found")

        return True  # Continue the loop

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
                    # Send both the current working directory and the file path
                    message = f"{os.getcwd()}||{args.file}"
                    client.sendall(message.encode())
                    print(f"Sent file path to existing instance: {args.file}")
                return
            except ConnectionRefusedError:
                print("No existing instance found, starting a new one.")
        else:
            print("No existing instance found, starting a new one.")

        app.command_line_file = args.file

    # Ensure the socket server is started before the app runs
    app.start_socket_server()

    app.run(sys.argv)

    if SOCKET_FILE.exists():
        SOCKET_FILE.unlink()


if __name__ == "__main__":
    main()

