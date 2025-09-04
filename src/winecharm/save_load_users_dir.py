import gi
import threading
import subprocess
import shutil
import shlex
import yaml
import os
from pathlib import Path
from gettext import gettext as _

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango  # Add Pango here
from datetime import datetime, timedelta

def show_save_user_dirs_dialog(self, script, script_key, button):
    """Show dialog to select directories for backup."""
    print("Method: show_save_user_dirs_dialog")
    wineprefix = Path(script).parent
    default_dir = wineprefix / "drive_c" / "users"

    # Create Adw.AlertDialog
    dialog = Adw.AlertDialog(
        heading=_("Select Directories to Backup"),
        body=_("Choose which directories to include in the backup.")
    )
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("ok", _("OK"))
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("ok")
    dialog.set_close_response("cancel")

    # Create content container
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    
    # Scrollable directory list
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_min_content_height(200)
    
    # ListBox with CSS class
    self.dir_list = Gtk.ListBox()
    self.dir_list.set_selection_mode(Gtk.SelectionMode.NONE)
    self.dir_list.add_css_class("boxed-list") 

    # Dictionary to track checkboxes for each row
    self.dir_checkboxes = {}
    
    # Load saved directories from .charm file
    script_data = self.extract_yaml_info(script_key)
    saved_dirs = script_data.get('save_dirs', [])
    
    # Track if any valid directories are added
    added_any = False
    if saved_dirs:
        for saved_dir in saved_dirs:
            saved_path = Path(saved_dir).expanduser().resolve()
            # Validate saved directory
            valid, error = self.is_valid_directory(saved_path, wineprefix)
            if valid:
                row = Adw.ActionRow()
                row.set_title(os.path.basename(str(saved_path)))
                row.set_subtitle(str(saved_path))
                check = Gtk.CheckButton()
                check.set_active(True)
                row.add_suffix(check)
                row.set_activatable_widget(check)
                self.dir_list.append(row)
                # Store checkbox reference
                self.dir_checkboxes[row] = check
                added_any = True
    
    # If no valid directories were added, add the default
    if not added_any:
        row = Adw.ActionRow()
        row.set_title(os.path.basename(str(default_dir)))
        row.set_subtitle(str(default_dir))
        check = Gtk.CheckButton()
        check.set_active(True)
        row.add_suffix(check)
        row.set_activatable_widget(check)
        self.dir_list.append(row)
        # Store checkbox reference
        self.dir_checkboxes[row] = check
    
    scrolled.set_child(self.dir_list)
    content_box.append(scrolled)

    # Add directory button
    add_btn = Gtk.Button(label=_("Add Directory"))
    add_btn.connect("clicked", self.on_add_directory, self.window, wineprefix)
    content_box.append(add_btn)

    dialog.set_extra_child(content_box)
    dialog.connect("response", self.on_directory_dialog_response, script, script_key)
    dialog.present(self.window)


def on_directory_dialog_response(self, dialog, response_id, script, script_key):
    """Handle dialog response and save selected directories to .charm file."""
    if response_id == "ok":
        # Get all rows from ListBox
        rows = []
        child = self.dir_list.get_first_child()
        while child is not None:
            rows.append(child)
            child = child.get_next_sibling()

        # Get selected directories using the checkbox dictionary
        selected_dirs = [row.get_subtitle() for row in rows if self.dir_checkboxes[row].get_active()]
        self.show_save_file_dialog(script, script_key, selected_dirs)
        
        # Update the .charm file with selected directories
        try:
            script_data = self.extract_yaml_info(script_key)
            script_path = Path(str(script_data['script_path'])).expanduser().resolve()
            
            # Convert paths to tilde format for storage
            save_dirs = [self.replace_home_with_tilde_in_path(dir) for dir in selected_dirs]
            script_data['save_dirs'] = save_dirs
            
            # Write updated data back to .charm file
            with open(script_path, 'w') as file:
                yaml.dump(script_data, file, default_style="'", default_flow_style=False, width=10000)
            print(f"Saved directories to {script_path}: {save_dirs}")
        except Exception as e:
            print(f"Error saving directories to .charm file: {e}")
            GLib.idle_add(self.show_error_dialog, _("Error"), 
                        _("Failed to save directories: {}").format(str(e)))
    
    dialog.close()

