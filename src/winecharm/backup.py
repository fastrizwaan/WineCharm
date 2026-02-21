#!/usr/bin/env python3

import gi
import threading
import subprocess
import os
import shutil
import time
import yaml
from pathlib import Path
from datetime import datetime

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gtk, Adw


##### BACKUP PREFIX
def show_backup_prefix_dialog(self, script, script_key, button):
    self.print_method_name()
    self.stop_processing = False
    wineprefix = Path(script).parent
    # Extract exe_file from script_data
    script_data = self.extract_yaml_info(script_key)
    if not script_data:
        raise Exception("Script data not found.")

    exe_file = self.expand_and_resolve_path(str(script_data['exe_file']))
    #exe_file = Path(str(exe_file).replace("%USERNAME%", user))
    exe_path = exe_file.parent
    exe_name = exe_file.name
    game_dir = wineprefix / "drive_c" / "GAMEDIR"
    game_dir_exe = game_dir / exe_path.name / exe_name


    # Check if game directory is inside the prefix
    is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

    creation_date_and_time = datetime.now().strftime("%Y%m%d%H%M")
    # Step 1: Suggest the backup file name
    default_backup_name = f"{script.stem}-{creation_date_and_time}.prefix"
    

    # Create a Gtk.FileDialog instance for saving the file
    file_dialog = Gtk.FileDialog.new()

    # Set the initial file name using set_initial_name() method
    file_dialog.set_initial_name(default_backup_name)

    # Open the dialog asynchronously to select the save location
    file_dialog.save(self.window, None, self.on_backup_prefix_dialog_response, script, script_key)

    print("FileDialog presented for saving the backup.")

def on_backup_prefix_dialog_response(self, dialog, result, script, script_key):
    self.print_method_name()
    try:
        # Retrieve the selected file (save location) using save_finish()
        backup_file = dialog.save_finish(result)
        if backup_file:
            self.on_back_button_clicked(None)
            self.flowbox.remove_all()
            backup_path = backup_file.get_path()  # Get the backup file path
            print(f"Backup will be saved to: {backup_path}")
            
            # Start the backup process in a separate thread
            threading.Thread(target=self.backup_prefix, args=(script, script_key,  backup_path)).start()

    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")

def on_backup_prefix_completed(self, script_key, backup_path):
    self.print_method_name()
    """
    Called when the backup process is complete. Updates the UI safely.
    """
    try:
        GLib.idle_add(self._complete_backup_ui_update, script_key, backup_path)
    except Exception as e:
        print(f"Error scheduling backup completion UI update: {e}")
        self.show_info_dialog(_("Warning"), _("Backup completed but there was an error updating the UI"))

def _complete_backup_ui_update(self, script_key, backup_path):
    self.print_method_name()
    """
    Performs the actual UI updates on the main thread after backup completion
    """
    try:
        # First disconnect any existing handlers
        if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
            if hasattr(self, 'open_button'):
                try:
                    self.open_button.disconnect(self.open_button_handler_id)
                except:
                    pass
                self.open_button_handler_id = None
        
        # Then reset the UI elements
        self.hide_processing_spinner()
        
        # Now reconnect the open button
        if hasattr(self, 'open_button'):
            self.open_button_handler_id = self.open_button.connect(
                "clicked", 
                self.on_open_button_clicked
            )
        
        # Update labels and icons
        self.set_open_button_label(_("Open"))
        self.set_open_button_icon_visible(True)
        
        # Show completion dialog
        self.show_info_dialog(_("Backup Complete"), _("Backup saved to %s") % backup_path)
        print("Backup process completed successfully.")

        # Update script options if available
        if hasattr(self, 'script_ui_data') and script_key in self.script_ui_data:
            self.show_options_for_script(
                self.script_ui_data[script_key],
                self.script_ui_data[script_key]['row'],
                script_key
            )
        
        return False  # Required for GLib.idle_add
        
    except Exception as e:
        print(f"Error during backup completion UI update: {e}")
        self.show_info_dialog(_("Warning"), _("Backup completed but there was an error updating the UI"))
        return False



