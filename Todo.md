- [x] Create all base directories Templates, Prefixes, Runners


Refactoring winecharm

- [ ] Move following methods from main program to reduce its size to bare miniumum
    - [ ] on_import_wine_directory_clicked
    - [ ] on_import_directory_response
    - [ ] copy_wine_directory
    - [ ] process_reg_files
    - [ ] create_scripts_for_exe_files
    - [ ] find_exe_files
    
    - [ ] backup_prefix
    - [ ] process_reg_files
    - [ ] reverse_process_reg_files
    - [ ] create_backup_archive
    - [ ] on_backup_dialog_response
    - [ ] show_backup_prefix_dialog
    - [ ] restore_from_backup
    - [ ] perform_restore
    
- [ ] Add all info from .charm and buttons, row, label in self.all_scripts, use script_key (sha256sum)
- [ ] play/stop button, row highlight should be manageed.



# Current issue
- [ ] if the process has ended, the launch_button is not reverted to stop and highlight is not removed
- [ ]  Error terminating script f427f2d354acd78f2177aaeb78a677d34d7825751dc3abe70d40fd537b70c4d8: Command 'bash -c 'export PATH=.:$PATH; WINEPREFIX=/var/home/rizvan/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Prefixes/ReShade_Setup_6.1.1-f427f2d354 wineserver -k'' returned non-zero exit status 1.

is not resetting the play functionality.
 
