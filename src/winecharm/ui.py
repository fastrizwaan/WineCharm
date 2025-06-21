#!/usr/bin/env python3

import gi
import threading
import subprocess
import shutil
import shlex
import yaml
from pathlib import Path

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Gdk, Adw, GdkPixbuf, Pango  # Add Pango here

def create_main_window(self):
    self.print_method_name()
    
        
    self.back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
    self.back_button.connect("clicked", self.on_back_button_clicked)
    self.open_button_handler_id = None
    # Create the main application window
    self.window = Adw.ApplicationWindow(application=self)
    self.window.set_default_size(585, 811)
    self.window.add_css_class("common-background")
    self.window.connect("close-request", self.quit_app)

    # Create a main container box to hold headerbar and content
    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    self.window.set_content(main_box)

    # Create and configure Adw.HeaderBar
    self.headerbar = Adw.HeaderBar()
    self.headerbar.add_css_class("flat")
    main_box.append(self.headerbar)

    # Create the main vertical box for content
    self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    self.vbox.set_margin_start(10)
    self.vbox.set_margin_end(10)
    self.vbox.set_margin_bottom(10)
    main_box.append(self.vbox)

    # Create title widget with icon and label
    self.title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    app_icon = Gtk.Image.new_from_icon_name("io.github.fastrizwaan.WineCharm")
    app_icon.set_pixel_size(18)
    self.title_box.append(app_icon)
    
    title_label = Gtk.Label(label="Wine Charm")
    title_label.set_markup("<b>Wine Charm</b>")
    title_label.set_use_markup(True)
    self.title_box.append(title_label)
    
    self.headerbar.set_title_widget(self.title_box)

    # Back button
    self.back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
    self.back_button.add_css_class("flat")
    self.back_button.set_visible(False)
    self.back_button.connect("clicked", self.on_back_button_clicked)
    self.headerbar.pack_start(self.back_button)

    # Create box for search and view toggle buttons
    view_and_sort_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)

    # Search button
    self.search_button = Gtk.ToggleButton()
    search_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
    self.search_button.set_child(search_icon)
    self.search_button.connect("toggled", self.on_search_button_clicked)
    self.search_button.add_css_class("flat")
    view_and_sort_box.append(self.search_button)

    # View toggle button
    self.view_toggle_button = Gtk.ToggleButton()
    icon_view_icon = Gtk.Image.new_from_icon_name("view-grid-symbolic")
    list_view_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
    self.view_toggle_button.set_child(icon_view_icon if self.icon_view else list_view_icon)
    self.view_toggle_button.add_css_class("flat")
    self.view_toggle_button.set_tooltip_text("Toggle Icon/List View")
    self.view_toggle_button.connect("toggled", self.on_view_toggle_button_clicked)
    view_and_sort_box.append(self.view_toggle_button)

    self.headerbar.pack_start(view_and_sort_box)

    # Menu button
    self.menu_button = Gtk.MenuButton()
    menu_icon = Gtk.Image.new_from_icon_name("open-menu-symbolic")
    self.menu_button.set_child(menu_icon)
    self.menu_button.add_css_class("flat")
    self.menu_button.set_tooltip_text("Menu")
    self.headerbar.pack_end(self.menu_button)

    # Create main menu
    menu = Gio.Menu()
    sort_submenu = Gio.Menu()
    sort_submenu.append("Name (A-Z)", "win.sort::progname::False")
    sort_submenu.append("Name (Z-A)", "win.sort::progname::True")
    sort_submenu.append("Wineprefix (A-Z)", "win.sort::wineprefix::False")
    sort_submenu.append("Wineprefix (Z-A)", "win.sort::wineprefix::True")
    sort_submenu.append("Time (Newest First)", "win.sort::mtime::True")
    sort_submenu.append("Time (Oldest First)", "win.sort::mtime::False")
    menu.append_submenu("🔠 Sort", sort_submenu)

    open_submenu = Gio.Menu()
    open_submenu.append("Open Filemanager", "win.open_filemanager_winecharm")
    open_submenu.append("Open Terminal", "win.open_terminal_winecharm")
    menu.append_submenu("📂 Open", open_submenu)
    
    self.menu_button.set_menu_model(menu)

    # Add hamburger menu actions
    for label, action in self.hamburger_actions:
        menu.append(label, f"win.{action.__name__}")
        action_item = Gio.SimpleAction.new(action.__name__, None)
        action_item.connect("activate", action)
        self.window.add_action(action_item)

    self.create_sort_actions()
    self.create_open_actions()

    # Open button
    self.open_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    self.open_button_box.set_halign(Gtk.Align.CENTER)
    open_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
    open_label = Gtk.Label(label="Open")
    self.open_button_box.append(open_icon)
    self.open_button_box.append(open_label)

    self.open_button = Gtk.Button()
    self.open_button.set_child(self.open_button_box)
    self.open_button.set_size_request(-1, 40)
    self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)
    self.vbox.append(self.open_button)

    # Search entry
    self.search_entry = Gtk.Entry()
    self.search_entry.set_size_request(-1, 40)
    self.search_entry.set_placeholder_text("Search")
    self.search_entry.connect("activate", self.on_search_entry_activated)
    self.search_entry.connect("changed", self.on_search_entry_changed)
    self.search_entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    search_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
    self.search_entry_box.append(self.search_entry)
    self.search_entry_box.set_hexpand(True)
    self.search_entry.set_hexpand(True)
    # Note: search_entry_box is not appended here, as it may be added dynamically

    # Main content
    self.main_frame = Gtk.Frame()
    self.main_frame.set_margin_top(0)
    self.vbox.append(self.main_frame)

    self.scrolled = Gtk.ScrolledWindow()
    self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    self.scrolled.set_vexpand(True)
    self.scrolled.set_hexpand(True)
    self.main_frame.set_child(self.scrolled)

    self.flowbox = Gtk.FlowBox()
    self.flowbox.set_valign(Gtk.Align.START)
    self.flowbox.set_max_children_per_line(100)
    self.flowbox.set_homogeneous(True)
    self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
    self.scrolled.set_child(self.flowbox)

    # Keyboard controller
    key_controller = Gtk.EventControllerKey()
    key_controller.connect("key-pressed", self.on_key_pressed)
    self.window.add_controller(key_controller)

    self.create_script_list()
    self.add_keyboard_actions()
    
