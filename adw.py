#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class MyApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.example.myapp", flags=0)
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        # Create a new window
        window = Adw.ApplicationWindow(application=app)
        window.set_title("Simple GTK4 Adw App")
        window.set_default_size(400, 300)

        # Create a button to show dialog
        button = Gtk.Button(label="Show Dialog")
        button.connect("clicked", self.on_button_clicked)

        # Set up the window's child widget
        window.set_content(button)
        window.present()

    def on_button_clicked(self, button):
        # Create and show the dialog
        dialog = Adw.MessageDialog.new(button.get_ancestor(Adw.ApplicationWindow))
        dialog.set_heading("Hi")       # Set the title
        dialog.set_body("Hello from the dialog!")  # Set the message body
        dialog.add_response("close", "_Close")
        dialog.set_default_response("close")
        dialog.connect("response", self.on_dialog_response)
        dialog.present()

    def on_dialog_response(self, dialog, response):
        # Close the dialog when a response is received
        dialog.close()

if __name__ == "__main__":
    app = MyApp()
    app.run()
