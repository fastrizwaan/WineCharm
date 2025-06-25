#!/usr/bin/env python3

import gi
import threading
import subprocess
import os
import shutil
import time
import yaml
from pathlib import Path
from threading import Lock

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Adw

####################### Restore Backup (prefix, bottle, .tar.zst, .wzt)

def restore_from_backup(self, action=None, param=None):
    self.print_method_name()
    # Step 1: Create required directories (if needed)
    self.create_required_directories()

    # Step 2: Create a new Gtk.FileDialog instance
    file_dialog = Gtk.FileDialog.new()

    # Step 3: Create file filters for .tar.zst and .wzt files
    file_filter_combined = Gtk.FileFilter()
    file_filter_combined.set_name("Backup Files (*.prefix, *.bottle, *.wzt)")
    file_filter_combined.add_pattern("*.prefix")
    file_filter_combined.add_pattern("*.bottle")
    file_filter_combined.add_pattern("*.wzt")

    file_filter_botle_tar = Gtk.FileFilter()
    file_filter_botle_tar.set_name("WineCharm Bottle Files (*.bottle)")
    file_filter_botle_tar.add_pattern("*.bottle")

    file_filter_tar = Gtk.FileFilter()
    file_filter_tar.set_name("WineCharm Prefix Backup (*.prefix)")
    file_filter_tar.add_pattern("*.prefix")

    file_filter_wzt = Gtk.FileFilter()
    file_filter_wzt.set_name("Winezgui Backup Files (*.wzt)")
    file_filter_wzt.add_pattern("*.wzt")

    # Step 4: Set the filters on the dialog
    filter_model = Gio.ListStore.new(Gtk.FileFilter)
    
    # Add the combined filter as the default option
    filter_model.append(file_filter_combined)

    # Add individual filters for .tar.zst and .wzt files
    filter_model.append(file_filter_tar)
    filter_model.append(file_filter_botle_tar)
    filter_model.append(file_filter_wzt)
    
    # Apply the filters to the file dialog
    file_dialog.set_filters(filter_model)

    # Step 5: Open the dialog and handle the response
    file_dialog.open(self.window, None, self.on_restore_file_dialog_response)

def get_total_uncompressed_size(self, archive_path):
    self.print_method_name()
    """
    Calculate the total uncompressed size of a tar archive without extracting it.

    Args:
        archive_path (str): The path to the tar archive.

    Returns:
        int: Total uncompressed size of the archive in bytes.
    """
    # Run the tar command and capture the output
    command = ['tar', '-tvf', archive_path]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Check if there was an error
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return 0

    total_size = 0

    # Process each line of the tar output
    for line in result.stdout.splitlines():
        # Split the line by spaces and extract the third field (file size)
        parts = line.split()
        if len(parts) > 2:
            try:
                size = int(parts[2])  # The size is in the third field
                total_size += size
            except ValueError:
                pass  # Skip lines where we can't parse the size

    print(f"Total uncompressed size: {total_size} bytes")
    return total_size


def check_disk_space_and_uncompressed_size(self, prefixes_dir, file_path):
    self.print_method_name()
    """
    Check the available disk space and uncompressed size of the backup file.

    Args:
        prefixes_dir (Path): The directory where the wine prefixes are stored.
        file_path (str): Path to the backup .tar.zst file.

    Returns:
        (bool, int, int): Tuple containing:
            - True if there's enough space, False otherwise.
            - Available disk space in bytes.
            - Uncompressed size of the archive in bytes.
    """
    try:
        # Step 1: Get available disk space in the prefixes directory
        df_output = subprocess.check_output(['df', '--output=avail', str(prefixes_dir)]).decode().splitlines()[1]
        available_space_kb = int(df_output.strip()) * 1024  # Convert KB to bytes

        # Step 2: Get the total uncompressed size of the tar.zst file
        uncompressed_size_bytes = self.get_total_uncompressed_size(file_path)

        print(f"Available space: {available_space_kb / (1024 * 1024)} MB")
        print(f"Uncompressed size: {uncompressed_size_bytes / (1024 * 1024)} MB")

        # Step 3: Compare available space with uncompressed size
        return available_space_kb >= uncompressed_size_bytes, available_space_kb, uncompressed_size_bytes

    except subprocess.CalledProcessError as e:
        print(f"Error checking disk space or uncompressed size: {e}")
        return False, 0, 0