def add_keyboard_actions(self):
    self.print_method_name()
    # Search action
    search_action = Gio.SimpleAction.new("search", None)
    search_action.connect("activate", lambda *_: self.search_button.set_active(not self.search_button.get_active()))
    self.window.add_action(search_action)

    # Open action (fixed signature)
    open_action = Gio.SimpleAction.new("open", None)
    open_action.connect("activate", lambda *_: self.on_open_button_clicked(None))
    self.window.add_action(open_action)

    # Toggle view action
    toggle_view_action = Gio.SimpleAction.new("toggle_view", None)
    toggle_view_action.connect("activate", lambda *_: self.on_view_toggle_button_clicked(self.view_toggle_button))
    self.window.add_action(toggle_view_action)

    # Kill all action
    kill_all_action = Gio.SimpleAction.new("kill_all", None)
    kill_all_action.connect("activate", self.on_kill_all_clicked)
    self.window.add_action(kill_all_action)

    # Back navigation action
    back_action = Gio.SimpleAction.new("back", None)
    back_action.connect("activate", lambda *_: self.on_back_button_clicked(None))
    self.window.add_action(back_action)

def create_sort_actions(self):
    self.print_method_name()
    """
    Create a single sorting action for the sorting options in the Sort submenu.
    """
    # Use 's' to denote that the action expects a string type parameter
    sort_action = Gio.SimpleAction.new("sort", GLib.VariantType('s'))
    sort_action.connect("activate", self.on_sort)
    self.window.add_action(sort_action)

def on_search_button_clicked(self, button):
    self.print_method_name()
    try:
        if self.search_active:
            # Before removing search entry, make sure it's in the vbox
            if self.search_entry_box.get_parent() == self.vbox:
                self.vbox.remove(self.search_entry_box)
            
            # Before adding open/launch button, make sure it's not already in the vbox
            if hasattr(self, 'launch_button') and self.launch_button is not None:
                if self.launch_button.get_parent() != self.vbox:
                    self.vbox.prepend(self.launch_button)
            else:
                if self.open_button.get_parent() != self.vbox:
                    self.vbox.prepend(self.open_button)
            
            self.search_active = False
            
            # Reset the appropriate view based on context
            if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
                self.search_entry.set_text("")
                self.populate_settings_options()
            elif hasattr(self, 'script_options_flowbox') and self.script_options_flowbox.get_parent() is not None:
                self.search_entry.set_text("")
                self.populate_script_options()
            else:
                self.filter_script_list("")
        else:
            # Only try to remove if button is in the vbox
            current_button = self.launch_button if hasattr(self, 'launch_button') and self.launch_button is not None else self.open_button
            if current_button.get_parent() == self.vbox:
                self.vbox.remove(current_button)
            
            # Only add search entry if it's not already in the vbox
            if self.search_entry_box.get_parent() != self.vbox:
                self.vbox.prepend(self.search_entry_box)
            
            self.search_entry.grab_focus()
            self.search_active = True
    except Exception as e:
        print(f"Error in search button handling: {e}")

def populate_script_options(self, filter_text=""):
    self.print_method_name()
    print("-x"*20)
    """
    Populate the script options flowbox with filtered options.
    """
    # Clear existing options
    while child := self.script_options_flowbox.get_first_child():
        self.script_options_flowbox.remove(child)

    # Add filtered options
    filter_text = filter_text.lower()
    for label, icon_name, callback in self.script_options:
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

            self.script_options_flowbox.append(option_button)

            # Handle the log button sensitivity
            if label == "Show log":
                # Replace underscores with spaces in the script stem for the log file name
                log_file_name = f"{self.current_script.stem.replace('_', ' ')}.log"
                log_file_path = self.current_script.parent / log_file_name
                # Debug output
                print(f"Log file path: {log_file_path}")
                print(f"Exists: {log_file_path.exists()}")
                print(f"Size: {log_file_path.stat().st_size if log_file_path.exists() else 0}")
                try:
                    if log_file_path.exists() and log_file_path.stat().st_size > 0:
                        print("Setting Show log button to sensitive")
                        option_button.set_sensitive(True)
                    else:
                        print("Setting Show log button to insensitive")
                        option_button.set_sensitive(False)
                except Exception as e:
                    print(f"Error checking log file: {e}")
                    option_button.set_sensitive(False)

            # Connect the button callback
            option_button.connect(
                "clicked",
                lambda btn, cb=callback: self.callback_wrapper(cb, self.current_script, self.current_script_key, btn)
            )

def on_key_pressed(self, controller, keyval, keycode, state):
    self.print_method_name()
    
    # Check if Ctrl is pressed to handle Ctrl+F
    if state & Gdk.ModifierType.CONTROL_MASK and keyval == Gdk.KEY_f:
        self.search_button.set_active(not self.search_button.get_active())
        return True

    # Handle Escape key to close search
    if keyval == Gdk.KEY_Escape:
        self.search_button.set_active(False)
        self.search_entry.set_text("")
        
        # Reset the appropriate view based on context
        if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
            self.populate_settings_options()
        elif hasattr(self, 'script_options_flowbox') and self.script_options_flowbox.get_parent() is not None:
            self.populate_script_options()
        else:
            self.filter_script_list("")
            
        # Clear focus to prevent any widget (e.g., Open button) from being focused
        self.window.set_focus(None)
        return True

    # Check if the key is a printable character and search is not active
    if not self.search_active and self.is_printable_key(keyval):
        # Activate search mode
        self.search_button.set_active(True)
        
        # Get the character from the keyval
        key_string = Gdk.keyval_to_unicode(keyval)
        if key_string:
            key_char = chr(key_string)
            # Set the search entry text to the typed character
            self.search_entry.set_text(key_char)
            # Move cursor to the end of the text
            self.search_entry.set_position(-1)
            # Trigger search
            self.on_search_entry_changed(self.search_entry)
        return True

    return False