def on_add_directory(self, button, parent_dialog, wineprefix):
    """Add a new directory to the backup list with validation."""
    dir_dialog = Gtk.FileDialog()
    dir_dialog.set_title(_("Select Directory to Add"))
    dir_dialog.set_initial_folder(Gio.File.new_for_path(str(wineprefix)))

    def on_dir_response(dlg, result):
        try:
            folder = dlg.select_folder_finish(result)
            path = folder.get_path()
            path_obj = Path(path)

            # Validate the directory
            valid, msg = self.is_valid_directory(path_obj, wineprefix)
            if not valid:
                self.show_error_dialog(_("Error"), msg)
                return
            
            # Check for duplicates
            existing_rows = []
            child = self.dir_list.get_first_child()
            while child is not None:
                existing_rows.append(child)
                child = child.get_next_sibling()

            if any(row.get_subtitle() == path for row in existing_rows):
                return  # Silently ignore duplicates
            
            # Add the directory to the list
            row = Adw.ActionRow()
            row.set_title(os.path.basename(path))
            row.set_subtitle(path)
            check = Gtk.CheckButton()
            check.set_active(True)
            row.add_suffix(check)
            row.set_activatable_widget(check)
            self.dir_list.append(row)
            # Store checkbox reference
            self.dir_checkboxes[row] = check
        except GLib.Error as e:
            if e.code != Gtk.DialogError.DISMISSED:
                print(f"Directory selection error: {e}")

    dir_dialog.select_folder(parent_dialog, None, on_dir_response)


def show_save_file_dialog(self, script, script_key, selected_dirs):
    """Show dialog to choose backup file location."""
    print("Method: show_save_file_dialog")
    creation_date_and_time = datetime.now().strftime("%Y%m%d%H%M")
    default_backup_name = f"{script.stem}-{creation_date_and_time}.saved"
    file_dialog = Gtk.FileDialog()
    file_dialog.set_initial_name(default_backup_name)
    file_dialog.save(self.window, None, 
                    lambda dlg, res: self.on_save_user_dirs_dialog_response(dlg, res, script, script_key, selected_dirs))

def on_save_user_dirs_dialog_response(self, dialog, result, script, script_key, selected_dirs):
    """Handle save file dialog response."""
    print("Method: on_save_user_dirs_dialog_response")
    try:
        backup_file = dialog.save_finish(result)
        if backup_file:
            backup_path = backup_file.get_path()
            print(f"Backup will be saved to: {backup_path}")
            threading.Thread(
                target=self.save_user_dirs,
                args=(script, script_key, backup_path, selected_dirs)
            ).start()
    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"Save error: {e}")

def save_user_dirs(self, script, script_key, backup_path, selected_dirs):
    """Save selected directories to a compressed archive."""
    print("Method: save_user_dirs")
    wineprefix = Path(script).parent
    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        print("Error: Couldn't determine username")
        return
    rel_paths = [str(Path(path).relative_to(wineprefix)) for path in selected_dirs 
                if Path(path).is_relative_to(wineprefix)]
    if not rel_paths:
        print("No valid directories selected")
        return
    try:
        tar_command = [
            'tar', '-I', 'zstd -T0',
            '--transform', f"s|{current_username}|%USERNAME%|g",
            '-cf', backup_path,
            '-C', str(wineprefix)
        ] + rel_paths
        print(f"Executing: {' '.join(tar_command)}")
        result = subprocess.run(tar_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Backup failed: {result.stderr}")
        print(f"Backup created at {backup_path}")
        GLib.idle_add(self.show_info_dialog, _("Backup Complete"), 
                        _("User directories saved to:\n{}").format(backup_path))
    except Exception as e:
        print(f"Backup error: {e}")
        GLib.idle_add(self.show_error_dialog, _("Backup Failed"), str(e))

def show_load_user_dirs_dialog(self, script, script_key, button):
    """Show dialog to load a backup file."""
    print("Method: show_load_user_dirs_dialog")
    file_dialog = Gtk.FileDialog()
    file_filter = Gtk.FileFilter()
    file_filter.set_name(_("Saved Files (*.sav.tar.zst, *.saved)"))
    file_filter.add_pattern("*.sav.tar.zst")
    file_filter.add_pattern("*.saved")
    filter_list_store = Gio.ListStore.new(Gtk.FileFilter)
    filter_list_store.append(file_filter)
    file_dialog.set_filters(filter_list_store)
    file_dialog.open(self.window, None, 
                    lambda dlg, res: self.on_load_user_dirs_dialog_response(dlg, res, script, script_key))

def on_load_user_dirs_dialog_response(self, dialog, result, script, script_key):
    """Handle load file dialog response with confirmation."""
    print("Method: on_load_user_dirs_dialog_response")
    try:
        backup_file = dialog.open_finish(result)
        if backup_file:
            backup_path = backup_file.get_path()
            print(f"Backup will be loaded from: {backup_path}")
            def on_confirm(confirm):
                if confirm:
                    threading.Thread(target=self.load_user_dirs, 
                                    args=(script, script_key, backup_path)).start()
            self.confirm_restore(backup_path, on_confirm)
    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"Load error: {e}")

