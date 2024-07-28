import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk

class TriplePaneApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.TriplePane', flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        window = Adw.ApplicationWindow(application=self)
        style_manager = Adw.StyleManager.get_default()

        # Define CSS styles for different screen sizes (customize as needed)
        large_screen_css = """
        #outer_view {
            min-sidebar-width: 470px;
            max-sidebar-width: 780px;
            sidebar-width-fraction: 0.47;
        }
        #inner_view {
            max-sidebar-width: 260px;
            sidebar-width-fraction: 0.38;
        }
        """

        tablet_css = """
        #outer_view {
            min-sidebar-width: 0px; /* Collapse completely on tablets */
            sidebar-width-fraction: 0;
        }
        #inner_view {
            max-sidebar-width: 200px; /* Adjust for tablet size */
            sidebar-width-fraction: 0.4;
        }
        """

        # Load default (large screen) CSS initially
        style_manager.set_from_string(large_screen_css)

        # Create the layout (same as before)
        outer_view = Adw.NavigationSplitView(name='outer_view')
        inner_view = Adw.NavigationSplitView(name='inner_view')
        # ... (rest of the layout setup)

        # Breakpoint logic (with CSS updates)
        breakpoint1 = Adw.Breakpoint.new(1280, Adw.BreakpointKind.MAX_WIDTH)
        breakpoint1.connect('activate', lambda bp: style_manager.set_from_string(large_screen_css))

        breakpoint2 = Adw.Breakpoint.new(768, Adw.BreakpointKind.MAX_WIDTH)
        breakpoint2.connect('activate', lambda bp: style_manager.set_from_string(tablet_css))

        # Add a default breakpoint for smaller screens (if needed)
        breakpoint3 = Adw.Breakpoint.new(0, Adw.BreakpointKind.MIN_WIDTH)
        breakpoint3.connect('activate', lambda bp: style_manager.set_from_string(large_screen_css))  # Revert to default style

        window.add_breakpoint(breakpoint1)
        window.add_breakpoint(breakpoint2)
        window.add_breakpoint(breakpoint3)  # Add the default breakpoint

        window.set_content(outer_view)
        window.present()

if __name__ == '__main__':
    app = TriplePaneApplication()
    app.run()