def on_restore_file_dialog_response(self, dialog, result):
    self.print_method_name()
    try:
        # Retrieve the selected file using open_finish() for Gtk.FileDialog in GTK 4
        file = dialog.open_finish(result)
        if file:
            # Get the file path
            file_path = file.get_path()
            print(f"Selected file: {file_path}")

            # the restore
            self.restore_prefix_bottle_wzt_tar_zst(file_path)

    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")


def restore_prefix_bottle_wzt_tar_zst(self, file_path):
    self.print_method_name()
    """
    Restore from a .prefix or .bottle which is a .tar.zst compressed file.
    """
    self.stop_processing = False

    # Clear the flowbox and show progress spinner
    GLib.idle_add(self.flowbox.remove_all)
    self.show_processing_spinner(f"Restoring")
    
    try:
        # Extract prefix name before starting
        extracted_prefix = self.extract_prefix_dir(file_path)
        print("= ="*50)
        print(f"extracted_prefix ={extracted_prefix}")
        if not extracted_prefix:
            raise Exception("Failed to determine prefix directory name")
        
        # Handle existing directory
        backup_dir = None
        if extracted_prefix.exists():
            timestamp = int(time.time())
            backup_dir = extracted_prefix.parent / f"{extracted_prefix.name}_backup_{timestamp}"
            shutil.move(str(extracted_prefix), str(backup_dir))
            print(f"Backed up existing directory to: {backup_dir}")

        #self.disconnect_open_button()
        #self.connect_open_button_with_import_wine_directory_cancel()
        self.connect_open_button_with_restore_backup_cancel()
        def restore_process():
            try:
                if file_path.endswith(".wzt"):
                    restore_steps = self.get_wzt_restore_steps(file_path)
                else:
                    restore_steps = self.get_restore_steps(file_path)

                for step_text, step_func in restore_steps:
                    if self.stop_processing:
                        if backup_dir and backup_dir.exists():
                            if extracted_prefix.exists():
                                shutil.rmtree(extracted_prefix)
                            shutil.move(str(backup_dir), str(extracted_prefix))
                            print(f"Restored original directory from: {backup_dir}")
                        return  # Finally block will handle UI reset

                    GLib.idle_add(self.show_initializing_step, step_text)
                    try:
                        step_func()
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        print(f"Error during step '{step_text}': {e}")
                        if backup_dir and backup_dir.exists():
                            if extracted_prefix.exists():
                                shutil.rmtree(extracted_prefix)
                            shutil.move(str(backup_dir), str(extracted_prefix))
                        GLib.idle_add(self.show_info_dialog, "Error", f"Failed during step '{step_text}': {str(e)}")
                        return  # Finally block will handle UI reset

                # Success case
                if backup_dir and backup_dir.exists():
                    shutil.rmtree(backup_dir)
                    print(f"Removed backup directory: {backup_dir}")

            except Exception as e:
                print(f"Error during restore process: {e}")
                if backup_dir and backup_dir.exists():
                    if extracted_prefix.exists():
                        shutil.rmtree(extracted_prefix)
                    shutil.move(str(backup_dir), str(extracted_prefix))
                GLib.idle_add(self.show_info_dialog, "Error", f"Restore failed: {str(e)}")

            finally:
                GLib.idle_add(self.on_restore_completed)
        # Start the restore process in a new thread
        threading.Thread(target=restore_process).start()

    except Exception as e:
        print(f"Error initiating restore process: {e}")
        GLib.idle_add(self.show_info_dialog, "Error", f"Failed to start restore: {str(e)}")



