import os
import re
import subprocess
import gi
from pathlib import Path

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
                self.extract_wzt_info(wzt_file)
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
                self.show_info_dialog(wzt_file, wzt_info_content)
            else:
                print("wzt-info.yml not found")
                self.ask_extract_anyway(wzt_file)
        except subprocess.CalledProcessError:
            print("wzt-info.yml not found")
            self.ask_extract_anyway(wzt_file)

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
            self.extract_wzt_file(wzt_file)
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
            self.extract_wzt_file(wzt_file)
        dialog.destroy()

    def extract_wzt_file(self, wzt_file):
        extract_dir = Path(os.path.expanduser("~/.var/app/io.github.fastrizwaan.WZTExtractor/data/wzt_extractor/"))
        extract_dir.mkdir(parents=True, exist_ok=True)

        print(f"Extracting {wzt_file} to {extract_dir}")
        try:
            subprocess.run(
                ["tar", "--zstd", "-xvf", wzt_file, "-C", extract_dir, "--transform", "s|XOUSERXO|${USER}|g"],
                check=True
            )
            self.perform_replacements(extract_dir)
            self.show_message_dialog(f"Extracted all files to {extract_dir}")
            self.extracted_dir = extract_dir
            self.open_extracted_button.set_sensitive(True)
        except subprocess.CalledProcessError as e:
            print(f"Error extracting file: {e}")
            self.show_message_dialog(f"Error extracting file: {e}")

    def perform_replacements(self, directory):
        find_replace_pairs = {
            r"XOFLATPAKNAMEXO": r"export FLATPAK_NAME=io.github.fastrizwaan.WineCharm",
            r"XOWINEVERXO": r"wine-9.1",
            r"XOINSTALLTYPEXO": r"export INSTALL_TYPE=flatpak",
            r"XOUSERHOMEXO": r"/var/home/rizvan",
            r"XOWINEZGUIDIRXO": r".var/app/io.github.fastrizwaan.WineCharm/data/winecharm",
            r"XOPREFIXXO": r".var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Prefixes",
            r"XOAPPLICATIONSDIRXO": r".local/share/applications",
            r"XODATADIRXO": r"export DATADIR=/app/share/winecharm",
            r"XOREGUSERSUSERXO": r"\\\\users\\\\rizvan",
            r"XOREGHOMEUSERXO": r"\\\\home\\\\rizvan",
            r"XOREGUSERNAMEUSERXO": r"\"USERNAME\"=\"rizvan\"",
            r"XOREGINSTALLEDBYUSERXO": r"\"InstalledBy\"=\"rizvan\"",
            r"XOREGREGOWNERUSERXO": r"\"RegOwner\"=\"rizvan\"",
            r"XOWINEEXEXO": r"/app/bin/wine",
        }
        self.replace_strings_in_files(directory, find_replace_pairs)

    def replace_strings_in_files(self, directory, find_replace_pairs):
        # Sort the find_replace_pairs by length of the find string in descending order
        sorted_pairs = sorted(find_replace_pairs.items(), key=lambda x: len(x[0]), reverse=True)

        # Iterate over all files in the directory
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                # Read the content of the file
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Perform the replacements
                for find, replace in sorted_pairs:
                    content = re.sub(find, replace, content)

                # Write the content back to the file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

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

