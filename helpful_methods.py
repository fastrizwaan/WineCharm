        # Regenerate sha256sum if missing
        if exe_file and not sha256sum:
            sha256_hash = hashlib.sha256()
            try:
                with open(exe_file, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                sha256sum = sha256_hash.hexdigest()
                print(f"Warning: sha256sum missing in {exe_file}. Regenerated hash.")
            except FileNotFoundError:
                print(f"Error: {exe_file} not found. Cannot compute sha256sum.")











# update runner for all files

    def update_charm_files_with_new_prefix(self, new_wineprefix, old_wineprefix):
        """
        Update all .charm files within the newly renamed prefix directory to reflect the new prefix path.

        :param new_wineprefix: The new Wine prefix path.
        :param old_wineprefix: The old Wine prefix path.
        """
        # Get the tilde-prefixed versions of the old and new Wine prefixes
        old_wineprefix_tilde = self.replace_home_with_tilde_in_path(str(old_wineprefix))
        new_wineprefix_tilde = self.replace_home_with_tilde_in_path(str(new_wineprefix))

        # Iterate through all .charm files within the new prefix directory
        for charm_file in Path(new_wineprefix).rglob("*.charm"):
            try:
                # Read the content of the .charm file
                with open(charm_file, "r") as file:
                    content = file.read()

                # Replace occurrences of the old prefix path with the new prefix path using tilde
                updated_content = content.replace(old_wineprefix_tilde, new_wineprefix_tilde)

                # Write the updated content back to the .charm file
                with open(charm_file, "w") as file:
                    file.write(updated_content)

                print(f"Updated .charm file: {charm_file}")

            except Exception as e:
                print(f"Error updating .charm file {charm_file}: {e}")


####### Can be used to save script_data runtime.
    def on_change_runner_response(self, dialog, response_id, runner_combo, all_runners, script_key):
        """
        Handle the response when the user selects a runner or cancels the dialog.
        """
        if response_id == "ok":
            selected_index = runner_combo.get_active()
            if selected_index < 0:
                print("No runner selected.")
                dialog.close()
                return

            new_runner_display, new_runner_path = all_runners[selected_index]
            print(f"Selected new runner: {new_runner_display} -> {new_runner_path}")

            # Set to an empty string if System Wine is selected
            new_runner_value = '' if new_runner_display.startswith("System Wine") else new_runner_path
            script_data = self.script_list.get(script_key, {})
            script_data['runner'] = self.replace_home_with_tilde_in_path(new_runner_value)

            script_path = Path(script_data['script_path']).expanduser().resolve()
            try:
                with open(script_path, 'w') as file:
                    yaml.dump(script_data, file, default_flow_style=False, width=1000)
                print(f"Runner for {script_path} updated to {new_runner_display}")
            except Exception as e:
                print(f"Error updating runner: {e}")
        else:
            print("Runner change canceled.")

        dialog.close()
