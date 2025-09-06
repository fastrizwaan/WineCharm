#!/usr/bin/env python3

import gi
import threading
import subprocess
import shutil
import shlex
import yaml
import time
import os
import re
import fnmatch
from pathlib import Path

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango

def rename_and_merge_user_directories(self, wineprefix):
    self.print_method_name()
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
    self.print_method_name()
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
    self.print_method_name()
    # Create a new Gtk.FileDialog for selecting a directory
    file_dialog = Gtk.FileDialog.new()

    # Set the action to select a folder (in GTK 4, it's done by default via FileDialog)
    file_dialog.set_modal(True)

    # Open the dialog to select a folder (async operation)
    file_dialog.select_folder(self.window, None, self.on_import_directory_response)

    print("FileDialog presented for importing Wine directory.")

def on_import_directory_response(self, dialog, result):
    self.print_method_name()
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

                # Destination directory
                dest_dir = self.prefixes_dir / Path(directory).name

                # Check if destination directory already exists
                if dest_dir.exists():
                    print(f"Destination directory already exists: {dest_dir}")
                    # Show confirmation dialog for overwriting
                    GLib.idle_add(self.show_import_wine_directory_overwrite_confirmation_dialog, directory, dest_dir)
                else:
                    # Proceed with copying if the directory doesn't exist
                    threading.Thread(target=self.import_wine_directory, args=(directory, dest_dir)).start()
            else:
                print(f"Invalid directory selected: {directory}")
                GLib.timeout_add_seconds(0.5, self.show_info_dialog, _("Invalid Directory"), _("The selected directory does not appear to be a valid Wine directory."))

    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")

    print("FileDialog operation complete.")

def import_wine_directory(self, src, dst):
    self.print_method_name()
    """
    Import the Wine directory with improved safety, rollback capability, and cancellation support.
    """
    self.stop_processing = False
    backup_dir = dst.parent / f"{dst.name}_backup_{int(time.time())}"
    
    # Clear the flowbox and initialize progress UI
    GLib.idle_add(self.flowbox.remove_all)
    
    steps = [
        (_("Backing up existing directory"), lambda: self.backup_existing_directory(dst, backup_dir)),
        (_("Copying Wine directory"), lambda: self.custom_copytree(src, dst)),
        (_("Processing registry files"), lambda: self.process_reg_files(dst)),
        (_("Performing Replacements"), lambda: self.perform_replacements(dst)),
        (_("Renaming and Merging User Directories"), lambda: self.rename_and_merge_user_directories(dst)),
        (_("Creating scripts for .exe files"), lambda: self.create_scripts_for_exe_files(dst)),
        (_("Replace symbolic links with directories"), lambda: self.remove_symlinks_and_create_directories(dst)),
        (_("Create Wineboot Required file"), lambda: self.create_wineboot_required_file(dst)),
    ]

    
    self.total_steps = len(steps)
    self.show_processing_spinner("Importing Wine Directory...")
    self.connect_open_button_with_import_wine_directory_cancel()

    def perform_import_steps():
        self.print_method_name()
        try:
            for index, (step_text, step_func) in enumerate(steps, 1):
                if self.stop_processing:
                    GLib.idle_add(lambda: self.handle_import_cancellation(dst, backup_dir))
                    return
                    
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    step_func()
                    GLib.idle_add(self.mark_step_as_done, step_text)
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index / self.total_steps))
                except Exception as step_error:
                    if "Operation cancelled by user" in str(step_error):
                        GLib.idle_add(lambda: self.handle_import_cancellation(dst, backup_dir))
                    else:
                        print(f"Error during step '{step_text}': {step_error}")
                        GLib.idle_add(
                            lambda error=step_error, text=step_text: self.handle_import_error(
                                dst,
                                backup_dir,
                                _("An error occurred during '%(step)s': %(error)s") % {
                                    "step": text,
                                    "error": error,
                                }
                            )
                        )

                    return

            if not self.stop_processing:
                self.cleanup_backup(backup_dir)
                GLib.idle_add(self.on_import_wine_directory_completed)
                
        except Exception as import_error:
            print(f"Error during import process: {import_error}")
            GLib.idle_add(
                lambda error=import_error: self.handle_import_error(
                    dst,
                    backup_dir,
                    _("Import failed: %s") % error
                )
            )


    threading.Thread(target=perform_import_steps).start()

