#!/usr/bin/env python3

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw

class MyApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.MyApp')

    def do_activate(self):
        window = Adw.ApplicationWindow(application=self)
        window.set_title("AdwPreferencesGroup Example")
        window.set_default_size(400, 300)

        toolbar_view = Adw.ToolbarView()
        window.set_content(toolbar_view)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        toolbar_view.set_content(scrolled_window)

        script_group = Adw.PreferencesGroup()
        script_group.set_title("Scripts")
        script_group.set_description("List of available scripts")
        scrolled_window.set_child(script_group)

        list_box = Gtk.ListBox()
        list_box.add_css_class('boxed-list')
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.set_margin_top(10)
        list_box.set_margin_bottom(10)
        list_box.set_margin_start(10)
        list_box.set_margin_end(10)

        for i in range(1, 6):
            row = Adw.ActionRow()
            row.set_title(f"Script {i}")
           # row.set_subtitle(f"Description of script {i}")

            list_box.append(row)

        script_group.add(list_box)

        window.present()

def main():
    app = MyApplication()
    app.run(None)

if __name__ == "__main__":
    main()
