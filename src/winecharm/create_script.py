#!/usr/bin/env python3

import gi
import threading
import subprocess
import shutil
import re
import os
import hashlib
import shlex
import yaml
from pathlib import Path

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')


from gi.repository import GLib, Gio, Gtk, Adw

def determine_progname(self, productname, exe_no_space, exe_name):
    self.print_method_name()
    """
    Determine the program name based on the product name extracted by exiftool, or fallback to executable name.
    Args:
        productname (str): The product name extracted from the executable.
        exe_no_space (str): The executable name without spaces.
        exe_name (str): The original executable name.
    Returns:
        str: The determined program name.
    """
    # Logic to determine the program name based on exe name and product name
    if "setup" in exe_name.lower() or "install" in exe_name.lower():
        return productname + '*'
    elif "setup" in productname.lower() or "install" in productname.lower():
        return productname
    else:
        # Fallback to product name or executable name without spaces if productname contains numbers or is non-ascii
        return productname if productname and not any(char.isdigit() for char in productname) and productname.isascii() else exe_no_space


def create_yaml_file(self, exe_path, prefix_dir=None, use_exe_name=False, runner_override=None):
    self.print_method_name()
    # Determine runner_to_use
    if runner_override is not None:
        runner_to_use = runner_override
    else:
        if self.runner_to_use:
            runner_to_use = self.replace_home_with_tilde_in_path(str(self.runner_to_use))
        else:
            runner_to_use = ""

    self.create_required_directories()
    exe_file = Path(exe_path).resolve()
    exe_name = exe_file.stem
    exe_no_space = exe_name.replace(" ", "_")

    # Calculate SHA256 hash
    sha256_hash = hashlib.sha256()
    with open(exe_file, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    sha256sum = sha256_hash.hexdigest()[:10]
    script_key = sha256_hash.hexdigest()
    # string to path
    self.template = Path(self.template).expanduser().resolve()
    print(f"         => create_yaml_file -> self.template = {self.template}")
    # Determine prefix directory
    if prefix_dir is None:
        if self.single_prefix:
            # Use architecture-specific single prefix directory
            if self.arch == 'win32':
                prefix_dir = self.single_prefix_dir_win32
                template_to_use = self.default_template_win32
            else:
                prefix_dir = self.single_prefix_dir_win64
                template_to_use = self.default_template_win64
            

            # Create prefix from template if needed
            if not prefix_dir.exists():
                #self.copy_template(prefix_dir, template_to_use)
                print("--->if not prefix_dir.exists():")
                self.custom_copytree(self.template, prefix_dir)
        else:
            # if the user has deleted the current in use runner and open an exe, it should use the default arch based runner.
            if not self.template.exists():
                # Use architecture-specific single prefix directory
                if self.arch == 'win32':
                    template_to_use = self.default_template_win32
                else:
                    template_to_use = self.default_template_win64
                print(f"Error: {self.template} has been deleted, using {template_to_use}")
                GLib.idle_add(
                    self.show_info_dialog,
                    _("Template Deleted"),
                    _("Template '%(old)s' has been deleted, using '%(new)s'.") % {
                        "old": self.template.name,
                        "new": template_to_use.name,
                        }
                )
                self.template = template_to_use

            # Create new unique prefix per executable
            prefix_dir = self.prefixes_dir / f"{exe_no_space}-{sha256sum[:10]}"
            if not prefix_dir.exists():
                if self.template.exists():
                    print("===>if self.template.exists():")
                    print(f"->>>{self.template} is being copied")
                    self.custom_copytree(self.template, prefix_dir)
                else:
                    self.ensure_directory_exists(prefix_dir)
        # Resolve the generated or selected prefix directory
        prefix_dir = Path(prefix_dir).resolve()
    else:
        # Resolve the user-provided prefix directory
        prefix_dir = Path(prefix_dir).expanduser().resolve()

    # Check if a script with the same sha256sum and wineprefix already exists
    if script_key in self.script_list:
        existing_script_data = self.script_list[script_key]
        existing_script_path = Path(existing_script_data['script_path']).expanduser().resolve()
        existing_wineprefix = existing_script_path.parent

        current_wineprefix = prefix_dir

        # Compare resolved paths to ensure accuracy
        if existing_wineprefix == current_wineprefix:
            # Remove existing .charm file and its entry
            if existing_script_path.exists():
                existing_script_path.unlink()
                print(f"Removed existing charm file: {existing_script_path}")
            del self.script_list[script_key]
            print(f"Removed old script_key {script_key} from script_list")
        else:
            print(f"Existing charm file in different prefix '{existing_wineprefix}' left intact.")

    # Proceed to create the YAML configuration and charm file
    wineprefix_name = prefix_dir.name

    # Extract product name using exiftool
    product_cmd = ['exiftool', shlex.quote(str(exe_file))]
    product_output = self.run_command(" ".join(product_cmd))
    if product_output is None:
        productname = exe_no_space
    else:
        productname_match = re.search(r'Product Name\s+:\s+(.+)', product_output)
        productname = productname_match.group(1).strip() if productname_match else exe_no_space

    # Determine program name based on use_exe_name flag
    if use_exe_name:
        progname = exe_name  # Use exe_name if flag is set
    else:
        progname = self.determine_progname(productname, exe_no_space, exe_name)
        
    # Create YAML file with proper naming
    yaml_file_path = prefix_dir / f"{exe_no_space if use_exe_name else progname.replace(' ', '_')}.charm"

    # Prepare YAML data with runner_to_use
    yaml_data = {
        'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
        'script_path': self.replace_home_with_tilde_in_path(str(yaml_file_path)),
        'wineprefix': self.replace_home_with_tilde_in_path(str(prefix_dir)),
        'progname': progname,
        'args': "",
        'sha256sum': sha256_hash.hexdigest(),
        'runner': runner_to_use,  # Use the determined runner
        'wine_debug': "WINEDEBUG=-fixme-all DXVK_LOG_LEVEL=none",
        'env_vars': ""
    }

    # Write the new YAML file
    with open(yaml_file_path, 'w') as yaml_file:
        yaml.dump(yaml_data, open(yaml_file_path, 'w'), default_style="'", default_flow_style=False, width=10000)

    # Update yaml_data with resolved paths
    yaml_data['exe_file'] = str(exe_file.expanduser().resolve())
    yaml_data['script_path'] = str(yaml_file_path.expanduser().resolve())
    yaml_data['wineprefix'] = str(prefix_dir.expanduser().resolve())
    # Extract icon and create desktop entry
    icon_path = self.extract_icon(exe_file, prefix_dir, exe_no_space, progname)
    #self.create_desktop_entry(progname, yaml_file_path, icon_path, prefix_dir)

    # Add the new script data directly to self.script_list
    self.new_scripts.add(yaml_file_path.stem)

    # Add or update script row in UI
    self.script_list[script_key] = yaml_data
    # Update the UI row for the renamed script
    row = self.create_script_row(script_key, yaml_data)
    if row:
        self.flowbox.prepend(row)
    # 
    self.script_list = {script_key: yaml_data, **self.script_list}
    self.script_ui_data[script_key]['script_path'] = yaml_data['script_path']
    #script_data['script_path'] = yaml_data['script_path']
    
    print(f"Created new charm file: {yaml_file_path} with script_key {script_key}")
    
    GLib.idle_add(self.create_script_list)



def extract_icon(self, exe_file, wineprefix, exe_no_space, progname):
    self.print_method_name()
    self.create_required_directories()
    icon_path = wineprefix / f"{progname.replace(' ', '_')}.png"
    #print(f"------ {wineprefix}")
    ico_path = self.tempdir / f"{exe_no_space}.ico"
   # print(f"-----{ico_path}")
    try:
        bash_cmd = f"""
        wrestool -x -t 14 {shlex.quote(str(exe_file))} > {shlex.quote(str(ico_path))} 2>/dev/null
        icotool -x {shlex.quote(str(ico_path))} -o {shlex.quote(str(self.tempdir))} 2>/dev/null
        """
        try:
            subprocess.run(bash_cmd, shell=True, executable='/bin/bash', check=True)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Command failed with error {e.returncode}, but continuing.")

        png_files = sorted(self.tempdir.glob(f"{exe_no_space}*.png"), key=lambda x: x.stat().st_size, reverse=True)
        if png_files:
            best_png = png_files[0]
            shutil.move(best_png, icon_path)

    finally:
        # Clean up only the temporary files created, not the directory itself
        for file in self.tempdir.glob(f"{exe_no_space}*"):
            try:
                file.unlink()
            except FileNotFoundError:
                print(f"File {file} not found for removal.")
        # Optionally remove the directory only if needed
        # self.tempdir.rmdir()

    return icon_path if icon_path.exists() else None


def track_all_lnk_files(self, wineprefix):
    self.print_method_name()
    lnk_files = self.find_lnk_files(wineprefix)
    
    for lnk_file in lnk_files:
        # Skip if already processed
        if self.is_lnk_file_processed(wineprefix, lnk_file):
            continue  
        # Add the .lnk file to the processed list
        self.add_lnk_file_to_processed(wineprefix, lnk_file)

def find_lnk_files(self, wineprefix):
    self.print_method_name()
    drive_c = wineprefix / "drive_c" 
    lnk_files = []

    for root, dirs, files in os.walk(drive_c):
        current_path = Path(root)

        # Exclude any directory that includes 'Recent' in its path
        if "Recent" in current_path.parts:
            continue  # Skip processing .lnk files in 'Recent' directory

        for file in files:
            file_path = current_path / file

            if file_path.suffix.lower() == ".lnk" and file_path.is_file():
                lnk_files.append(file_path)

    return lnk_files


def add_lnk_file_to_processed(self, wineprefix, lnk_file):
    self.print_method_name()
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
        yaml.dump(found_lnk_files, file, default_style="'", default_flow_style=False, width=10000)

def is_lnk_file_processed(self, wineprefix, lnk_file):
    self.print_method_name()
    found_lnk_files_path = wineprefix / "found_lnk_files.yaml"
    if found_lnk_files_path.exists():
        with open(found_lnk_files_path, 'r') as file:
            found_lnk_files = yaml.safe_load(file) or []
            return lnk_file.name in found_lnk_files
    return False

def create_scripts_for_lnk_files(self, wineprefix, parent_runner=None):
    self.print_method_name()
    self.lnk_processed_success_status = False
    lnk_files = self.find_lnk_files(wineprefix)
    exe_files = self.extract_exe_files_from_lnk(lnk_files, wineprefix)
    product_name_map = {}

    for exe_file in exe_files:
        exe_name = exe_file.stem
        product_name = self.get_product_name(exe_file) or exe_name
        product_name_map.setdefault(product_name, []).append(exe_file)

    for product_name, exe_files in product_name_map.items():
        if len(exe_files) > 1:
            for exe_file in exe_files:
                self.create_yaml_file(exe_file, wineprefix, use_exe_name=True, runner_override=parent_runner)
        else:
            self.create_yaml_file(exe_files[0], wineprefix, use_exe_name=False, runner_override=parent_runner)

    self.find_and_remove_wine_created_shortcuts()
     
def extract_exe_files_from_lnk(self, lnk_files, wineprefix):
    self.print_method_name()
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
            
            # Skip if the target DOS name is not an .exe file
            if target_dos_name and not target_dos_name.lower().endswith('.exe'):
                print(f"Skipping non-exe target: {target_dos_name}")
                continue
                
            if target_dos_name:
                exe_name = target_dos_name.strip()
                exe_path = self.find_exe_path(wineprefix, exe_name)
                if exe_path and "unins" not in exe_path.stem.lower():
                    exe_files.append(exe_path)
                    self.add_lnk_file_to_processed(wineprefix, lnk_file)  # Track the .lnk file, not the .exe file
    return exe_files