def get_restore_steps(self, file_path):
    self.print_method_name()
    """
    Return the list of steps for restoring a prefix/bottle backup.
    """
    return [
        ("Checking Uncompressed Size", lambda: self.check_disk_space_and_show_step(file_path)),
        ("Extracting Backup File", lambda: self.extract_backup(file_path)),
        ("Processing Registry Files", lambda: self.process_reg_files(self.extract_prefix_dir(file_path))),
        ("Performing Replacements", lambda: self.perform_replacements(self.extract_prefix_dir(file_path))),
        ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
        ("Renaming and merging user directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(file_path))),
        ("Add Shortcuts to Script List", lambda: self.add_charm_files_to_script_list(self.extract_prefix_dir(file_path))),
        ("Create Wineboot Required file", lambda: self.create_wineboot_required_file(self.extract_prefix_dir(file_path))),
    ]

def get_wzt_restore_steps(self, file_path):
    self.print_method_name()
    """
    Return the list of steps for restoring a WZT backup.
    """
    return [
        ("Checking Disk Space", lambda: self.check_disk_space_and_show_step(file_path)),
        ("Extracting WZT Backup File", lambda: self.extract_backup(file_path)),
        ("Performing User Related Replacements", lambda: self.perform_replacements(self.extract_prefix_dir(file_path))),
        ("Processing WineZGUI Script Files", lambda: self.process_sh_files(self.extract_prefix_dir(file_path))),
        ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
        ("Renaming and Merging User Directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(file_path))),
        ("Search LNK Files and Append to Found List", lambda: self.find_and_save_lnk_files(self.extract_prefix_dir(file_path))),
        ("Create Wineboot Required file", lambda: self.create_wineboot_required_file(self.extract_prefix_dir(file_path))),
    ]

def create_wineboot_required_file(self, wineprefix):
    wineboot_file_path = Path(wineprefix) / "wineboot-required.yml"

    data = {
        'wineboot': 'required'
    }

    try:
        with open(wineboot_file_path, 'w') as file:
            yaml.dump(data, file, default_flow_style=False, width=10000)
        print(f"wineboot-required.yml file created successfully at {wineboot_file_path}")
    except Exception as e:
        print(f"Error creating wineboot-required.yml file: {e}")

def perform_replacements(self, directory):
    self.print_method_name()
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
        "XOWINEEXEXO": "",
        "XOWINEVERXO": "wine-9.0",
        "/media/%USERNAME%/": f'/media/{user}/',
    }

    self.replace_strings_in_files(directory, find_replace_pairs)
    

def replace_strings_in_files(self, directory, find_replace_pairs):
    self.print_method_name()
    """
    Replace strings in files with interruption support, progress tracking and error handling
    """
    try:
        # Count total files for progress tracking
        total_files = sum(1 for _, _, files in os.walk(directory) 
                        for _ in files)
        processed_files = 0

        for root, dirs, files in os.walk(directory):
            if self.stop_processing:
                raise Exception("Operation cancelled by user")

            for file in files:
                if self.stop_processing:
                    raise Exception("Operation cancelled by user")

                processed_files += 1
                file_path = Path(root) / file

                # Update progress
                if hasattr(self, 'progress_bar'):
                    GLib.idle_add(
                        lambda: self.progress_bar.set_fraction(processed_files / total_files)
                    )

                # Skip binary files
                if self.is_binary_file(file_path):
                    #print(f"Skipping binary file: {file_path}")
                    continue

                # Skip files where permission is denied
                if not os.access(file_path, os.R_OK | os.W_OK):
                    #print(f"Skipping file: {file_path} (Permission denied)")
                    continue

                try:
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    modified = False
                    new_content = content

                    # Perform replacements
                    for find_str, replace_str in find_replace_pairs.items():
                        if find_str in new_content:
                            new_content = new_content.replace(find_str, replace_str)
                            modified = True

                    # Write modified content if changes were made
                    if modified:
                        if self.stop_processing:
                            raise Exception("Operation cancelled by user")
                        
                        # Create temporary file
                        temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
                        try:
                            with open(temp_path, 'w', encoding='utf-8') as f:
                                f.write(new_content)
                            # Atomic replace
                            temp_path.replace(file_path)
                            print(f"Replacements applied to file: {file_path}")
                        except Exception as e:
                            if temp_path.exists():
                                temp_path.unlink()
                            raise e

                except (UnicodeDecodeError, FileNotFoundError, PermissionError) as e:
                    #   print(f"Skipping file: {file_path} ({e})")
                    continue

    except Exception as e:
        if "Operation cancelled by user" in str(e):
            print("String replacement operation cancelled")
        raise


def is_binary_file(self, file_path):
    #self.print_method_name()
    """
    Check if a file is binary with interruption support
    """
    try:
        if self.stop_processing:
            raise Exception("Operation cancelled by user")
            
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            if b'\0' in chunk:
                return True
    except Exception as e:
        if "Operation cancelled by user" in str(e):
            raise
        #print(f"Could not check file {file_path} ({e})")
    return False
    
def process_sh_files(self, directory):
    self.print_method_name()
    """
    Process all .sh files and convert them to .charm files.
    Returns a list of created .charm file paths or an empty list if none created.
    """
    sh_files = self.find_sh_files(directory)
    created_charm_files = []  # Track paths of created .charm files
    
    print(f"sh_files = \n {sh_files}")
    
    for sh_file in sh_files:
        variables = self.extract_infofile_path_from_sh(sh_file)
        exe_file = variables.get('EXE_FILE', '')
        progname = variables.get('PROGNAME', '')
        sha256sum = variables.get('CHECKSUM', '')

        print(" = "*20)
        print(f"""
        exe_file = {exe_file}
        progname = {progname}
        sha256sum = {sha256sum}
        """)
        # Regenerate sha256sum if missing
        if exe_file and not sha256sum:
            sha256_hash = hashlib.sha256()
            try:
                with open(exe_file, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                sha256sum = sha256_hash.hexdigest()
                print(f"Warning: sha256sum missing in {exe_file}. Regenerated hash.")
            except FileNotFoundError:
                print(f"Error: {exe_file} not found. Cannot compute sha256sum.")

        info_file_path = variables.get('INFOFILE')
        if info_file_path:
            info_file_path = os.path.join(os.path.dirname(sh_file), info_file_path)
            if os.path.exists(info_file_path):
                try:
                    info_data = self.parse_info_file(info_file_path)
                    runner = info_data.get('Runner', '')
                    
                    # Set runner to empty string if it's '/app/bin/wine' or system wine from
                    if runner == '/app/bin/wine' or runner == '/usr/bin/wine' or runner == '/usr/sbin/wine' or runner == '/usr/local/bin/wine':
                        runner = ''
                        
                    # Locate environment-variable.yml and cmdline.yml
                    env_var_file_path = os.path.join(os.path.dirname(sh_file), "environment-variable.yml")
                    cmdline_file_path = os.path.join(os.path.dirname(sh_file), "cmdline.yml")

                    # Load environment variables and command-line arguments
                    env_vars = self.load_and_fix_yaml(env_var_file_path, "environment-variable.yml")
                    args = self.load_and_fix_yaml(cmdline_file_path, "cmdline.yml")

                    # Check if directory contains "winezgui/WineZGUI" (case-insensitive)
                    if 'winezgui'.lower() in str(directory).lower():
                        progname = f"{progname} (WineZGUI)"

                    yml_path = sh_file.replace('.sh', '.charm')
                    self.create_charm_file({
                        'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
                        'script_path': self.replace_home_with_tilde_in_path(str(yml_path)),
                        'wineprefix': self.replace_home_with_tilde_in_path(str(directory)),
                        'progname': progname,  # Use modified progname
                        'sha256sum': sha256sum,
                        'runner': runner,
                        'args': args,  # Include command-line arguments
                        'env_vars': env_vars  # Include environment variables
                    }, yml_path)

                    ## Add the new script data directly to the script list
                    self.new_scripts.add(Path(yml_path).stem)
                    print(f"Created {yml_path}")
                    created_charm_files.append(yml_path)  # Add to list of created files

                except Exception as e:
                    print(f"Error parsing INFOFILE {info_file_path}: {e}")
            else:
                print(f"INFOFILE {info_file_path} not found")
        else:
            print(f"No INFOFILE found in {sh_file}")

    # If no .charm files were created, create scripts for .lnk and .exe files
    if not created_charm_files:
        print(f"No .charm files created. Proceeding to create scripts for .lnk and .exe files in {directory}")
        self.create_scripts_for_lnk_files(directory)
        print(f"Scripts created for .lnk files in {directory}")

        if self.lnk_processed_success_status:
            print("Skipping create_scripts_for_exe_files creation: .lnk files processed successfully.")
        else:
            self.create_scripts_for_exe_files(directory)
            print(f"Scripts created for .exe files in {directory}")
    else:
        self.track_all_lnk_files(directory)

    return created_charm_files  # Return list of created .charm file paths


def load_and_fix_yaml(self, yaml_file_path, filename):
    self.print_method_name()
    """
    Load data from the specified YAML file, fixing missing spaces around colons.
    """
    if not os.path.exists(yaml_file_path):
        print(f"{filename} not found at {yaml_file_path}")
        return ""

    try:
        with open(yaml_file_path, 'r') as f:
            content = f.read()

        # Fix any missing spaces around colons using regex
        fixed_content = re.sub(r'(\S):(\S)', r'\1: \2', content)

        # Load the fixed YAML content
        yaml_data = yaml.safe_load(fixed_content)

        # Log what we found to debug the issue
        print(f"Loaded data from {filename}: {yaml_data}")

        # Handle different formats gracefully
        if isinstance(yaml_data, dict):
            return yaml_data.get('args', '')  # Return the 'args' value
        else:
            print(f"Unexpected data format in {filename}: {yaml_data}")
            return ""

    except Exception as e:
        print(f"Error reading or parsing {filename} at {yaml_file_path}: {e}")
        return ""

def create_charm_file(self, info_data, yml_path):
    self.print_method_name()
    """
    Create a .charm file with the provided information.
    """
    # Print to confirm the function is being executed
    print(f"Creating .charm file at path: {yml_path}")

    # Extract data with default empty values to prevent KeyErrors
    exe_file = info_data.get('exe_file', '')
    progname = info_data.get('progname', '')
    args = info_data.get('args', '')
    sha256sum = info_data.get('sha256sum', '')
    runner = info_data.get('runner', '')
    env_vars = info_data.get('env_vars', '')  # Now treating env_vars as a string
    script_path = info_data.get('script_path', '')
    wineprefix = info_data.get('wineprefix', '')

    # Debugging: Print all values before writing
    print(f"exe_file: {exe_file}")
    print(f"progname: {progname}")
    print(f"args: {args}")
    print(f"sha256sum: {sha256sum}")
    print(f"runner: {runner}")
    print(f"env_vars: {env_vars}")
    print(f"script_path: {script_path}")
    print(f"wineprefix: {wineprefix}")

    try:
        # Open the file and write all key-value pairs in YAML format
        with open(yml_path, 'w') as yml_file:
            yml_file.write(f"exe_file: '{exe_file}'\n")
            yml_file.write(f"progname: '{progname}'\n")
            yml_file.write(f"args: '{args}'\n")
            yml_file.write(f"sha256sum: '{sha256sum}'\n")
            yml_file.write(f"runner: '{runner}'\n")
            yml_file.write(f"script_path: '{script_path}'\n")
            yml_file.write(f"wineprefix: '{wineprefix}'\n")
            yml_file.write(f"env_vars: '{env_vars}'\n")

        print(f"Actual content successfully written to {yml_path}")

    except Exception as e:
        print(f"Error writing to file: {e}")


def extract_infofile_path_from_sh(self, file_path):
    self.print_method_name()
    variables = {}
    with open(file_path, 'r') as file:
        for line in file:
            if line.startswith('export '):
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key = parts[0].replace('export ', '').strip()
                    value = parts[1].strip().strip('"')
                    variables[key] = value
    #print(f"Variables: {variables}")
    return variables
            
def find_sh_files(self, directory):
    self.print_method_name()
    sh_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".sh"):
                sh_files.append(os.path.join(root, file))
    return sh_files

def find_and_save_lnk_files(self, wineprefix):
    self.print_method_name()
    drive_c = wineprefix / "drive_c" / "ProgramData"
    found_lnk_files_path = wineprefix / "found_lnk_files.yaml"
    lnk_files = []

    for root, dirs, files in os.walk(drive_c):
        for file in files:
            file_path = Path(root) / file

            if file_path.suffix.lower() == ".lnk" and file_path.is_file():
                print(f"Found .lnk file: {file_path}")
                lnk_files.append(file_path.name)

    # Read existing found_lnk_files if the file exists
    if found_lnk_files_path.exists():
        with open(found_lnk_files_path, 'r') as file:
            existing_lnk_files = yaml.safe_load(file) or []
    else:
        existing_lnk_files = []

    # Merge found lnk files with existing ones, avoiding duplicates
    updated_lnk_files = list(set(existing_lnk_files + lnk_files))

    # Save the updated list back to found_lnk_files.yaml
    with open(found_lnk_files_path, 'w') as file:
        yaml.dump(updated_lnk_files, file, default_style="'", default_flow_style=False, width=10000)

    print(f"Saved {len(lnk_files)} .lnk files to {found_lnk_files_path}")
    self.load_script_list(wineprefix)

def parse_info_file(self, file_path):
    self.print_method_name()
    info_data = {}
    with open(file_path, 'r') as file:
        for line in file:
            if ':' in line:
                key, value = line.split(':', 1)
                info_data[key.strip()] = value.strip()
    return info_data



def add_charm_files_to_script_list(self, extracted_prefix_dir):
    self.print_method_name()
    """
    Find all .charm files in the extracted prefix directory and add them to self.script_list.
    
    Args:
        extracted_prefix_dir: The directory where the Wine prefix has been extracted.
    """
    # Look for all .charm files in the extracted directory
    charm_files = list(Path(extracted_prefix_dir).rglob("*.charm"))  # Recursively find all .charm files
    
    if not charm_files:
        print(f"No .charm files found in {extracted_prefix_dir}")
        #GLib.idle_add(self.show_initializing_step, "Checking Available Disk Space")
        return

    print(f"Found {len(charm_files)} .charm files in {extracted_prefix_dir}")

    for charm_file in charm_files:
        try:
            with open(charm_file, 'r') as file:
                script_data = yaml.safe_load(file)  # Load the YAML content from the .charm file
                
                if not isinstance(script_data, dict):
                    print(f"Invalid format in {charm_file}")
                    continue

                # Extract the script key (e.g., sha256sum) from the loaded data
                script_key = script_data.get('sha256sum')
                if not script_key:
                    print(f"Missing 'sha256sum' in {charm_file}, skipping...")
                    continue

                # Add the new script data directly to self.script_list
                self.new_scripts.add(charm_file.stem)
                # Set 'script_path' to the charm file itself if not already set
                script_data['script_path'] = str(charm_file.expanduser().resolve())
                self.script_list = {script_key: script_data, **self.script_list}
                # Add to self.script_list using the script_key
                self.script_list[script_key] = script_data
                print(f"Added {charm_file} to script_list with key {script_key}")

                # Update the timestamp of the .charm file
                charm_file.touch()
                print(f"Updated timestamp for {charm_file}")
                
        except Exception as e:
            print(f"Error loading .charm file {charm_file}: {e}")
    
    # Once done, update the UI
   # GLib.idle_add(self.create_script_list)

    
def on_restore_completed(self):
    self.print_method_name()
    """
    Called when the restore process is complete. Updates UI, restores scripts, and resets the open button.
    """
    # Reconnect open button and reset its label
    
    #if self.open_button_handler_id is not None:
     #   self.open_button.disconnect(self.open_button_handler_id)
    #self.disconnect_open_button()
    #self.set_open_button_label("Open")
    #self.set_open_button_icon_visible(True)
    self.hide_processing_spinner()
    self.reconnect_open_button()


    # Restore the script list in the flowbox
    GLib.timeout_add_seconds(0.5, self.load_script_list)
    #GLib.idle_add(self.create_script_list)

    print("Restore process completed and script list restored.")

def extract_backup(self, file_path):
    self.print_method_name()
    """
    Extract the .tar.zst backup to the Wine prefixes directory with proper process management.
    """
    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        raise Exception("Unable to determine the current username from the environment.")

    try:
        # Get the prefix directory using the dedicated method
        extracted_prefix_dir = self.extract_prefix_dir(file_path)
        if not extracted_prefix_dir:
            raise Exception("Failed to determine the prefix directory from the backup.")

        print(f"Extracted prefix directory: {extracted_prefix_dir}")

        # Create a new process group
        def preexec_function():
            os.setpgrp()

        # Extract the archive with process tracking
        extract_process = subprocess.Popen(
            ['tar', '-I', 'zstd -T0', '-xf', file_path, '-C', self.prefixes_dir,
             "--transform", rf"s|XOUSERXO|{current_username}|g", 
             "--transform", rf"s|%USERNAME%|{current_username}|g"],
            preexec_fn=preexec_function
        )
        
        with self.process_lock:
            self.current_process = extract_process

        while extract_process.poll() is None:
            if self.stop_processing:
                print("Cancellation requested, terminating tar process...")
                self._kill_current_process()
                
                # Clean up partially extracted files
                if extracted_prefix_dir.exists():
                    print(f"Cleaning up partially extracted files at {extracted_prefix_dir}")
                    shutil.rmtree(extracted_prefix_dir, ignore_errors=True)
                
                raise Exception("Operation cancelled by user")
            time.sleep(0.1)

        if extract_process.returncode != 0:
            raise Exception(f"Tar extraction failed with return code {extract_process.returncode}")

        return extracted_prefix_dir

    except Exception as e:
        print(f"Error during extraction: {e}")
        if "Operation cancelled by user" not in str(e):
            raise
        return None
    finally:
        with self.process_lock:
            self.current_process = None

def _kill_current_process(self):
    self.print_method_name()
    """
    Helper method to kill the current process and its process group.
    """
    with self.process_lock:
        if self.current_process:
            try:
                # Kill the entire process group
                pgid = os.getpgid(self.current_process.pid)
                os.killpg(pgid, signal.SIGTERM)
                
                # Give it a moment to terminate gracefully
                try:
                    self.current_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # If it doesn't terminate gracefully, force kill
                    os.killpg(pgid, signal.SIGKILL)
                
                return True
            except ProcessLookupError:
                # Process already terminated
                return True
            except Exception as e:
                print(f"Error killing process: {e}")
                return False
    return False


def extract_prefix_dir(self, file_path):
    self.print_method_name()
    """
    Return the extracted prefix directory for the backup file.
    This method ensures that only the first directory is returned, not individual files.
    """
    try:
        # Extract only directories by filtering those that end with '/'
        extracted_prefix_name = subprocess.check_output(
            ["bash", "-c", f"tar -tf '{file_path}' | head -n2 | grep '/$' |head -n1 | cut -f1 -d '/'"]
        ).decode('utf-8').strip()
        print(f"extracted_prefix_name={extracted_prefix_name}")

        # Handle .tar.zst or .wzt with ./ or ../ in the directory name
        if extracted_prefix_name == '.' or extracted_prefix_name == '..':
            extracted_prefix_name = subprocess.check_output(
            ["bash", "-c", f"tar -tf '{file_path}' | head -n2 | grep '/$' |head -n1 | cut -f2 -d '/'"]
        ).decode('utf-8').strip()
            print(f"extracted_prefix_name={extracted_prefix_name}")

        if not extracted_prefix_name:
            raise Exception("No directory found in the tar archive.")
        

        # Print the correct path for debugging
        extracted_prefix_path = Path(self.prefixes_dir) / extracted_prefix_name
        print("_" * 100)
        print(extracted_prefix_name)
        print(extracted_prefix_path)
        
        return extracted_prefix_path
    except subprocess.CalledProcessError as e:
        print(f"Error extracting prefix directory: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def check_disk_space_and_show_step(self, file_path):
    self.print_method_name()
    """
    Check available disk space and the uncompressed size of the backup file, showing this as a step.
    First checks if compressed file size is < 1/4 of available space for quick approval.
    """
    # Update the UI to indicate that disk space is being checked
    #GLib.idle_add(self.show_initializing_step, "Checking Available Disk Space")

    # Perform the quick disk space check first
    enough_space, available_space, size_to_check = self.check_disk_space_quick(self.prefixes_dir, file_path)

    if not enough_space:
        # Show warning about disk space
        GLib.idle_add(self.show_info_dialog, "Insufficient Disk Space",
                    f"The estimated required space is {size_to_check / (1024 * 1024):.2f} MB, "
                    f"but only {available_space / (1024 * 1024):.2f} MB is available. Please free up space.")
        return False

    # If enough space, update the UI and log the success
    message = f"Disk space check passed: {size_to_check / (1024 * 1024):.2f} MB required"
    GLib.idle_add(self.show_initializing_step, message)
    print(message)
    GLib.idle_add(self.mark_step_as_done, message)
    return True

def check_disk_space_quick(self, prefixes_dir, file_path):
    self.print_method_name()
    """
    Quick check of disk space by comparing compressed file size with available space.
    Only if compressed size is > 10x of available space, we need the full uncompressed check.
    
    Args:
        prefixes_dir (Path): The directory where the wine prefixes are stored.
        file_path (str): Path to the backup .tar.zst file.

    Returns:
        (bool, int, int): Tuple containing:
            - True if there's enough space, False otherwise
            - Available disk space in bytes
            - Size checked (either compressed or uncompressed) in bytes
    """
    try:
        # Get available disk space
        df_output = subprocess.check_output(['df', '--output=avail', str(prefixes_dir)]).decode().splitlines()[1]
        available_space = int(df_output.strip()) * 1024  # Convert KB to bytes

        # Get compressed file size
        compressed_size = Path(file_path).stat().st_size

        # If compressed file is less than 10x of available space, we're safe to proceed
        if compressed_size * 10 <= available_space:
            print(f"Quick check passed - Compressed size: {compressed_size / (1024 * 1024):.2f} MB")
            return True, available_space, compressed_size

        # Otherwise, check the actual uncompressed size
        uncompressed_size = self.get_total_uncompressed_size(file_path)
        return available_space >= uncompressed_size, available_space, uncompressed_size

    except (subprocess.CalledProcessError, OSError) as e:
        print(f"Error checking disk space: {e}")
        return False, 0, 0

def connect_open_button_with_restore_backup_cancel(self):
    self.print_method_name()
    """
    Connect cancel handler to the open button
    """
    if self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_restore_backup_clicked)
    
    self.set_open_button_icon_visible(False)

def on_cancel_restore_backup_clicked(self, button):
    self.print_method_name()
    """
    Handle cancel button click with immediate process termination
    """
    dialog = Adw.AlertDialog(
        title="Cancel Restoring Backup?",
        body="This will immediately stop the extraction process. Any partially extracted files will be cleaned up."
    )
    dialog.add_response("continue", "Continue")
    dialog.add_response("cancel", "Cancel Restore")
    dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.connect("response", self.on_cancel_restore_backup_dialog_response)
    dialog.present(self.window,)

def on_cancel_restore_backup_dialog_response(self, dialog, response):
    self.print_method_name()
    """
    Handle cancel dialog response with cleanup
    """
    if response == "cancel":
        self.stop_processing = True
        dialog.close()
        
        def cleanup():
            try:
                self._kill_current_process()
                GLib.idle_add(self.on_restore_completed)
                GLib.idle_add(self.show_info_dialog, "Cancelled", 
                            "Restore process was cancelled and cleaned up successfully")
                GLib.idle_add(self.create_script_list)
            except Exception as e:
                print(f"Error during cleanup: {e}")
                GLib.idle_add(self.show_info_dialog, "Error", 
                            f"Error during cleanup: {str(e)}")
        
        # Run cleanup in a separate thread to avoid blocking the UI
        threading.Thread(target=cleanup).start()
    else:
        self.stop_processing = False
        dialog.close()


