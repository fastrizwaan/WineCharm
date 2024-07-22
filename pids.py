import subprocess

def get_child_pids(parent_pid):
    try:
        # Run the `ps` command to list all processes with their PPIDs
        result = subprocess.run(['ps', '-eo', 'pid,ppid', '--no-headers'], capture_output=True, text=True, check=True)
        child_pids = []
        for line in result.stdout.splitlines():
            pid, ppid = map(int, line.split())
            if ppid == parent_pid:
                child_pids.append(pid)
        return child_pids
    except subprocess.CalledProcessError as e:
        print(f"Error running ps command: {e}")
        return []

parent_pid = 21184
child_pids = get_child_pids(parent_pid)

if child_pids:
    print(f"The child PIDs of {parent_pid} are {child_pids}")
else:
    print(f"No child processes found for PID {parent_pid}.")
