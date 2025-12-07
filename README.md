# Free-Python-code-to-recover-MS-Edge-tabs-after-a-crash
Free Python code to recover MS Edge tabs after a crash
# Recover Edge Open Tabs

Recover_MS_Edge_Open_Tabs — a small Python utility to recover MS Edge grouped tabs from a corrupted session file.
Edge can be set to open the previous session by default, however if the PC is not shut down properly, like due to 
loss of power, it can fail to load the previous session. Often repeatedly pressing Ctrl-Shift-T will restore the 
previously open tabs, however sometimes it will only restore a maximum of 25 open tabs. Save the Session and Tabs 
files from C:\Users\<YourUsername>\AppData\Local\Microsoft\Edge\User Data\Default\Sessions, and put a copy of 
them in the same folder as this script and it will hopefully recover your open tabs in the form of a bookmarks 
file that you can import into Edge and use to restore your open tabs. The script will create a bookmarks folder 
for each tab group. The code was written by ChatGPT, with guidance from me.

## What it does
- Reads an MS Edge `Session_*` binary (and optional `Tabs_*` file).
- Replaces non-printable bytes with `|`.
- Detects tab-group tags and reconstructs tab group names.
- Extracts grouped tab URLs and writes:
  - a dated CSV: `YYYY-MM-DD_Recovered_Edge_Tabs_v54.csv`
  - a dated Netscape-format bookmarks HTML: `YYYY-MM-DD_Recovered_Edge_Tabs_Saved_As_Bookmarks_v54.html`
  - replaced-text files for Session and Tabs
- All outputs are placed inside a dated parent folder.

## Usage
```bash
python Recover_MS_Edge_Open_Tabs_v54.py --session Session_XXXXXXXXXXXX --tabs Tabs_YYYYYYYYYYYY

Example Command Prompt execution command:
python Recover_MS_Edge_Open_Tabs_v54.py --session Session_13408966887033535 --tabs Tabs_13408966866613624
