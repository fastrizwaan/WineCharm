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

def initialize_template(self, template_dir, callback, arch='win64', new=False):
    """
    Modified template initialization with architecture support
    """
    template_dir = Path(template_dir) if not isinstance(template_dir, Path) else template_dir
    
    self.create_required_directories()
    self.initializing_template = True
    self.stop_processing = False
    self.current_arch = arch  # Store current architecture
    
    # Disabled Cancel/Interruption
    ## Disconnect open button handler
    #if self.open_button_handler_id is not None:
    #    self.open_button.disconnect(self.open_button_handler_id)
    #    self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_init_clicked)
    self.disconnect_open_button()
    

    # Architecture-specific steps
    steps = [
        (_("Initializing wineprefix"), 
        f"WINEARCH={arch} WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
        (_("Replace symbolic links with directories"), 
        lambda: self.remove_symlinks_and_create_directories(template_dir)),
        (_("Installing arial font"), 
        f"WINEPREFIX='{template_dir}' winetricks -q arial"),
        # ("Installing tahoma", 
        # f"WINEPREFIX='{template_dir}' winetricks -q tahoma"),
        # ("Installing times", 
        # f"WINEPREFIX='{template_dir}' winetricks -q times"),
        # ("Installing courier", 
        # f"WINEPREFIX='{template_dir}' winetricks -q courier"),
        # ("Installing webdings", 
        # f"WINEPREFIX='{template_dir}' winetricks -q webdings"),
        (_("Installing openal"), 
        f"WINEPREFIX='{template_dir}' winetricks -q openal"),
        #("Installing vkd3d", 
        #f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
        #("Installing dxvk", 
        #f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
    ]
    
    # Set total steps and initialize progress UI
    self.total_steps = len(steps)
    self.show_processing_spinner(f"Initializing {template_dir.name} Template...")

    def initialize():
        for index, (step_text, command) in enumerate(steps, 1):
            if self.stop_processing:
                GLib.idle_add(self.cleanup_cancelled_template_init, template_dir)
                return
                
            GLib.idle_add(self.show_initializing_step, step_text)
            try:
                if callable(command):
                    command()
                else:
                    process = subprocess.Popen(command, shell=True, 
                                            stdout=subprocess.PIPE, 
                                            stderr=subprocess.PIPE)
                    while process.poll() is None:
                        if self.stop_processing:
                            process.terminate()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            GLib.idle_add(self.cleanup_cancelled_template_init, template_dir)
                            return
                        time.sleep(0.1)
                    
                    if process.returncode != 0:
                        raise subprocess.CalledProcessError(process.returncode, command)
                
                GLib.idle_add(self.mark_step_as_done, step_text)
                if hasattr(self, 'progress_bar'):
                    GLib.idle_add(lambda: self.progress_bar.set_fraction(index / self.total_steps))
                
            except subprocess.CalledProcessError as e:
                print(f"Error initializing template: {e}")
                GLib.idle_add(self.cleanup_cancelled_template_init, template_dir)
                return
                
        if not self.stop_processing:
            GLib.idle_add(lambda: self.on_template_initialized(arch, new))
            GLib.idle_add(self.hide_processing_spinner)
            self.disconnect_open_button()
            GLib.idle_add(self.reset_ui_after_template_init)
    threading.Thread(target=initialize).start()

def on_template_initialized(self, arch=None, new=False):
    print(f"Template initialization complete for {arch if arch else 'default'} architecture.")
    self.initializing_template = False
    # Update architecture setting if we were initializing a specific arch
    if arch:
        self.arch = arch
        # Set template path based on architecture
        self.template = self.default_template_win32 if arch == 'win32' \
            else self.default_template_win64
        self.save_settings()
    
    # Ensure the spinner is stopped after initialization
    self.hide_processing_spinner()
    
    # Success case
    self.show_initializing_step("Initialization Complete!")
    self.mark_step_as_done("Initialization Complete!")
    

    
    # Process command-line file if it exists
    if self.command_line_file:
        print("Processing command-line file after template initialization")
        file_extension = Path(self.command_line_file).suffix.lower()
        if file_extension in ['.exe', '.msi']:
            print(f"Processing file: {self.command_line_file} (Valid extension: {file_extension})")
            GLib.idle_add(self.show_processing_spinner, "Processing...")
            self.process_cli_file(self.command_line_file)
        elif file_extension in ['.wzt', '.bottle', '.prefix']:
            print(f"Restoring from backup: {self.command_line_file}")
            self.restore_prefix_bottle_wzt_tar_zst(self.command_line_file)
        else:
            print(f"Invalid file type: {file_extension}. Only .exe or .msi files are allowed.")
            GLib.timeout_add_seconds(0.5, self.show_info_dialog, _("Invalid File Type"), _("Only .exe and .msi files are supported."))
            self.command_line_file = None
            return False

    # If not called from settings, reconnect open button; else, go to settings
    if not self.called_from_settings:
        self.reconnect_open_button()
        # Skip create_script_list here since it's handled above for new=True
        if not new:
            GLib.timeout_add_seconds(0.5, self.create_script_list)
    
    if self.called_from_settings:
        GLib.idle_add(lambda: self.replace_open_button_with_settings())
        self.show_options_for_settings()
    
    self.set_dynamic_variables()
    # Run script processing for first launch if new=True
    if new:
        print("- - - - - - - ")
        print("- - - - - - - ")
        print("First launch: Processing scripts after template initialization.")
        print("- - - - - - - ")
        print("- - - - - - - ")
        self.process_winezgui_sh_files(suppress_no_scripts_dialog=True)
        self.load_script_list()
        self.create_script_list()
            
def copy_template(self, dest_dir, source_template=None):
    self.print_method_name()
    if source_template is None:
        source_template = self.template
    source_template = Path(source_template)
    dest_dir = Path(dest_dir)
    
    if source_template.exists():
        #shutil.copytree(source_template, dest_dir, symlinks=True, dirs_exist_ok=True)
        self.custom_copytree(source_template, dest_dir)
        print(f"Copied template {source_template} to {dest_dir}")
    else:
        print(f"Template {source_template} does not exist. Creating empty prefix.")
        self.ensure_directory_exists(dest_dir)
        
def on_cancel_template_init_clicked(self, button):
    self.print_method_name()
    """
    Handle cancel button click during template initialization
    """
    dialog = Adw.AlertDialog(
        title="Cancel Initialization",
        body=_("Do you want to cancel the template initialization process?")
    )
    dialog.add_response("continue", _("Continue"))
    dialog.add_response("cancel", _("Cancel Initialization"))
    dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.connect("response", self.on_cancel_template_init_dialog_response)
    dialog.present(self.window)

def on_cancel_template_init_dialog_response(self, dialog, response):
    self.print_method_name()
    """
    Handle cancel dialog response for template initialization
    """
    if response == "cancel":
        self.stop_processing = True
    dialog.close()

def cleanup_cancelled_template_init(self, template_dir):
    self.print_method_name()
    """
    Clean up after template initialization is cancelled, create a basic template,
    and update settings.yml
    """
    template_dir = Path(template_dir) if not isinstance(template_dir, Path) else template_dir
    
    try:
        if template_dir.exists():
            shutil.rmtree(template_dir)
            print(f"Removed incomplete template directory: {template_dir}")
        
        # Create the directory
        template_dir.mkdir(parents=True, exist_ok=True)
            
        # Initialize basic wineprefix with minimal setup
        basic_steps = [
            (_("Creating basic wineprefix"), f"WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
            (_("Setting up directories"), lambda: self.remove_symlinks_and_create_directories(template_dir))
        ]
        
        for step_text, command in basic_steps:
            GLib.idle_add(self.show_initializing_step, step_text)
            try:
                if callable(command):
                    command()
                else:
                    subprocess.run(command, shell=True, check=True)
                GLib.idle_add(self.mark_step_as_done, step_text)
            except Exception as e:
                print(f"Error during basic template setup: {e}")
                raise
                
        print("Initialized basic wineprefix")
        
        # Update template in settings
        self.template = template_dir
        self.save_settings()
        print(f"Updated settings with new template path: {template_dir}")
        
    except Exception as e:
        print(f"Error during template cleanup: {e}")
    finally:
        self.initializing_template = False
        self.stop_processing = False
        GLib.idle_add(self.reset_ui_after_template_init)
        self.show_info_dialog(_("Basic Template Created"), 
                    _("A basic template was created and settings were updated. Some features may be limited."))


def reset_ui_after_template_init(self):
    self.print_method_name()
    """
    Reset UI elements after template initialization and show confirmation
    """
    self.set_open_button_label("Open")
    self.set_open_button_icon_visible(True)
    self.hide_processing_spinner()
    
    if self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
        self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
    
    self.flowbox.remove_all()

def get_template_arch(self, template_path):
    self.print_method_name()
    """Extract architecture from template's system.reg file"""
    system_reg = Path(template_path) / "system.reg"
    if not system_reg.exists():
        return "win64"  # Default assumption
    
    try:
        with open(system_reg, "r") as f:
            for line in f:
                if line.startswith("#arch="):
                    return line.strip().split("=")[1].lower()
    except Exception as e:
        print(f"Error reading {system_reg}: {e}")
    
    return "win64"  # Fallback if not found

def set_default_template(self, action=None):
    self.print_method_name()
    """Set default template with architecture auto-detection and update"""
    # Collect templates with architecture info
    templates = []
    for template_dir in self.templates_dir.iterdir():
        if template_dir.is_dir() and (template_dir / "system.reg").exists():
            arch = self.get_template_arch(template_dir)
            display_name = f"{template_dir.name} ({arch.upper()})"
            templates.append((display_name, str(template_dir.resolve()), arch))

    # Add default templates if they exist
    default_templates = [
        (self.default_template_win64, "win64"),
        (self.default_template_win32, "win32")
    ]
    for dt_path, dt_arch in default_templates:
        if dt_path.exists() and not any(str(dt_path) == t[1] for t in templates):
            display_name = f"{dt_path.name} ({dt_arch.upper()})"
            templates.append((display_name, str(dt_path.resolve()), dt_arch))

    if not templates:
        self.show_info_dialog(_("No Templates"), _("No valid templates found."))
        return

    # Create dropdown list
    template_list = Gtk.StringList()
    current_template = self.expand_and_resolve_path(self.settings.get('template', ""))
    current_index = 0
    
    # Sort templates and find current selection
    sorted_templates = sorted(templates, key=lambda x: x[0].lower())
    for i, (display, path, arch) in enumerate(sorted_templates):
        template_list.append(display)
        if Path(path) == current_template:
            current_index = i

    dropdown = Gtk.DropDown(model=template_list, selected=current_index)
    dropdown.set_hexpand(True)

    # Dialog layout
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content.append(Gtk.Label(label="Select template:"))
    content.append(dropdown)

    dialog = Adw.AlertDialog(
        heading=_("Set Default Template"),
        body=_("Template architecture will be set automatically"),
        extra_child=content
    )
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("ok", _("Save"))
    dialog.set_default_response("ok")

    def on_response(dialog, response_id):
        self.print_method_name()
        if response_id == "ok":
            selected_idx = dropdown.get_selected()
            if selected_idx != Gtk.INVALID_LIST_POSITION:
                # Get selected template data
                display_name, template_path, arch = sorted_templates[selected_idx]
                
                # Update settings
                self.settings['template'] = self.replace_home_with_tilde_in_path(template_path)
                self.settings['arch'] = arch
                
                # Update instance variables
                self.template = Path(template_path).resolve()
                self.arch = arch
                
                self.save_settings()
                
                self.show_info_dialog(
                    _("Template Updated"),
                    _("Set default template to:\n%(template)s\nArchitecture: %(arch)s") % {
                        "template": display_name,
                        "arch": arch.upper(),
                    }
                )
    dialog.connect("response", on_response)
    dialog.present(self.window)

############# Delete template
def delete_template(self, action=None):
    self.print_method_name()
    """Delete a template directory with safety checks and settings updates"""
    self.load_settings()  # Ensure fresh settings
    current_arch = self.settings.get('arch', 'win64')
    self.template = self.settings.get('template', self.default_template_win64)
    print("-="*50)
    # Resolve default template paths for current architecture
    default_templates = {
        'win64': self.default_template_win64.expanduser().resolve(),
        'win32': self.default_template_win32.expanduser().resolve()
    }
    current_default = default_templates[current_arch]

    # Collect templates with architecture info
    templates = []
    for template_dir in self.templates_dir.iterdir():
        tpl_path = template_dir.resolve()
        if template_dir.is_dir() and (template_dir / "system.reg").exists():
            arch = self.get_template_arch(template_dir)
            display_name = f"{template_dir.name} ({arch.upper()})"
            is_current_default = (tpl_path == current_default)
            templates.append((display_name, tpl_path, arch, is_current_default))

    if not templates:
        self.show_info_dialog(_("No Templates"), _("No templates found to delete."))
        return

    # Create dialog components
    dialog = Adw.AlertDialog(
        heading=_("Delete Template"),
        body=_("Select a template to permanently delete:")
    )

    # Create dropdown with template names
    model = Gtk.StringList.new([name for name, path, arch, is_default in templates])
    dropdown = Gtk.DropDown(model=model)
    dropdown.set_selected(0)

    # Add to dialog content
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.append(dropdown)
    dialog.set_extra_child(content_box)

    # Configure dialog buttons
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("delete", _("Delete"))
    dialog.set_default_response("delete")

    def on_response(dialog, response_id, dropdown, templates):
        self.print_method_name()
        if response_id == "delete":
            selected_idx = dropdown.get_selected()
            if 0 <= selected_idx < len(templates):
                display_name, template_path, template_arch, is_current_default = templates[selected_idx]
                
                # Immediate prevention checks
                if is_current_default:
                    self.show_info_dialog(
                        _("Protected Template"),
                        _("Cannot delete the active / default %s template!\n"
                        "Switch architectures / template first to delete this template.") % current_arch
                    )
                    return

                # Deletion execution
                def perform_deletion():
                    try:
                        shutil.rmtree(template_path)
                        # Clear settings reference if needed
                        if self.settings.get('template', '') == str(template_path):
                            self.settings['template'] = ''
                            self.save_settings()
                        self.show_info_dialog(_("Deleted"), _("Removed: %s") % display_name)
                    except Exception as e:
                        self.show_info_dialog(_("Error"), _("Deletion failed: %s") % str(e))

                # Additional confirmation for non-default templates
                confirm_dialog = Adw.AlertDialog(
                    heading=_("Confirm Deletion"),
                    body=f"Permanently delete:\n{display_name}?"
                )
                confirm_dialog.add_response("cancel", _("Keep"))
                confirm_dialog.add_response("delete", _("Delete Forever"))
                confirm_dialog.connect("response", 
                    lambda d, r: perform_deletion() if r == "delete" else None
                )
                confirm_dialog.present(self.window)

        dialog.close()

    dialog.connect("response", on_response, dropdown, templates)
    dialog.present(self.window)

################## import template
def import_template(self, action=None, param=None):
    self.print_method_name()
    """Import a Wine directory as a template into the templates directory."""
    file_dialog = Gtk.FileDialog.new()
    file_dialog.set_modal(True)
    file_dialog.select_folder(self.window, None, self.on_import_template_response)

def on_import_template_response(self, dialog, result):
    self.print_method_name()
    try:
        folder = dialog.select_folder_finish(result)
        if folder:
            src = Path(folder.get_path())
            if not (src / "system.reg").exists():
                GLib.idle_add(self.show_info_dialog, _("Invalid Template"), 
                            _("Selected directory is not a valid Wine prefix"))
                return

            template_name = src.name
            dst = self.templates_dir / template_name
            backup_dir = self.templates_dir / f"{template_name}_backup_{int(time.time())}"

            steps = [
                (_("Verifying template"), lambda: self.verify_template_source(src)),
                (_("Backing up existing template"), lambda: self.backup_existing_directory(dst, backup_dir)),
                (_("Copying template files"), lambda: self.custom_copytree(src, dst)),
                (_("Processing registry files"), lambda: self.process_reg_files(dst)),
                (_("Standardizing user directories"), lambda: self.rename_and_merge_user_directories(dst)),
                (_("Cleaning template files"), lambda: self.clean_template_files(dst)),
            ]


            self.show_processing_spinner(_("Importing %s") % template_name)
            self.connect_open_button_with_import_wine_directory_cancel()
            threading.Thread(target=self.process_template_import, args=(steps, dst, backup_dir)).start()

    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"Template import error: {e}")

def process_template_import(self, steps, dst, backup_dir):
    self.print_method_name()
    """Handle template import with error handling and rollback"""
    self.stop_processing = False
    self.total_steps = len(steps)
    
    try:
        for index, (step_text, step_func) in enumerate(steps, 1):
            if self.stop_processing:
                raise Exception("Operation cancelled by user")
                
            GLib.idle_add(self.show_initializing_step, step_text)
            step_func()
            GLib.idle_add(self.mark_step_as_done, step_text)
            GLib.idle_add(lambda: self.progress_bar.set_fraction(index / self.total_steps))

        GLib.idle_add(self.show_info_dialog, _("Success"),
                    _("Template '%s' imported successfully") % dst.name)
        self.cleanup_backup(backup_dir)

    except Exception as e:
        GLib.idle_add(self.handle_template_import_error, dst, backup_dir, str(e))
        
    finally:
        GLib.idle_add(self.on_import_template_directory_completed)

def verify_template_source(self, src):
    self.print_method_name()
    """Validate the source directory contains a valid Wine prefix"""
    required_files = ["system.reg", "userdef.reg", "dosdevices"]
    missing = [f for f in required_files if not (src / f).exists()]
    if missing:
        raise Exception(f"Missing required Wine files: {', '.join(missing)}")

def clean_template_files(self, template_path):
    self.print_method_name()
    """Remove unnecessary files from the template"""
    # Remove any existing charm files
    for charm_file in template_path.glob("*.charm"):
        charm_file.unlink()
    
    # Clean desktop files
    applications_dir = template_path / "drive_c/users" / os.getenv("USER") / "Desktop"
    if applications_dir.exists():
        for desktop_file in applications_dir.glob("*.desktop"):
            desktop_file.unlink()

def handle_template_import_error(self, dst, backup_dir, error_msg):
    self.print_method_name()
    """Handle template import errors and cleanup"""
    try:
        if dst.exists():
            shutil.rmtree(dst)
        if backup_dir.exists():
            backup_dir.rename(dst)
    except Exception as e:
        error_msg += f"\nCleanup error: {str(e)}"
    
    self.show_info_dialog(_("Template Import Failed"), error_msg)

def on_import_template_directory_completed(self):
    self.print_method_name()
    """
    Called when the template import process is complete. Updates UI, restores scripts, and resets the open button.
    """
    # Reconnect open button and reset its label
    self.set_open_button_label("Open")
    self.set_open_button_icon_visible(True)
    
    self.hide_processing_spinner()

    # This will disconnect open_button handler, use this then reconnect the open
    #if self.open_button_handler_id is not None:
    #    self.open_button.disconnect(self.open_button_handler_id)

    self.reconnect_open_button()
    self.show_options_for_settings()
    print("Template directory import completed.")
    
##### Template Backup
def backup_template(self, action=None):
    self.print_method_name()
    """
    Allow the user to backup a template with interruptible process.
    """
    all_templates = [t.name for t in self.templates_dir.iterdir() if t.is_dir()]
    if not all_templates:
        self.show_info_dialog(_("No Templates Available"), _("No templates found to backup."))
        return

    dialog = Adw.AlertDialog(
        heading=_("Backup Template"),
        body=_("Select a template to backup:")
    )
    model = Gtk.StringList.new(all_templates)
    dropdown = Gtk.DropDown(model=model)
    dropdown.set_selected(0)
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.append(dropdown)

    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("ok", _("OK"))
    dialog.set_default_response("ok")
    dialog.set_close_response("cancel")
    dialog.set_extra_child(content_box)

    dialog.connect("response", self.on_backup_template_response, dropdown, all_templates)
    dialog.present(self.window)

def on_backup_template_response(self, dialog, response_id, dropdown, templates):
    self.print_method_name()
    if response_id == "ok":
        selected_index = dropdown.get_selected()
        if 0 <= selected_index < len(templates):
            template_name = templates[selected_index]
            template_path = self.templates_dir / template_name

            file_dialog = Gtk.FileDialog.new()
            file_dialog.set_initial_name(f"{template_name}.template")
            file_filter = Gtk.FileFilter()
            file_filter.set_name("Template Archives")
            file_filter.add_pattern("*.template")
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(file_filter)
            file_dialog.set_filters(filters)

            def on_save_response(dlg, result):
                try:
                    save_file = dlg.save_finish(result)
                    if save_file:
                        dest_path = save_file.get_path()
                        threading.Thread(
                            target=self.create_template_backup,
                            args=(template_path, dest_path)
                        ).start()
                except GLib.Error as e:
                    if e.domain == 'gtk-dialog-error-quark' and e.code == 2:
                        print("Backup Template Cancelled!")
                        return
                    print(f"Backup Template failedfailed: {e}")

            file_dialog.save(self.window, None, on_save_response)
    dialog.close()

def create_template_backup(self, template_path, dest_path):
    self.print_method_name()
    """
    Create compressed template archive using zstd compression with interruptible progress.
    """
    self.stop_processing = False
    self.current_backup_path = dest_path
    usershome = os.path.expanduser('~')
    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        raise Exception("Unable to determine the current username from the environment.")
    find_replace_pairs = {usershome: '~', f'\'{usershome}': '\'~\''}
    find_replace_media_username = {f'/media/{current_username}/': '/media/%USERNAME%/'}
    restore_media_username = {'/media/%USERNAME%/': f'/media/{current_username}/'}

    def perform_backup_steps():
        self.print_method_name()
        try:
            steps = [
                (_("Replace \"%s\" with '~' in files") % usershome, lambda: self.replace_strings_in_files(template_path, find_replace_pairs)),
                (_("Reverting user-specific .reg changes"), lambda: self.reverse_process_reg_files(template_path)),
                (_("Replace \"/media/%s\" with '/media/%%USERNAME%%' in files") % current_username,lambda: self.replace_strings_in_files(template_path, find_replace_media_username)),
                (_("Creating backup archive"), lambda: run_backup()), (_("Re-applying user-specific .reg changes"), lambda: self.process_reg_files(template_path)),
                (_("Revert %%USERNAME%% with \"%s\" in script files") % current_username, lambda: self.replace_strings_in_files(template_path, restore_media_username)),
            ]

            self.total_steps = len(steps)
            
            for step_text, step_func in steps:
                if self.stop_processing:
                    GLib.idle_add(self.cleanup_cancelled_template_backup)
                    return

                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    # Run step and handle output
                    step_func()
                    if self.stop_processing:
                        GLib.idle_add(self.cleanup_cancelled_template_backup)
                        return
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    if not self.stop_processing:
                        GLib.idle_add(
                            self.show_info_dialog,
                            _("Backup Failed"),
                            _("Error during '%(step)s': %(error)s") % {
                                "step": step_text,
                                "error": e,
                            }
                        )

                    GLib.idle_add(self.cleanup_cancelled_template_backup)
                    return

            GLib.idle_add(self.show_info_dialog, _("Backup Complete"),
                        _("Template saved to %s") % dest_path)
        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.revert_open_button)

    def run_backup():
        self.print_method_name()
        if self.stop_processing:
            raise Exception("Operation cancelled by user")

        cmd = [
            'tar',
            '-I', 'zstd -T0',
            '--transform', f"s|{template_path.name}/drive_c/users/{current_username}|{template_path.name}/drive_c/users/%USERNAME%|g",
            '-cvf', dest_path,
            '-C', str(template_path.parent),
            template_path.name
        ]

        # Start process with piped output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        # Start output reader thread
        def read_output():
            self.print_method_name()
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    print(output.strip())

        output_thread = threading.Thread(target=read_output)
        output_thread.start()

        # Monitor process with periodic checks
        while process.poll() is None:
            if self.stop_processing:
                process.terminate()
                try:
                    process.wait(timeout=2)
                    if Path(dest_path).exists():
                        Path(dest_path).unlink()
                except subprocess.TimeoutExpired:
                    process.kill()
                raise Exception("Backup cancelled by user")
            time.sleep(0.1)

        output_thread.join()

        if process.returncode != 0 and not self.stop_processing:
            raise Exception(f"Backup failed with code {process.returncode}")

    self.show_processing_spinner("Exporting...")
    self.connect_cancel_button_for_template_backup()
    threading.Thread(target=perform_backup_steps, daemon=True).start()