def on_search_entry_activated(self, entry):
    self.print_method_name()
    search_term = entry.get_text().lower()
    self.filter_script_list(search_term)

def on_search_entry_changed(self, entry):
    self.print_method_name()
    search_term = entry.get_text().lower()
    # Check if we're in settings view
    if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
        self.populate_settings_options(search_term)
    elif hasattr(self, 'script_options_flowbox') and self.script_options_flowbox.get_parent() is not None:
        self.populate_script_options(search_term)  # Only pass search term
    else:
        self.filter_script_list(search_term)

def filter_script_list(self, search_term):
    self.print_method_name()
    """
    Filters the script list based on the search term and updates the UI accordingly.
    
    Parameters:
        search_term (str): The term to search for within exe_name, script_name (script_path.stem), or progname.
    """
    # Normalize the search term for case-insensitive matching
    search_term = search_term.lower()
    
    # Clear the existing flowbox to prepare for the filtered scripts
    self.flowbox.remove_all()
    
    # Flag to check if any scripts match the search term
    found_match = False
    
    # Iterate over all scripts in self.script_list using script_key and script_data
    for script_key, script_data in list(self.script_list.items()):
        # Resolve the script path, executable name, and get the progname
        script_path = Path(str(script_data['script_path'])).expanduser().resolve()
        exe_name = Path(str(script_data['exe_file'])).expanduser().resolve().name
        progname = str(script_data.get('progname', '')).lower()  # Fallback to empty string if 'progname' is missing
        
        # Check if the search term is present in the exe_name, script_name (stem), or progname
        if (search_term in exe_name.lower() or 
            search_term in script_path.stem.lower() or 
            search_term in progname):
            found_match = True
            
            # Create a script row. Ensure that create_script_row accepts script_key and script_data
            row = self.create_script_row(script_key, script_data)
            
            # Append the created row to the flowbox for display
            self.flowbox.append(row)
            
            # If the script is currently running, update the UI to reflect its running state
            if script_key in self.running_processes:
                #self.update_ui_for_running_process(script_key, row, self.running_processes)
                self.update_ui_for_running_process(self.running_processes)


    if not found_match:
        print(f"No matches found for search term: {search_term}")

