import gi
import sys
import os

gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk, Gio, GLib, Gdk

class MyApp(Adw.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            application_id="org.example.myapp",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
            **kwargs
        )
        self.connect('activate', self.on_activate)
        self.connect('open', self.on_open)

        self.add_main_option(
            "test",
            ord("t"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Command line test",
            None,
        )

        self.set_option_context_parameter_string("FILE")
        self.set_option_context_summary("  FILE is The video file to load")
        self.set_option_context_description("where FILE is The video file to load")

    def on_activate(self, app):
        self.win = Gtk.ApplicationWindow(application=app)
        self.win.set_title("File Opener")
        self.win.set_default_size(600, 400)

        # Create a ScrolledWindow
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Create a TextView to display file contents
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)  # Make the text view read-only
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)

        # Add the TextView to the ScrolledWindow
        self.scrolled_window.set_child(self.text_view)

        # Set the ScrolledWindow as the main content of the window
        self.win.set_child(self.scrolled_window)

        self.win.present()

        # Handle files passed via sys.argv
        self.handle_sys_argv()

    def on_open_file(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Please choose a file",
            transient_for=self.win,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Open", Gtk.ResponseType.OK,
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            print(f"File selected: {dialog.get_filename()}")
            self.handle_file(dialog.get_filename())
        elif response == Gtk.ResponseType.CANCEL:
            print("No file selected")
        
        dialog.close()

    def on_open(self, app, files, n_files, hint):
        for file in files:
            self.handle_file(file.get_path())

    def handle_sys_argv(self):
        if len(sys.argv) > 1:
            for file in sys.argv[1:]:
                print(f"Handling file from sys.argv: {file}")
                self.handle_file(file)

    def handle_file(self, file_path):
        file_path = os.path.abspath(file_path)  # Convert to absolute path
        print(f"Handling file: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"Error: File not found: {file_path}")
            return
        
        with open(file_path, 'r') as file:
            file_content = file.read()
        
        # Display the file content in the TextView
        buffer = self.text_view.get_buffer()
        buffer.set_text(file_content)

if __name__ == "__main__":
    app = MyApp()
    app.run()
