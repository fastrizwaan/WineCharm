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

        main_frame = Gtk.Frame()
        main_frame.set_margin_top(5)
        main_frame.set_margin_bottom(5)
        main_frame.set_margin_start(5)
        main_frame.set_margin_end(5)
        toolbar_view.set_content(main_frame)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        main_frame.set_child(scrolled_window)

        script_group = Adw.PreferencesGroup()
        script_group.set_title("Scripts")
        script_group.set_description("List of available scripts")
        script_group.separate_rows = True
        scrolled_window.set_child(script_group)

        for i in range(1, 6):
            row = Adw.ActionRow()
            row.set_title(f"Script {i}")
            row.set_subtitle(f"Description of script {i}")
            script_group.add(row)

        window.present()

def main():
    app = MyApplication()
    app.run(None)

if __name__ == "__main__":
    main()
