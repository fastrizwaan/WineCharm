[1mdiff --git a/flatpak/io.github.fastrizwaan.WineCharm.yaml b/flatpak/io.github.fastrizwaan.WineCharm.yaml[m
[1mindex 904bc2b..dff5906 100644[m
[1m--- a/flatpak/io.github.fastrizwaan.WineCharm.yaml[m
[1m+++ b/flatpak/io.github.fastrizwaan.WineCharm.yaml[m
[36m@@ -2,8 +2,8 @@[m [mid: io.github.fastrizwaan.WineCharm[m
 sdk: org.gnome.Sdk[m
 runtime: org.gnome.Platform[m
 base: org.winehq.Wine[m
[31m-base-version: stable-23.08[m
[31m-runtime-version: &runtime-version '46'[m
[32m+[m[32mbase-version: stable-24.08[m
[32m+[m[32mruntime-version: &runtime-version '47'[m
 command: winecharm[m
 [m
 #rename-icon: winezgui[m
[36m@@ -207,8 +207,8 @@[m [mmodules:[m
       - pip3 install --prefix=/app PyYAML*.whl[m
     sources:[m
       - type: file[m
[31m-        url: https://files.pythonhosted.org/packages/7b/5e/efd033ab7199a0b2044dab3b9f7a4f6670e6a52c089de572e928d2873b06/PyYAML-6.0.1-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl[m
[31m-        sha256: d2b04aac4d386b172d5b9692e2d2da8de7bfb6c387fa4f801fbf6fb2e6ba4673[m
[32m+[m[32m        url: https://files.pythonhosted.org/packages/b9/2b/614b4752f2e127db5cc206abc23a8c19678e92b23c3db30fc86ab731d3bd/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl[m
[32m+[m[32m        sha256: 80bab7bfc629882493af4aa31a4cfa43a4c57c83813253626916b8c7ada83476[m
         only-arches:[m
           - x86_64[m
         x-checker-data:[m
[1mdiff --git a/winecharm.py b/winecharm.py[m
[1mindex e846abc..bf30d98 100755[m
[1m--- a/winecharm.py[m
[1m+++ b/winecharm.py[m
[36m@@ -36,7 +36,7 @@[m [mclass WineCharmApp(Gtk.Application):[m
         Adw.init()[m
         [m
         # Move the global variables to instance attributes[m
[31m-        self.debug = True[m
[32m+[m[32m        self.debug = False[m
         self.version = "0.97"[m
         [m
         # Paths and directories[m
[36m@@ -2154,12 +2154,13 @@[m [mclass WineCharmApp(Gtk.Application):[m
         return icon_path if icon_path.exists() else None[m
 [m
     def find_lnk_files(self, wineprefix):[m
[31m-        drive_c = wineprefix / "drive_c"[m
[32m+[m[32m        drive_c = wineprefix / "drive_c" / "ProgramData"[m
         lnk_files = [][m
 [m
         for root, dirs, files in os.walk(drive_c):[m
             for file in files:[m
                 file_path = Path(root) / file[m
[32m+[m
                 if file_path.suffix.lower() == ".lnk" and file_path.is_file():[m
                     lnk_files.append(file_path)[m
 [m
[36m@@ -2932,13 +2933,14 @@[m [mclass WineCharmApp(Gtk.Application):[m
         return sh_files[m
 [m
     def find_and_save_lnk_files(self, wineprefix):[m
[31m-        drive_c = wineprefix / "drive_c"[m
[32m+[m[32m        drive_c = wineprefix / "drive_c" / "ProgramData"[m
         found_lnk_files_path = wineprefix / "found_lnk_files.yaml"[m
         lnk_files = [][m
 [m
         for root, dirs, files in os.walk(drive_c):[m
             for file in files:[m
                 file_path = Path(root) / file[m
[32m+[m
                 if file_path.suffix.lower() == ".lnk" and file_path.is_file():[m
                     print(f"Found .lnk file: {file_path}")[m
                     lnk_files.append(file_path.name)[m
