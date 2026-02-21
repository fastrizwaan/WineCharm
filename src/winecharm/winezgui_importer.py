#!/usr/bin/env python3

import gi
import threading
import subprocess
import shutil
import shlex
import yaml
from pathlib import Path

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')


from gi.repository import GLib, Gio, Gtk, Adw


def process_winezgui_sh_files(self, action=None, param=None, prompt=None, suppress_no_scripts_dialog=False):
    self.print_method_name()
    """
    Process WineZGUI .sh files to create corresponding .charm files in their prefix directories.
    """
    self.show_processing_spinner(_("Processing WineZGUI Scripts..."))
    
    def process_in_background():
        try:
            if not self.winezgui_prefixes_dir.exists():
                GLib.idle_add(self.show_info_dialog, _("Directory Not Found"), _("WineZGUI prefixes directory not found: %s") % self.winezgui_prefixes_dir)
                return

            # Collect unique prefix directories containing .sh files
            prefix_dirs = set()
            for subdir in self.winezgui_prefixes_dir.iterdir():
                if subdir.is_dir() and list(subdir.glob("*.sh")):
                    prefix_dirs.add(subdir)

            if not prefix_dirs and not suppress_no_scripts_dialog:
                GLib.idle_add(self.show_info_dialog, _("No Scripts Found"), _("No .sh files found in WineZGUI prefixes directory."))
                return

            created_count = 0
            created_charm_files = set()  # Track unique .charm files to avoid duplicates
            for prefix_dir in prefix_dirs:
                if self.stop_processing:
                    break
                charm_files = self.process_sh_files(prefix_dir)
                # Add only new, unique .charm files to the set
                for charm_file in charm_files:
                    if charm_file not in created_charm_files:
                        created_charm_files.add(charm_file)
                        created_count += 1

            if created_count > 0:  # Show dialog only if .charm files were created
                GLib.idle_add(self.show_info_dialog, _("Processing Complete"), _("Created %d .charm files from WineZGUI scripts.") % created_count)

        finally:
            GLib.idle_add(self.hide_processing_spinner)
            GLib.idle_add(self.load_script_list)
    threading.Thread(target=process_in_background, daemon=True).start()