def update_ui_for_running_process(self, current_running_processes):

    self.print_method_name()
    """
    Update the UI to reflect the state of running processes.
    
    Args:
        current_running_processes (dict): A dictionary containing details of the current running processes.
    """
    # Iterate over all scripts in script_ui_data to update the UI state
    for script_key, ui_state in self.script_ui_data.items():
        if not ui_state:
            print(f"No script data found for script_key: {script_key}")
            continue

        # Retrieve row, play_button, and options_button
        row = ui_state.get('row')
        play_button = ui_state.get('play_button')
        options_button = ui_state.get('options_button')

        if script_key in current_running_processes:
            # If the script is running, add the highlighted class and update button states
            if not ui_state['is_running']:  # Only update if the current state is not already running
                if row:
                    self.update_row_highlight(row, True)
                    row.add_css_class("highlighted")
                    print(f"Added 'highlighted' to row for script_key: {script_key}")

                # Set the play button to 'Stop' since the script is running
                if play_button:
                    self.set_play_stop_button_state(play_button, True)

                # Update internal running state
                ui_state['is_running'] = True

        else:
            # If the script is not running, remove highlight and reset buttons, but only if it's marked as running
            if ui_state['is_running']:  # Only update if the current state is marked as running
                if row:
                    self.update_row_highlight(row, False)
                    row.remove_css_class("highlighted")
                    #row.remove_css_class("blue")
                    print(f"Removed 'highlighted' from row for script_key: {script_key}")

                # Set play button back to 'Play'
                if play_button:
                    self.set_play_stop_button_state(play_button, False)

                # Update internal state to not running
                ui_state['is_running'] = False
                ui_state['is_clicked_row'] = False

        # Update the play/stop button visibility if the script row is currently clicked
        if ui_state.get('is_clicked_row', False):
            if play_button and options_button:
                self.show_buttons(play_button, options_button)
                self.set_play_stop_button_state(play_button, True)
                print(f"Updated play/stop button for clicked row with script_key: {script_key}")

        # Update the launch button state if it matches the script_key
        if self.launch_button and getattr(self, 'launch_button_exe_name', None) == script_key:
            if script_key in current_running_processes:
                self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic"))
                self.launch_button.set_tooltip_text("Stop")
            else:
                self.launch_button.set_child(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                self.launch_button.set_tooltip_text("Play")
            print(f"Updated launch button for script_key: {script_key}")

def on_open_button_clicked(self, button):
    self.print_method_name()
    self.open_file_dialog()

def open_file_dialog(self):
    self.print_method_name()
    file_dialog = Gtk.FileDialog.new()
    filter_model = Gio.ListStore.new(Gtk.FileFilter)
    filter_model.append(self.create_file_filter())
    file_dialog.set_filters(filter_model)
    file_dialog.open(self.window, None, self.on_open_file_dialog_response)

def create_file_filter(self):
    self.print_method_name()
    file_filter = Gtk.FileFilter()
    file_filter.set_name("EXE and MSI files")
    file_filter.add_mime_type("application/x-ms-dos-executable")
    # Add patterns for case-insensitive extensions
    for ext in ["*.exe", "*.EXE", "*.msi", "*.MSI"]:
        file_filter.add_pattern(ext)
    return file_filter

def on_open_file_dialog_response(self, dialog, result):
    self.print_method_name()
    try:
        file = dialog.open_finish(result)
        if file:
            file_path = file.get_path()
            print("- - - - - - - - - - - - - -self.show_processing_spinner")
            self.monitoring_active = False
            
            # If there's already a processing thread, stop it
            if hasattr(self, 'processing_thread') and self.processing_thread and self.processing_thread.is_alive():
                self.stop_processing = True
                self.processing_thread.join(timeout=0.5)  # Wait briefly for thread to stop
                self.hide_processing_spinner()
                self.set_open_button_label("Open")
                self.set_open_button_icon_visible(True)
                return

            # Show processing spinner
            self.show_processing_spinner("Processing...")
            
            # Start a new background thread to process the file
            self.stop_processing = False
            self.processing_thread = threading.Thread(target=self.process_cli_file_in_thread, args=(file_path,))
            self.processing_thread.start()

    except GLib.Error as e:
        if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
            print(f"An error occurred: {e}")
    finally:
        self.window.set_visible(True)
        self.monitoring_active = True


        
def on_back_button_clicked(self, button):
    self.print_method_name()
    # If search is active, toggle it off first
    if self.search_active:
        self.search_button.set_active(False)

    # Reset the header bar title and visibility of buttons
    self.headerbar.set_title_widget(self.title_box)
    self.menu_button.set_visible(True)
    self.search_button.set_visible(True)
    self.view_toggle_button.set_visible(True)
    self.back_button.set_visible(False)

    # Remove the "Launch" button if it exists
    if hasattr(self, 'launch_button') and self.launch_button is not None:
        if self.launch_button.get_parent() == self.vbox:
            self.vbox.remove(self.launch_button)
        self.launch_button = None

    # Restore the "Open" button
    if self.open_button.get_parent() != self.vbox:
        self.vbox.prepend(self.open_button)
    self.open_button.set_visible(True)
    
    # Restore original open button functionality
    self.restore_open_button()

    # Ensure the correct child is set in the main_frame
    if self.main_frame.get_child() != self.scrolled:
        self.main_frame.set_child(self.scrolled)

    self.remove_accelerator_context()
        
    # Restore the script list
    self.create_script_list()

def open_filemanager_winecharm(self, action, param):
    self.print_method_name()
    wineprefix = Path(self.winecharmdir)  # Replace with the actual wineprefix path
    print(f"Opening file manager for {wineprefix}")
    command = ["xdg-open", str(wineprefix)]
    try:
        subprocess.Popen(command)
    except Exception as e:
        print(f"Error opening file manager: {e}")

def open_terminal_winecharm(self, param=None, action=None):
    self.print_method_name()
    # Set wineprefix to self.template
    wineprefix = Path(self.template).expanduser().resolve()

    print(f"Opening terminal for {wineprefix}")

    self.ensure_directory_exists(wineprefix)

    # Load settings to get the runner
    settings = self.load_settings()
    runner = settings.get('runner', 'wine')  # Default to 'wine' if runner is not specified
    runner_path = Path(runner).expanduser().resolve()
    runner_dir = runner_path.parent.resolve()

    if shutil.which("flatpak-spawn"):
        command = [
            "wcterm", "bash", "--norc", "-c",
            (
                rf'export PS1="[\u@\h:\w]\$ "; '
                f'export WINEPREFIX={shlex.quote(str(wineprefix))}; '
                f'export PATH={shlex.quote(str(runner_dir))}:$PATH; '
                f'cd {shlex.quote(str(wineprefix))}; '
                'exec bash --norc -i'
            )
        ]
    else:
        # List of terminal commands to check
        terminal_commands = [
            ("ptyxis", ["ptyxis", "--"]),
            ("gnome-terminal", ["gnome-terminal", "--wait", "--"]),
            ("konsole", ["konsole", "-e"]),
            ("xfce4-terminal", ["xfce4-terminal", "--disable-server", "-x"]),
        ]

        # Find the first available terminal
        terminal_command = None
        for terminal, command_prefix in terminal_commands:
            if shutil.which(terminal):
                terminal_command = command_prefix
                break

        if not terminal_command:
            print("No suitable terminal emulator found.")
            return

        command = terminal_command + [
            "bash", "--norc", "-c",
            (
                rf'export PS1="[\u@\h:\w]\$ "; '
                f'export WINEPREFIX={shlex.quote(str(wineprefix))}; '
                f'export PATH={shlex.quote(str(runner_dir))}:$PATH; '
                f'cd {shlex.quote(str(wineprefix))}; '
                'exec bash --norc -i'
            )
        ]

    print(f"Running command: {command}")

    try:
        subprocess.Popen(command)
    except Exception as e:
        print(f"Error opening terminal: {e}")

    
def remove_accelerator_context(self):
    # Cleanup accelerator group when leaving options view
    if hasattr(self, 'accel_group'):
        self.window.remove_accel_group(self.accel_group)
        del self.accel_group
        
def setup_accelerator_context(self):
    self.print_method_name()
    controller = Gtk.ShortcutController()
    shortcut = Gtk.Shortcut(
        trigger=Gtk.ShortcutTrigger.parse_string("<Ctrl>BackSpace"),
        action=Gtk.CallbackAction.new(lambda *_: self.on_back_button_clicked(None))
    )
    controller.add_shortcut(shortcut)
    self.window.add_controller(controller)
    
def restore_open_button(self):
    self.print_method_name()
    # Remove settings click handler
    if hasattr(self, 'open_button_handler_id'):
        self.open_button.disconnect(self.open_button_handler_id)
    
    self.set_open_button_label("Open")
    self.set_open_button_icon_visible(True)
    # Reconnect original click handler
    self.open_button_handler_id = self.open_button.connect(
        "clicked",
        self.on_open_button_clicked
    )


def create_script_list(self):
    self.print_method_name()
    """Create UI rows for scripts efficiently with batch updates, including highlighting."""
    self.flowbox.remove_all()
    
    if not self.script_list:
        return
    
    self.script_ui_data = {}
    
    rows = []
    for script_key, script_data in self.script_list.items():
        row = self.create_script_row(script_key, script_data)
        if row:
            rows.append(row)
            if script_key in self.running_processes:
                self.update_row_highlight(row, True)
                self.script_ui_data[script_key]['highlighted'] = True
                self.script_ui_data[script_key]['is_running'] = True
            else:
                self.update_row_highlight(row, False)
                self.script_ui_data[script_key]['highlighted'] = False
                self.script_ui_data[script_key]['is_running'] = False
    
    for row in rows:
        self.flowbox.append(row)


def create_script_row(self, script_key, script_data):
    script = Path(str(script_data['script_path'])).expanduser()
    
    # Common title text setup
    title_text = str(script_data.get('progname', script.stem)).replace('_', ' ')
    if script.stem in self.new_scripts:
        title_text = f"<b>{title_text}</b>"

    if self.icon_view:
        # ICON VIEW
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        container.add_css_class("rounded-container")
        container.set_size_request(100, 100)
        container.set_hexpand(True)
        #container.set_vexpand(True)
        container.set_halign(Gtk.Align.FILL)
        #container.set_valign(Gtk.Align.FILL)
        # Top: Horizontal box for [options][icon][play]
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        top_box.set_hexpand(True)
        top_box.set_vexpand(True)
        #top_box.set_valign(Gtk.Align.CENTER)
        #top_box.set_halign(Gtk.Align.FILL)
        top_box.set_size_request(50,50)
        # Options button (larger, consistent width, initially hidden)
        options_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options")
        options_button.add_css_class("flat")
        options_button.set_size_request(32, -1)  # Consistent width with play button
        options_button.set_hexpand(True)
        options_button.set_margin_start(0)
        options_button.set_margin_end(0)
        options_button.set_margin_top(0)
        options_button.set_margin_bottom(0)
        options_button.set_opacity(0)  # Hidden by default
        options_button.set_sensitive(False)
        #options_button.set_halign(Gtk.Align.FILL)
        #options_button.set_halign(Gtk.Align.FILL)
        top_box.append(options_button)

        # Icon (centered)
        icon = self.load_icon(script, 96, 96, 10)
        icon_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon_container.set_hexpand(True)  # Allow icon to expand in the center
        icon_container.set_halign(Gtk.Align.CENTER)
        #icon_container.set_valign(Gtk.Align.CENTER)
        if icon:
            icon_container.add_css_class("rounded-icon")
            icon_image = Gtk.Image.new_from_paintable(icon)
            icon_image.set_pixel_size(96)
            icon_image.set_halign(Gtk.Align.CENTER)
            #icon_image.set_valign(Gtk.Align.CENTER)
            icon_container.append(icon_image)
        else:
            icon_image = Gtk.Image()
            icon_container.append(icon_image)
        icon_container.set_margin_top(0)
        icon_container.set_margin_bottom(1)
        top_box.append(icon_container)

        # Play button (larger, consistent width, initially hidden)
        play_button = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Play")
        play_button.add_css_class("flat")
        #play_button.set_halign(Gtk.Align.FILL)
        play_button.set_size_request(36, -1)  # Consistent width with options button
        play_button.set_opacity(0)  # Hidden by default
        play_button.set_sensitive(False)
        play_button.set_hexpand(True)
        top_box.append(play_button)

        container.append(top_box)

        # Bottom: Label (always visible, ellipsized, color changes with "blue" class)
        label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        label_box.set_halign(Gtk.Align.CENTER)
        #label_box.set_valign(Gtk.Align.FILL)
        main_label = Gtk.Label()
        main_label.set_max_width_chars(18)
        main_label.set_lines(2)
        main_label.set_wrap(True)
        main_label.set_ellipsize(Pango.EllipsizeMode.END)
        #main_label.set_valign(Gtk.Align.FILL)
        main_label.set_markup(title_text)
        main_label.set_tooltip_text(str(script_data.get('progname', script.stem)))
        label_box.append(main_label)


        #label_box.set_size_request(-1, 40)
        label_box.set_opacity(1)  # Always visible
        label_box.set_sensitive(True)  # Always active
        
        container.append(label_box)

        # Store UI data
        self.script_ui_data[script_key] = {
            'row': container,
            'play_button': play_button,
            'options_button': options_button,
            'label_box': label_box,
            'button_box': top_box,
            'label_button_box': None,
            'is_running': False,
            'script_path': script,
            'showing_buttons': False
        }

        # Add click gesture to the icon container
        click = Gtk.GestureClick()
        click.connect("released", lambda gesture, n, x, y: self.toggle_overlay_buttons(script_key))
        icon_container.add_controller(click)

        # Connect button signals
        play_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, btn, container))
        options_button.connect("clicked", lambda btn: self.show_options_for_script(
            self.script_ui_data[script_key], container, script_key))

        return container

    if not self.icon_view:
        # LIST VIEW (unchanged)
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        container.add_css_class('rounded-container')

        # Icon (left-aligned)
        script = Path(str(script_data['script_path'])).expanduser()
        title_text = str(script_data.get('progname', script.stem)).replace('_', ' ')
        if script.stem in self.new_scripts:
            title_text = f"<b>{title_text}</b>"
        
        icon = self.load_icon(script, 40, 40, 4)
        if icon:
            icon_container = Gtk.Box()
            icon_container.add_css_class("rounded-icon")
            icon_image = Gtk.Image.new_from_paintable(icon)
            icon_image.set_pixel_size(40)
            icon_image.set_halign(Gtk.Align.CENTER)
            icon_container.append(icon_image)
            icon_container.set_margin_start(6)
        else:
            icon_container = Gtk.Box()
            icon_image = Gtk.Image()
            icon_container.append(icon_image)
            icon_container.set_margin_start(6)
        container.append(icon_container)

        # Container for label or buttons
        label_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_button_box.set_hexpand(True)
        label_button_box.set_valign(Gtk.Align.CENTER)

        # Create label_box
        label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        label_box.set_hexpand(True)
        main_label = Gtk.Label()
        main_label.set_hexpand(True)
        main_label.set_halign(Gtk.Align.START)
        main_label.set_wrap(True)
        main_label.set_max_width_chars(25)
        main_label.set_ellipsize(Pango.EllipsizeMode.END)
        main_label.set_markup(title_text)
        label_box.append(main_label)

        # Create button_box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        button_box.set_hexpand(True)
        box_main_label = Gtk.Label()
        box_main_label.set_markup(title_text)
        box_main_label.set_wrap(True)
        box_main_label.set_max_width_chars(15)
        box_main_label.set_ellipsize(Pango.EllipsizeMode.END)
        
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        
        play_button = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Play")
        play_button.set_size_request(60, -1)
        play_button.set_opacity(1)
        play_button.set_sensitive(True)
        
        options_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options")
        options_button.set_size_request(34, -1)
        options_button.set_opacity(1)
        options_button.set_sensitive(True)
        
        button_box.append(box_main_label)
        button_box.append(spacer)
        button_box.append(play_button)
        button_box.append(options_button)
        button_box.set_margin_end(4)
        button_box.set_size_request(60, 34)
        label_button_box.append(label_box)
        container.append(label_button_box)

        # Store UI data
        self.script_ui_data[script_key] = {
            'row': container,
            'play_button': play_button,
            'options_button': options_button,
            'label_box': label_box,
            'button_box': button_box,
            'label_button_box': label_button_box,
            'is_running': False,
            'script_path': script,
            'showing_buttons': False
        }

        # Add click gesture
        click = Gtk.GestureClick()
        click.connect("released", lambda gesture, n, x, y: self.toggle_overlay_buttons(script_key))
        container.add_controller(click)

        # Connect button signals
        play_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, btn, container))
        options_button.connect("clicked", lambda btn: self.show_options_for_script(
            self.script_ui_data[script_key], container, script_key))
        
        return container