def backup_prefix(self, script, script_key, backup_path):
    self.print_method_name()
    """
    Backs up the Wine prefix in a stepwise manner, indicating progress via spinner and label updates.
    """
    # Store current script info for cancellation handling
    self.current_script = script
    self.current_script_key = script_key
    self.stop_processing = False
    self.current_backup_path = backup_path
    wineprefix = Path(script).parent

    try:
        # Step 1: Initialize the UI for backup process
        self.show_processing_spinner(_("Exporting..."))
        self.connect_open_button_with_backup_cancel(script_key)

        # Get the user's home directory to replace with `~`
        usershome = os.path.expanduser('~')
        find_replace_pairs = {usershome: '~'}
        
        def perform_backup_steps():
            self.print_method_name()
            try:
                steps = [
                    (_("Replace \"%s\" with '~' in script files") % usershome, lambda: self.replace_strings_in_files(wineprefix, find_replace_pairs)),
                    (_("Reverting user-specific .reg changes"), lambda: self.reverse_process_reg_files(wineprefix)),
                    (_("Creating backup archive"), lambda: self.create_backup_archive(wineprefix, backup_path)),
                    (_("Re-applying user-specific .reg changes"), lambda: self.process_reg_files(wineprefix)),
                ]

                self.total_steps = len(steps)
                
                for step_text, step_func in steps:
                    if self.stop_processing:
                        GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)
                        return

                    GLib.idle_add(self.show_initializing_step, step_text)
                    try:
                        step_func()
                        if self.stop_processing:
                            GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)
                            return
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        print(f"Error during step '{step_text}': {e}")
                        if not self.stop_processing:
                            GLib.idle_add(
                                self.show_info_dialog,
                                _("Backup Failed"),
                                _("Error during '%(step)s': %(error)s") % {
                                    "step": step_text,
                                    "error": str(e),
                                }
                            )

                        GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)
                        return

                if not self.stop_processing:
                    GLib.idle_add(self.on_backup_prefix_completed, script_key, backup_path)
                    
            except Exception as e:
                print(f"Backup process failed: {e}")
                GLib.idle_add(self.cleanup_cancelled_backup, script, script_key)

        # Run the backup steps in a separate thread
        self.processing_thread = threading.Thread(target=perform_backup_steps)
        self.processing_thread.start()

    except Exception as e:
        print(f"Error initializing backup process: {e}")
        self.cleanup_cancelled_backup(script, script_key)

def create_backup_archive(self, wineprefix, backup_path):
    self.print_method_name()
    """
    Create a backup archive with interruption support
    """
    if self.stop_processing:
        raise Exception("Operation cancelled by user")

    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        raise Exception("Unable to determine the current username from the environment.")

    tar_command = [
        'tar',
        '-I', 'zstd -T0',
        '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",
        '-cf', backup_path,
        '-C', str(wineprefix.parent),
        wineprefix.name
    ]

    print(f"Running backup command: {' '.join(tar_command)}")

    process = subprocess.Popen(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    while process.poll() is None:
        if self.stop_processing:
            process.terminate()
            try:
                process.wait(timeout=2)
                if Path(backup_path).exists():
                    Path(backup_path).unlink()
            except subprocess.TimeoutExpired:
                process.kill()
            raise Exception("Operation cancelled by user")
        time.sleep(0.1)

    if process.returncode != 0 and not self.stop_processing:
        stderr = process.stderr.read().decode()
        raise Exception(f"Backup failed: {stderr}")

def connect_open_button_with_backup_cancel(self, script_key):
    self.print_method_name()
    """
    Connect cancel handler to the open button for backup process
    """
    if self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_backup_clicked, script_key)
    
    self.set_open_button_icon_visible(False)

def cleanup_cancelled_backup(self, script, script_key):
    self.print_method_name()
    """
    Clean up after backup is cancelled
    """
    try:
        # Clean up partial backup file if it exists
        if hasattr(self, 'current_backup_path') and Path(self.current_backup_path).exists():
            try:
                Path(self.current_backup_path).unlink()
                self.current_backup_path = None
            except Exception as e:
                print(f"Error deleting partial backup file: {e}")
    except Exception as e:
        print(f"Error during backup cleanup: {e}")
    finally:
        try:
            # Reset UI state
            self.set_open_button_label(_("Open"))
            self.set_open_button_icon_visible(True)
            self.hide_processing_spinner()
            
            if self.stop_processing:
                self.show_info_dialog(_("Cancelled"), _("Backup was cancelled"))
            
            # Safely update UI elements
            if hasattr(self, 'script_ui_data') and script_key in self.script_ui_data:
                self.show_options_for_script(self.script_ui_data[script_key], 
                                        self.script_ui_data[script_key]['row'], 
                                        script_key)
        except Exception as e:
            print(f"Error during UI cleanup: {e}")
            self.show_info_dialog(_("Warning"), _("There was an error updating the UI"))

