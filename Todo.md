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
- 1. [ ] if the process has ended, the launch_button is not reverted to stop and highlight is not removed
- 2. [ ]  Error terminating script f427f2d354acd78f2177aaeb78a677d34d7825751dc3abe70d40fd537b70c4d8: Command 'bash -c 'export PATH=.:$PATH; WINEPREFIX=/var/home/rizvan/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Prefixes/ReShade_Setup_6.1.1-f427f2d354 wineserver -k'' returned non-zero exit status 1. this is related to 1.

is not resetting the play functionality.
 
 # Todo WineCharm 0.97
 - 1. [ ] Runner Support
     - [ ] Check working runner before launch (this will help when freedesktop runtime has changed or on system)
     - [ ] On startup, do a working runner check; 
           (runner_ver=runner --version, if not runner_ver: report user that runner is not compatible, and let the user choose other runner.)
     - [ ] Script level
        - [ ] Create Bundle Bottle (Game_dir + Runner + Prefix) = bottle (Hello-Bundle.bottle)
        - [ ] Import Runner
        - [ ] Import Game Directory
     - [ ] Settings level
         - [ ] Download
             - List
             - [ ] Proton
             - [ ] Wine Stable ones
             - [ ] Wine Latest
             - [ ] Wine multi lib supported
         - [ ] Default
         - [ ] Change
         - [ ] List all Runners even from prefixes_dir/*/Runner/runner_dir/bin/wine

 - 2. [ ] Settings support (like show_options_for_script)
     - [ ] Arch 
     - [ ] Runner
         - [ ] same as Settings level above
     - [ ] Template
        - [ ] Configure
        - [ ] New
        - [ ] Copy
        - [ ] Delete


 - 3. [] update all scripts
     - [ ] repair 
     
     
     
WineZGUI bug: Downloading and setting runner (say wine-9.0) and creating a script's bundle with a different runner (say wine-7.0) will create bundle with Global runner (9.0) instead of local runner (7.0); perhaps global runner variable needs fixing for local runner in create prefix and create bundle.