def toggle_overlay_buttons(self, script_key):
    # Hide buttons and reset other rows
    for key, ui in self.script_ui_data.items():
        if key != script_key and ui.get('showing_buttons', False):
            if self.icon_view:
                ui['play_button'].set_opacity(0)
                ui['play_button'].set_sensitive(False)
                ui['options_button'].set_opacity(0)
                ui['options_button'].set_sensitive(False)
                # Label remains visible, no change needed
            else:
                ui['label_button_box'].remove(ui['button_box'])
                ui['label_button_box'].append(ui['label_box'])
            ui['showing_buttons'] = False
            ui['row'].remove_css_class("blue")

    # Toggle the current row
    ui = self.script_ui_data.get(script_key)
    if not ui:
        return

    showing_buttons = ui.get('showing_buttons', False)

    if self.icon_view:
        if showing_buttons:
            # Hide buttons, label stays visible
            ui['play_button'].set_opacity(0)
            ui['play_button'].set_sensitive(False)
            ui['options_button'].set_opacity(0)
            ui['options_button'].set_sensitive(False)
            ui['showing_buttons'] = False
            ui['row'].remove_css_class("blue")
        else:
            # Show buttons, label stays visible
            ui['play_button'].set_opacity(1)
            ui['play_button'].set_sensitive(True)
            ui['options_button'].set_opacity(1)
            ui['options_button'].set_sensitive(True)
            ui['showing_buttons'] = True
            ui['row'].add_css_class("blue")
    else:
        label_button_box = ui['label_button_box']
        if showing_buttons:
            label_button_box.remove(ui['button_box'])
            label_button_box.append(ui['label_box'])
            ui['showing_buttons'] = False
            ui['row'].remove_css_class("blue")
        else:
            label_button_box.remove(ui['label_box'])
            label_button_box.append(ui['button_box'])
            ui['showing_buttons'] = True
            ui['row'].add_css_class("blue")

    # Update play button icon based on running state
    pb = ui['play_button']
    if ui.get("is_running"):
        pb.set_icon_name("media-playback-stop-symbolic")
        pb.set_tooltip_text("Stop")
    else:
        pb.set_icon_name("media-playback-start-symbolic")
        pb.set_tooltip_text("Play")
    
