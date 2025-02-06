fix open

    def initialize_app(self):
        
        if not hasattr(self, 'window') or not self.window:
            # Call the startup code
            self.create_main_window()
            self.create_script_list()
            GLib.idle_add(self.window.present)
            #self.check_running_processes_and_update_buttons()
            
            missing_programs = self.check_required_programs()
            if missing_programs:
                self.show_missing_programs_dialog(missing_programs)
            else:
                if not self.default_template.exists():
                    self.initialize_template(self.default_template, self.on_template_initialized)
                else:
                    self.set_dynamic_variables()

    def process_cli_file(self, file_path):
        print(f"Processing CLI file: {file_path}")
        abs_file_path = str(Path(file_path).resolve())
        print(f"Resolved absolute CLI file path: {abs_file_path}")

        try:
            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return
            self.create_yaml_file(abs_file_path, None)

        except Exception as e:
            print(f"Error processing file: {e}")
        finally:
            if self.initializing_template:
                pass  # Keep showing spinner
            else:
                GLib.timeout_add_seconds(1, self.hide_processing_spinner)
                
            GLib.timeout_add_seconds(0.5, self.create_script_list)


    def on_open(self, app, files, *args):
        # Ensure the application is fully initialized
        print("1. on_open method called")
        
        # Initialize the application if it hasn't been already
        self.initialize_app()
        print("2. self.initialize_app initiated")
        
        # Present the window as soon as possible
        GLib.idle_add(self.window.present)
        print("3. self.window.present() Complete")
        
        # Check if the command_line_file exists and is either .exe or .msi
        if self.command_line_file:
            print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
            print(self.command_line_file)
            
            file_extension = Path(self.command_line_file).suffix.lower()
            if file_extension in ['.exe', '.msi']:
                print(f"Processing file: {self.command_line_file} (Valid extension: {file_extension})")
                print("Trying to process file inside on template initialized")

                GLib.idle_add(self.show_processing_spinner)
                self.process_cli_file(self.command_line_file)
            else:
                print(f"Invalid file type: {file_extension}. Only .exe or .msi files are allowed.")
                GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Invalid File Type", "Only .exe and .msi files are supported.")
                self.command_line_file = None
                return False
        self.check_running_processes_on_startup()


    def process_cli_file_in_thread(self, file_path):
        try:
            print(f"Processing CLI file in thread: {file_path}")
            abs_file_path = str(Path(file_path).resolve())
            print(f"Resolved absolute CLI file path: {abs_file_path}")

            if not Path(abs_file_path).exists():
                print(f"File does not exist: {abs_file_path}")
                return

            # Perform the heavy processing here
            self.create_yaml_file(abs_file_path, None)

            # Schedule GUI updates in the main thread
            #GLib.idle_add(self.update_gui_after_file_processing, abs_file_path)

        except Exception as e:
            print(f"Error processing file in background: {e}")
        finally:
            if self.initializing_template:
                pass  # Keep showing spinner
            else:
                GLib.idle_add(self.hide_processing_spinner)
            
            GLib.timeout_add_seconds(0.5, self.create_script_list)


    def process_cli_file_later(self, file_path):
        # Use GLib.idle_add to ensure this runs after the main loop starts
        GLib.idle_add(self.show_processing_spinner)
        GLib.idle_add(self.process_cli_file, file_path)


    def on_startup(self, app):
        self.create_main_window()
        # Clear or initialize the script list
        self.script_list = {}
        self.load_script_list()
        self.create_script_list()
        #self.check_running_processes_and_update_buttons()
        
        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        else:
            if not self.default_template.exists():
                self.initialize_template(self.default_template, self.on_template_initialized)
            else:
                self.set_dynamic_variables()
                # Process the command-line file if the template already exists
                if self.command_line_file:
                    print("Template exists. Processing command-line file after UI initialization.")
                    self.process_cli_file_later(self.command_line_file)
        # After loading scripts and building the UI, check for running processes
        self.check_running_processes_on_startup()

        # Start fetching runner URLs asynchronously
        threading.Thread(target=self.maybe_fetch_runner_urls).start()


    def remove_symlinks_and_create_directories(self, wineprefix):
        """
        Remove all symbolic link files in the specified directory (drive_c/users/{user}) and 
        create normal directories in their place.
        
        Args:
            wineprefix: The path to the Wine prefix where symbolic links will be removed.
        """
        userhome = os.getenv("USER") or os.getenv("USERNAME")
        if not userhome:
            print("Error: Unable to determine the current user from environment.")
            return
        
        user_dir = Path(wineprefix) / "drive_c" / "users"
        print(f"Removing symlinks from: {user_dir}")

        # Iterate through all symbolic links in the user's directory
        for item in user_dir.rglob("*"):
            if item.is_symlink():
                try:
                    # Remove the symlink and create a directory in its place
                    item.unlink()
                    item.mkdir(parents=True, exist_ok=True)
                    print(f"Replaced symlink with directory: {item}")
                except Exception as e:
                    print(f"Error processing {item}: {e}")

    def initialize_template(self, template_dir, callback):
        self.create_required_directories()
        self.initializing_template = True
        if self.open_button_handler_id is not None:
            self.open_button.disconnect(self.open_button_handler_id)

        self.spinner = Gtk.Spinner()
        self.spinner.start()
        self.open_button_box.append(self.spinner)

        self.set_open_button_label("Initializing...")
        self.set_open_button_icon_visible(False)  # Hide the open-folder icon
        self.search_button.set_sensitive(False)  # Disable the search button
        self.view_toggle_button.set_sensitive(False)
        self.ensure_directory_exists(template_dir)

        steps = [
            ("Initializing wineprefix", f"WINEPREFIX='{template_dir}' WINEDEBUG=-all wineboot -i"),
            ("Replace symbolic links with directories", lambda: self.remove_symlinks_and_create_directories(template_dir)),
            ("Installing corefonts",    f"WINEPREFIX='{template_dir}' winetricks -q corefonts"),
            ("Installing openal",       f"WINEPREFIX='{template_dir}' winetricks -q openal"),
            #("Installing vkd3d",        f"WINEPREFIX='{template_dir}' winetricks -q vkd3d"),
            #("Installing dxvk",         f"WINEPREFIX='{template_dir}' winetricks -q dxvk"),
            #("Installing vcrun2005",    f"WINEPREFIX='{template_dir}' winetricks -q vcrun2005"),
            #("Installing vcrun2019",    f"WINEPREFIX='{template_dir}' winetricks -q vcrun2019"),
        ]

        def initialize():
            for step_text, command in steps:
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    if callable(command):
                        # If the command is a callable, invoke it directly
                        command()
                    else:
                        # Run the command in the shell
                        subprocess.run(command, shell=True, check=True)
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except subprocess.CalledProcessError as e:
                    print(f"Error initializing template: {e}")
                    break
            GLib.idle_add(callback)

        threading.Thread(target=initialize).start()

    def on_template_initialized(self):
        print("Template initialization complete.")
        self.initializing_template = False
        
        # Ensure the spinner is stopped after initialization
        self.hide_processing_spinner()
        
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.search_button.set_sensitive(True)
        self.view_toggle_button.set_sensitive(True)
        
        if self.open_button_handler_id is not None:
            self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)

        print("Template initialization completed and UI updated.")
        self.show_initializing_step("Initialization Complete!")
        self.mark_step_as_done("Initialization Complete!")
        self.hide_processing_spinner()
        GLib.timeout_add_seconds(0.5, self.create_script_list)
        
        # Check if there's a command-line file to process after initialization
        if self.command_line_file:
            print("Processing command-line file after template initialization")
            self.process_cli_file_later(self.command_line_file)
            self.command_line_file = None  # Reset after processing

        #
        self.set_dynamic_variables()