def confirm_restore(self, backup_path, callback):
    """Show confirmation dialog before restoring."""
    dialog = Adw.AlertDialog(
        heading=_("Confirm Restore"),
        body=_("Restoring from {} will overwrite existing user directories. Proceed?").format(backup_path)
    )
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("restore", _("Restore"))
    dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.connect("response", lambda d, r: callback(r == "restore"))
    dialog.present(self.window)

def load_user_dirs(self, script, script_key, backup_path):
    """Restore user directories from a backup file."""
    print("Method: load_user_dirs")
    wineprefix = Path(script).parent
    if not wineprefix.exists():
        print(f"Error: Wineprefix not found at {wineprefix}")
        return
    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        print("Error: Unable to determine username")
        return
    try:
        extract_dir = wineprefix / "drive_c" / "users" if backup_path.endswith('.sav.tar.zst') else wineprefix
        extract_dir.mkdir(parents=True, exist_ok=True)
        tar_command = [
            'tar', '-I', 'zstd -d',
            '-xf', backup_path,
            '--transform', f"s|%USERNAME%|{current_username}|g",
            '--transform', f"s|XOUSERXO|{current_username}|g",
            '-C', str(extract_dir)
        ]
        print(f"Executing: {' '.join(tar_command)}")
        result = subprocess.run(tar_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Restore failed: {result.stderr}")
        print(f"Backup loaded to {extract_dir}")
        GLib.idle_add(self.show_info_dialog, _("Restore Complete"), 
                        _("User directories restored to:\n{}").format(extract_dir))
    except Exception as e:
        print(f"Restore error: {e}")
        GLib.idle_add(self.show_error_dialog, _("Restore Failed"), str(e))

def is_valid_directory(self, path_obj, wineprefix):
    """
    Validate if a directory can be added to the backup list.
    
    Args:
        path_obj (Path): The selected directory path.
        wineprefix (Path): The wineprefix path.
    
    Returns:
        tuple: (bool, str) - (is_valid, error_message)
    """
    # Ensure the directory is within the wineprefix
    if not path_obj.is_relative_to(wineprefix):
        return False, _("Directory must be within Wine prefix")
    
    # Define directories to exclude exactly (not their subdirectories)
    exact_exclusions = [
        wineprefix,              # Wineprefix itself
        wineprefix / "drive_c"   # drive_c itself
    ]
    
    # Define directories to exclude including their subdirectories
    subtree_exclusions = {
        wineprefix / "dosdevices": _("Cannot select dosdevices or its subdirectories"),
        wineprefix / "drive_c" / "windows": _("Cannot select drive_c/windows or its subdirectories")
    }
    
    # Check exact exclusions
    if path_obj in exact_exclusions:
        if path_obj == wineprefix:
            return False, _("Cannot select the wineprefix directory")
        elif path_obj == wineprefix / "drive_c":
            return False, _("Cannot select the drive_c directory")
    
    # Check subtree exclusions
    for excl, msg in subtree_exclusions.items():
        try:
            path_obj.relative_to(excl)
            return False, msg  # Path is excl or a subdirectory of excl
        except ValueError:
            pass  # Not a match, continue checking
    
    return True, ""  # Directory is valid



def show_error_dialog(self, title, message):
    """Display an error dialog."""
    dialog = Adw.AlertDialog(heading=title, body=message)
    dialog.add_response("ok", _("OK"))
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.present(self.window)