def on_cancel_backup_clicked(self, button, script_key):
    self.print_method_name()
    """
    Handle cancel button click during backup
    """
    dialog = Adw.AlertDialog(
        heading=_("Cancel Backup"),
        body=_("Do you want to cancel the backup process?")
    )

    dialog.add_response("continue", _("Continue"))
    dialog.add_response("cancel", _("Cancel Backup"))
    dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.connect("response", self.on_cancel_backup_dialog_response, script_key)
    dialog.present(self.window)

def on_cancel_backup_dialog_response(self, dialog, response, script_key):
    self.print_method_name()
    """
    Handle cancel dialog response for backup
    """
    if response == "cancel":
        self.stop_processing = True
    dialog.close()
    GLib.idle_add(self.create_script_list)
######################### CREATE BOTTLE
# Get directory size method
def get_directory_size(self, path):
    self.print_method_name()
    if not path.exists():
        print(f"The provided path '{path}' does not exist.")
        return 0

    try:
        total_size = sum(f.stat().st_size for f in path.glob('**/*') if f.is_file())
        return total_size
    except Exception as e:
        print(f"Error calculating directory size: {e}")
        return 0

def create_bottle(self, script, script_key, backup_path):
    self.print_method_name()
    """
    Backs up the Wine prefix in a stepwise manner, indicating progress via spinner and label updates.
    """
    # Store current script info for cancellation handling
    self.current_script = script
    self.current_script_key = script_key
    self.stop_processing = False
    self.current_backup_path = backup_path
    wineprefix = Path(script).parent

    self.hide_processing_spinner()

    # Step 1: Disconnect the UI elements and initialize the spinner
    self.show_processing_spinner(_("Bottling..."))
    self.connect_open_button_with_bottling_cancel(script_key)

    # Get the user's home directory to replace with `~`
    usershome = os.path.expanduser('~')

    # Get the current username from the environment
    user = os.getenv("USER") or os.getenv("USERNAME")
    if not user:
        raise Exception("Unable to determine the current username from the environment.")
    
    find_replace_pairs = {usershome: '~', f'\'{usershome}': '\'~\''}
    find_replace_media_username = {f'/media/{user}/': '/media/%USERNAME%/'}
    restore_media_username = {'/media/%USERNAME%/': f'/media/{user}/'}

    # Extract exe_file from script_data
    script_data = self.extract_yaml_info(script_key)
    if not script_data:
        raise Exception("Script data not found.")

    exe_file = self.expand_and_resolve_path(str(script_data['exe_file']))
    exe_file = Path(str(exe_file).replace("%USERNAME%", user))
    exe_path = exe_file.parent
    exe_name = exe_file.name
    
    try:
        # Get the runner from the script data
        runner = self.get_runner(script_data)
        runner_dir = runner.parent.resolve()
    except Exception as e:
        print(f"Error getting runner: {e}")
        return
    

    # If runner is inside the script
    if runner:
        print(f"RUNNER FOUND = {runner}")
        # Check if the runner is inside runners_dir
        is_runner_inside_prefix = runner.is_relative_to(self.runners_dir)
        print("===========================================================")
        if is_runner_inside_prefix:
            print("RUNNER INSIDE PREFIX")
            runner_dir = runner.parent.parent
            runner_dir_exe = runner_dir / "bin/wine"

            target_runner_dir = wineprefix / "Runner" 
            target_runner_exe = target_runner_dir / runner_dir.name / "bin/wine"
        else:
            target_runner_exe = runner
            runner_dir_exe = runner
            print("RUNNER IS NOT INSIDE PREFIX")

    # Check if game directory is inside the prefix
    is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

    print("==========================================================")
    # exe_file path replacement should use existing exe_file if it's already inside prefix
    if is_exe_inside_prefix:
        game_dir = exe_path
        game_dir_exe = exe_file
        print(f"""
        exe_file is inside wineprefix:
        game_dir = {game_dir}
        game_dir_exe = {game_dir_exe}
        """)
    else:
        game_dir = wineprefix / "drive_c" / "GAMEDIR"
        game_dir_exe = game_dir / exe_path.name / exe_name
        print(f"""
        exe_file is OUTSIDE wineprefix:
        game_dir = {game_dir}
        game_dir_exe = {game_dir_exe}
        """)

    def perform_backup_steps():
        self.print_method_name()
        try:
            # Basic steps that are always needed
            basic_steps = [
                (_("Replace \"%s\" with '~' in files") % usershome, lambda: self.replace_strings_in_files(wineprefix, find_replace_pairs)),
                (_("Reverting user-specific .reg changes"), lambda: self.reverse_process_reg_files(wineprefix)),
                (_("Replace \"/media/%s\" with '/media/%%USERNAME%%' in files") % user, lambda: self.replace_strings_in_files(wineprefix, find_replace_media_username)),
                (_("Updating exe_file Path in Script"), lambda: self.update_exe_file_path_in_script(script, self.replace_home_with_tilde_in_path(str(game_dir_exe)))),
                (_("Creating Bottle archive"), lambda: self.create_bottle_archive(script_key, wineprefix, backup_path)),
                (_("Re-applying user-specific .reg changes"), lambda: self.process_reg_files(wineprefix)),
                (_("Revert %%USERNAME%% with \"%s\" in script files") % user, lambda: self.replace_strings_in_files(wineprefix, restore_media_username)),
                (_("Reverting exe_file Path in Script"), lambda: self.update_exe_file_path_in_script(script, self.replace_home_with_tilde_in_path(str(exe_file))))
            ]

            
            # Set total steps and initialize progress UI
            self.total_steps = len(basic_steps)

            # Add runner-related steps only if runner exists and is not empty
            steps = basic_steps.copy()
            if runner and str(runner).strip():
                is_runner_inside_prefix = runner.is_relative_to(self.runners_dir)
                if is_runner_inside_prefix:
                    runner_update_index = next(i for i, (text, _) in enumerate(steps) if text == "Creating Bottle archive")
                    steps.insert(
                        runner_update_index,
                        (_("Updating runner Path in Script"),
                        lambda: self.update_runner_path_in_script(
                            script,
                            self.replace_home_with_tilde_in_path(str(target_runner_exe))
                        ))
                    )
                    steps.append(
                        (_("Reverting runner Path in Script"),
                        lambda: self.update_runner_path_in_script(
                            script,
                            self.replace_home_with_tilde_in_path(str(runner))
                        ))
                    )

            for step_text, step_func in steps:
                if self.stop_processing:
                    GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)
                    return

                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    step_func()
                    if self.stop_processing:
                        GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)
                        return
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    print(f"Error during step '{step_text}': {e}")
                    if not self.stop_processing:
                        GLib.idle_add(
                            self.show_info_dialog,
                            _("Backup Failed"),
                            _("Error during '%(step)s': %(error)s") % {
                                "step": step_text,
                                "error": str(e),
                            }
                        )


                    GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)
                    return

            if not self.stop_processing:
                GLib.idle_add(self.on_create_bottle_completed, script_key, backup_path)
            
        except Exception as e:
            print(f"Backup process failed: {e}")
            GLib.idle_add(self.cleanup_cancelled_bottle, script, script_key)

    # Run the backup steps in a separate thread to keep the UI responsive
    self.processing_thread = threading.Thread(target=perform_backup_steps)
    self.processing_thread.start()