def show_buttons(self, play_button, options_button):
    self.print_method_name()
    play_button.set_visible(True)
    options_button.set_visible(True)

def hide_buttons(self, play_button, options_button):
    self.print_method_name()
    if play_button is not None:
        play_button.set_visible(False)
    if options_button is not None:
        options_button.set_visible(False)

def on_script_row_clicked(self, script_key):
    self.count = 0
    self.print_method_name()
    """
    Handles the click event on a script row, manages row highlighting, and play/stop button state.
    
    Args:
        script_key (str): The unique key for the script (e.g., sha256sum).
    """
    # Retrieve the current script data for the clicked row
    current_data = self.script_ui_data.get(script_key)
    if not current_data:
        print(f"No script data found for script_key: {script_key}")
        return

    # Track the previously clicked row and update the `is_clicked_row` state
    for key, data in self.script_ui_data.items():
        if data['is_clicked_row']:
            # If the previously clicked row is not the current one, remove the blue highlight
            if key != script_key:
                data['is_clicked_row'] = False
                data['row'].remove_css_class("blue")
                self.hide_buttons(data['play_button'], data['options_button'])
                print(f"Removing 'blue' highlight for previously clicked row with script_key: {key}")

    # Toggle the `is_clicked_row` state for the currently clicked row
    current_data['is_clicked_row'] = not current_data['is_clicked_row']
    print(f"script_key = {script_key} is set to data['is_clicked_row'] = {current_data['is_clicked_row']}")

    # Update the UI based on the new `is_clicked_row` state
    row = current_data['row']
    play_button = current_data['play_button']
    options_button = current_data['options_button']
    is_running = current_data['is_running']
    is_clicked = current_data['is_clicked_row']

    if is_clicked:
        # Highlight the current row in blue and show the buttons
        row.remove_css_class("highlight")
        row.add_css_class("blue")
        self.show_buttons(play_button, options_button)
        print(f"Highlighting clicked row for script_key: {script_key} with 'blue'")
    else:
        # Remove highlight and hide buttons for the current row if it's not running
        row.remove_css_class("blue")
        self.hide_buttons(play_button, options_button)
        print(f"Removing 'blue' highlight for clicked row with script_key: {script_key}")

    # Update the play/stop button state
    if is_running:
        # If the script is running: set play button to 'Stop' and add 'highlighted' class
        self.set_play_stop_button_state(play_button, True)
        row.add_css_class("highlighted")
        print(f"Script {script_key} is running. Setting play button to 'Stop' and adding 'highlighted'.")
    else:
        # If the script is not running and not clicked, reset play button and highlight
        if not is_clicked:
            self.set_play_stop_button_state(play_button, False)
            row.remove_css_class("highlighted")
            print(f"Script {script_key} is not running. Setting play button to 'Play' and removing 'highlighted'.")

        # If the script is not running but clicked, ensure it stays highlighted in blue
        if is_clicked and not is_running:
            row.add_css_class("blue")
            print(f"Preserving 'blue' highlight for clicked but not running script_key: {script_key}")

