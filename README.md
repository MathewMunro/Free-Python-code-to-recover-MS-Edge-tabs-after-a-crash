# Free-Python-code-to-recover-MS-Edge-tabs-after-a-crash
Free Python code to recover MS Edge tabs after a crash
# Recover Edge Open Tabs
Recover_MS_Edge_Open_Tabs — a small Python utility to recover MS Edge grouped tabs from a corrupted session file.

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
python Recover_MS_Edge_Open_Tabs_v54.py --session Session_XXXXXXXXXXXX --tabs Tabs_YYYYYYYYYYYY

## Requirements
Python 3.8+ (standard library only; no third-party packages required)

##License
This repository is licensed under the MIT License — see LICENSE

## Contributing
If you find bugs or have improvement ideas, please open an issue or submit a pull request.

## Author
The code was written by ChatGPT, with algorithmic guidance from me (Mathew Munro).

## Detailed Explanation
If Edge crashes, and the previous session won't load, don't close Edge.

Sometimes pressing Ctrl-Shift-T will restore all the previously open tabs simultaneously, sometimes it will bring back whole tab groups at a time, and sometimes, if you had more than 25 ungrouped tabs open when it crashed, it will only bring back 25 individual tabs.

If it fails to bring back all your open tabs, data can sometimes be extracted from the Session and Tabs files using the Python script Recover_MS_Edge_Open_Tabs_v54.py

The Session and Tabs files are stored in the following location: C:\Users\<YourUsername>\AppData\Local\Microsoft\Edge\User Data\Default\Sessions, for example: C:\Users\mathew\AppData\Local\Microsoft\Edge\User Data\Default\Sessions

Copy the Session_xxx and Tabs_xxx files to the same location as the Python script, for example: D:\Documents\Mat\Apps\Browsers & Extensions\Edge

Then if Python isn't already installed, install it. It was working with Stable Release 'Python 3.13.9 - Oct. 14, 2025' Windows installer (64-bit)

Then open Command Prompt, and navigate to the folder that contains the Python script, for example, enter D:
Then cd "D:\Documents\Mat\Apps\Browsers & Extensions\Edge"

Then enter the execution command: python Recover_MS_Edge_Open_Tabs_v54.py --session Session_XXXXXXXXXXXX --tabs Tabs_YYYYYYYYYYYY
For example: python Recover_MS_Edge_Open_Tabs_v54.py --session Session_13408966887033535 --tabs Tabs_13408966866613624

It will output all files to a new folder inside the folder you rant it from. The folder name will be prepended with the date last modified of the session file <Date>_Recovered_Edge_Tabs_v54. The output will include a csv file with the URLs and tab group names, text files with the contents of the Session and Tabs files with non-printable characters replaced with pipe characters ('|'), and a bookmarks file (.html) that can be imported into Edge. As a precaution to avoid the risk of losing your current bookmarks, before importing the bookmarks file created by the script, export a copy of your current bookmarks.

It may not recover all the open tabs & tab groups, because an unexpected shutdown can cause file corruption or incomplete writing of the file. If you don't specify a tabs file, it will try to recover the tabs anyway, but ungrouped tabs will end up allocated to a random tab group.
