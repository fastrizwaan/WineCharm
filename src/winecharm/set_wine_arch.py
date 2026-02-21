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

def set_wine_arch(self):
    self.print_method_name()
    """
    Allow the user to set the Wine architecture using Adw.AlertDialog.
    """
    # Create AlertDialog
    dialog = Adw.AlertDialog(
        heading=_("Set Wine Architecture"),
        body=_("Select the default architecture for new prefixes:")
    )

    # Create radio buttons for architecture selection
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    win32_radio = Gtk.CheckButton(label=_("32-bit (win32)"))
    win64_radio = Gtk.CheckButton(label=_("64-bit (win64)"))
    win64_radio.set_group(win32_radio)

    # Set current selection
    current_arch = self.arch
    win32_radio.set_active(current_arch == 'win32')
    win64_radio.set_active(current_arch == 'win64')

    # Add radio buttons to dialog
    vbox.append(win32_radio)
    vbox.append(win64_radio)
    dialog.set_extra_child(vbox)

    # Configure dialog buttons
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("ok", _("OK"))
    dialog.set_default_response("ok")
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

    # Response handler
    def on_response(dialog, response):
        self.print_method_name()
        if response == "ok":
            new_arch = 'win32' if win32_radio.get_active() else 'win64'
            if new_arch != current_arch:
                self.main_frame.set_child(None)
                handle_architecture_change(new_arch)
        dialog.close()

    # Architecture change handler
    def handle_architecture_change(new_arch):
        self.print_method_name()
        # Determine paths based on selected architecture
        new_template = self.default_template_win32 if new_arch == 'win32' else self.default_template_win64
        single_prefix_dir = self.single_prefix_dir_win32 if new_arch == 'win32' else self.single_prefix_dir_win64

        # Update settings
        self.arch = new_arch
        self.template = new_template

        self.settings['template'] = self.replace_home_with_tilde_in_path(str(new_template))
        self.settings['arch'] = self.replace_home_with_tilde_in_path(str(new_arch))
        self.save_settings()
        
        # Resolve template path
        new_template = Path(new_template).expanduser().resolve()
        
        # Initialize new template if needed
        if not new_template.exists():
            print(f"Initializing new {new_arch} template...")
            self.on_back_button_clicked(None)
            self.called_from_settings = True
            self.initialize_template(new_template, 
                                lambda: finalize_arch_change(single_prefix_dir),
                                arch=new_arch)
        else:
            print(f"Using existing {new_arch} template")
            self.show_options_for_settings()
            finalize_arch_change(single_prefix_dir)

    # Finalization handler
    def finalize_arch_change(single_prefix_dir):
        self.print_method_name()
        if self.single_prefix and not single_prefix_dir.exists():
            print(f"Copying to {single_prefix_dir.name}...")
            self.copy_template(single_prefix_dir)
        self.set_dynamic_variables()
        self.show_options_for_settings()

    self.show_options_for_settings()
    # Connect response signal and present dialog
    dialog.connect("response", on_response)
    dialog.present(self.window)
    