def connect_cancel_button_for_template_backup(self):
    self.print_method_name()
    if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
    self.open_button_handler_id = self.open_button.connect("clicked", self.on_cancel_template_backup_clicked)
    self.set_open_button_label("Cancel")
    self.set_open_button_icon_visible(False)

def on_cancel_template_backup_clicked(self, button):
    self.print_method_name()
    dialog = Adw.AlertDialog(
        heading=_("Cancel Backup"),
        body=_("Do you want to cancel the template backup process?")
    )
    dialog.add_response("continue", _("Continue"))
    dialog.add_response("cancel", _("Cancel Backup"))
    dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.connect("response", self.on_cancel_template_backup_dialog_response)
    dialog.present(self.window)

def on_cancel_template_backup_dialog_response(self, dialog, response):
    self.print_method_name()
    if response == "cancel":
        self.stop_processing = True
    dialog.close()

def cleanup_cancelled_template_backup(self):
    self.print_method_name()
    try:
        if hasattr(self, 'current_backup_path') and self.current_backup_path and Path(self.current_backup_path).exists():
            Path(self.current_backup_path).unlink()
    except Exception as e:
        print(f"Error deleting partial backup file: {e}")
    finally:
        self.hide_processing_spinner()
        self.show_info_dialog(_("Cancelled"), _("Template backup was cancelled"))
        self.revert_open_button()

