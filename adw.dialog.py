import gi

# Import necessary GTK and Adwaita versions
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class CustomWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("AdwDialog with Text Entry Example")
        self.set_default_size(600, 400)

        # Main layout box
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.set_content(box)

        # Button to open the dialog
        open_dialog_button = Gtk.Button(label="Open Dialog")
        open_dialog_button.connect("clicked", self.on_open_dialog)
        box.append(open_dialog_button)

    def on_open_dialog(self, button):
        # Create the AdwDialog instance
        dialog = Adw.Dialog()
        dialog.set_title("Enter Options")
        dialog.set_content_width(400)
        dialog.set_content_height(200)

        # Create a content box for the dialog
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)

        # Create an entry field with pre-filled text
        entry = Gtk.Entry()
        entry.set_text("-opengl")
        content_box.append(entry)

        # Set the content box as the dialog's child
        dialog.set_child(content_box)

        # Add action buttons to the content
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ok_button = Gtk.Button(label="_OK")
        ok_button.add_css_class("suggested-action")
        ok_button.connect("clicked", lambda btn: self.on_dialog_ok_clicked(dialog, entry))
        cancel_button = Gtk.Button(label="_Cancel")
        cancel_button.connect("clicked", lambda btn: dialog.close())

        button_box.append(ok_button)
        button_box.append(cancel_button)
        content_box.append(button_box)

        # Present the dialog properly using adw_dialog_present()
        dialog.present(self)

    def on_dialog_ok_clicked(self, dialog, entry):
        # Print the entered text when "OK" is pressed
        print("Entered text:", entry.get_text())
        dialog.close()

class MyApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.example.AdwDialogExample")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        # Create and present the main application window
        win = CustomWindow(application=app)
        win.present()

# Run the application
app = MyApp()
app.run()