def on_create_bottle_completed(self, script_key, backup_path):
    self.print_method_name()
    """
    Called when the bottle creation process is complete. Schedules UI updates safely.
    """
    try:
        GLib.idle_add(self._complete_bottle_creation_ui_update, script_key, backup_path)
    except Exception as e:
        print(f"Error scheduling bottle creation UI update: {e}")
        self.show_info_dialog(_("Warning"), _("Bottle created but there was an error updating the UI"))

def _complete_bottle_creation_ui_update(self, script_key, backup_path):
    self.print_method_name()
    """
    Performs the actual UI updates on the main thread after bottle creation completion
    """
    try:
        # First disconnect any existing handlers
        if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
            if hasattr(self, 'open_button'):
                try:
                    self.open_button.disconnect(self.open_button_handler_id)
                except:
                    pass
                self.open_button_handler_id = None
        
        # Reset the UI elements
        self.hide_processing_spinner()
        
        # Reconnect the open button
        if hasattr(self, 'open_button'):
            self.open_button_handler_id = self.open_button.connect(
                "clicked", 
                self.on_open_button_clicked
            )
        
        # Update labels and icons
        self.set_open_button_label(_("Open"))
        self.set_open_button_icon_visible(True)
        
        # Show completion dialog
        self.show_info_dialog(_("Bottle Created"), _("%s") % backup_path)
        print("Bottle creating process completed successfully.")

        # Safely update UI elements
        if hasattr(self, 'script_ui_data') and script_key in self.script_ui_data:
            self.show_options_for_script(self.script_ui_data[script_key], 
                                    self.script_ui_data[script_key]['row'], 
                                    script_key)

        return False  # Required for GLib.idle_add
        
    except Exception as e:
        print(f"Error during bottle creation UI update: {e}")
        self.show_info_dialog(_("Warning"), _("Bottle created but there was an error updating the UI"))
        return False


