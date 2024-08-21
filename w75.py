#!/usr/bin/env python3

import io
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
wzt_prefix = None

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
                # Call the method to show WZT info dialog instead of directly starting extraction
                self.show_wzt_info_dialog(wzt_file)
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
        user = os.getenv('USER')
        print(f"Extracting {wzt_file} to {extract_dir}")
        try:
            # Extract the wzt_prefix
            wzt_prefix = subprocess.check_output(
                ["bash", "-c", f"tar -tf '{wzt_file}' | head -n2 | grep '/' | cut -f1 -d '/'"]
            ).decode('utf-8').strip()
            
            extract_dir = Path(os.path.expanduser(prefixes_dir))
            extracted_wzt_prefix = extract_dir / wzt_prefix
        
            subprocess.run(
                ["tar", "-xvf", wzt_file, "-C", extract_dir, "--transform", f"s|XOUSERXO|{user}|g"],
                check=True
            )
            self.perform_replacements(extracted_wzt_prefix)
            self.process_sh_files(extracted_wzt_prefix)

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


    def is_text_file(self, file_path):
        # Read a portion of the file to check if it is a text file
        try:
            with open(file_path, 'rb') as file:
                chunk = file.read(1024)  # Read the first 1024 bytes
                if b'\0' in chunk:
                    return False  # Binary file
        except Exception as e:
            print(f"Error checking file: {file_path} ({e})")
            return False

        return True  # Text file


 
    def process_sh_files(self, directory):
        sh_files = self.find_sh_files(directory)
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


    def show_wzt_info_dialog(self, wzt_file):
        try:
            # Attempt to extract wzt-info.yml content
            command = ["tar", "--occurrence=1", "--extract", "-O", "-f", wzt_file, "wzt-info.yml"]
            wzt_info_output = subprocess.check_output(command).decode('utf-8').strip()

            # If wzt-info.yml is found, show it in a dialog
            dialog = Gtk.Dialog(transient_for=self.window, modal=True)
            dialog.set_title(os.path.basename(wzt_file))  # Set the dialog title to the .wzt file name
            dialog.set_default_size(400, 300)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            vbox.set_margin_start(10)
            vbox.set_margin_end(10)
            vbox.set_margin_top(10)
            vbox.set_margin_bottom(10)

            text_view = Gtk.TextView()
            text_view.set_editable(False)
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(wzt_info_output)

            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled_window.set_child(text_view)
            scrolled_window.set_vexpand(True)  # Allow the TextView to expand vertically
            scrolled_window.set_hexpand(True)  # Allow the TextView to expand horizontally

            vbox.append(scrolled_window)

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_halign(Gtk.Align.END)

            cancel_button = Gtk.Button(label="Cancel")
            cancel_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))

            ok_button = Gtk.Button(label="OK")
            ok_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

            hbox.append(cancel_button)
            hbox.append(ok_button)

            vbox.append(hbox)

            dialog.set_child(vbox)

            dialog.connect("response", self.on_wzt_info_dialog_response, wzt_file)
            dialog.present()

        except subprocess.CalledProcessError as e:
            # If wzt-info.yml is not found, show a dialog asking to extract anyway
            self.show_info_not_found_dialog(wzt_file)



    def show_info_not_found_dialog(self, wzt_file):
        # Dialog to ask the user if they want to extract without wzt-info.yml
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="WZT Info Not Found",
            secondary_text="The file 'wzt-info.yml' was not found in the selected WZT archive.\nDo you want to extract the archive anyway?",
        )
        dialog.connect("response", self.on_wzt_info_dialog_response, wzt_file)
        dialog.present()

    def on_wzt_info_dialog_response(self, dialog, response_id, wzt_file):
        if response_id in (Gtk.ResponseType.OK, Gtk.ResponseType.YES):
            self.start_extraction_thread(wzt_file)
        dialog.destroy()










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



def main():
    app = WZTExtractorApp()
    app.run(None)

if __name__ == "__main__":
    main()

