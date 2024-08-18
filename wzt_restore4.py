#!/usr/bin/env python3

import os
import re
import subprocess
import threading
import gi
import yaml
from pathlib import Path

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, GLib, Adw

prefixes_dir = "~/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Prefixes"

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

        self.spinner = Gtk.Spinner()
        self.vbox.append(self.spinner)

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
                self.start_extraction_thread(wzt_file)
        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")
        finally:
            self.window.set_visible(True)

    def start_extraction_thread(self, wzt_file):
        self.spinner.start()
        self.open_button.set_sensitive(False)
        threading.Thread(target=self.extract_wzt_file, args=(wzt_file,), daemon=True).start()

    def extract_wzt_file(self, wzt_file):
        extract_dir = Path(os.path.expanduser(prefixes_dir))
        extract_dir.mkdir(parents=True, exist_ok=True)

        print(f"Extracting {wzt_file} to {extract_dir}")
        try:
            subprocess.run(
                ["tar", "--zstd", "-xvf", wzt_file, "-C", extract_dir, "--transform", "s|XOUSERXO|${USER}|g"],
                check=True
            )
            self.perform_replacements(extract_dir)
            self.process_sh_files(extract_dir)
            self.on_extraction_complete(success=True, message=f"Extracted all files to {extract_dir}")
            self.extracted_dir = extract_dir
        except subprocess.CalledProcessError as e:
            print(f"Error extracting file: {e}")
            self.on_extraction_complete(success=False, message=f"Error extracting file: {e}")

    def on_extraction_complete(self, success, message):
        GLib.idle_add(self.spinner.stop)
        GLib.idle_add(self.open_button.set_sensitive, True)
        GLib.idle_add(self.open_extracted_button.set_sensitive, success)
        GLib.idle_add(self.show_message_dialog, message)

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
        sorted_pairs = sorted(find_replace_pairs.items(), key=lambda x: len(x[0]), reverse=True)

        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    changes = []
                    modified_content = content

                    for find, replace in sorted_pairs:
                        if re.search(find, modified_content):
                            modified_content = re.sub(find, replace, modified_content)
                            changes.append((find, replace))

                    if changes:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(modified_content)

                        print(f"File: {file_path}")
                        for find, replace in changes:
                            print(f"  Replaced: {find} with {replace}")
                except (UnicodeDecodeError, FileNotFoundError, PermissionError) as e:
                    print(f"Skipping file: {file_path} ({e})")

    def process_sh_files(self, directory):
        sh_files = self.find_sh_files(directory)
        for sh_file in sh_files:
            variables = self.extract_infofile_path_from_sh(sh_file)
            if variables:
                info_file_path = variables.get('INFOFILE')
                if info_file_path:
                    info_file_path = os.path.join(os.path.dirname(sh_file), info_file_path)
                    if os.path.exists(info_file_path):
                        try:
                            info_data = self.parse_info_file(info_file_path)
                            print(f"Parsed info_data: {info_data}")  # Debugging statement
                            yml_path = sh_file.replace('.sh', '.charm')
                            self.create_charm_file(info_data, yml_path)
                            print(f"Created {yml_path}")
                        except Exception as e:
                            print(f"Error parsing INFOFILE {info_file_path}: {e}")
                    else:
                        print(f"INFOFILE {info_file_path} not found")
                else:
                    print(f"No INFOFILE found in {sh_file}")

    def parse_info_file(self, file_path):
        info_data = {}
        with open(file_path, 'r') as file:
            for line in file:
                if ':' in line:
                    key, value = line.split(':', 1)
                    info_data[key.strip()] = value.strip()
        return info_data

    def create_charm_file(self, info_data, yml_path):
        # Start by printing a message indicating the function is being called
        print(f"Creating .charm file at path: {yml_path}")
        
        # Debugging: Print the info_data dictionary
        print(f"Info Data Dictionary: {info_data}")

        # Prepare the data to be written
        yml_content = {
            'exe_file': info_data.get('Exe', ''),
            'wineprefix': info_data.get('Prefix', ''),
            'progname': info_data.get('Name', ''),
            'args': '',  # args might need to be manually set or extracted differently
            'sha256sum': info_data.get('Sha256sum', ''),
            'runner': info_data.get('Runner', '')
        }

        # Debugging: Print out the yml_content before writing it to the file
        print(f"YAML Content to be Written: {yml_content}")

        # Check each key-value pair in yml_content before writing
        for key, value in yml_content.items():
            print(f"Writing key: '{key}' with value: '{value}'")
            if value == '':
                print(f"Warning: The key '{key}' has an empty value.")

        # Write the data manually to the file
        try:
            with open(yml_path, 'w') as yml_file:
                for key, value in yml_content.items():
                    print(f"Writing to file: {key}: '{value}'")  # Debugging statement
                    yml_file.write(f"{key}: '{value}'\n")
            print(f"Successfully created .charm file at: {yml_path}")
        except Exception as e:
            print(f"Error writing to file: {e}")






    def find_sh_files(self, directory):
        sh_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(".sh"):
                    sh_files.append(os.path.join(root, file))
        return sh_files

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

    def create_charm_file(self, info_data, yml_path):
        yml_content = {
            'exe_file': info_data.get('exe_file', ''),
            'wineprefix': info_data.get('wineprefix', ''),
            'progname': info_data.get('progname', ''),
            'args': info_data.get('args', ''),
            'sha256sum': info_data.get('sha256sum', ''),
            'runner': info_data.get('runner', '')
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

