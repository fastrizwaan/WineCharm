        ### TEMP
        def get_directory_size(path):
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
            return total_size

        def on_backup_confirmation_response(dialog, response_id, script, script_key, backup_path):
            if response_id == "continue":
                dialog.close()
                # Start the backup process in a separate thread
                threading.Thread(target=self.create_bottle, args=(script, script_key, backup_path)).start()

        total_size = get_directory_size(wineprefix)
        if total_size > 3 * 1024 * 1024 * 1024:  # 3GB in bytes
            # Show confirmation dialog
        dialog = Adw.MessageDialog.new(
            self.window,
            "Large Game Directory",
            "The game directory is larger than 3GB. Do you want to continue?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("continue", "Continue")
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        #dialog.connect("response", perform_backup_steps, script, script_key, backup_path)
            dialog.connect("response", self.on_backup_confirmation_response, script, script_key, backup_path)
        dialog.present()
        else:
            # If the directory size is less than 3GB, proceed with the backup
            self.create_bottle(script, script_key, backup_path)




            #########################/CREATE BOTTLE
################# get directory size
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




 


        # Step 1: Disconnect the UI elements and initialize the spinner
        
        self.show_processing_spinner("Bottling...")
        # Step 2: Define the steps for the backup process
        

        # Calculate the directory size in bytes
        directory_size = self.get_directory_size(exe_path)

        # Convert directory size to GB for comparison
        directory_size_gb = directory_size / (1024 ** 3)  # 1 GB is 1024^3 bytes
        print("----------------------------------------------------------")
        print(directory_size)
        print(directory_size_gb)

        if directory_size_gb > 3:
            
            print("Size Greater than 3GB")





    def show_create_bottle_dialog(self, script, script_key, button):

        # Step 0: Check if the executable file exists
        # Extract exe_file from script_data
        script_data = self.extract_yaml_info(script_key)
        if not script_data:
            raise Exception("Script data not found.")

        exe_file = self.expand_and_resolve_path(script_data['exe_file'])
        #exe_file = Path(str(exe_file).replace("%USERNAME%", user))
        exe_path = exe_file.parent
        
        # If exe_not found i.e., game_dir is not accessble due to unmounted directory
        if not exe_file.exists():
            GLib.timeout_add_seconds(0.5, self.show_info_dialog, "Exe Not Found", f"Not Mounted or Deleted?\n{exe_file}")
            return
            
        # Step 1: Suggest the backup file name
        default_backup_name = f"{script.stem} prefix backup.tar.zst"

        # Create a Gtk.FileDialog instance for saving the file
        file_dialog = Gtk.FileDialog.new()

        # Set the initial file name using set_initial_name() method
        file_dialog.set_initial_name(default_backup_name)

        # Open the dialog asynchronously to select the save location
        file_dialog.save(self.window, None, self.on_create_bottle_dialog_response, script, script_key)

        print("FileDialog presented for saving the backup.")