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
```bash
python Recover_MS_Edge_Open_Tabs_v54.py --session Session_XXXXXXXXXXXX --tabs Tabs_YYYYYYYYYYYY

Example Command Prompt execution command:
python Recover_MS_Edge_Open_Tabs_v54.py --session Session_13408966887033535 --tabs Tabs_13408966866613624