#################### NEW RESTORE template like restore wzt
def restore_template_from_backup(self, action=None, param=None):
    self.print_method_name()
    # Step 1: Create required directories if needed
    self.create_required_directories()

    # Step 2: Create a new Gtk.FileDialog instance
    file_dialog = Gtk.FileDialog.new()

    # Step 3: Create file filter for .wzt files only
    file_filter_wzt = Gtk.FileFilter()
    file_filter_wzt.set_name("WineCharm Template Files (*.template)")
    file_filter_wzt.add_pattern("*.template")

    # Step 4: Set the filter on the dialog
    filter_model = Gio.ListStore.new(Gtk.FileFilter)
    filter_model.append(file_filter_wzt)  # Only WZT files for templates
    file_dialog.set_filters(filter_model)

    # Step 5: Open the dialog and handle the response
    file_dialog.open(self.window, None, self.on_restore_template_file_dialog_response)

def on_restore_template_file_dialog_response(self, dialog, result):
    self.print_method_name()
    try:
        file = dialog.open_finish(result)
        if file:
            file_path = file.get_path()
            print(f"Selected template file: {file_path}")
            self.restore_template_tar_zst(file_path)
    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")

def restore_template_tar_zst(self, file_path):
    self.print_method_name()
    """
    Restore a template from a .wzt backup file to the templates directory.
    """
    self.stop_processing = False
    
    try:
        # Determine extracted template directory
        extracted_template = self.extract_template_dir(file_path)
        if not extracted_template:
            raise Exception("Failed to determine template directory name")
        
        # Handle existing directory
        backup_dir = None
        if extracted_template.exists():
            timestamp = int(time.time())
            backup_dir = extracted_template.parent / f"{extracted_template.name}_backup_{timestamp}"
            shutil.move(str(extracted_template), str(backup_dir))
            print(f"Backed up existing template directory to: {backup_dir}")

        # UI setup
        GLib.idle_add(self.flowbox.remove_all)
        self.show_processing_spinner("Restoring Template")
        self.connect_open_button_with_restore_backup_cancel()

        def restore_process():
            self.print_method_name()
            try:
                # Get WZT restore steps modified for templates
                restore_steps = self.get_template_restore_steps(file_path)

                for step_text, step_func in restore_steps:
                    if self.stop_processing:
                        # Handle cancellation by restoring backup
                        if backup_dir and backup_dir.exists():
                            if extracted_template.exists():
                                shutil.rmtree(extracted_template)
                            shutil.move(str(backup_dir), str(extracted_template))
                            print(f"Restored original template directory from: {backup_dir}")
                        GLib.idle_add(self.on_template_restore_completed)
                        return

                    GLib.idle_add(self.show_initializing_step, step_text)
                    try:
                        step_func()
                        GLib.idle_add(self.mark_step_as_done, step_text)
                    except Exception as e:
                        print(f"Error during step '{step_text}': {e}")
                        # Restore backup on failure
                        if backup_dir and backup_dir.exists():
                            if extracted_template.exists():
                                shutil.rmtree(extracted_template)
                            shutil.move(str(backup_dir), str(extracted_template))
                        GLib.idle_add(
                            self.show_info_dialog,
                            _("Error"),
                            _("Failed during step '%(step)s': %(error)s") % {
                                "step": step_text,
                                "error": e,
                            }
                        )

                        return

                # Cleanup backup after successful restore
                if backup_dir and backup_dir.exists():
                    shutil.rmtree(backup_dir)
                    print(f"Removed backup directory: {backup_dir}")

                GLib.idle_add(self.on_template_restore_completed)

            except Exception as e:
                print(f"Error during template restore: {e}")
                if backup_dir and backup_dir.exists():
                    if extracted_template.exists():
                        shutil.rmtree(extracted_template)
                    shutil.move(str(backup_dir), str(extracted_template))
                GLib.idle_add(self.show_info_dialog, _("Error"), _("Template restore failed: %s") % e)

        # Start restore thread
        threading.Thread(target=restore_process).start()

    except Exception as e:
        print(f"Error initiating template restore: {e}")
        GLib.idle_add(self.show_info_dialog, _("Error"), _("Failed to start template restore: %s") % e)

