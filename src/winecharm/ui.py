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
