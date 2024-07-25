#!/usr/bin/env python3

import gi
import time
import threading

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

class SimpleAdwApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.SimpleAdwApp')
        self.window = None
        self.status_bar = None

    def do_activate(self):
        if not self.window:
            self.window = Adw.ApplicationWindow(application=self)
            self.window.set_title("Simple Adw App")
            self.window.set_default_size(400, 200)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.window.set_content(vbox)

            button = Gtk.Button(label="Show Message")
            button.connect("clicked", self.on_button_clicked)
            vbox.append(button)

            self.status_bar = Adw.StatusPage()
            vbox.append(self.status_bar)

        self.window.present()

    def on_button_clicked(self, button):
        self.show_status_message("This is a status message!")

    def show_status_message(self, message):
        self.status_bar.set_description(message)
        self.status_bar.set_visible(True)
        GLib.timeout_add_seconds(10, self.hide_status_message)

    def hide_status_message(self):
        self.status_bar.set_visible(False)
        return False

def main():
    app = SimpleAdwApp()
    return app.run(None)

if __name__ == "__main__":
    main()
