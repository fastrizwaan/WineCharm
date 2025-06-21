#!/usr/bin/env python3

import gi
import yaml
from pathlib import Path
import subprocess

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Pango, Adw

def on_settings_clicked(self, action=None, param=None):
    self.print_method_name()
    print("Settings action triggered")
    # You can add code here to open a settings window or dialog.
    
def load_settings(self):
    self.print_method_name()
    """Load settings from the Settings.yaml file."""
    if self.settings_file.exists():
        with open(self.settings_file, 'r') as settings_file:
            settings = yaml.safe_load(settings_file) or {}

        # Expand and resolve paths when loading
        self.template = self.expand_and_resolve_path(settings.get('template', self.default_template_win64))
        self.runner = self.expand_and_resolve_path(settings.get('runner', ''))
        self.arch = settings.get('arch', "win64")
        self.icon_view = settings.get('icon_view', False)
        self.env_vars = settings.get('env_vars', '')
        self.wine_debug = settings.get('wine_debug', '')
        self.single_prefix = settings.get('single-prefix', False)
        return settings

    # If no settings file, return an empty dictionary
    return {}
    
def save_settings(self):
    self.print_method_name()
    """Save current settings to the Settings.yaml file."""
    settings = {
        'template': self.replace_home_with_tilde_in_path(str(self.template)),
        'arch': self.arch,
        'runner': self.replace_home_with_tilde_in_path(str(self.settings.get('runner', ''))),
        'wine_debug': "WINEDEBUG=-fixme-all DXVK_LOG_LEVEL=none",
        'env_vars': '',
        'icon_view': self.icon_view,
        'single-prefix': self.single_prefix
    }

    try:
        with open(self.settings_file, 'w') as settings_file:
            yaml.dump(settings, settings_file, default_style="'", default_flow_style=False, width=10000)
        #print(f"Settings saved to {self.settings_file} with content:\n{settings}")
    except Exception as e:
        print(f"Error saving settings: {e}")
        
def set_dynamic_variables(self):
    self.print_method_name()
    # Check if Settings.yaml exists and set the template and arch accordingly
    if self.settings_file.exists():
        settings = self.load_settings()  # Assuming load_settings() returns a dictionary
        self.template = self.expand_and_resolve_path(settings.get('template', self.default_template_win64))
        self.arch = settings.get('arch', "win64")
        self.icon_view = settings.get('icon_view', False)
        self.single_prefix = settings.get('single-prefix', False)
    else:
        self.template = self.expand_and_resolve_path(self.default_template_win64)
        self.arch = "win64"
        self.runner = ""
        self.template = self.default_template_win64  # Set template to the initialized one
        self.icon_view = False
        self.single_prefix = False

    self.save_settings()

def replace_open_button_with_settings(self):
    self.print_method_name()
    # Remove existing click handler from open button only if it exists
    if hasattr(self, 'open_button_handler_id') and self.open_button_handler_id is not None:
        self.open_button.disconnect(self.open_button_handler_id)
    
    self.set_open_button_label("Settings")
    self.set_open_button_icon_visible(False)
    
    # Connect new click handler
    self.open_button_handler_id = self.open_button.connect(
        "clicked",
        lambda btn: print("Settings clicked")
    )

def show_options_for_settings(self, action=None, param=None):
    self.print_method_name()
    """
    Display the settings options with search functionality using existing search mechanism.
    """
    # Add accelerator context for settings view
    self.setup_accelerator_context()

    self.search_button.set_active(False)
    # Ensure the search button is visible and the search entry is cleared
    self.search_button.set_visible(True)
    self.search_entry.set_text("")
    self.main_frame.set_child(None)

    # Create a scrolled window for settings options
    scrolled_window = Gtk.ScrolledWindow()
    scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled_window.set_vexpand(True)

    self.settings_flowbox = Gtk.FlowBox()
    self.settings_flowbox.set_valign(Gtk.Align.START)
    self.settings_flowbox.set_halign(Gtk.Align.FILL)
    self.settings_flowbox.set_max_children_per_line(4)
    self.settings_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
    self.settings_flowbox.set_vexpand(True)
    self.settings_flowbox.set_hexpand(True)
    scrolled_window.set_child(self.settings_flowbox)

    self.main_frame.set_child(scrolled_window)

    # Store settings options as instance variable for filtering
    self.settings_options = [
        ("Runner Set Default", "runner-set-default-symbolic", self.set_default_runner),
        ("Runner Download", "runner-download-symbolic", self.on_settings_download_runner_clicked),
        ("Runner Import", "runner-import-symbolic", self.import_runner),
        ("Runner Backup", "runner-backup-symbolic", self.backup_runner),
        ("Runner Restore", "runner-restore-symbolic", self.restore_runner),
        ("Runner Delete", "runner-delete-symbolic", self.delete_runner),
        ("Template Set Default", "template-default-symbolic", self.set_default_template),
        ("Template Configure", "template-configure-symbolic", self.configure_template),
        ("Template Terminal", "template-terminal-symbolic", self.open_terminal_winecharm),
        ("Template Import", "template-import-symbolic", self.import_template),
        ("Template Create", "template-create-symbolic", self.create_template),
        ("Template Clone", "template-clone-symbolic", self.clone_template),
        ("Template Backup", "template-backup-symbolic", self.backup_template),
        ("Template Restore", "template-restore-symbolic", self.restore_template_from_backup),
        ("Template Delete", "template-delete-symbolic", self.delete_template),
        ("Set Wine Arch", "set-wine-arch-symbolic", self.set_wine_arch),
        ("Single Prefix Mode", "single-prefix-mode-symbolic", self.single_prefix_mode),
    ]

    # Initial population of options
    self.populate_settings_options()

    # Hide unnecessary UI components
    self.menu_button.set_visible(False)
    self.view_toggle_button.set_visible(False)

    if self.back_button.get_parent() is None:
        self.headerbar.pack_start(self.back_button)
    self.back_button.set_visible(True)

    self.replace_open_button_with_settings()
    self.selected_row = None

def populate_settings_options(self, filter_text=""):
    self.print_method_name()
    """
    Populate the settings flowbox with filtered options.
    """
    # Clear existing options using GTK4's method
    while child := self.settings_flowbox.get_first_child():
        self.settings_flowbox.remove(child)

    # Add filtered options
    filter_text = filter_text.lower()
    for label, icon_name, callback in self.settings_options:
        if filter_text in label.lower():
            option_button = Gtk.Button()
            option_button.set_size_request(-1, 40)
            option_button.add_css_class("flat")
            option_button.add_css_class("normal-font")

            option_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            option_button.set_child(option_hbox)

            option_icon = Gtk.Image.new_from_icon_name(icon_name)
            option_label = Gtk.Label(label=label)
            option_label.set_xalign(0)
            option_label.set_hexpand(True)
            option_label.set_ellipsize(Pango.EllipsizeMode.END)
            option_hbox.append(option_icon)
            option_hbox.append(option_label)

            self.settings_flowbox.append(option_button)
            option_button.connect("clicked", lambda btn, cb=callback: cb())