def extract_template_backup(self, file_path):
    self.print_method_name()
    """
    Extract template backup to templates directory with process management.
    """
    current_username = os.getenv("USER") or os.getenv("USERNAME")
    if not current_username:
        raise Exception("Unable to determine current username")

    try:
        # Create new process group
        def preexec_function():
            os.setpgrp()

        # Get template name from archive
        list_process = subprocess.Popen(
            ['tar', '-tf', file_path],
            stdout=subprocess.PIPE,
            preexec_fn=preexec_function,
            universal_newlines=True
        )
        
        with self.process_lock:
            self.current_process = list_process
        
        if self.stop_processing:
            self._kill_current_process()
            raise Exception("Operation cancelled by user")
            
        output, stderr = list_process.communicate()
        extracted_template_name = output.splitlines()[0].split('/')[0]
        extracted_template_dir = Path(self.templates_dir) / extracted_template_name

        print(f"Extracting template to: {extracted_template_dir}")

        # Extract archive
        extract_process = subprocess.Popen(
            ['tar', '-xf', file_path, '-C', self.templates_dir,
            "--transform", rf"s|XOUSERXO|{current_username}|g", 
            "--transform", rf"s|%USERNAME%|{current_username}|g"],
            preexec_fn=preexec_function
        )
        
        with self.process_lock:
            self.current_process = extract_process

        while extract_process.poll() is None:
            if self.stop_processing:
                print("Cancelling template extraction...")
                self._kill_current_process()
                if extracted_template_dir.exists():
                    shutil.rmtree(extracted_template_dir, ignore_errors=True)
                raise Exception("Operation cancelled by user")
            time.sleep(0.1)

        if extract_process.returncode != 0:
            raise Exception(f"Template extraction failed with code {extract_process.returncode}")

        return extracted_template_dir

    except Exception as e:
        print(f"Template extraction error: {e}")
        if "Operation cancelled by user" not in str(e):
            raise
        return None
    finally:
        with self.process_lock:
            self.current_process = None

