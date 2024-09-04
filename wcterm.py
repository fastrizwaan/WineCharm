#!/usr/bin/env python3

import sys
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import GObject, GLib, Vte, Gtk

GObject.type_register(Vte.Terminal)

class WCTerm(object):

    def __init__(self, command=None):
        # Create the main window
        self._window = Gtk.Window()
        self._window.set_title("WCTerm")
        self._window.set_default_size(800, 480)
        self._window.connect("delete-event", self.stop)

        # Create a ScrolledWindow
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Create the terminal widget
        self._terminal = Vte.Terminal()
        self._terminal.set_scroll_on_keystroke(True)
        self._terminal.set_scroll_on_output(False)

        self._terminal.connect("child-exited", self._child_exited_cb)

        # Add the terminal to the scrolled window
        scrolled_window.add(self._terminal)

        # Add the scrolled window to the main window
        self._window.add(scrolled_window)

        # Show all widgets
        self._window.show_all()

        # Spawn the initial command or shell
        self._run_command(command)

    def _run_command(self, command):
        if command is None:
            command = ['/bin/bash']  # Default to bash if no command is provided
        else:
            # Run the command inside a shell to handle complex commands like "ls; read"
            command = ['/bin/bash', '-c', command]
            
        self._terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            None,  # Working directory
            command,  # Command to run
            None,  # Environment
            GLib.SpawnFlags.DEFAULT,  # Use DEFAULT instead of DO_NOT_REAP_CHILD
            None,  # Child setup function
            None,  # User data
            -1,  # Child process ID
            None,  # Cancellable
            None   # Callback
        )

    def _child_exited_cb(self, term, status, user_data=None):
        Gtk.main_quit()

    def start(self):
        Gtk.main()

    def stop(self, widget, event, user_data=None):
        Gtk.main_quit()

if __name__ == '__main__':
    # Get the command from the command line arguments
    command = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    try:
        app = WCTerm(command=command)
        app.start()
    except KeyboardInterrupt:
        pass

