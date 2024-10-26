    def add_desktop_shortcut(self, script, script_key, *args):
        """
        Show a dialog with checkboxes to allow the user to select shortcuts for desktop creation.
        
        Args:
            script: The script that contains information about the shortcut.
            script_key: The unique identifier for the script in the script_list.
        """
        # Ensure we're using the updated script path from the script_data
        script_data = self.script_list.get(script_key)
        if not script_data:
            print(f"Error: Script key {script_key} not found in script_list.")
            return

        # Extract the Wine prefix directory associated with this script
        wine_prefix_dir = Path(script_data['script_path']).parent.expanduser().resolve()
        script_path = Path(script_data['script_path']).expanduser().resolve()

        # Fetch the list of charm files only in the specific Wine prefix directory
        charm_files = list(wine_prefix_dir.rglob("*.charm"))

        # If there are no charm files, show a message
        if not charm_files:
            self.show_info_dialog("No Shortcuts", f"No shortcuts are available for desktop creation in {wine_prefix_dir}.")
            return

        # Create a new dialog using Adw.Window
        dialog = Adw.Window(title="Create Desktop Shortcuts")
        dialog.set_transient_for(self.window)
        dialog.set_modal(True)
        dialog.set_default_size(400, -1)  # Set a reasonable default width
        
        # Create the main content box using Adw.ToolbarView for proper header bar integration
        toolbar_view = Adw.ToolbarView()
        
        # Create and set up the header bar
        header_bar = Adw.HeaderBar()
        toolbar_view.add_top_bar(header_bar)
        
        # Add cancel button to header bar
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda btn: dialog.destroy())
        header_bar.pack_start(cancel_button)
        
        # Add create button to header bar
        create_button = Gtk.Button(label="Create")
        create_button.add_css_class("suggested-action")
        header_bar.pack_end(create_button)
        
        # Create the main content area using Adw.PreferencesPage
        content = Adw.PreferencesPage()
        
        # Create a group for shortcuts
        shortcuts_group = Adw.PreferencesGroup()
        shortcuts_group.set_title(f"Select shortcuts for {wine_prefix_dir.name}")
        content.add(shortcuts_group)
        
        # A dictionary to store the checkboxes and corresponding charm files
        checkbox_dict = {}

        # Create an Adw.PreferencesGroup for the checkboxes
        for charm_file in charm_files:
            # Create a row for each shortcut
            row = Adw.ActionRow()
            
            # Get the icon and title information from the charm file
            icon_title_widget = self.create_icon_title_widget(charm_file)
            
            # Extract the icon and label from the icon_title_widget
            # Assuming icon_title_widget is a Gtk.Box containing an icon and label
            icon = None
            title = charm_file.stem  # Default to filename stem
            
            for child in icon_title_widget:
                if isinstance(child, Gtk.Image):
                    icon = child
                elif isinstance(child, Gtk.Label):
                    title = child.get_text()
            
            # Set the title and icon for the row
            row.set_title(title)
            if icon:
                row.add_prefix(icon)
            
            # Create a checkbox for each shortcut
            checkbox = Gtk.CheckButton()
            row.add_prefix(checkbox)
            
            # Store the checkbox and associated file in the dictionary
            checkbox_dict[checkbox] = charm_file
            
            shortcuts_group.add(row)

        # Create a group for category selection
        category_group = Adw.PreferencesGroup()
        category_group.set_title("Category")
        content.add(category_group)

        # Categories list
        categories = [
            "AudioVideo", "Audio", "Video", "Development", "Education",
            "Game", "Graphics", "Network", "Office", "Science",
            "Settings", "System", "Utility"
        ]
        
        # Create a ComboRow for category selection
        category_row = Adw.ComboRow()
        category_row.set_model(Gtk.StringList.new(categories))
        category_row.set_selected(categories.index("Game"))  # Set default to "Game"
        category_group.add(category_row)

        # Create a scrolled window to contain the content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(content)
        scrolled.set_vexpand(True)
        
        # Set up the content in the toolbar view
        toolbar_view.set_content(scrolled)
        
        # Connect the create button click handler
        create_button.connect(
            "clicked",
            lambda btn: self.on_add_desktop_shortcut_response_new(
                dialog, checkbox_dict, category_row, categories
            )
        )
        
        # Set the content and present the dialog
        dialog.set_content(toolbar_view)
        dialog.present()

    def on_add_desktop_shortcut_response_new(self, dialog, checkbox_dict, category_row, categories):
        """
        Handle the response from the create desktop shortcut dialog using modern Adw widgets.
        
        Args:
            dialog: The Adw.Window instance.
            checkbox_dict: Dictionary mapping checkboxes to charm files.
            category_row: The Adw.ComboRow widget for selecting the category.
            categories: List of available categories.
        """
        # Get the selected category from the combo row
        selected_index = category_row.get_selected()
        selected_category = categories[selected_index]

        # Iterate through the checkboxes and create shortcuts for selected files
        for checkbox, charm_file in checkbox_dict.items():
            if checkbox.get_active():  # Check if the checkbox is selected
                try:
                    # Load the script data to create the desktop shortcut
                    script_key = self.get_script_key_from_shortcut(charm_file)
                    script_data = self.script_list.get(script_key)

                    if not script_data:
                        print(f"Error: Script data for {charm_file} not found.")
                        continue

                    progname = script_data.get('progname', '')
                    script_path = Path(script_data['script_path']).expanduser().resolve()
                    wineprefix = Path(script_data['script_path']).parent.expanduser().resolve()
                    icon_name = script_path.stem + ".png"
                    icon_dir = script_path.parent
                    icon_path = icon_dir / icon_name

                    # Create the desktop entry using the existing method
                    self.create_desktop_entry(progname, script_path, icon_path, wineprefix, selected_category)
                    print(f"Desktop shortcut created for: {charm_file}")

                except Exception as e:
                    print(f"Error creating desktop shortcut for {charm_file}: {e}")

        # Notify the user of successful shortcut creation
        self.show_info_dialog("Shortcut Created", "Desktop shortcuts created successfully.")
        
        # Close the dialog
        dialog.destroy()