def set_play_stop_button_state(self, button, is_playing):
    # Check if the button already has a child (Gtk.Image)
    current_child = button.get_child()
    
    if current_child and isinstance(current_child, Gtk.Image):
        # Reuse the existing Gtk.Image child
        image = current_child
    else:
        # Create a new Gtk.Image if none exists
        image = Gtk.Image()
        button.set_child(image)
    
    # Set the icon name and tooltip based on the state
    if is_playing:
        image.set_from_icon_name("media-playback-stop-symbolic")
        button.set_tooltip_text("Stop")
    else:
        image.set_from_icon_name("media-playback-start-symbolic")
        button.set_tooltip_text("Play")
    
    # Explicitly set pixel size to ensure crisp rendering
    # image.set_pixel_size(24)
    
    # Ensure the icon is re-rendered cleanly
    image.queue_draw()
    
def update_row_highlight(self, row, highlight):
    #self.print_method_name()
    if highlight:
        row.add_css_class("highlighted")
    else:
        #row.remove_css_class("blue")
        row.remove_css_class("highlighted")


def replace_open_button_with_launch(self, script, row, script_key):
    self.print_method_name()
    script_data = self.extract_yaml_info(script_key)
    if not script_data:
        return None
        
    if self.open_button.get_parent():
        self.vbox.remove(self.open_button)

    self.launch_button = Gtk.Button()
    self.launch_button.set_size_request(-1, 40)

    #yaml_info = self.extract_yaml_info(script)
    script_key = script_data['sha256sum']  # Use sha256sum as the key

    if script_key in self.running_processes:
        launch_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
        self.launch_button.set_tooltip_text("Stop")
    else:
        launch_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        self.launch_button.set_tooltip_text("Play")

    self.launch_button.set_child(launch_icon)
    self.launch_button.connect("clicked", lambda btn: self.toggle_play_stop(script_key, self.launch_button, row))

    # Store the script_key associated with this launch button
    self.launch_button_exe_name = script_key

    self.vbox.prepend(self.launch_button)
    self.launch_button.set_visible(True)

def replace_launch_button(self, ui_state, row, script_key):
    self.print_method_name()
    """
    Replace the open button with a launch button.
    """
    try:
        # Remove existing launch button if it exists
        if hasattr(self, 'launch_button') and self.launch_button is not None:
            parent = self.launch_button.get_parent()
            if parent is not None:
                parent.remove(self.launch_button)

        # Create new launch button
        self.launch_button = Gtk.Button()
        self.launch_button.set_size_request(-1, 40)
        
        # Set initial icon state
        is_running = script_key in self.running_processes
        launch_icon = Gtk.Image.new_from_icon_name(
            "media-playback-stop-symbolic" if is_running
            else "media-playback-start-symbolic"
        )
        self.launch_button.set_tooltip_text("Stop" if is_running else "Play")
        self.launch_button.set_child(launch_icon)
        
        # Connect click handler
        self.launch_button.connect(
            "clicked",
            lambda btn: self.toggle_play_stop(script_key, self.launch_button, row)
        )
        
        # Add to vbox
        if hasattr(self, 'vbox') and self.vbox is not None:
            if self.open_button.get_parent() == self.vbox:
                self.vbox.remove(self.open_button)
            self.vbox.prepend(self.launch_button)
            self.launch_button.set_visible(True)
        
    except Exception as e:
        print(f"Error in replace_launch_button: {e}")
        self.launch_button = None

def on_view_toggle_button_clicked(self, button):
    self.print_method_name()
    # Toggle the icon view state
    self.icon_view = not self.icon_view

    # Update the icon for the toggle button based on the current view state
    icon_name = "view-grid-symbolic" if self.icon_view else "view-list-symbolic"
    button.set_child(Gtk.Image.new_from_icon_name(icon_name))

    # Update the maximum children per line in the flowbox based on the current view state
    #max_children_per_line = 8 if self.icon_view else 4
    #self.flowbox.set_max_children_per_line(max_children_per_line)
    # Recreate the script list with the new view
    self.create_script_list()
    GLib.idle_add(self.save_settings)

