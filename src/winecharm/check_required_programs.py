#!/usr/bin/env python3

import gi
import threading
import subprocess
import os
import shutil
import time
import yaml
from pathlib import Path
from threading import Lock

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gio, Gtk, Adw

def check_required_programs(self):
    self.print_method_name()
    #if shutil.which("flatpak-spawn"):
    #    return []
        
    # List of supported terminals
    terminal_options = [
        'ptyxis',
        'gnome-terminal',
        'konsole',
        'xfce4-terminal',
        'wcterm'
    ]
    
    # Base required programs
    required_programs = [
        'exiftool',
        'wine',
        'winetricks',
        'wrestool',
        'icotool',
        'pgrep',
        'xdg-open'
    ]
    
    # Check if at least one terminal is available
    terminal_found = any(shutil.which(term) for term in terminal_options)
    if not terminal_found:
        # If no terminal is found, add "terminal-emulator" as a missing requirement
        missing_programs = [prog for prog in required_programs if not shutil.which(prog)]
        missing_programs.append("terminal-emulator")
        return missing_programs
        
    return [prog for prog in required_programs if not shutil.which(prog)]

def show_missing_programs_dialog(self, missing_programs):
    self.print_method_name()
    if not missing_programs:
        return
        
    message_parts = []
    
    # Handle terminal emulator message
    if "terminal-emulator" in missing_programs:
        message_parts.append(
            "Missing required terminal emulator.\nPlease install one of the following:\n"
            "• ptyxis\n"
            "• gnome-terminal\n"
            "• konsole\n"
            "• xfce4-terminal"
        )
        # Remove terminal-emulator from the list for other missing programs
        other_missing = [prog for prog in missing_programs if prog != "terminal-emulator"]
        if other_missing:
            message_parts.append("\nOther missing required programs:\n" + 
                                "\n".join(f"• {prog}" for prog in other_missing))
    else:
        message_parts.append("The following required programs are missing:\n" +
                            "\n".join(f"• {prog}" for prog in missing_programs))
        
    message = "\n".join(message_parts)
    
    GLib.timeout_add_seconds(1, self.show_info_dialog,"Missing Programs", message)

    

