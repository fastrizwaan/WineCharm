    # Get directory size method
    def get_directory_size(self, path):
        if not path.exists():
            print(f"The provided path '{path}' does not exist.")
            return 0

        try:
            total_size = sum(f.stat().st_size for f in path.glob('**/*') if f.is_file())
            return total_size
        except Exception as e:
            print(f"Error calculating directory size: {e}")
            return 0

    def create_bottle(self, script, script_key, backup_path):
        """
        Backs up the Wine prefix in a stepwise manner, indicating progress via spinner and label updates.
        """
        wineprefix = Path(script).parent

        # Step 1: Disconnect the UI elements and initialize the spinner
        
        self.show_processing_spinner("Bottling...")
        #self.set_open_button_icon_visible(False)
        #self.disconnect_open_button()

        # Get the user's home directory to replace with `~`
        usershome = os.path.expanduser('~')

        # Get the current username from the environment
        user = os.getenv("USER") or os.getenv("USERNAME")
        if not user:
            raise Exception("Unable to determine the current username from the environment.")
        
        find_replace_pairs = {usershome: '~', f'\'{usershome}': '`\~'}
        find_replace_media_username = {f'/media/{user}/': '/media/%USERNAME%/'}
        restore_media_username = {'/media/%USERNAME%/': f'/media/{user}/'}

        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = self.expand_and_resolve_path(script_data['exe_file'])
        #exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_path = exe_file.parent
        exe_name = exe_file.name

        runner = self.expand_and_resolve_path(script_data['runner'])

        # If runner is inside the script
        if runner:
            print(f"RUNNER FOUND = {runner}")
            # Check if the runner is inside runners_dir
            is_runner_inside_prefix = runner.is_relative_to(self.runners_dir)
            print("===========================================================")
            if is_runner_inside_prefix:
                print("RUNNER INSIDE PREFIX")
                runner_dir = runner.parent.parent
                runner_dir_exe = runner_dir / "bin/wine"

                target_runner_dir = wineprefix / "Runner" 
                target_runner_exe = target_runner_dir / runner_dir.name / "bin/wine"
            else:
                target_runner_exe = runner
                runner_dir_exe = runner
                print("RUNNER IS NOT INSIDE PREFIX")

        # Check if game directory is inside the prefix
        is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

        print("==========================================================")
        # exe_file path replacement should use existing exe_file if it's already inside prefix
        if is_exe_inside_prefix:
            game_dir = exe_path
            game_dir_exe = exe_file
            print(f"""
            exe_file is inside wineprefix:
            game_dir = {game_dir}
            game_dir_exe = {game_dir_exe}
            """)
        else:
            game_dir = wineprefix / "drive_c" / "GAMEDIR"
            game_dir_exe = game_dir / exe_path.name / exe_name
            print(f"""
            exe_file is OUTSIDE wineprefix:
            game_dir = {game_dir}
            game_dir_exe = {game_dir_exe}
            """)
        # Step 2: Define the steps for the backup process

        def perform_backup_steps():
            steps = [
                (f"Replace \"{usershome}\" with '~' in script files", lambda: self.replace_strings_in_specific_files(wineprefix, find_replace_pairs)),
                ("Reverting user-specific .reg changes", lambda: self.reverse_process_reg_files(wineprefix)),
                (f"Replace \"/media/{user}\" with '/media/%USERNAME%' in script files", lambda: self.replace_strings_in_specific_files(wineprefix, find_replace_media_username)),
                ("Updating exe_file Path in Script", lambda: self.update_exe_file_path_in_script(script, self.replace_home_with_tilde_in_path(str(game_dir_exe)))),
                ("Updating runner Path in Script", lambda: self.update_runner_path_in_script(script, self.replace_home_with_tilde_in_path(str(target_runner_exe)))),
                ("Creating Bottle archive", lambda: self.create_bottle_archive(script_key, wineprefix, backup_path)),
                ("Re-applying user-specific .reg changes", lambda: self.process_reg_files(wineprefix)),
                (f"Revert %USERNAME% with \"{user}\" in script files", lambda: self.replace_strings_in_specific_files(wineprefix, restore_media_username)),
                ("Reverting exe_file Path in Script", lambda: self.update_exe_file_path_in_script(script, self.replace_home_with_tilde_in_path(str(exe_file)))),
                ("Reverting runner Path in Script", lambda: self.update_runner_path_in_script(script, self.replace_home_with_tilde_in_path(str(runner)))),
            ]
            for step_text, step_func in steps:
                GLib.idle_add(self.show_initializing_step, step_text)
                try:
                    # Execute the step
                    step_func()
                    GLib.idle_add(self.mark_step_as_done, step_text)
                except Exception as e:
                    print(f"Error during step '{step_text}': {e}")
                    GLib.idle_add(self.show_info_dialog, "Backup Failed", f"Error during '{step_text}': {str(e)}")
                    break

            # Step 3: Once all steps are completed, reset the UI
            GLib.idle_add(self.on_create_bottle_completed, script_key, backup_path)

        # Step 4: Run the backup steps in a separate thread to keep the UI responsive
        threading.Thread(target=perform_backup_steps).start()

    def on_create_bottle_completed(self, script_key, backup_path):
        """
        Called when the backup process is complete. Updates the UI accordingly.
        """
        # Reset the button label and remove the spinner
        self.set_open_button_label("Open")
        self.set_open_button_icon_visible(True)
        self.reconnect_open_button()
        self.hide_processing_spinner()

        # Notify the user that the backup is complete
        self.show_info_dialog("Bottle Created", f"{backup_path}")
        print("Bottle creating process completed successfully.")

        # Iterate over all script buttons and update the UI based on `is_clicked_row`
        for key, data in self.script_ui_data.items():
            row_button = data['row']
            row_play_button = data['play_button']
            row_options_button = data['options_button']
        self.show_options_for_script(self.script_ui_data[script_key], row_button, script_key)

    def on_backup_confirmation_response(self, dialog, response_id, script, script_key):
        if response_id == "continue":
            dialog.close()
            self.show_create_bottle_dialog(script, script_key)
        else:
            return

    def create_bottle_selected(self, script, script_key, button):

        # Step 1: Check if the executable file exists
        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        wineprefix = Path(script).parent
        exe_file = self.expand_and_resolve_path(script_data['exe_file'])
        #exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_path = exe_file.parent
        exe_name = exe_file.name
        game_dir = wineprefix / "drive_c" / "GAMEDIR"
        game_dir_exe = game_dir / exe_path.name / exe_name

        # Check if the game directory is in DO_NOT_BUNDLE_FROM directories
        if str(exe_path) in self.get_do_not_bundle_directories():
            msg1 = "Cannot copy the selected game directory"
            msg2 = "Please move the files to a different directory to create a bundle."
            self.show_info_dialog(msg1, msg2)
            return

        # If exe_not found i.e., game_dir is not accessble due to unmounted directory
        if not exe_file.exists():
            GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Exe Not Found", f"Not Mounted or Deleted?\n{exe_file}")
            return

        # Step 2: Check for size if > 3GB ask the user:
        # Calculate the directory size in bytes
        directory_size = self.get_directory_size(exe_path)

        # Convert directory size to GB for comparison
        directory_size_gb = directory_size / (1024 ** 3)  # 1 GB is 1024^3 bytes
        directory_size_gb = round(directory_size_gb, 2)  # round to two decimal places

        print("----------------------------------------------------------")
        print(directory_size)
        print(directory_size_gb)

        if directory_size_gb > 3:
            print("Size Greater than 3GB")
            # Show confirmation dialog
            dialog = Adw.MessageDialog.new(
            self.window,
            "Large Game Directory",
            f"The game directory size is {directory_size_gb}GB. Do you want to continue?"
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("continue", "Continue")
            dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        #dialog.connect("response", perform_backup_steps, script, script_key, backup_path)
            dialog.connect("response", self.on_backup_confirmation_response, script, script_key)
            dialog.present()
            print("----------------------------------------------------------")
        else:
            self.show_create_bottle_dialog(script, script_key)

    def show_create_bottle_dialog(self, script, script_key):
            # Step 3: Suggest the backup file name
            default_backup_name = f"{script.stem}-bottle.tar.zst"

            # Create a Gtk.FileDialog instance for saving the file
            file_dialog = Gtk.FileDialog.new()

            # Set the initial file name using set_initial_name() method
            file_dialog.set_initial_name(default_backup_name)

            # Open the dialog asynchronously to select the save location
            file_dialog.save(self.window, None, self.on_create_bottle_dialog_response, script, script_key)

            print("FileDialog presented for saving the backup.")

    def on_create_bottle_dialog_response(self, dialog, result, script, script_key):
        try:
            # Retrieve the selected file (save location) using save_finish()
            backup_file = dialog.save_finish(result)
            if backup_file:
                self.on_back_button_clicked(None)
                self.flowbox.remove_all()
                backup_path = backup_file.get_path()  # Get the backup file path
                print(f"Backup will be saved to: {backup_path}")

                # Start the backup process in a separate thread
                threading.Thread(target=self.create_bottle, args=(script, script_key, backup_path)).start()

        except GLib.Error as e:
            # Handle any errors, such as cancellation
            print(f"An error occurred: {e}")

    def create_bottle_archive(self, script_key, wineprefix, backup_path):

        # Get the current username from the environment
        current_username = os.getenv("USER") or os.getenv("USERNAME")
        if not current_username:
            raise Exception("Unable to determine the current username from the environment.")

        # Escape the wineprefix name for the transform pattern to handle special characters
        #escaped_prefix_name = re.escape(wineprefix.name)

        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = Path(script_data['exe_file']).expanduser().resolve()
        exe_file = Path(str(exe_file).replace("%USERNAME%", current_username))
        exe_path = exe_file.parent

        # Check if game directory is inside the prefix
        is_exe_inside_prefix = exe_path.is_relative_to(wineprefix)

        tar_game_dir_name = exe_path.name
        tar_game_dir_path = exe_path.parent
        # Prepare the transform pattern to rename the user's directory to '%USERNAME%'
        # The pattern must be expanded to include anything under the user's folder
        #transform_pattern = rf"s|{escaped_prefix_name}/drive_c/users/{current_username}|{escaped_prefix_name}/drive_c/users/%USERNAME%|g"
        #transform_pattern2 = rf"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g"

        runner = self.expand_and_resolve_path(script_data['runner'])

        # If runner is inside the script
        if runner:
            print(f"RUNNER FOUND = {runner}")
            # Check if the runner is inside runners_dir
            is_runner_inside_prefix = runner.is_relative_to(self.runners_dir)
            print("===========================================================")
            if is_runner_inside_prefix:
                print("RUNNER INSIDE PREFIX")
                runner_dir_path = runner.parent.parent.parent
                runner_dir = runner.parent.parent
                runner_dir_exe = runner_dir / "bin/wine"
                runner_dir_name = runner_dir.name
            else:
                runner_dir_exe = runner
                runner_dir_name = ''
                runner_dir_path = ''
                print("RUNNER IS NOT INSIDE PREFIX")        
        

        # prefix_runners_dir = wineprefix / "Runner"
        # Prepare the tar command with the --transform option based on whether the executable file is located inside the wine prefix or not
        if is_exe_inside_prefix and runner:
            tar_command = [
            'tar',
            '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
            '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",  # Rename the directory and its contents
            '--transform', f"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g",
            '--transform', f"s|^\./{runner_dir_name}|{wineprefix.name}/Runner/{runner_dir_name}|g",
            '-cf', backup_path,
            '-C', str(wineprefix.parent),
            wineprefix.name,
            '-C', str(runner_dir_path),
            rf"./{runner_dir_name}",
            ]
        if is_exe_inside_prefix and not runner:
            tar_command = [
            'tar',
            '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
            '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",  # Rename the directory and its contents
            '--transform', f"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g",
            '-cf', backup_path,
            '-C', str(wineprefix.parent),
            wineprefix.name,
            ]
        elif not is_exe_inside_prefix and runner:
            tar_command = [
                'tar',
                '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
                '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",  # Rename the directory and its contents
                '--transform', f"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g",
                '--transform', f"s|^\./{runner_dir_name}|{wineprefix.name}/Runner/{runner_dir_name}|g",
                '-cf', backup_path,
                '-C', str(wineprefix.parent),
                wineprefix.name,
                '-C', str(tar_game_dir_path),
                rf"./{tar_game_dir_name}",
                '-C', str(runner_dir_path),
                rf"./{runner_dir_name}",
            ]
        elif not is_exe_inside_prefix and not runner:
            tar_command = [
                'tar',
                '-I', 'zstd -T0',  # Use zstd compression with all available CPU cores
                '--transform', f"s|{wineprefix.name}/drive_c/users/{current_username}|{wineprefix.name}/drive_c/users/%USERNAME%|g",  # Rename the directory and its contents
                '--transform', f"s|^\./{tar_game_dir_name}|{wineprefix.name}/drive_c/GAMEDIR/{tar_game_dir_name}|g",
                '-cf', backup_path,
                '-C', str(wineprefix.parent),
                wineprefix.name,
                '-C', str(tar_game_dir_path),
                rf"./{tar_game_dir_name}",
            ]
        else:
            print("no runner not prefix")

        print(f"Running create bottle command: {' '.join(tar_command)}")

        # Execute the tar command
        result = subprocess.run(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            raise Exception(f"Backup failed: {result.stderr}")

        print(f"Backup archive created at {backup_path}")
#########################/CREATE BOTTLE
