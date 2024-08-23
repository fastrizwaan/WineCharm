


    def terminate_script_riz(self, script_key):
        process_info = self.running_processes[script_key]
        pid = process_info.get('pid')
        exe_name = process_info.get('exe_name')
        wineprefix = Path(process_info['script']).parent

        # Use wineprefix along with winedbg to accurately target the process
        #refined_processes = self.get_wine_processes(wineprefix, exe_name)
        command = f"WINEPREFIX={shlex.quote(str(wineprefix))} wineserver -k &"
        try:
            subprocess.run(command, shell=True, check=True)
            print(f"Successfully ran {pid} in {wineprefix}")
            del self.running_processes[script_key]
        except subprocess.CalledProcessError as e:
            print(f"Error running winetricks script: {e}")


    def get_wine_processes(self, wineprefix, exe_name):
        try:
            command = f"WINEPREFIX={shlex.quote(wineprefix)} winedbg --command 'info proc'"
            winedbg_output = subprocess.check_output(command, shell=True).decode().splitlines()

            processes = []
            for line in winedbg_output:
                # Print each line for debugging purposes
                print(f"winedbg output line: {line}")

                if line.strip() and 'executable' not in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            pid = int(parts[0], 16)  # Convert hex PID to int
                            current_exe_name = parts[-1].strip("'")
                            if current_exe_name == exe_name:
                                processes.append((pid, current_exe_name))
                        except ValueError:
                            print(f"Skipping line due to ValueError: {line}")
                            continue  # Skip lines that don't have valid hexadecimal PIDs

            return processes
        except subprocess.CalledProcessError as e:
            print(f"Error running winedbg: {e}")
            return []

