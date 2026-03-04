#!/usr/bin/env python3

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gio, Gtk, Adw


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from winecharm import ui


# ui.py expects "_" in its module globals.
if "_" not in ui.__dict__:
    ui._ = lambda s: s


class UIPopupHarness(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.fastrizwaan.WineCharm.PopupTest")
        self.window = None
        self.icon_view = False
        self.search_active = False
        self.hamburger_actions = []
        self.app_icon_name = "io.github.fastrizwaan.WineCharm"
        self.app_icon_available = False
        self.app_icon_path = None

        self.connect("activate", self.on_activate)

    def print_method_name(self):
        return

    def quit_app(self, *_args):
        self.quit()
        return False

    def on_back_button_clicked(self, *_args):
        return

    def on_search_button_clicked(self, *_args):
        return

    def on_view_toggle_button_clicked(self, *_args):
        return

    def on_open_button_clicked(self, *_args):
        return

    def on_search_entry_activated(self, *_args):
        return

    def on_search_entry_changed(self, *_args):
        return

    def on_key_pressed(self, *_args):
        return False

    def create_sort_actions(self):
        return

    def create_open_actions(self):
        return

    def create_script_list(self):
        return

    def add_keyboard_actions(self):
        return

    def _on_noop_action(self, *_args):
        print("No-op action triggered")

    def _on_open_dropdown_dialog_clicked(self, _button):
        model = Gtk.StringList.new(["Game", "Utility", "Office"])
        dropdown = Gtk.DropDown(model=model)
        dropdown.set_selected(0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.append(Gtk.Label(label="Open this dropdown, then Alt+Tab away"))
        content.append(dropdown)

        dialog = Adw.AlertDialog(
            heading="DropDown Dialog Test",
            body="Use this to validate popup behavior on focus change.",
        )
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_close_response("close")
        dialog.present(self.window)

    def _add_popup_test_controls(self):
        info = Gtk.Label(
            label=(
                "Popup Test Harness\n"
                "1) Open Menu and DropDown\n"
                "2) Alt+Tab to another app\n"
                "3) Check if popup stays visible"
            )
        )
        info.set_xalign(0)
        info.set_margin_top(8)
        self.vbox.append(info)

        test_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        test_row.set_margin_top(8)
        self.vbox.append(test_row)

        menu_model = Gio.Menu()
        menu_model.append("No-op Action", "app.noop")
        menu_model.append("No-op Action 2", "app.noop")
        menu_button = Gtk.MenuButton(label="Test Menu Popover")
        menu_button.set_menu_model(menu_model)
        test_row.append(menu_button)

        model = Gtk.StringList.new(["Option A", "Option B", "Option C"])
        dropdown = Gtk.DropDown(model=model)
        dropdown.set_selected(0)
        test_row.append(dropdown)

        open_dialog_btn = Gtk.Button(label="Open Dialog With DropDown")
        open_dialog_btn.connect("clicked", self._on_open_dropdown_dialog_clicked)
        self.vbox.append(open_dialog_btn)

    def on_activate(self, *_args):
        if self.window is None:
            noop_action = Gio.SimpleAction.new("noop", None)
            noop_action.connect("activate", self._on_noop_action)
            self.add_action(noop_action)

            ui.create_main_window(self)
            self._add_popup_test_controls()

        self.window.present()


def main():
    app = UIPopupHarness()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
