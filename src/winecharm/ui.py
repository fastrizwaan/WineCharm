import gi
from gi.repository import Gtk, Adw, Gio, Gdk, GLib
from pathlib import Path
import shlex
import subprocess
import os
import shutil

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')


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

