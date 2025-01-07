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
    
- [x] Add all info from .charm and buttons, row, label in self.all_scripts, use script_key (sha256sum)
- [x] play/stop button, row highlight should be manageed.


is not resetting the play functionality.
 
 # Todo WineCharm 0.97
 - 1. [x] Runner Support
     - [x] Check working runner before launch (this will help when freedesktop runtime has changed or on system)
     - [x] On startup, do a working runner check; 
           (runner_ver=runner --version, if not runner_ver: report user that runner is not compatible, and let the user choose other runner.)
     - [ ] Script level
        - [ ] Create Bundle Bottle (Game_dir + Runner + Prefix) = bottle (Hello-Bundle.bottle)
            - [x] check if exe_file exists before bundling  the game_dir
            - [x] Check size of Gamedir and print on terminal
            - [x] if > 3GB ask user with a dialog before proceeding
            - [x] check if gamedir is inside prefixdir, suggest -bottle name for backup prefix
            - [ ] check if gamedir is inside prefixdir, then use a different command to create bottle
            - [ ] Bundle runner when exe_file inside prefixdir with backup prefix/create bottle
            - [ ] bundle runner/runners if any charm file has it.
            - [ ] update runner path in the charm script file
            - [ ] copy runner dir while tarring (if bottle)
            - [ ] update runner path in the script file
            - [x] Copy Game Dir while tarring
            - [x] Avoid do not include dirs
            - [x] Change /media/$USER to %USERNAME%
            - [x] Before creating bottle, restore /media/$USER so that
            - [x] update script files with new path drivec/GAMEDIR/<dir>/exe_file.exe (much like import game dir)
            - [ ] Show GUI progress of tarring using % 
            - [ ] Allow cancellation of bundle creation, while it is running using same open/bottling button
            - [ ] Revert scripts with actual path, if interrupted or due to power failure or other reasons. (self repair)
                - [ ] create a copy at winecharm's data directory...
                - [ ] create a file/mechanism which will repair broken wineprefix
                
        - [ ] Import Runner
        - [x] Import Game Directory
     - [ ] Settings level
         - [x] Download
             - List
             - [x] Proton
             - [x] Wine Stable ones
             - [x] Wine Latest
             - [x] Wine multi lib supported
         - [x] Default
         - [x] Change
         - [x] List all Runners even from prefixes_dir/*/Runner/runner_dir/bin/wine

 - 2. [x] Settings support (like show_options_for_script)
     - [ ] Arch 
     - [x] Runner
         - [ ] same as Settings level above
     - [ ] Template
        - [ ] Configure
        - [ ] New
        - [ ] Copy
        - [ ] Delete


 - 3. [] update all scripts
     - [ ] repair 
     
- 4. Script (options)
    - [x] Run Other Exe in wineprefix  (open other exe)
    - [x] Import Game directory
    - [x] Winetricks CLI (install dxvk vkd3d)
    - [ ] Import Runner inside prefix
    - [x] Set Environment Variable
    - [x] Save drive_c/user directory to file (with %USERNAME%)
    - [x] Load file for drive_c/user directory
    - [ ] About
        - [ ] Name, Size, Gamedir size, Prefix size, if gamedir in prefix then combined.
    - [x] Change Runner
    - [x] Rename prefix directory
    - [ ] Set Wine Arch
    - [x] Set Application Category
    - [x] winecfg
    - [x] regedit

WineZGUI bug: Downloading and setting runner (say wine-9.0) and creating a script's bundle with a different runner (say wine-7.0) will create bundle with Global runner (9.0) instead of local runner (7.0); perhaps global runner variable needs fixing for local runner in create prefix and create bundle.