def on_backup_confirmation_response(self, dialog, response_id, script, script_key):
    self.print_method_name()
    if response_id == "continue":
        dialog.close()
        self.show_create_bottle_dialog(script, script_key)
    else:
        return

def create_bottle_selected(self, script, script_key, button):
    self.print_method_name()
    self.stop_processing = False
    # Step 1: Check if the executable file exists
    # Extract exe_file from script_data
    script_data = self.extract_yaml_info(script_key)
    if not script_data:
        raise Exception("Script data not found.")

    wineprefix = Path(script).parent
    exe_file = self.expand_and_resolve_path(script_data['exe_file'])
    #exe_file = Path(str(exe_file).replace("%USERNAME%", user))
    exe_path = exe_file.parent
    exe_name = exe_file.name
    game_dir = wineprefix / "drive_c" / "GAMEDIR"
    game_dir_exe = game_dir / exe_path.name / exe_name

    # Check if the game directory is in DO_NOT_BUNDLE_FROM directories
    if str(exe_path) in self.get_do_not_bundle_directories():
        msg1 = _("Cannot copy the selected game directory")
        msg2 = _("Please move the files to a different directory to create a bundle.")
        self.show_info_dialog(msg1, msg2)
        return

    # If exe_not found i.e., game_dir is not accessble due to unmounted directory
    if not exe_file.exists():
        GLib.timeout_add_seconds(1, self.show_info_dialog,
                         _("Exe Not Found"),
                         _("Not Mounted or Deleted?\n%s") % exe_file)
        return

    # Step 2: Check for size if > 3GB ask the user:
    # Calculate the directory size in bytes
    directory_size = self.get_directory_size(exe_path)

    # Convert directory size to GB for comparison
    directory_size_gb = directory_size / (1024 ** 3)  # 1 GB is 1024^3 bytes
    directory_size_gb = round(directory_size_gb, 2)  # round to two decimal places

    print("----------------------------------------------------------")
    print(directory_size)
    print(directory_size_gb)

    if directory_size_gb > 3:
        print("Size Greater than 3GB")
        # Show confirmation dialog
        dialog = Adw.AlertDialog(
            heading=_("Large Game Directory"),
            body=_("The game directory size is %(size)sGB. Do you want to continue?") % {
                "size": directory_size_gb
            }
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("continue", _("Continue"))
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self.on_backup_confirmation_response, script, script_key)
        dialog.present(self.window)
        print("----------------------------------------------------------")
    else:
        self.show_create_bottle_dialog(script, script_key)

def show_create_bottle_dialog(self, script, script_key):
    self.print_method_name()

    creation_date_and_time = datetime.now().strftime("%Y%m%d%H%M")
    # Suggest the backup file name
    default_backup_name = f"{script.stem}-{creation_date_and_time}.bottle"

    # Create a Gtk.FileDialog instance for saving the file
    file_dialog = Gtk.FileDialog.new()

    # Set the initial file name using set_initial_name() method
    file_dialog.set_initial_name(default_backup_name)

    # Open the dialog asynchronously to select the save location
    file_dialog.save(self.window, None, self.on_create_bottle_dialog_response, script, script_key)

    print("FileDialog presented for saving the backup.")

