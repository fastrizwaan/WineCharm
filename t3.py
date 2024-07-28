import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio

class TriplePaneApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.TriplePane', flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        window = Adw.ApplicationWindow(application=self)

        outer_view = Adw.NavigationSplitView()
        outer_view.set_min_sidebar_width(470)
        outer_view.set_max_sidebar_width(780)
        outer_view.set_sidebar_width_fraction(0.47)

        inner_view = Adw.NavigationSplitView()
        inner_view.set_max_sidebar_width(260)
        inner_view.set_sidebar_width_fraction(0.38)

        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.append(Gtk.Label(label="Sidebar"))
        sidebar = Adw.NavigationPage(child=sidebar_box)
        inner_view.set_sidebar(sidebar)

        middle_pane_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        middle_pane_box.append(Gtk.Label(label="Middle Pane"))
        middle_pane = Adw.NavigationPage(child=middle_pane_box)
        inner_view.set_content(middle_pane)

        outer_sidebar = Adw.NavigationPage(child=inner_view)
        outer_view.set_sidebar(outer_sidebar)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.append(Gtk.Label(label="Content"))
        content = Adw.NavigationPage(child=content_box)
        outer_view.set_content(content)

        window.set_content(outer_view)

        breakpoint_condition1 = Adw.BreakpointCondition.parse("max-width: 860px")
        breakpoint1 = Adw.Breakpoint.new(breakpoint_condition1)
        breakpoint1.add_setter(outer_view, 'collapsed', True)
        breakpoint1.add_setter(inner_view, 'sidebar-width-fraction', 0.33)

        breakpoint_condition2 = Adw.BreakpointCondition.parse("max-width: 500px")
        breakpoint2 = Adw.Breakpoint.new(breakpoint_condition2)
        breakpoint2.add_setter(outer_view, 'collapsed', True)
        breakpoint2.add_setter(inner_view, 'sidebar-width-fraction', 0.33)
        breakpoint2.add_setter(inner_view, 'collapsed', True)

        window.add_controller(breakpoint1)
        window.add_controller(breakpoint2)

        window.present()

if __name__ == '__main__':
    app = TriplePaneApplication()
    app.run()
