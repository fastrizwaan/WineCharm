    def show_options_for_script(self, ui_state, row, script_key):
        """
        Display the options for a specific script.
        
        Args:
            ui_state (dict): Information about the script stored in script_data_two.
            row (Gtk.Widget): The row UI element where the options will be displayed.
            script_key (str): The unique key for the script (should be sha256sum or a unique identifier).
        """
        # Get the script path from ui_state
        script = Path(ui_state['script_path'])  # Get the script path from ui_state

        # Ensure the search button is toggled off and the search entry is cleared
        self.search_button.set_active(False)
        self.search_button.set_visible(True)
        self.search_entry.set_text("")
        self.main_frame.set_child(None)

        # Create a scrolled window for script options
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)

        self.options_flowbox = Gtk.FlowBox()
        self.options_flowbox.set_valign(Gtk.Align.START)
        self.options_flowbox.set_halign(Gtk.Align.FILL)
        self.options_flowbox.set_max_children_per_line(4)
        self.options_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.options_flowbox.set_vexpand(True)
        self.options_flowbox.set_hexpand(True)
        scrolled_window.set_child(self.options_flowbox)

        self.main_frame.set_child(scrolled_window)

        # Initialize or replace self.options_listbox with the current self.options_flowbox
        self.options_listbox = self.options_flowbox

        # Store script options as instance variable for filtering
        self.script_options = [
            ("Show log", "document-open-symbolic", self.show_log_file),
            ("Open Terminal", "utilities-terminal-symbolic", self.open_terminal),
            ("Install dxvk vkd3d", "emblem-system-symbolic", self.install_dxvk_vkd3d),
            ("Open Filemanager", "system-file-manager-symbolic", self.open_filemanager),
            ("Edit Script File", "text-editor-symbolic", self.open_script_file),
            ("Delete Wineprefix", "user-trash-symbolic", self.show_delete_wineprefix_confirmation),
            ("Delete Shortcut", "edit-delete-symbolic", self.show_delete_shortcut_confirmation),
            ("Wine Arguments", "preferences-system-symbolic", self.show_wine_arguments_entry),
            ("Rename Shortcut", "text-editor-symbolic", self.show_rename_shortcut_entry),
            ("Change Icon", "applications-graphics-symbolic", self.show_change_icon_dialog),
            ("Backup Prefix", "document-save-symbolic", self.show_backup_prefix_dialog),
            ("Create Bottle", "package-x-generic-symbolic", self.create_bottle_selected),
            ("Save Wine User Dirs", "document-save-symbolic", self.show_save_user_dirs_dialog),
            ("Load Wine User Dirs", "document-revert-symbolic", self.show_load_user_dirs_dialog),
            ("Reset Shortcut", "view-refresh-symbolic", self.reset_shortcut_confirmation),
            ("Add Desktop Shortcut", "user-bookmarks-symbolic", self.add_desktop_shortcut),
            ("Remove Desktop Shortcut", "action-unavailable-symbolic", self.remove_desktop_shortcut),
            ("Import Game Directory", "folder-download-symbolic", self.import_game_directory),
            ("Run Other Exe", "system-run-symbolic", self.run_other_exe),
            ("Environment Variables", "preferences-system-symbolic", self.set_environment_variables),
            ("Change Runner", "preferences-desktop-apps-symbolic", self.change_runner),
            ("Rename Prefix Directory", "folder-visiting-symbolic", self.rename_prefix_directory),
            ("Wine Config (winecfg)", "preferences-system-symbolic", self.wine_config),
            ("Registry Editor (regedit)", "dialog-password-symbolic", self.wine_registry_editor)

        ]

        # Initial population of options
        self.populate_script_options()

        # Use `script` as a Path object for `create_icon_title_widget`
        self.headerbar.set_title_widget(self.create_icon_title_widget(script))
     
        # Hide unnecessary UI components
        self.menu_button.set_visible(False)
        self.view_toggle_button.set_visible(False)

        if self.back_button.get_parent() is None:
            self.headerbar.pack_start(self.back_button)
        self.back_button.set_visible(True)

        self.open_button.set_visible(False)
        self.replace_open_button_with_launch(ui_state, row, script_key)
        self.update_execute_button_icon(ui_state)
        self.selected_row = None


    def populate_script_options(self, filter_text=""):
        # Clear existing options using GTK4's method
        while child := self.settings_flowbox.get_first_child():
            self.settings_flowbox.remove(child)

        # Add filtered options    
        for label, icon_name, callback in self.script_options:
            option_button = Gtk.Button()
            option_button.set_size_request(150, 36)
            option_button.add_css_class("flat")
            option_button.add_css_class("normal-font")

            option_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            option_button.set_child(option_hbox)

            option_icon = Gtk.Image.new_from_icon_name(icon_name)
            option_label = Gtk.Label(label=label)
            option_label.set_xalign(0)
            option_label.set_hexpand(True)
            option_label.set_ellipsize(Pango.EllipsizeMode.END)
            option_hbox.append(option_icon)
            option_hbox.append(option_label)


            # Enable or disable the "Show log" button based on log file existence and size
            if label == "Show log":
                log_file_path = script.parent / f"{script.stem}.log"
                if not log_file_path.exists() or log_file_path.stat().st_size == 0:
                    option_button.set_sensitive(False)

            # Ensure the correct button (`btn`) is passed to the callback
            option_button.connect(
                "clicked",
                lambda btn, cb=callback, sc=script, sk=script_key: self.callback_wrapper(cb, sc, sk, btn)
            )
            self.options_flowbox.append(option_button)

    # Modify the existing search handlers to work with script options
    def on_search_entry_changed(self, entry):
        search_term = entry.get_text().lower()
        # Check if we're in settings view
        if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
            self.populate_settings_options(search_term)
        elif hasattr(self, 'options_flowbox') and self.options_flowbox.get_parent() is not None:
            self.populate_script_options(search_term)            
        else:
            self.filter_script_list(search_term)


##################### clear up the settings search
    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.search_button.set_active(False)
            # Check if we're in settings view
            if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
                self.search_entry.set_text("")  # Clear the search entry
                self.populate_settings_options()  # Reset settings options
            elif hasattr(self, 'options_flowbox') and self.options_flowbox.get_parent() is not None:
                self.search_entry.set_text("")  # Clear the search entry
                self.populate_script_options()  # Reset settings options
            else:
                self.filter_script_list("")  # Reset the script list

    def on_search_button_clicked(self, button):
        if self.search_active:
            self.vbox.remove(self.search_entry_box)
            self.vbox.prepend(self.open_button)
            self.search_active = False
            # Check if we're in settings view
            if hasattr(self, 'settings_flowbox') and self.settings_flowbox.get_parent() is not None:
                self.search_entry.set_text("")  # Clear the search entry
                self.populate_settings_options()  # Reset settings options
            elif hasattr(self, 'options_flowbox') and self.options_flowbox.get_parent() is not None:
                self.search_entry.set_text("")  # Clear the search entry
                self.populate_script_options()  # Reset settings options
            else:
                self.filter_script_list("")  # Reset the script list
        else:
            self.vbox.remove(self.open_button)
            self.vbox.prepend(self.search_entry_box)
            self.search_entry.grab_focus()
            self.search_active = True