def on_create_bottle_dialog_response(self, dialog, result, script, script_key):
    self.print_method_name()
    try:
        # Retrieve the selected file (save location) using save_finish()
        backup_file = dialog.save_finish(result)
        if backup_file:
            self.on_back_button_clicked(None)
            self.flowbox.remove_all()
            backup_path = backup_file.get_path()  # Get the backup file path
            print(f"Backup will be saved to: {backup_path}")

            # Start the backup process in a separate thread
            threading.Thread(target=self.create_bottle, args=(script, script_key, backup_path)).start()

    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")

def create_bottle_archive(self, script_key, wineprefix, backup_path):
    self.print_method_name()
    """
    Create a bottle archive with interruption support
    """

    if self.stop_processing:
        raise Exception("Operation cancelled by user")

    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        raise Exception("Unable to determine the current username from the environment.")

    script_data = self.extract_yaml_info(script_key)
    if not script_data:
        raise Exception("Script data not found.")

    exe_file = Path(str(script_data['exe_file'])).expanduser().resolve()
    exe_file = Path(str(exe_file).replace("%USERNAME%", current_username))
    exe_path = exe_file.parent
    tar_game_dir_name = exe_path.name
    tar_game_dir_path = exe_path.parent

    try:
        # Get the runner from the script data
        runner = self.get_runner(script_data)
        runner_dir = runner.parent.resolve()
    except Exception as e:
        print(f"Error getting runner: {e}")
        return

    # Build tar command with transforms
    tar_command = [
        'tar',
        '-I', 'zstd -T0',
        '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",
    ]

    is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)
    if not is_exe_inside_prefix:
        tar_command.extend([
            '--transform', rf"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g"
        ])

    sources = []
    sources.append(('-C', str(wineprefix.parent), wineprefix.name))

    if runner and runner.is_relative_to(self.runners_dir):
        runner_dir = runner.parent.parent
        runner_dir_name = runner_dir.name
        runner_dir_path = runner_dir.parent
        tar_command.extend([
            '--transform', rf"s|^\./{runner_dir_name}|{wineprefix.name}/Runner/{runner_dir_name}|g"
        ])
        sources.append(('-C', str(runner_dir_path), rf"./{runner_dir_name}"))

    if not is_exe_inside_prefix:
        sources.append(('-C', str(tar_game_dir_path), rf"./{tar_game_dir_name}"))

    tar_command.extend(['-cf', backup_path])

    for source in sources:
        tar_command.extend(source)

    print(f"Running create bottle command: {' '.join(tar_command)}")

    process = subprocess.Popen(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    while process.poll() is None:
        if self.stop_processing:
            process.terminate()
            try:
                process.wait(timeout=2)
                if Path(backup_path).exists():
                    Path(backup_path).unlink()
            except subprocess.TimeoutExpired:
                process.kill()
            raise Exception("Operation cancelled by user")
        time.sleep(0.1)

    if process.returncode != 0 and not self.stop_processing:
        stderr = process.stderr.read().decode()
        raise Exception(f"Backup failed: {stderr}")

    # Get the current username from the environment
    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        raise Exception("Unable to determine the current username from the environment.")

    # Extract exe_file from script_data
    script_data = self.extract_yaml_info(script_key)
    if not script_data:
        raise Exception("Script data not found.")

    exe_file = Path(str(script_data['exe_file'])).expanduser().resolve()
    exe_file = Path(str(exe_file).replace("%USERNAME%", current_username))
    exe_path = exe_file.parent

    # Check if game directory is inside the prefix
    is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

    tar_game_dir_name = exe_path.name
    tar_game_dir_path = exe_path.parent

    try:
        # Get the runner from the script data
        runner = self.get_runner(script_data)
        runner_dir = runner.parent.resolve()
    except Exception as e:
        print(f"Error getting runner: {e}")
        return

    # Start building the tar command with common options
    tar_command = [
        'tar',
        '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
        '--transform', rf"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",
    ]

    # If game is not in prefix, add game directory transform
    if not is_exe_inside_prefix:
        tar_command.extend([
            '--transform', rf"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g"
        ])

    # Initialize the list of source directories and their base paths
    sources = []
    
    # Always add the wineprefix
    sources.append(('-C', str(wineprefix.parent), wineprefix.name))

    # If runner exists and is inside runners_dir
    if runner and runner.is_relative_to(self.runners_dir):
        runner_dir = runner.parent.parent
        runner_dir_name = runner_dir.name
        runner_dir_path = runner_dir.parent
        tar_command.extend([
            '--transform', rf"s|^\./{runner_dir_name}|{wineprefix.name}/Runner/{runner_dir_name}|g"
        ])
        sources.append(('-C', str(runner_dir_path), rf"./{runner_dir_name}"))


    # If game is not in prefix, add it as a source
    if not is_exe_inside_prefix:
        sources.append(('-C', str(tar_game_dir_path), rf"./{tar_game_dir_name}"))

    # Add the output file path
    tar_command.extend(['-cf', backup_path])

    # Add all sources to the command
    for source in sources:
        tar_command.extend(source)

    print(f"Running create bottle command: {' '.join(tar_command)}")

    # Execute the tar command
    result = subprocess.run(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        raise Exception(f"Backup failed: {result.stderr}")

    print(f"Backup archive created at {backup_path}")

def connect_open_button_with_bottling_cancel(self, script_key):
    self.print_method_name()
    """
    Connect cancel handler to the open button
    """
    if self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_bottle_clicked, script_key)
    
    self.set_open_button_icon_visible(False)

def cleanup_cancelled_bottle(self, script, script_key):
    self.print_method_name()
    """
    Clean up after bottle creation is cancelled
    """
    try:
        if Path(script).exists():
            script_data = self.extract_yaml_info(script_key)
            if script_data:
                # Revert exe_file path
                if 'exe_file' in script_data:
                    original_exe = script_data['exe_file']
                    self.update_exe_file_path_in_script(script, original_exe)
                
                # Revert runner path if it exists
                if 'runner' in script_data and script_data['runner']:
                    original_runner = script_data['runner']
                    self.update_runner_path_in_script(script, original_runner)

    except Exception as e:
        print(f"Error during cleanup: {e}")
    finally:
        #self.reconnect_open_button()
        self.hide_processing_spinner()
        if self.stop_processing:
            self.show_info_dialog(_("Cancelled"), _("Bottle creation was cancelled"))
        # Iterate over all script buttons and update the UI based on `is_clicked_row`
            for key, data in self.script_ui_data.items():
                row_button = data['row']
                row_play_button = data['play_button']
                row_options_button = data['options_button']
            self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)
            # Delete partial backup file if it exists
            if hasattr(self, 'current_backup_path') and Path(self.current_backup_path).exists():
                try:
                    Path(self.current_backup_path).unlink()
                    self.current_backup_path = None
                except Exception as e:
                    print(f"Error deleting partial backup file: {e}")