def on_import_wine_directory_completed(self):
    self.print_method_name()
    """
    Called when the import process is complete. Updates UI, restores scripts, and resets the open button.
    """
    # Reconnect open button and reset its label
    self.set_open_button_label("Open")
    self.set_open_button_icon_visible(True)
    
    self.hide_processing_spinner()

    # This will disconnect open_button handler, use this then reconnect the open
    #if self.open_button_handler_id is not None:
    #    self.open_button.disconnect(self.open_button_handler_id)

    self.reconnect_open_button()
    self.load_script_list()
    # Restore the script list in the flowbox
    GLib.idle_add(self.create_script_list)

    print("Wine directory import completed and script list restored.")

def copy_wine_directory(self, src, dst):
    self.print_method_name()
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
    self.print_method_name()
    """
    Show a confirmation dialog asking the user whether to overwrite the existing directory.
    """
    dialog = Adw.AlertDialog(
        title="Overwrite Existing Directory?",
        body=f"The directory {dest_dir.name} already exists. Do you want to overwrite it?"
    )

    # Add overwrite and cancel buttons
    dialog.add_response("overwrite", _("Overwrite"))
    dialog.set_response_appearance("overwrite", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.add_response("cancel", _("Cancel"))
    dialog.set_default_response("cancel")

    # Connect the dialog response to the overwrite handler
    dialog.connect("response", self.on_import_wine_directory_overwrite_response, src, dest_dir)

    # Show the dialog
    dialog.present(self.window)


def on_import_wine_directory_overwrite_response(self, dialog, response_id, src, dest_dir):
    self.print_method_name()
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
            GLib.timeout_add_seconds(1, self.show_info_dialog, _("Error"), _("Could not delete directory: %s") % e)
    else:
        print("User canceled the overwrite.")
        # If canceled, restore the UI to its original state
        self.reconnect_open_button()
        self.hide_processing_spinner()
        GLib.idle_add(self.create_script_list)
        # No need to restore the script list as it wasn't cleared

def on_cancel_import_wine_direcotory_dialog_response(self, dialog, response):
    self.print_method_name()
    """
    Handle cancel dialog response
    """
    if response == "cancel":
        self.stop_processing = True
        dialog.close()
    else:
        self.stop_processing = False
        dialog.close()
        #GLib.timeout_add_seconds(0.5, dialog.close)

def on_cancel_import_wine_directory_clicked(self, button):
    self.print_method_name()
    """
    Handle cancel button click
    """
    dialog = Adw.AlertDialog(
        title="Cancel Import",
        body=_("Do you want to cancel the wine directory import process?")
    )
    dialog.add_response("continue", _("Continue"))
    dialog.add_response("cancel", _("Cancel Creation"))
    dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.connect("response", self.on_cancel_import_wine_direcotory_dialog_response)
    dialog.present(self.window)


def connect_open_button_with_import_wine_directory_cancel(self):
    self.print_method_name()
    """
    Connect cancel handler to the open button
    """
    if self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_import_wine_directory_clicked)
    
    self.set_open_button_icon_visible(False)




def handle_import_cancellation(self, dst, backup_dir):
    self.print_method_name()
    """
    Handle import cancellation by restoring from backup.
    """
    try:
        if dst.exists():
            shutil.rmtree(dst)
            print(f"Removed incomplete import directory: {dst}")
        
        if backup_dir.exists():
            # Create the parent directory if it doesn't exist
            dst.parent.mkdir(parents=True, exist_ok=True)
            backup_dir.rename(dst)
            print(f"Restored original directory from backup")
            
    except Exception as e:
        print(f"Error during cancellation cleanup: {e}")
        # Still show cancelled message but also show error
        GLib.idle_add(
            self.show_info_dialog,
            _("Error"),
            _("Wine directory import was cancelled but encountered errors during cleanup: %(error)s\n"
            "Backup directory may still exist at: %(backup)s") % {
                "error": e,
                "backup": backup_dir,
            }
        )
        return

    
    self.stop_processing = False
    GLib.idle_add(self.on_import_wine_directory_completed)
    GLib.idle_add(self.show_info_dialog, _("Cancelled"), _("Wine directory import was cancelled"))

def handle_import_error(self, dst, backup_dir, error_message):
    self.print_method_name()
    """
    Handle errors during import by restoring from backup.
    """
    try:
        if dst.exists():
            shutil.rmtree(dst)
            print(f"Removed failed import directory: {dst}")
            
        if backup_dir.exists():
            backup_dir.rename(dst)
            print(f"Restored original directory after error")
            
    except Exception as e:
        print(_("Error during error cleanup: %s") % e)
        error_message += "\n"
        error_message += _("Additional error during cleanup: %s") % e

        if backup_dir.exists():
            error_message += "\n"
            error_message += _("Backup directory may still exist at: %s") % backup_dir

    self.stop_processing = False
    GLib.idle_add(self.on_import_wine_directory_completed)
    GLib.idle_add(self.show_info_dialog, _("Error"), error_message)

