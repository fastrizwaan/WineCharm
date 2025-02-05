process_cli_file

    def on_startup(self, app):
        self.create_main_window()
        self.script_list = {}
        self.load_script_list()

        self.single_prefix = False
        self.load_settings()
        print(f"Single Prefix: {self.single_prefix}")

        def initialize_template_if_needed(template_path, arch, single_prefix_dir=None):
            if not template_path.exists():
                self.set_open_button_label("Initializing")
                print(f"Initializing {arch} template...")
                self.initialize_template(template_path, self.on_template_initialized, arch=arch)
                return True
            elif self.single_prefix and single_prefix_dir and not single_prefix_dir.exists():
                print(f"Copying {arch} template to single prefix...")
                self.copy_template(single_prefix_dir)
            return False

        # Corrected conditions: Only check current arch when single_prefix is False
        arch_templates = []
        if self.single_prefix:
            # Check both templates if single_prefix is enabled
            arch_templates = [
                (True, self.default_template_win32, 'win32', self.single_prefix_dir_win32),
                (True, self.default_template_win64, 'win64', self.single_prefix_dir_win64)
            ]
        else:
            # Check only the current arch's template
            if self.arch == 'win32':
                arch_templates = [
                    (True, self.default_template_win32, 'win32', self.single_prefix_dir_win32)
                ]
            else:
                arch_templates = [
                    (True, self.default_template_win64, 'win64', self.single_prefix_dir_win64)
                ]

        needs_initialization = False
        for check, template, arch, single_dir in arch_templates:
            if check:
                needs_initialization |= initialize_template_if_needed(template, arch, single_dir)

        if not needs_initialization:
            self.create_script_list()
            self.set_dynamic_variables()
            if self.command_line_file:
                print("Processing command-line file after UI initialization")
                self.process_cli_file_later(self.command_line_file)

        missing_programs = self.check_required_programs()
        if missing_programs:
            self.show_missing_programs_dialog(missing_programs)
        
        self.check_running_processes_on_startup()
        threading.Thread(target=self.maybe_fetch_runner_urls).start()

    def start_socket_server(self):
        def server_thread():
            socket_dir = self.SOCKET_FILE.parent

            # Ensure the directory for the socket file exists
            self.create_required_directories()

            # Remove existing socket file if it exists
            if self.SOCKET_FILE.exists():
                self.SOCKET_FILE.unlink()

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(self.SOCKET_FILE))
                server.listen()

                while True:
                    conn, _ = server.accept()
                    with conn:
                        message = conn.recv(1024).decode()
                        if message:
                            command_parts = message.split("||")
                            command = command_parts[0]

                            if command == "show_dialog":
                                title = command_parts[1]
                                body = command_parts[2]
                                # Call show_info_dialog in the main thread using GLib.idle_add
                                GLib.timeout_add_seconds(0.5, self.show_info_dialog, title, body)
                            elif command == "process_file":
                                file_path = command_parts[1]
                                GLib.idle_add(self.process_cli_file, file_path)

        # Run the server in a separate thread
        threading.Thread(target=server_thread, daemon=True).start()


    def initialize_app(self):
        if not hasattr(self, 'window') or not self.window:
            # Call the startup code
            self.create_main_window()
            self.create_script_list()
            #self.check_running_processes_and_update_buttons()
            
            missing_programs = self.check_required_programs()
            if missing_programs:
                self.show_missing_programs_dialog(missing_programs)
            else:
                if not self.default_template.exists() and not self.single_prefix:
                    self.initialize_template(self.default_template, self.on_template_initialized)
                if not self.default_template.exists() and self.single_prefix:
                    self.initialize_template(self.default_template, self.on_template_initialized)
                    self.copy_template(self.single_prefixes_dir)
                elif self.default_template.exists() and not self.single_prefixes_dir.exists() and self.single_prefix:
                    self.copy_template(self.single_prefixes_dir)
                else:
                    self.set_dynamic_variables()

    def process_cli_file_later(self, file_path):
        # Use GLib.idle_add to ensure this runs after the main loop starts
        GLib.idle_add(self.show_processing_spinner, "hello world")
        GLib.idle_add(self.process_cli_file, file_path)

    def process_cli_file_in_thread(self, file_path):
        """Process CLI file in a background thread with step-based progress"""
        self.stop_processing = False
        
        GLib.idle_add(lambda: self.show_processing_spinner("Processing..."))
        steps = [
            ("Creating configuration", lambda: self.create_yaml_file(str(file_path), None)),
        ]
        try:
            # Show progress bar and initialize UI
            self.total_steps = len(steps)
            
            # Process each step
            for index, (step_text, step_func) in enumerate(steps, 1):
                if self.stop_processing:
                    return
                    
                # Update progress bar
                GLib.idle_add(lambda i=index: self.progress_bar.set_fraction((i-1)/self.total_steps))
                #GLib.idle_add(lambda t=step_text: self.set_open_button_label(t))
                
                try:
                    # Execute the step
                    step_func()
                    # Update progress after step completion
                    GLib.idle_add(lambda i=index: self.progress_bar.set_fraction(i/self.total_steps))
                except Exception as e:
                    print(f"Error during step '{step_text}': {e}")
                    GLib.idle_add(lambda: self.show_info_dialog("Error", f"An error occurred during '{step_text}': {e}"))
                    return

        except Exception as e:
            print(f"Error during file processing: {e}")
            GLib.idle_add(lambda: self.show_info_dialog("Error", f"Processing failed: {e}"))
        finally:
            # Clean up and update UI
            def cleanup():
                if not self.initializing_template:
                    self.hide_processing_spinner()
                self.create_script_list()
                return False
            
            GLib.timeout_add(500, cleanup)

    def on_template_initialized(self, arch=None):
        print(f"Template initialization complete for {arch if arch else 'default'} architecture.")
        self.initializing_template = False
        
        # Update architecture setting if we were initializing a specific arch
        if arch:
            self.arch = arch
            # Set template path based on architecture
            self.template = self.default_template_win32 if arch == 'win32' \
                else self.default_template_win64
            self.save_settings()
        
        # Ensure the spinner is stopped after initialization
        self.hide_processing_spinner()
        
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.search_button.set_sensitive(True)
        self.view_toggle_button.set_sensitive(True)
        
        # Disabled Cancel/Interruption
        #if self.open_button_handler_id is not None:
        #    self.open_button_handler_id = self.open_button.connect("clicked", self.on_open_button_clicked)

        print("Template initialization completed and UI updated.")
        self.show_initializing_step("Initialization Complete!")
        self.mark_step_as_done("Initialization Complete!")
        
        # If not called from settings create script list else go to settings
        if not self.called_from_settings:
            GLib.timeout_add_seconds(0.5, self.create_script_list)
        
        if self.called_from_settings:
            self.on_template_restore_completed()
            
        # Check if there's a command-line file to process after initialization
        if self.command_line_file:
            print("Processing command-line file after template initialization")
            self.process_cli_file_later(self.command_line_file)
            self.command_line_file = None  # Reset after processing

        self.set_dynamic_variables()
        self.reconnect_open_button()
        self.called_from_settings = False

    def on_open_file_dialog_response(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = file.get_path()
                print("- - - - - - - - - - - - - -self.show_processing_spinner")
                self.monitoring_active = False
                
                # If there's already a processing thread, stop it
                if hasattr(self, 'processing_thread') and self.processing_thread and self.processing_thread.is_alive():
                    self.stop_processing = True
                    self.processing_thread.join(timeout=0.5)  # Wait briefly for thread to stop
                    self.hide_processing_spinner()
                    self.set_open_button_label("Open")
                    self.set_open_button_icon_visible(True)
                    return

                # Show processing spinner
                self.show_processing_spinner("Processing...")
                
                # Start a new background thread to process the file
                self.stop_processing = False
                self.processing_thread = threading.Thread(target=self.process_cli_file_in_thread, args=(file_path,))
                self.processing_thread.start()

        except GLib.Error as e:
            if e.domain != 'gtk-dialog-error-quark' or e.code != 2:
                print(f"An error occurred: {e}")
        finally:
            self.window.set_visible(True)
            self.monitoring_active = True

    def process_cli_file_in_thread(self, file_path):
        """
        Process CLI file in a background thread with proper Path handling
        """
        try:
            print(f"Processing CLI file in thread: {file_path}")
            file_path = Path(file_path) if not isinstance(file_path, Path) else file_path
            abs_file_path = file_path.resolve()
            print(f"Resolved absolute CLI file path: {abs_file_path}")

            if not abs_file_path.exists():
                print(f"File does not exist: {abs_file_path}")
                return

            # Perform the heavy processing here
            self.create_yaml_file(str(abs_file_path), None)

        except Exception as e:
            print(f"Error processing file in background: {e}")
        finally:
            if self.initializing_template:
                pass  # Keep showing spinner
            else:
                GLib.idle_add(self.hide_processing_spinner)
            
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


def parse_args():
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(description="WineCharm GUI application or headless mode for .charm files")
    parser.add_argument('file', nargs='?', help="Path to the .exe, .msi, or .charm file")
    return parser.parse_args()
    
def main():
    args = parse_args()

    # Create an instance of WineCharmApp
    app = WineCharmApp()

    # If a file is provided, handle it appropriately
    if args.file:
        file_path = Path(args.file).expanduser().resolve()
        file_extension = file_path.suffix.lower()

        # If it's a .charm file, launch it without GUI
        if file_extension == '.charm':
            try:
                # Load the .charm file data
                with open(file_path, 'r', encoding='utf-8') as file:
                    script_data = yaml.safe_load(file)

                exe_file = script_data.get("exe_file")
                if not exe_file:
                    print("Error: No executable file defined in the .charm script.")
                    sys.exit(1)

                # Prepare to launch the executable
                exe_path = Path(exe_file).expanduser().resolve()
                if not exe_path.exists():
                    print(f"Error: Executable '{exe_path}' not found.")
                    sys.exit(1)

                # Extract additional environment and arguments
                
                # if .charm file has script_path use it
                wineprefix_path_candidate = script_data.get('script_path')

                if not wineprefix_path_candidate:  # script_path not found
                    # if .charm file has wineprefix in it, then use it
                    wineprefix_path_candidate = script_data.get('wineprefix')
                    if not wineprefix_path_candidate:  # if wineprefix not found
                        wineprefix_path_candidate = file_path  # use the current .charm file's path

                # Resolve the final wineprefix path
                wineprefix = Path(wineprefix_path_candidate).parent.expanduser().resolve()
                
                env_vars = script_data.get("env_vars", "").strip()
                script_args = script_data.get("args", "").strip()
                runner = script_data.get("runner", "wine")

                # Resolve runner path
                if runner:
                    runner = Path(runner).expanduser().resolve()
                    runner_dir = str(runner.parent.expanduser().resolve())
                    path_env = f'export PATH="{runner_dir}:$PATH"'
                else:
                    runner = "wine"
                    runner_dir = ""  # Or set a specific default if required
                    path_env = ""

                # Prepare the command safely using shlex for quoting
                exe_parent = shlex.quote(str(exe_path.parent.resolve()))
                wineprefix = shlex.quote(str(wineprefix))
                runner = shlex.quote(str(runner))

                # Construct the command parts
                command_parts = []

                # Add path to runner if it exists
                if path_env:
                    command_parts.append(f"{path_env}")

                # Change to the executable's directory
                command_parts.append(f"cd {exe_parent}")

                # Add environment variables if present
                if env_vars:
                    command_parts.append(f"{env_vars}")

                # Add wineprefix and runner
                command_parts.append(f"WINEPREFIX={wineprefix} {runner} {shlex.quote(str(exe_path))}")

                # Add script arguments if present
                if script_args:
                    command_parts.append(f"{script_args}")

                # Join all the command parts
                command = " && ".join(command_parts)

                print(f"Executing: {command}")
                subprocess.run(command, shell=True)

                # Exit after headless execution to ensure no GUI elements are opened
                sys.exit(0)

            except Exception as e:
                print(f"Error: Unable to launch the .charm script: {e}")
                sys.exit(1)

        # For .exe or .msi files, validate the file type and continue with GUI mode
        elif file_extension in ['.exe', '.msi']:
            if app.SOCKET_FILE.exists():
                try:
                    # Send the file to an existing running instance
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.connect(str(app.SOCKET_FILE))
                        message = f"process_file||{args.file}"
                        client.sendall(message.encode())
                        print(f"Sent file path to existing instance: {args.file}")
                    return
                except ConnectionRefusedError:
                    print("No existing instance found, starting a new one.")

            # If no existing instance is running, proceed with normal startup and processing
            app.command_line_file = args.file

        else:
            # Invalid file type, print error and handle accordingly
            print(f"Invalid file type: {file_extension}. Only .exe, .msi, or .charm files are allowed.")
            
            # If no instance is running, start WineCharmApp and show the error dialog directly
            if not app.SOCKET_FILE.exists():
                app.start_socket_server()
                GLib.timeout_add_seconds(1.5, app.show_info_dialog, "Invalid File Type", f"Only .exe, .msi, or .charm files are allowed. You provided: {file_extension}")
                app.run(sys.argv)

                # Clean up the socket file
                if app.SOCKET_FILE.exists():
                    app.SOCKET_FILE.unlink()
            else:
                # If an instance is running, send the error message to the running instance
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.connect(str(app.SOCKET_FILE))
                        message = f"show_dialog||Invalid file type: {file_extension}||Only .exe, .msi, or .charm files are allowed."
                        client.sendall(message.encode())
                    return
                except ConnectionRefusedError:
                    print("No existing instance found, starting a new one.")
            
            # Return early to skip further processing
            return

    # Start the socket server and run the application (GUI mode)
    app.start_socket_server()
    app.run(sys.argv)

    # Clean up the socket file
    if app.SOCKET_FILE.exists():
        app.SOCKET_FILE.unlink()

if __name__ == "__main__":
    main()