def extract_template_dir(self, file_path):
    self.print_method_name()
    """
    Determine template directory name from backup file.
    """
    try:
        extracted_template_name = subprocess.check_output(
            ["bash", "-c", f"tar -tf '{file_path}' | head -n2 | grep '/$' | head -n1 | cut -f1 -d '/'"]
        ).decode('utf-8').strip()

        if not extracted_template_name:
            raise Exception("No directory found in template archive")

        return Path(self.templates_dir) / extracted_template_name
    
    except subprocess.CalledProcessError as e:
        print(f"Error extracting template directory: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_template_restore_steps(self, file_path):
    self.print_method_name()
    """
    Return steps for template restore using WZT format.
    """
    return [
        ("Checking Disk Space", lambda: self.check_template_disk_space(file_path)),
        ("Extracting Template File", lambda: self.extract_template_backup(file_path)),
        ("Processing Configuration Files", lambda: self.perform_replacements(self.extract_template_dir(file_path))),
        ("Updating Shortcut List", lambda: self.find_and_save_lnk_files(self.extract_template_dir(file_path))),
        ("Finalizing Template Structure", lambda: self.remove_symlinks_and_create_directories(self.extract_template_dir(file_path))),
        ("Replace symbolic links with directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
        ("Create Wineboot Required file", lambda: self.create_wineboot_required_file(self.extract_prefix_dir(file_path)))
    ]

def check_template_disk_space(self, file_path):
    self.print_method_name()
    """
    Check disk space in templates directory against backup size.
    """
    try:
        # Get available space in templates directory
        df_output = subprocess.check_output(['df', '--output=avail', str(self.templates_dir)]).decode().splitlines()[1]
        available_space = int(df_output.strip()) * 1024  # Convert KB to bytes

        # Get compressed size
        compressed_size = Path(file_path).stat().st_size

        # Quick check if compressed size is less than 1/4 available space
        if compressed_size * 4 <= available_space:
            print(f"Quick space check passed for template")
            return True

        # Full check with uncompressed size
        uncompressed_size = self.get_total_uncompressed_size(file_path)
        if available_space >= uncompressed_size:
            print(f"Template disk space check passed")
            return True
        
        # Show error if insufficient space
        GLib.idle_add(
            self.show_info_dialog,
            _("Insufficient Space"),
            _("Need %(need).1fMB, only %(avail).1fMB available.") % {
                "need": uncompressed_size / (1024 * 1024),
                "avail": available_space / (1024 * 1024),
            }
        )


        return False

    except subprocess.CalledProcessError as e:
        print(f"Disk check error: {e}")
        return False

def on_template_restore_completed(self):
    self.print_method_name()
    """
    Cleanup after template restore completion.
    """
    self.hide_processing_spinner()
    self.reconnect_open_button()
    self.show_options_for_settings()
    print("Template restore completed successfully")


################ clone template
def clone_template(self, action=None):
    self.print_method_name()
    """
    Allow the user to clone a template with an editable name suggestion.
    """
    all_templates = [t.name for t in self.templates_dir.iterdir() if t.is_dir()]
    if not all_templates:
        self.show_info_dialog(_("No Templates Available"), _("No templates found to clone."))
        return

    dialog = Adw.AlertDialog(
        heading=_("Clone Template"),
        body=_("Select a template to clone and enter a new name:")
    )

    # Template selection dropdown
    model = Gtk.StringList.new(all_templates)
    dropdown = Gtk.DropDown(model=model)
    dropdown.set_selected(0)

    # Editable name entry with placeholder
    entry = Gtk.Entry()
    entry.set_placeholder_text(_("Set Template Clone Name"))
    entry.set_activates_default(True)
    
    # Connect signals
    dropdown.connect("notify::selected", self.on_template_selected_for_clone, entry, all_templates)
    entry.connect("changed", self.on_clone_name_changed, dropdown, all_templates)

    # Container layout
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content_box.append(dropdown)
    content_box.append(entry)

    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("ok", _("OK"))
    dialog.set_default_response("ok")
    dialog.set_close_response("cancel")
    dialog.set_extra_child(content_box)

    dialog.connect("response", self.on_clone_template_response, dropdown, entry, all_templates)
    dialog.present(self.window)

def on_template_selected_for_clone(self, dropdown, _pspec, entry, templates):
    self.print_method_name()
    """Update entry text when template selection changes"""
    selected_index = dropdown.get_selected()
    if 0 <= selected_index < len(templates):
        template_name = templates[selected_index]
        new_name = f"{template_name} (clone)"
        entry.set_text(new_name)
        entry.set_position(len(new_name))  # Move cursor to end

def on_clone_name_changed(self, entry, dropdown, templates):
    self.print_method_name()
    """Real-time validation of clone name"""
    new_name = entry.get_text().strip()
    dest_path = self.templates_dir / new_name
    
    # Clear previous error styling
    entry.remove_css_class("error")
    
    # Validate new name
    if not new_name:
        entry.add_css_class("error")
    elif dest_path.exists():
        entry.add_css_class("error")

def on_clone_template_response(self, dialog, response_id, dropdown, entry, templates):
    self.print_method_name()
    if response_id == "ok":
        selected_index = dropdown.get_selected()
        new_name = entry.get_text().strip()

        if 0 <= selected_index < len(templates):
            source_name = templates[selected_index]
            source_path = self.templates_dir / source_name
            dest_path = self.templates_dir / new_name

            # Final validation
            if not new_name:
                self.show_info_dialog(_("Invalid Name"), _("Please enter a name for the clone."))
                return
            if dest_path.exists():
                self.show_info_dialog(_("Error"), _("A template with this name already exists."))
                return

            # Start cloning process
            self.show_processing_spinner("Cloning template...")
            threading.Thread(
                target=self.perform_template_clone,
                args=(source_path, dest_path),
                daemon=True
            ).start()

    dialog.close()

def perform_template_clone(self, source_path, dest_path):
    self.print_method_name()
    """Perform the actual directory copy with error handling"""
    try:
        self.custom_copytree(source_path, dest_path)
        GLib.idle_add(
            self.show_info_dialog,
            _("Clone Successful"),
            _("Successfully cloned to %s") % dest_path.name
        )
    except Exception as e:
        GLib.idle_add(
            self.show_info_dialog,
            _("Clone Error"),
            _("An error occurred: %s") % str(e)
        )
    finally:
        GLib.idle_add(self.on_template_restore_completed)

########### Create Template
def create_template(self, action=None):
    self.print_method_name()
    dialog = Adw.AlertDialog(
        heading=_("Create Template"),
        body=_("Enter a name and select architecture:")
    )
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    
    entry = Gtk.Entry()
    entry.set_placeholder_text(_("Template Name"))
    content_box.append(entry)
    
    radio_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    win32_radio = Gtk.CheckButton(label="32-bit (win32)")
    win64_radio = Gtk.CheckButton(label="64-bit (win64)")
    win64_radio.set_group(win32_radio)
    win64_radio.set_active(True)
    radio_box.append(win32_radio)
    radio_box.append(win64_radio)
    content_box.append(radio_box)
    
    dialog.set_extra_child(content_box)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("ok", _("OK"))
    dialog.set_default_response("ok")
    
    def on_response(dialog, response):
        self.print_method_name()
        if response == "ok":
            name = entry.get_text().strip()
            if not name:
                self.show_info_dialog(_("Invalid Name"), _("Please enter a valid name."))
            else:
                arch = "win32" if win32_radio.get_active() else "win64"
                prefix_dir = self.templates_dir / name
                self.called_from_settings = True
                self.initialize_template(prefix_dir, callback=None, arch=arch)

        dialog.close()
    
    dialog.connect("response", on_response)
    dialog.present(self.window)


# Needs to think about this: do we need separate template configure option?
def configure_template(self, action=None):
    pass

def revert_open_button(self):
    self.print_method_name()
    """
    Cleanup after template restore completion.
    """
    self.hide_processing_spinner()
    self.reconnect_open_button()
    self.show_options_for_settings()
    print("Template created successfully")



