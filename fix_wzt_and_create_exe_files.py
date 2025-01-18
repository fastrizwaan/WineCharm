################################################################################################################################
    def process_sh_files(self, directory, skip_ui_update=False):
        """
        Process all .sh files and convert them to .charm files.
        Args:
            directory: Directory to process
            skip_ui_update: If True, skips updating the UI during processing
        """
        sh_files = self.find_sh_files(directory)
        created_charm_files = False

        for sh_file in sh_files:
            variables = self.extract_infofile_path_from_sh(sh_file)
            exe_file = variables.get('EXE_FILE', '')
            progname = variables.get('PROGNAME', '')
            sha256sum = variables.get('CHECKSUM', '')

            # Rest of the existing logic for processing files...
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

            info_file_path = variables.get('INFOFILE')
            if info_file_path:
                info_file_path = os.path.join(os.path.dirname(sh_file), info_file_path)
                if os.path.exists(info_file_path):
                    try:
                        info_data = self.parse_info_file(info_file_path)
                        runner = info_data.get('Runner', '')

                        env_var_file_path = os.path.join(os.path.dirname(sh_file), "environment-variable.yml")
                        cmdline_file_path = os.path.join(os.path.dirname(sh_file), "cmdline.yml")

                        env_vars = self.load_and_fix_yaml(env_var_file_path, "environment-variable.yml")
                        args = self.load_and_fix_yaml(cmdline_file_path, "cmdline.yml")

                        yml_path = sh_file.replace('.sh', '.charm')
                        self.create_charm_file({
                            'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
                            'script_path': self.replace_home_with_tilde_in_path(str(yml_path)),
                            'wineprefix': self.replace_home_with_tilde_in_path(str(directory)),
                            'progname': progname,
                            'sha256sum': sha256sum,
                            'runner': runner,
                            'args': args,
                            'env_vars': env_vars
                        }, yml_path, skip_ui_update)

                        self.new_scripts.add(Path(yml_path).stem)
                        print(f"Created {yml_path}")
                        created_charm_files = True

                    except Exception as e:
                        print(f"Error parsing INFOFILE {info_file_path}: {e}")
                else:
                    print(f"INFOFILE {info_file_path} not found")
            else:
                print(f"No INFOFILE found in {sh_file}")

        if not created_charm_files:
            print(f"No .charm files created. Proceeding to create scripts for .lnk and .exe files in {directory}")
            self.create_scripts_for_lnk_files(directory, skip_ui_update)
            print(f"Scripts created for .lnk files in {directory}")

            self.create_scripts_for_exe_files(directory, skip_ui_update)
            print(f"Scripts created for .exe files in {directory}")

    def create_yaml_file(self, exe_path, prefix_dir=None, use_exe_name=False, skip_ui_update=False):
        """
        Create a YAML file for the given executable.
        Args:
            exe_path: Path to the executable
            prefix_dir: Optional prefix directory
            use_exe_name: Whether to use exe name for the yaml file
            skip_ui_update: If True, skips updating the UI
        """
        self.create_required_directories()
        exe_file = Path(exe_path).resolve()
        exe_name = exe_file.stem
        exe_no_space = exe_name.replace(" ", "_")

        # Calculate SHA256 hash
        sha256_hash = hashlib.sha256()
        with open(exe_file, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        sha256sum = sha256_hash.hexdigest()[:10]

        # Rest of the existing yaml file creation logic...
        script_key = sha256_hash.hexdigest()
        if script_key in self.script_list:
            existing_script_path = Path(self.script_list[script_key]['script_path']).expanduser().resolve()
            if existing_script_path.exists():
                existing_script_path.unlink()
                print(f"Removed existing charm file: {existing_script_path}")

        if prefix_dir is None:
            prefix_dir = self.prefixes_dir / f"{exe_no_space}-{sha256sum}"
            if not prefix_dir.exists():
                if self.template.exists():
                    self.copy_template(prefix_dir)
                else:
                    self.ensure_directory_exists(prefix_dir)

        # Add the data to script_list
        yaml_data = {
            'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
            'script_path': self.replace_home_with_tilde_in_path(str(yaml_file_path)),
            'wineprefix': self.replace_home_with_tilde_in_path(str(prefix_dir)),
            'progname': progname,
            'args': "",
            'sha256sum': sha256_hash.hexdigest(),
            'runner': "",
            'wine_debug': "WINEDEBUG=fixme-all DXVK_LOG_LEVEL=none",
            'env_vars': ""
        }

        # Only update the UI if skip_ui_update is False
        if not skip_ui_update:
            self.script_list[script_key] = yaml_data
            row = self.create_script_row(script_key, yaml_data)
            if row:
                self.flowbox.prepend(row)
            GLib.idle_add(self.create_script_list)
        else:
            # Still update the script_list but don't update UI
            self.script_list[script_key] = yaml_data

        print(f"Created new charm file: {yaml_file_path} with script_key {script_key}")

    def create_scripts_for_exe_files(self, wineprefix, skip_ui_update=False):
        """
        Create scripts for exe files in the wineprefix.
        Args:
            wineprefix: The Wine prefix directory
            skip_ui_update: If True, skips updating the UI
        """
        exe_files = self.find_exe_files(wineprefix)
        for exe_file in exe_files:
            self.create_yaml_file(exe_file, wineprefix, use_exe_name=True, skip_ui_update=skip_ui_update)
        
        # Only update the UI if skip_ui_update is False
        if not skip_ui_update:
            GLib.timeout_add_seconds(0.5, self.create_script_list)

    def get_wzt_restore_steps(self, file_path):
        """
        Return the list of steps for restoring a WZT backup.
        Modified to pass skip_ui_update=True during restoration.
        """
        return [
            ("Checking Disk Space", lambda: self.check_disk_space_and_show_step(file_path)),
            ("Extracting WZT Backup File", lambda: self.extract_backup(file_path)),
            ("Performing User Related Replacements", lambda: self.perform_replacements(self.extract_prefix_dir(file_path))),
            ("Processing WineZGUI Script Files", lambda: self.process_sh_files(self.extract_prefix_dir(file_path), skip_ui_update=True)),
            ("Search LNK Files and Append to Found List", lambda: self.find_and_save_lnk_files(self.extract_prefix_dir(file_path))),
            ("Replacing Symbolic Links with Directories", lambda: self.remove_symlinks_and_create_directories(self.extract_prefix_dir(file_path))),
            ("Renaming and Merging User Directories", lambda: self.rename_and_merge_user_directories(self.extract_prefix_dir(file_path))),
        ]

################################################################################################################3
    def process_sh_files(self, directory, skip_ui_update=False):
        """
        Process all .sh files and convert them to .charm files.
        Args:
            directory: Directory to process
            skip_ui_update: If True, skips updating the UI during processing
        """
        sh_files = self.find_sh_files(directory)
        created_charm_files = False

        for sh_file in sh_files:
            variables = self.extract_infofile_path_from_sh(sh_file)
            exe_file = variables.get('EXE_FILE', '')
            progname = variables.get('PROGNAME', '')
            sha256sum = variables.get('CHECKSUM', '')

            # Rest of the existing logic for processing files...
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

            info_file_path = variables.get('INFOFILE')
            if info_file_path:
                info_file_path = os.path.join(os.path.dirname(sh_file), info_file_path)
                if os.path.exists(info_file_path):
                    try:
                        info_data = self.parse_info_file(info_file_path)
                        runner = info_data.get('Runner', '')

                        env_var_file_path = os.path.join(os.path.dirname(sh_file), "environment-variable.yml")
                        cmdline_file_path = os.path.join(os.path.dirname(sh_file), "cmdline.yml")

                        env_vars = self.load_and_fix_yaml(env_var_file_path, "environment-variable.yml")
                        args = self.load_and_fix_yaml(cmdline_file_path, "cmdline.yml")

                        yml_path = sh_file.replace('.sh', '.charm')
                        self.create_charm_file({
                            'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
                            'script_path': self.replace_home_with_tilde_in_path(str(yml_path)),
                            'wineprefix': self.replace_home_with_tilde_in_path(str(directory)),
                            'progname': progname,
                            'sha256sum': sha256sum,
                            'runner': runner,
                            'args': args,
                            'env_vars': env_vars
                        }, yml_path)

                        self.new_scripts.add(Path(yml_path).stem)
                        print(f"Created {yml_path}")
                        created_charm_files = True

                    except Exception as e:
                        print(f"Error parsing INFOFILE {info_file_path}: {e}")
                else:
                    print(f"INFOFILE {info_file_path} not found")
            else:
                print(f"No INFOFILE found in {sh_file}")

        if not created_charm_files:
            print(f"No .charm files created. Proceeding to create scripts for .lnk and .exe files in {directory}")
            self.create_scripts_for_lnk_files(directory, skip_ui_update)
            print(f"Scripts created for .lnk files in {directory}")

            self.create_scripts_for_exe_files(directory, skip_ui_update)
            print(f"Scripts created for .exe files in {directory}")


    def create_yaml_file_for_process_sh(self, exe_path, prefix_dir=None, use_exe_name=False, skip_ui_update=False):
        """
        Create a YAML file for the given executable.
        Args:
            exe_path: Path to the executable
            prefix_dir: Optional prefix directory
            use_exe_name: Whether to use exe name for the yaml file
            skip_ui_update: If True, skips updating the UI
        """
        self.create_required_directories()
        exe_file = Path(exe_path).resolve()
        exe_name = exe_file.stem
        exe_no_space = exe_name.replace(" ", "_")

        # Calculate SHA256 hash
        sha256_hash = hashlib.sha256()
        with open(exe_file, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        sha256sum = sha256_hash.hexdigest()[:10]

        # Rest of the existing yaml file creation logic...
        script_key = sha256_hash.hexdigest()
        if script_key in self.script_list:
            existing_script_path = Path(self.script_list[script_key]['script_path']).expanduser().resolve()
            if existing_script_path.exists():
                existing_script_path.unlink()
                print(f"Removed existing charm file: {existing_script_path}")

        if prefix_dir is None:
            prefix_dir = self.prefixes_dir / f"{exe_no_space}-{sha256sum}"
            if not prefix_dir.exists():
                if self.template.exists():
                    self.copy_template(prefix_dir)
                else:
                    self.ensure_directory_exists(prefix_dir)

        wineprefix_name = prefix_dir.name

        # Get product name and determine program name
        product_cmd = ['exiftool', shlex.quote(str(exe_file))]
        product_output = self.run_command(" ".join(product_cmd))
        if product_output is None:
            productname = exe_no_space
        else:
            productname_match = re.search(r'Product Name\s+:\s+(.+)', product_output)
            productname = productname_match.group(1).strip() if productname_match else exe_no_space

        if use_exe_name:
            progname = exe_name
        else:
            progname = self.determine_progname(productname, exe_no_space, exe_name)

        yaml_file_path = prefix_dir / f"{exe_no_space if use_exe_name else progname.replace(' ', '_')}.charm"

        # Add the data to script_list
        yaml_data = {
            'exe_file': self.replace_home_with_tilde_in_path(str(exe_file)),
            'script_path': self.replace_home_with_tilde_in_path(str(yaml_file_path)),
            'wineprefix': self.replace_home_with_tilde_in_path(str(prefix_dir)),
            'progname': progname,
            'args': "",
            'sha256sum': sha256_hash.hexdigest(),
            'runner': "",
            'wine_debug': "WINEDEBUG=fixme-all DXVK_LOG_LEVEL=none",
            'env_vars': ""
        }

        # Write the YAML file
        with open(yaml_file_path, 'w') as yaml_file:
            yaml.dump(yaml_data, yaml_file, default_flow_style=False, width=1000)

        # Only update the UI if skip_ui_update is False
        if not skip_ui_update:
            self.script_list[script_key] = yaml_data
            row = self.create_script_row(script_key, yaml_data)
            if row:
                self.flowbox.prepend(row)
            GLib.idle_add(self.create_script_list)
        else:
            # Still update the script_list but don't update UI
            self.script_list[script_key] = yaml_data

        print(f"Created new charm file: {yaml_file_path} with script_key {script_key}")

    def create_scripts_for_exe_files(self, wineprefix, skip_ui_update=False):
        """
        Create scripts for exe files in the wineprefix.
        Args:
            wineprefix: The Wine prefix directory
            skip_ui_update: If True, skips updating the UI
        """
        exe_files = self.find_exe_files(wineprefix)
        for exe_file in exe_files:
            self.create_yaml_file_for_process_sh(exe_file, wineprefix, use_exe_name=True, skip_ui_update=skip_ui_update)
        
        # Only update the UI if skip_ui_update is False
        if not skip_ui_update:
            GLib.timeout_add_seconds(0.5, self.create_script_list)


