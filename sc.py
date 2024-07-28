import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio

class TriplePaneApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.TriplePane', flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        window = Adw.ApplicationWindow(application=self)
        window.set_default_size(800, 600)
        window.set_size_request(800, 600)

        outer_view = Adw.NavigationSplitView()
        outer_view.set_min_sidebar_width(200)
        outer_view.set_max_sidebar_width(300)
        outer_view.set_sidebar_width_fraction(0.33)

        inner_view = Adw.NavigationSplitView()
        inner_view.set_min_sidebar_width(200)
        inner_view.set_max_sidebar_width(300)
        inner_view.set_sidebar_width_fraction(0.33)

        # Stack to manage different views
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack.set_transition_duration(500)

        # Sidebar
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_label = Gtk.Label(label="Sidebar")
        show_middle_pane_button = Gtk.Button(label="Show Middle Pane")
        show_middle_pane_button.connect("clicked", lambda _: stack.set_visible_child_name("middle_pane"))
        show_content_button = Gtk.Button(label="Show Content")
        show_content_button.connect("clicked", lambda _: stack.set_visible_child_name("content"))
        show_sidebar_button = Gtk.Button(label="Show Sidebar")
        show_sidebar_button.connect("clicked", lambda _: stack.set_visible_child_name("sidebar"))
        sidebar_box.append(sidebar_label)
        sidebar_box.append(show_middle_pane_button)
        sidebar_box.append(show_content_button)
        sidebar_box.append(show_sidebar_button)
        stack.add_named(sidebar_box, "sidebar")

        # Middle Pane
        middle_pane_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        middle_pane_label = Gtk.Label(label="Middle Pane")
        show_sidebar_button = Gtk.Button(label="Show Sidebar")
        show_sidebar_button.connect("clicked", lambda _: stack.set_visible_child_name("sidebar"))
        show_content_button = Gtk.Button(label="Show Content")
        show_content_button.connect("clicked", lambda _: stack.set_visible_child_name("content"))
        show_middle_pane_button = Gtk.Button(label="Show Middle Pane")
        show_middle_pane_button.connect("clicked", lambda _: stack.set_visible_child_name("middle_pane"))
        middle_pane_box.append(middle_pane_label)
        middle_pane_box.append(show_sidebar_button)
        middle_pane_box.append(show_content_button)
        middle_pane_box.append(show_middle_pane_button)
        stack.add_named(middle_pane_box, "middle_pane")

        # Content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_label = Gtk.Label(label="Content")
        show_sidebar_button = Gtk.Button(label="Show Sidebar")
        show_sidebar_button.connect("clicked", lambda _: stack.set_visible_child_name("sidebar"))
        show_middle_pane_button = Gtk.Button(label="Show Middle Pane")
        show_middle_pane_button.connect("clicked", lambda _: stack.set_visible_child_name("middle_pane"))
        show_content_button = Gtk.Button(label="Show Content")
        show_content_button.connect("clicked", lambda _: stack.set_visible_child_name("content"))
        content_box.append(content_label)
        content_box.append(show_sidebar_button)
        content_box.append(show_middle_pane_button)
        content_box.append(show_content_button)
        stack.add_named(content_box, "content")

        window.set_content(stack)
        stack.set_visible_child_name("sidebar")

        breakpoint_condition1 = Adw.BreakpointCondition.parse("max-width: 860px")
        breakpoint1 = Adw.Breakpoint.new(breakpoint_condition1)
        breakpoint1.add_setter(outer_view, 'collapsed', True)
        breakpoint1.add_setter(inner_view, 'sidebar-width-fraction', 0.33)

        breakpoint_condition2 = Adw.BreakpointCondition.parse("max-width: 500px")
        breakpoint2 = Adw.Breakpoint.new(breakpoint_condition2)
        breakpoint2.add_setter(outer_view, 'collapsed', True)
        breakpoint2.add_setter(inner_view, 'collapsed', True)

        window.add_breakpoint(breakpoint1)
        window.add_breakpoint(breakpoint2)

        window.present()

if __name__ == '__main__':
    app = TriplePaneApplication()
    app.run()
