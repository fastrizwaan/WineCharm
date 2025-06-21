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


0.99.4
- [x] Settings default Runner in settings, then creating new script like AOCSETUP
- [x] Default Runner is not respected by newly created .charm script, fix it.
- [x] do not show not found dialog for winezgui
- [x] wow64 with bin/wine be treated as win64 arch
- [x] show dialog to run wineboot -u
- [x] Create bottle hangs with ~/AOCSETUP.EXE ( do not include not detecting?) flatpak shows can't access properly.
- [x] restore loads scripts properly on success.
- 
- [ ] Set Default runner on system with wine; 32 bits packages not installed; use wine64 or suggest user for get wine64 runner
Error validating runner /var/home/rizvan/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Runners/wine-10.0-amd64/bin/wine: [Errno 2] No such file or directory: '/var/home/rizvan/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Runners/wine-10.0-amd64/bin/wine'
Error validating runner /var/home/rizvan/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Runners/wine-10.0-amd64/bin/wine: [Errno 2] No such file or directory: '/var/home/rizvan/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Runners/wine-10.0-amd64/bin/wine'
Invalid default runner: /var/home/rizvan/.var/app/io.github.fastrizwaan.WineCharm/data/winecharm/Runners/wine-10.0-amd64/bin/wine


0.99.3
- [x] Import on 1st start, and can be called from menu
- [x] show added scripts count
- [x] show log fix


0.99.1
- [x] port to libadwaita from gtk4 only

# 0.99.0
- [x] Beautiful list view
- [x] Beautiful Icon view


# Todo 0.98
- [ ] show recommended dxvk, vkd3d, openal, corefonts (get them separate, arial, times, etc. for progress) and show show all winetricks dlls with a window with checkbox
- [ ] show winetricks dlls
- [x] Show dialog for save directories with option to add directories to .charm script
- [ ] launch to Run without args (for epsxe)
- [ ] determine max screensize and update the registry files for distribution of files. if GPURes values are found like these
        user.reg:"GPUResX"="1920"
        user.reg:"GPUResY"="1080"
- [x] use args and env vars in headless .charm file launch
- [x] create need-wineboot.yml and check in launch, then do wineboot -u for restore/import so that game runs.
- [x] isolate dirs after restore
- [x] fix download runner gtk error
- [x] show single progress if single runner is being downloaded
- [x] make icons unique


 # Todo WineCharm 0.97
- [x] keep margin/padding for button, so that they don't overlap the text
- [x] Arch, Template feature working required
- [x] single wine prefix set template winecharm-single
- [x] Warn prefix name when using single prefix
- [x] do not remove search "Removed existing charm file" from single_prefix 
- [x] Create template
- [x] Runner getting wrong "~/WineCharm" or pwd is used for runner while creating bottle.
- [x] template configure
- [x] open terminal at template
- [x] fix the following error which is there for initializing template, startup with scripts installed.
    /usr/lib/python3.12/site-packages/gi/overrides/GObject.py:491: Warning: ../gobject/gsignal.c:2684: instance '0x55d9ea6653c0' has no handler with id '634'
 
 - BUGS and Features
    - [x] Cancellable
        - [x] Initialize Template
        - [x] Create Prefix
        - [x] Create Bottle
    - [x] These need to extract in a temporary directoy then moved when overwriting. if overwriting is canceled, delete the extracted directory
        - [x] Restore Bottle
        - [x] Import Wine Directory
        - [x] Restore Prefix
        - [x] Restore WZT
    
    - [x] Search in Settings
    - [x] Search in Script options
    
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
            - [x] check if gamedir is inside prefixdir, then use a different command to create bottle
            - [x] Bundle runner when exe_file inside prefixdir with create bottle
            - [x] bundle runner/runners if current charm file has it.
            - [x] update runner path in the charm script file
            - [x] copy runner dir while tarring (if bottle)
            - [x] update runner path in the script file
            - [x] Copy Game Dir while tarring
            - [x] Avoid do not include dirs
            - [x] Change /media/$USER to %USERNAME%
            - [x] Before creating bottle, restore /media/$USER so that
            - [x] update script files with new path drivec/GAMEDIR/<dir>/exe_file.exe (much like import game dir)
            - [x] Show GUI progress of tarring using progressbar 
            - [x] Allow cancellation of bundle creation, while it is running using same open/bottling button
            - [x] Revert scripts with actual path, if interrupted or due to power failure or other reasons. (self repair)

    - [ ] create a file/mechanism which will repair broken wineprefix
        - [ ] create a file WINEZGUIDIR/backup_unfinished.yml and add file list with path and wineprefix info to the yml file; and copy the .charm .txt & .yml & *.reg files to WINEZGUIDIR/bottling/
            - [ ] Required for all tar -cvf where files are changes, like prefix and bottle creation.
        - [ ] if found WINEZGUIDIR/bottling_unfinished.yml on app launch repair the wineprefix, replace the files in the wineprefix

    - [x] make the extraction and copying slow process immediately kill-able, like tar command and copy directory. 
    - [x] Launch script, if sha256sum is missing, and exe is found update sha256sum in the .charm file
    - [x] If setup is launched with a different runner, newly created script must use the runner as specified in the setup .charm file. If this script has runner, create new .charm files should use it.
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
     - [x] Arch 
     - [x] Runner
         - [x] same as Settings level above
     - [x] Template
        - [x] Configure
        - [x] New
        - [x] Copy
        - [x] Delete


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
    - [x] Set Application Category
    - [x] winecfg
    - [x] regedit

WineZGUI bug: Downloading and setting runner (say wine-9.0) and creating a script's bundle with a different runner (say wine-7.0) will create bundle with Global runner (9.0) instead of local runner (7.0); perhaps global runner variable needs fixing for local runner in create prefix and create bundle.
