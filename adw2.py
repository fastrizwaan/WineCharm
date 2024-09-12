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
        self.window = Adw.ApplicationWindow(application=app)
        self.window.set_title("Adw Dialog Example")
        self.window.set_default_size(400, 300)

        # Create a button to show the error dialog
        button = Gtk.Button(label="Show Error Dialog")
        button.connect("clicked", self.on_button_clicked)

        # Set up the window's child widget
        self.window.set_content(button)
        self.window.present()

    def on_button_clicked(self, button):
        self.show_error_dialog("Error", "Something went wrong!")

    def show_error_dialog(self, title, message):
        # Create Adw.MessageDialog
        dialog = Adw.MessageDialog.new(self.window)
        dialog.set_heading(title)
        dialog.set_body(message)

        # Add a close button
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.connect("response", lambda d, r: d.destroy())

        dialog.present()

if __name__ == "__main__":
    app = MyApp()
    app.run()