def on_cancel_bottle_clicked(self, button, script_key):
    self.print_method_name()
    """
    Handle cancel button click
    """
    dialog = Adw.AlertDialog(
    heading=_("Cancel Bottle Creation"),
    body=_("Do you want to cancel the bottle creation process?")
    )
    dialog.add_response("continue", _("Continue"))
    dialog.add_response("cancel", _("Cancel Creation"))

    dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.connect("response", self.on_cancel_bottle_dialog_response, script_key)
    dialog.present(self.window)


def on_cancel_bottle_dialog_response(self, dialog, response, script_key):
    self.print_method_name()
    """
    Handle cancel dialog response
    """
    if response == "cancel":
        self.stop_processing = True
        dialog.close()
        #GLib.timeout_add_seconds(0.5, dialog.close)
#            self.set_open_button_label("Open")
#            self.set_open_button_icon_visible(True)
#            self.reconnect_open_button()
#            self.hide_processing_spinner()


#            # Iterate over all script buttons and update the UI based on `is_clicked_row`
#            for key, data in self.script_ui_data.items():
#                row_button = data['row']
#                row_play_button = data['play_button']
#                row_options_button = data['options_button']
#            self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)
    else:
        self.stop_processing = False
        dialog.close()
        #GLib.timeout_add_seconds(0.5, dialog.close)

###################################### / CREATE BOTTLE  end
def backup_existing_directory(self, dst, backup_dir):
    self.print_method_name()
    """
    Safely backup the existing directory if it exists.
    """
    if dst.exists():
        try:
            # Create the parent directory if it doesn't exist
            backup_dir.parent.mkdir(parents=True, exist_ok=True)
            # First create the destination directory
            dst.rename(backup_dir)
            print(f"Created backup of existing directory: {backup_dir}")
        except Exception as e:
            raise Exception(f"Failed to create backup: {e}")
            
            
            
############ fix hang of bottle runner issue in 64bit only env
            
