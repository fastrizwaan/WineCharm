import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

def response_cb(dialog, response_id, self):
    # Handle the response
    print(f"Response: {response_id}")
    dialog.close()

def show_replace_file_dialog(parent, filename, self):
    dialog = Adw.MessageDialog.new(parent, "Replace File?", None)

    dialog.format_body("A file named “%s” already exists. Do you want to replace it?" % filename)

    dialog.add_responses(
        "cancel", "_Cancel",
        "replace", "_Replace",
    )

    dialog.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    dialog.connect("response", response_cb, self)

    dialog.present()

# Example usage
if __name__ == "__main__":
    import sys
    app = Gtk.Application(application_id='com.example.GtkApplication')
    app.connect('activate', lambda app: show_replace_file_dialog(None, "example.txt", app))
    app.run(sys.argv)
