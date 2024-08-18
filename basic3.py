import gi
import sys

gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk, Gio, GLib

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

        open_button = Gtk.Button(label="Open File")
        open_button.connect("clicked", self.on_open_file)

        self.win.set_child(open_button)
        self.win.show()

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
        print(f"Handling file: {file_path}")
        # Here you would add logic to handle the file (e.g., open and process it)

if __name__ == "__main__":
    app = MyApp()
    app.run()
