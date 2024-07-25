#!/usr/bin/env python3

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class SimpleAdwApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.SimpleAdwApp')
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        window = Adw.ApplicationWindow(application=self)
        window.set_title("Simple Adw App")
        window.set_default_size(400, 300)

        content = Adw.Bin()

        boxed_list = Gtk.ListBox()
        boxed_list.set_selection_mode(Gtk.SelectionMode.NONE)
        boxed_list.add_css_class("boxed-list")

        for i in range(10):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            label = Gtk.Label(label=f"Item {i + 1}")
            box.append(label)
            row.set_child(box)
            boxed_list.append(row)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_child(boxed_list)

        content.set_child(scrolled_window)
        window.set_content(content)
        window.present()

def main():
    app = SimpleAdwApp()
    return app.run()

if __name__ == "__main__":
    main()
