#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from pathlib import Path

#####################  single prefix mode

def single_prefix_mode(self):
    self.print_method_name()
    dialog = Adw.AlertDialog(
        heading="Single Prefix Mode",
        body="Choose prefix mode for new games:\nSingle prefix saves space but makes it harder to backup individual games."
    )

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    
    # Create radio buttons with fresh state
    single_prefix_radio = Gtk.CheckButton(label="Single Prefix Mode")
    multiple_prefix_radio = Gtk.CheckButton(label="Multiple Prefix Mode")
    multiple_prefix_radio.set_group(single_prefix_radio)
    
    # Always refresh from settings before showing dialog
    self.load_settings()  # Ensure latest values
    current_state = self.single_prefix
    single_prefix_radio.set_active(current_state)
    multiple_prefix_radio.set_active(not current_state)

    vbox.append(single_prefix_radio)
    vbox.append(multiple_prefix_radio)
    dialog.set_extra_child(vbox)

    dialog.add_response("cancel", "Cancel")
    dialog.add_response("apply", "Apply")
    dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("cancel")

    def on_response(dialog, response):
        self.print_method_name()
        if response == "apply":
            new_state = single_prefix_radio.get_active()
            if new_state != current_state:
                self.handle_prefix_mode_change(new_state)
        dialog.close()

    dialog.connect("response", on_response)
    dialog.present(self.window)

def handle_prefix_mode_change(self, new_state):
    self.print_method_name()
    previous_state = self.single_prefix
    self.single_prefix = new_state
    
    try:
        # Determine architecture-specific paths
        template_dir = (self.default_template_win32 if self.arch == 'win32' 
                        else self.default_template_win64)
        single_dir = (self.single_prefix_dir_win32 if self.arch == 'win32'
                    else self.single_prefix_dir_win64)

        # Initialize template if needed
        if not template_dir.exists():
            self.initialize_template(template_dir, 
                                lambda: self.finalize_prefix_mode_change(single_dir),
                                arch=self.arch)
        else:
            self.finalize_prefix_mode_change(single_dir)
            
        self.save_settings()
        print(f"Prefix mode changed to {'Single' if new_state else 'Multiple'}")
        
    except Exception as e:
        print(f"Error changing prefix mode: {e}")
        self.single_prefix = previous_state  # Rollback on error
        self.save_settings()
        self.show_error_dialog("Mode Change Failed", str(e))
    
    finally:
        self.set_dynamic_variables()

def finalize_prefix_mode_change(self, single_dir):
    self.print_method_name()
    if self.single_prefix:
        if not single_dir.exists():
            print("Creating single prefix copy...")
            self.copy_template(single_dir)
    else:
        print("Reverting to multiple prefixes")
##################### / single prefix mode
