import os
import re
import subprocess
import gi
import yaml
from pathlib import Path
import mimetypes
import threading

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, GLib, Adw

class WZTExtractorApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.fastrizwaan.WZTExtractor')
        Adw.init()
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        self.create_main_window()

    def create_main_window(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("WZT Extractor")
        self.window.set_default_size(400, 200)

        self.headerbar = Gtk.HeaderBar()
        self.headerbar.set_show_title_buttons(True)
        self.window.set_titlebar(self.headerbar)

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.vbox.set_margin_start(10)
        self.vbox.set_margin_end(10)
        self.vbox.set_margin_top(10)
        self.vbox.set_margin_bottom(10)
        self.window.set_child(self.vbox)

        self.button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.button_box.set_halign(Gtk.Align.CENTER)
        open_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
        open_label = Gtk.Label(label="Open .wzt file")

        self.button_box.append(open_icon)
        self.button_box.append(open_label)

        self.open_button = Gtk.Button()
        self.open_button.set_child(self.button_box)
        self.open_button.connect("clicked", self.on_open_file_clicked)
        self.vbox.append(self.open_button)

        self.open_extracted_button = Gtk.Button(label="Open Extracted Directory")
        self.open_extracted_button.connect("clicked", self.on_open_extracted_dir_clicked)
        self.open_extracted_button.set_sensitive(False)
        self.vbox.append(self.open_extracted_button)

        self.window.present()

    def on_open_file_clicked(self, button):
        self.open_file_dialog()

    def open_file_dialog(self):
        file_dialog = Gtk.FileDialog.new()
        filter_model = Gio.ListStore.new(Gtk.FileFilter)
        file_filter = Gtk.FileFilter()
        file_filter.set_name("WZT files")
        file_filter.add_pattern("*.wzt")
        filter_model.append(file_filter)
        file_dialog.set_filters(filter_model)
        file_dialog.open(self.window, None, self.on_file_dialog_response)

    def on_file_dialog_response(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                wzt_file = file.get_path()
                print(f"Selected file: {wzt_file}")
                threading.Thread(target=self.extract_wzt_info, args=(wzt_file,)).start()
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")
        finally:
            self.window.set_visible(True)

    def extract_wzt_info(self, wzt_file):
        try:
            result = subprocess.run(
                ["tar", "--occurrence=1", "--extract", "-O", "-f", wzt_file, "wzt-info.yml"],
                capture_output=True, text=True, check=True
            )
            wzt_info_content = result.stdout
            if wzt_info_content:
                print(f"wzt-info.yml content:\n{wzt_info_content}")
                GLib.idle_add(self.show_info_dialog, wzt_file, wzt_info_content)
            else:
                print("wzt-info.yml not found")
                GLib.idle_add(self.ask_extract_anyway, wzt_file)
        except subprocess.CalledProcessError:
            print("wzt-info.yml not found")
            GLib.idle_add(self.ask_extract_anyway, wzt_file)

    def show_info_dialog(self, wzt_file, wzt_info_content):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Content of wzt-info.yml",
        )
        dialog.props.secondary_text = wzt_info_content
        dialog.connect("response", self.on_info_dialog_response, wzt_file)
        dialog.present()

    def on_info_dialog_response(self, dialog, response, wzt_file):
        if response == Gtk.ResponseType.OK:
            threading.Thread(target=self.extract_wzt_file, args=(wzt_file,)).start()
        dialog.destroy()

    def ask_extract_anyway(self, wzt_file):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="wzt-info.yml not found, extract anyhow?",
        )
        dialog.connect("response", self.on_ask_extract_anyway_response, wzt_file)
        dialog.present()

    def on_ask_extract_anyway_response(self, dialog, response, wzt_file):
        if response == Gtk.ResponseType.YES:
            threading.Thread(target=self.extract_wzt_file, args=(wzt_file,)).start()
        dialog.destroy()

    def extract_wzt_file(self, wzt_file):
        try:
            # Run the command to determine the prefix directory
            wzt_prefix_result = subprocess.run(
                ["bash", "-c", f"tar -tf {wzt_file} | head -n2 | grep '/' | cut -f1 -d '/'"],
                capture_output=True, text=True
            )

            # Check if the command was successful
            wzt_prefix = wzt_prefix_result.stdout.strip()

            prefixes_dir = Path(os.path.expanduser(f"~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Prefixes"))
            extract_dir = prefixes_dir / wzt_prefix
            extract_dir.mkdir(parents=True, exist_ok=True)

            print(f"Extracting {wzt_file} to {extract_dir}")
            subprocess.run(
                ["tar", "--zstd", "-xvf", wzt_file, "-C", prefixes_dir, "--transform", f"s|XOUSERXO|{os.getenv('USER')}|g"],
                check=True
            )
            GLib.idle_add(self.perform_replacements_and_process_sh, extract_dir)
        except subprocess.CalledProcessError as e:
            print(f"Error extracting file: {e}")
            GLib.idle_add(self.show_message_dialog, f"Error extracting file: {e}")



    def perform_replacements_and_process_sh(self, extract_dir):
        self.perform_replacements(extract_dir)
        self.process_sh_files(extract_dir)
        self.show_message_dialog(f"Extracted all files to {extract_dir}")
        self.extracted_dir = extract_dir
        self.open_extracted_button.set_sensitive(True)

    def perform_replacements(self, directory):
        user = os.getenv('USER')
        runner = subprocess.check_output(['which', 'wine']).decode('utf-8').strip()
        winever = subprocess.check_output([runner, '--version']).decode('utf-8').strip()
        usershome = os.path.expanduser('~')
        datadir = os.getenv('DATADIR', '/usr/share')

        find_replace_pairs = {
            r"XOCONFIGXO": r"\\?\\H:\\.config",
            r"XOFLATPAKNAMEXO": r"io.github.fastrizwaan.WineCharm",
            r"XOINSTALLTYPEXO": r"flatpak",
            r"XOPREFIXXO": r".var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Prefixes",
            r"XOWINEZGUIDIRXO": r".var/app/io.github.fastrizwaan.WineCharm/data/winecharm",
            r"XODATADIRXO": datadir,
            r"XODESKTOPDIRXO": r".local/share/applications/winecharm",
            r"XOAPPLICATIONSXO": r".local/share/applications",
            r"XOAPPLICATIONSDIRXO": r".local/share/applications",
            r"XOREGUSERSUSERXO": r"\\users\\{}".format(user),
            r"XOREGHOMEUSERXO": r"\\home\\{}".format(user),
            r"XOREGUSERNAMEUSERXO": r"\"USERNAME\"=\"{}\"".format(user),
            r"XOREGINSTALLEDBYUSERXO": r"\"InstalledBy\"=\"{}\"".format(user),
            r"XOREGREGOWNERUSERXO": r"\"RegOwner\"=\"{}\"".format(user),
            r"XOUSERHOMEXO": usershome,
            r"XOUSERSUSERXO": r"/users/{}".format(user),
            r"XOMEDIASUSERXO": r"/media/{}".format(user),
            r"XOFLATPAKIDXO": r"io.github.fastrizwaan.WineCharm",
            r"XOWINEEXEXO": runner,
            r"XOWINEVERXO": winever,
        }

        self.replace_strings_in_files(directory, find_replace_pairs)

    def replace_strings_in_files(self, directory, find_replace_pairs):
        # Sort the find_replace_pairs by length of the find string in descending order
        sorted_pairs = sorted(find_replace_pairs.items(), key=lambda x: len(x[0]), reverse=True)

        # Iterate over all files in the directory
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    # Read the content of the file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Track changes
                    changes = []
                    modified_content = content

                    # Perform the replacements
                    for find, replace in sorted_pairs:
                        if re.search(find, modified_content):
                            modified_content = re.sub(find, replace, modified_content)
                            changes.append((find, replace))

                    # Write the content back to the file if it was modified
                    if changes:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(modified_content)

                        # Print the changes
                        print(f"File: {file_path}")
                        for find, replace in changes:
                            print(f"  Replaced: {find} with {replace}")
                except (UnicodeDecodeError, FileNotFoundError, PermissionError) as e:
                    print(f"Skipping file: {file_path} ({e})")

    def process_sh_files(self, directory):
        sh_files = self.find_sh_files(directory)
        for sh_file in sh_files:
            variables = self.extract_variables_from_sh(sh_file)
            if variables:
                yml_path = sh_file.replace('.sh', '.charm')
                self.create_yml_file(variables, yml_path)
                print(f"Created {yml_path}")

    def find_sh_files(self, directory):
        sh_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(".sh"):
                    sh_files.append(os.path.join(root, file))
        return sh_files

    def extract_variables_from_sh(self, file_path):
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

    def create_yml_file(self, variables, yml_path):
        yml_content = {
            'args': '',
            'progname': variables.get('PROGNAME', ''),
            'wineprefix': variables.get('PREFIXDIR', ''),
            'exe_file': variables.get('EXE_FILE', '')
        }
        with open(yml_path, 'w') as yml_file:
            yaml.dump(yml_content, yml_file, default_flow_style=False)

    def show_message_dialog(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.present()
        dialog.connect("response", lambda d, r: d.destroy())

    def on_open_extracted_dir_clicked(self, button):
        if hasattr(self, 'extracted_dir'):
            print(f"Opening extracted directory: {self.extracted_dir}")
            os.system(f'xdg-open "{self.extracted_dir}"')

def main():
    app = WZTExtractorApp()
    app.run(None)

if __name__ == "__main__":
    main()