def show_processing_spinner(self, label_text):
    self.print_method_name()

    # Clear existing content
    self.flowbox.remove_all()

    if hasattr(self, 'progress_bar'):
        self.vbox.remove(self.progress_bar)
        del self.progress_bar

    # Ensure main flowbox is visible
    self.main_frame.set_child(self.scrolled)
    
    # Add progress bar
    self.progress_bar = Gtk.ProgressBar()
    self.progress_bar.add_css_class("header-progress")
    self.progress_bar.set_show_text(False)
    self.progress_bar.set_margin_top(0)
    self.progress_bar.set_margin_bottom(0)
    self.progress_bar.set_fraction(0.0)
    #self.progress_bar.set_size_request(420, -1)
    self.vbox.prepend(self.progress_bar)
    self.flowbox.remove_all()
    
    # Update button label
    self.set_open_button_label(label_text)
    
    # Initialize steps
    self.step_boxes = []
    
    # Disable UI elements
    self.search_button.set_sensitive(False)
    self.view_toggle_button.set_sensitive(False)
    self.menu_button.set_sensitive(False)

def hide_processing_spinner(self):
    self.print_method_name()
    """Restore UI state after process completion with safe widget removal"""
    try:
        if hasattr(self, 'progress_bar'):
            self.vbox.remove(self.progress_bar)
            del self.progress_bar

        # Update button back to original state
        self.set_open_button_label("Open")
            
        # Safely re-enable UI elements
        if hasattr(self, 'search_button'):
            self.search_button.set_sensitive(True)
        if hasattr(self, 'view_toggle_button'):
            self.view_toggle_button.set_sensitive(True)
        if hasattr(self, 'menu_button'):    
            self.menu_button.set_sensitive(True)

        # Clear step tracking safely
        if hasattr(self, 'step_boxes'):
            self.step_boxes = []
            
    except Exception as e:
        print(f"Error in hide_processing_spinner: {e}")


def disable_open_button(self):
    self.print_method_name()
    if self.open_button:
        self.open_button.set_sensitive(False)
    print("Open button disabled.")

def enable_open_button(self):
    self.print_method_name()
    if self.open_button:
        self.open_button.set_sensitive(True)
    print("Open button enabled.")


def set_open_button_icon_visible(self, visible):
    self.print_method_name()
    box = self.open_button.get_child()
    child = box.get_first_child()
    while child:
        if isinstance(child, Gtk.Image):
            child.set_visible(visible)
        child = child.get_next_sibling()


def set_open_button_label(self, label_text):
    self.print_method_name()
    """Helper method to update the open button's label"""
    box = self.open_button.get_child()
    if not box:
        return
        
    child = box.get_first_child()
    while child:
        if isinstance(child, Gtk.Label):
            child.set_label(label_text)
        elif isinstance(child, Gtk.Image):
            child.set_visible(False)  # Hide the icon during processing
        child = child.get_next_sibling()

def show_initializing_step(self, step_text):
    self.print_method_name()
    """
    Show a new processing step in the flowbox
    """
    

    if hasattr(self, 'progress_bar'):
        # Calculate total steps dynamically
        if hasattr(self, 'total_steps'):
            total_steps = self.total_steps
        else:
            # Default for bottle creation
            total_steps = 8
        
        current_step = len(self.step_boxes) + 1
        progress = current_step / total_steps
        
        # Update progress bar
        self.progress_bar.set_fraction(progress)
        self.progress_bar.set_text(f"Step {current_step}/{total_steps}")
        
        # Create step box
        step_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        step_box.set_margin_start(12)
        step_box.set_margin_end(12)
        step_box.set_margin_top(6)
        step_box.set_margin_bottom(6)
        
        # Add status icon and label
        step_spinner = Gtk.Spinner()
        step_label = Gtk.Label(label=step_text)
        step_label.set_halign(Gtk.Align.START)
        step_label.set_hexpand(True)
        
        step_box.append(step_spinner)
        step_box.append(step_label)
        step_spinner.start()

        
        # Add to flowbox
        flowbox_child = Gtk.FlowBoxChild()
        flowbox_child.set_child(step_box)
        self.flowbox.append(flowbox_child)
        
        # Store reference
        self.step_boxes.append((step_box, step_spinner, step_label))

def mark_step_as_done(self, step_text):
    self.print_method_name()
    """
    Mark a step as completed in the flowbox
    """
    if hasattr(self, 'step_boxes'):
        for step_box, step_spinner, step_label in self.step_boxes:
            if step_label.get_text() == step_text:
                step_box.remove(step_spinner)
                done_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                step_box.prepend(done_icon)
                break

def on_cancel_button_clicked(self, button, parent, original_button):
    self.print_method_name()
    # Restore the original button as the child of the FlowBoxChild
    parent.set_child(original_button)
    original_button.set_sensitive(True)

def show_info_dialog(self, title, message, callback=None):
    self.print_method_name()
    dialog = Adw.AlertDialog(
        heading=title,
        body=message
    )
    
    # Add response using non-deprecated method
    dialog.add_response("ok", "OK")
    
    # Configure dialog properties
    dialog.props.default_response = "ok"
    dialog.props.close_response = "ok"

    def on_response(d, r):
        self.print_method_name()
        #d.close()
        if callback is not None:
            callback()

    dialog.connect("response", on_response)
    dialog.present(self.window)

def update_ui_for_running_script_on_startup(self, script_key):
    self.print_method_name()
    ui_state = self.script_ui_data.get(script_key)
    if not ui_state:
        print(f"No UI state found for script_key: {script_key}")
        return

    row = ui_state.get('row')
    play_button = ui_state.get('play_button')

    # Update UI elements
    if row:
        self.update_row_highlight(row, True)
        row.add_css_class("highlighted")

    if play_button:
        self.set_play_stop_button_state(play_button, True)
        ui_state['is_running'] = True  # Ensure is_running is set