def cleanup_backup(self, backup_dir):
    self.print_method_name()
    """
    Clean up backup directory after successful import.
    """
    try:
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
            print(f"Removed backup directory after successful import: {backup_dir}")
    except Exception as e:
        print(f"Warning: Failed to remove backup directory: {e}")
        # Continue anyway since the import was successful


def cleanup_cancelled_import(self, temp_dir):
    self.print_method_name()
    """
    Clean up temporary directory and reset UI after cancelled import
    """
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print(f"Removed temporary directory: {temp_dir}")
    except Exception as e:
        print(f"Error cleaning up temporary directory: {e}")
    finally:
        self.stop_processing = False
        GLib.idle_add(self.on_import_wine_directory_completed)
        if not self.stop_processing:
            GLib.idle_add(self.show_info_dialog, _("Cancelled"), _("Wine directory import was cancelled"))

        #self.open_button.disconnect(self.open_button_handler_id)

        #self.reconnect_open_button()
        #self.load_script_list()
        ## Restore the script list in the flowbox
        GLib.idle_add(self.create_script_list)

def disconnect_open_button(self):
    self.print_method_name()
    """
    Disconnect the open button's handler and update its label to "Importing...".
    """
    if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
        self.open_button_handler_id = None  # Reset the handler ID after disconnecting
    
    # Update the label and hide the icon
    self.set_open_button_label("Importing...")
    self.set_open_button_icon_visible(False)  # Hide the open-folder icon
    print("Open button disconnected and spinner shown.")

def reconnect_open_button(self):
    self.print_method_name()
    """
    Reconnect the open button's handler and reset its label.
    """
    # Disconnect before reconnecting
    self.disconnect_open_button()

    if hasattr(self, 'open_button') and self.open_button is not None:
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
    
    # Reset the label and show the icon
    self.set_open_button_label("Open")
    self.set_open_button_icon_visible(True)
    print("Open button reconnected and UI reset.")

    
def create_scripts_for_exe_files(self, wineprefix):
    self.print_method_name()
    exe_files = self.find_exe_files(wineprefix)
    for exe_file in exe_files:
        self.create_yaml_file(exe_file, wineprefix, use_exe_name=True)
        
    #GLib.timeout_add_seconds(0.5, self.create_script_list)

def find_exe_files(self, wineprefix):
    self.print_method_name()
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
    self.print_method_name()
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
    self.print_method_name()
    try:
        src_path = Path(src).resolve()
        dst_path = Path(dst).resolve()

        # Ensure source exists
        if not src_path.exists():
            raise FileNotFoundError(f"Source directory {src_path} does not exist")

        # Create parent directory for destination
        dst_path.mkdir(parents=True, exist_ok=True)

        def preexec_function():
            """Ensure child processes don't receive signals"""
            os.setpgrp()

        # Use cp -a to copy contents of src to dst (not the directory itself)
        # The '/.' ensures we copy directory contents rather than the directory
        copy_process = subprocess.Popen(
            ['cp', '-a', f'{src_path}/.', str(dst_path)],
            preexec_fn=preexec_function,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        with self.process_lock:
            self.current_process = copy_process

        # Monitor process and handle cancellation
        while copy_process.poll() is None:
            if self.stop_processing:
                print("Cancellation requested, terminating copy process...")
                self._kill_current_process()
                if dst_path.exists():
                    print(f"Cleaning up partially copied files at {dst_path}")
                    shutil.rmtree(dst_path, ignore_errors=True)
                print("Operation cancelled by user")
                return

            # Pulse progress bar if available
            if hasattr(self, 'progress_bar'):
                GLib.idle_add(lambda: self.progress_bar.pulse())

            time.sleep(0.1)  # Reduce CPU usage

        # Handle completion
        if copy_process.returncode != 0:
            error_msg = copy_process.stderr.read().decode() if copy_process.stderr else "Unknown error"
            raise RuntimeError(f"Copy failed with code {copy_process.returncode}: {error_msg}")

        # Final progress update
        if hasattr(self, 'progress_bar'):
            GLib.idle_add(lambda: self.progress_bar.set_fraction(1.0))

    except Exception as e:
        print(f"Copy error: {str(e)}")
        if dst_path.exists():
            shutil.rmtree(dst_path, ignore_errors=True)
        raise
    finally:
        with self.process_lock:
            self.current_process = None

