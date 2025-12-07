#!/usr/bin/env python3
"""
Recover_MS_Edge_Open_Tabs_v54.py

Reads an MS Edge Session binary file (and optional Tabs file), replaces non-printable bytes
with a pipe character ('|'), writes the modified content to text files (one per Session/Tabs),
extracts:
  - SessionTagsAndGroupsTable: detected session tab-group tags and reconstructed tab-group names.
  - SessionGroupedTabsTable: grouped-tab URLs found by matching interleaved URL copies and
    assigning to the first tag occurrence to the right (with Tabs-file confirmation where provided).

Additionally:
  - Generates a Netscape-format bookmarks HTML file containing folders per tab group
    and an "Ungrouped" folder for those classified as ungrouped.
  - Creates a dated parent folder (based on the Session file last-modified date, or today if unavailable)
    and writes all outputs (CSV, bookmarks, replaced-text files) into that parent folder.

Version changes in v54:
 - Removed creation of per-group .url files and per-group directories on disk (you requested this).
 - Small safe performance improvements:
     * cached computed block start (first_closing_brace index)
     * used bisect search over sorted tag-occurrence positions to find the first tag after an index
     * precompiled common regexes
     * avoided re-calling expensive find operations
 - Otherwise algorithm and outputs preserved.

Usage:
  python Recover_MS_Edge_Open_Tabs_v54.py --session Session_XXXXXXXXXXXX --tabs Tabs_YYYYYYYYYYYY
"""
import os
import sys
import re
import csv
import argparse
from datetime import datetime
from pathlib import Path
import html
import bisect

# ---------------- User-changeable parameters ----------------
REPEAT_COUNT_REQUIRED = 5                  # tag must occur exactly this many times in the tag block
TAG_LENGTH_CHARS = 19                      # tag candidate length (characters)
ADVANCE_AFTER_TAG_TO_GROUP_START = 4       # group_start = tag_first_start + TAG_LENGTH_CHARS + 4
REPLACEMENT_CHAR_PIPE = '|'                # visible replacement for non-printable bytes
CSV_OUTPUT_FILENAME_SUFFIX = "Recovered_Edge_Tabs_v54.csv"   # date prefix will be added
BOOKMARKS_FILENAME_SUFFIX = "Recovered_Edge_Tabs_Saved_As_Bookmarks_v54.html"
URL_RIGHTCONTEXT_MAX_CHARS = 30000         # limit for CSV URL_RightContext
PARENT_FOLDER_SUFFIX = "Recovered_Edge_Tabs_v54"             # folder name suffix, date prefix added
# ------------------------------------------------------------


# ---------------- Helper functions (clear names + docstrings) ----------------

def parse_command_line_arguments():
    """Parse command-line arguments for the session and optional tabs filenames."""
    p = argparse.ArgumentParser(description="Recover Edge grouped-tab URLs from Session and Tabs files.")
    p.add_argument("--session", "-s", help="Session binary filename (e.g. Session_XXXXXXXX)", default=None)
    p.add_argument("--tabs", "-t", help="Tabs filename (binary or text)", default=None)
    return p.parse_args()


def find_earliest_lowercase_http_position_in_bytes(byte_buffer):
    """
    Return earliest index of b'http://' or b'https://' in the provided bytes buffer.
    If neither is present return len(byte_buffer).
    """
    pos_http = byte_buffer.find(b'http://')
    pos_https = byte_buffer.find(b'https://')
    candidates = [p for p in (pos_http, pos_https) if p != -1]
    return min(candidates) if candidates else len(byte_buffer)


def convert_single_byte_to_display_char(byte_value):
    """
    Convert a single byte (int 0..255) to a single display character:
      - If printable ASCII range (32..126): return corresponding character.
      - Otherwise return the configured replacement pipe character.
    """
    return chr(byte_value) if 32 <= byte_value <= 126 else REPLACEMENT_CHAR_PIPE


def find_non_overlapping_positions_in_text(full_text, substring):
    """
    Find all non-overlapping start indices of 'substring' within 'full_text'.
    Advance the search start by len(substring) after each match to avoid overlaps.
    Returns list of integer start indices relative to full_text.
    """
    positions = []
    start_idx = 0
    L = len(substring)
    while True:
        found = full_text.find(substring, start_idx)
        if found == -1:
            break
        positions.append(found)
        start_idx = found + L
    return positions


def build_pipe_interleaved_text_for_url(url_text):
    """
    Given a URL string e.g. 'https://www.example.com/', return its pipe-interleaved representation:
      '|h|t|t|p|s|:|/|/|w|w|w|.|e|x|a|m|p|l|e|.|c|o|m|/'
    """
    if not url_text:
        return ""
    return REPLACEMENT_CHAR_PIPE + REPLACEMENT_CHAR_PIPE.join(list(url_text)) + REPLACEMENT_CHAR_PIPE


def build_pipe_interleaved_text_for_group_name(group_name):
    """
    Given a group name like 'Group_Alpha' return its pipe interleaved version:
      '|G|r|o|u|p|_|A|l|p|h|a|'
    """
    if not group_name:
        return ""
    return REPLACEMENT_CHAR_PIPE + REPLACEMENT_CHAR_PIPE.join(list(group_name)) + REPLACEMENT_CHAR_PIPE


def sanitize_filename_component(s):
    """
    Create a filesystem-safe string: replace characters typically illegal in filenames.
    Truncate moderately to avoid extremely long names.
    """
    if not s:
        return "empty"
    return re.sub(r'[<>:"/\\|?*\n\r\t]+', '_', s)[:200]


def ensure_parent_folder_for_outputs(base_dir, date_prefix):
    """
    Create and return the parent output folder path, using date_prefix + PARENT_FOLDER_SUFFIX.
    """
    name = f"{date_prefix}_{PARENT_FOLDER_SUFFIX}"
    parent = Path(base_dir) / name
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def make_bookmark_title_from_url(u):
    """
    Create a short title for a bookmark from the URL for display in bookmarks HTML.
    Domain + last path segment (if >1 char) is used.
    """
    try:
        parsed = re.match(r'https?://([^/]+)(/.*)?', u, re.IGNORECASE)
        if not parsed:
            return u
        domain = parsed.group(1)
        path = parsed.group(2) or ''
        last_segment = ""
        if path:
            parts = [p for p in path.split('/') if p]
            if parts:
                last_seg = parts[-1]
                if len(last_seg) > 1:
                    last_segment = "/" + last_seg
        title = domain + last_segment
        return title if title else u
    except Exception:
        return u


# ---------------- Main program ----------------

def main():
    args = parse_command_line_arguments()
    session_file = args.session
    tabs_file = args.tabs
    code_version_string = "Recover_MS_Edge_Open_Tabs_v54.py"

    # Determine date prefix from session file last-modified or fallback to today
    if session_file and os.path.exists(session_file):
        try:
            mtime = os.path.getmtime(session_file)
            date_prefix = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        except Exception:
            date_prefix = datetime.now().strftime("%Y-%m-%d")
    else:
        date_prefix = datetime.now().strftime("%Y-%m-%d")

    csv_output_filename = f"{date_prefix}_{CSV_OUTPUT_FILENAME_SUFFIX}"
    bookmarks_filename = f"{date_prefix}_{BOOKMARKS_FILENAME_SUFFIX}"

    # Parent output folder
    parent_folder = ensure_parent_folder_for_outputs(os.getcwd(), date_prefix)

    # Prepare replaced-text filenames (date prefixed)
    session_replaced_filename = None
    tabs_replaced_filename = None
    if session_file:
        session_basename = Path(session_file).name
        session_replaced_filename = f"{date_prefix}_{sanitize_filename_component(session_basename)}_non-printables_replaced_with_pipe_char.txt"
    if tabs_file:
        tabs_basename = Path(tabs_file).name
        tabs_replaced_filename = f"{date_prefix}_{sanitize_filename_component(tabs_basename)}_non-printables_replaced_with_pipe_char.txt"

    # Containers
    session_bytes = b''
    session_text_with_pipes = ""
    session_tab_group_block_text = ""
    text_after_first_url = ""
    tabs_text_with_pipes = ""

    # Read Session file and produce pipe-substituted text and the tab-group block
    if session_file:
        if not os.path.isfile(session_file):
            print("Error: session file not found:", session_file)
            sys.exit(1)
        with open(session_file, "rb") as fh:
            session_bytes = fh.read()

        # convert once and reuse
        session_text_with_pipes = ''.join(convert_single_byte_to_display_char(b) for b in session_bytes)

        # compute once; avoid repeated .find calls later
        first_closing_brace_idx = session_bytes.find(b'}')
        block_start_abs = (first_closing_brace_idx + 1) if first_closing_brace_idx != -1 else 0
        first_http_abs = find_earliest_lowercase_http_position_in_bytes(session_bytes)

        if block_start_abs < first_http_abs:
            block_slice = session_bytes[block_start_abs:first_http_abs]
            session_tab_group_block_text = ''.join(convert_single_byte_to_display_char(b) for b in block_slice)
        else:
            session_tab_group_block_text = ""

        if first_http_abs < len(session_bytes):
            text_after_first_url = ''.join(convert_single_byte_to_display_char(b) for b in session_bytes[first_http_abs:])
        else:
            text_after_first_url = ""

    # Read Tabs file (optional) and convert to pipe-substituted text
    if tabs_file:
        if not os.path.isfile(tabs_file):
            print("Error: tabs file not found:", tabs_file)
            sys.exit(1)
        with open(tabs_file, "rb") as fh:
            tabs_bytes = fh.read()
        tabs_text_with_pipes = ''.join(convert_single_byte_to_display_char(b) for b in tabs_bytes)

    # ---------------- Detect tab-group tags and reconstruct group names ----------------
    session_tags_and_groups = []

    if session_tab_group_block_text:
        block_text = session_tab_group_block_text
        seen_candidates = set()
        for rel_pos in range(0, max(0, len(block_text) - TAG_LENGTH_CHARS + 1)):
            # candidate tags start with three pipe chars '|||'
            if block_text[rel_pos:rel_pos + 3] != REPLACEMENT_CHAR_PIPE * 3:
                continue
            candidate = block_text[rel_pos:rel_pos + TAG_LENGTH_CHARS]
            if candidate in seen_candidates:
                continue
            seen_candidates.add(candidate)
            pos_list_rel = find_non_overlapping_positions_in_text(block_text, candidate)
            if len(pos_list_rel) == REPEAT_COUNT_REQUIRED:
                abs_first_pos = block_start_abs + pos_list_rel[0]
                session_tags_and_groups.append({
                    "SessionTabGroupTag": candidate,
                    "PositionsRelInBlock": pos_list_rel,
                    "TagFirstPosAbs": abs_first_pos
                })

        # reconstruct spaced/name using dollar-sign heuristic as previously agreed
        full_text = session_text_with_pipes
        reconstructed = []
        for ent in session_tags_and_groups:
            tag_text = ent["SessionTabGroupTag"]
            pos_rel_list = ent["PositionsRelInBlock"]
            if len(pos_rel_list) < 2:
                continue
            second_rel = pos_rel_list[1]
            first_abs = ent["TagFirstPosAbs"]
            group_spaced_start_abs = first_abs + TAG_LENGTH_CHARS + ADVANCE_AFTER_TAG_TO_GROUP_START

            presumptive_dollar_rel = second_rel - 44
            if presumptive_dollar_rel < 0:
                search_left_rel = max(0, second_rel - 80)
                found = block_text.rfind('$', search_left_rel, second_rel)
                presumptive_dollar_rel = found if found != -1 else max(0, second_rel - 44)
            presumptive_dollar_abs = block_start_abs + presumptive_dollar_rel

            scan_idx = presumptive_dollar_abs - 1
            group_spaced_end_abs = None
            while scan_idx >= 0:
                if full_text[scan_idx] != REPLACEMENT_CHAR_PIPE:
                    group_spaced_end_abs = scan_idx
                    break
                scan_idx -= 1
            if group_spaced_end_abs is None:
                continue
            if group_spaced_start_abs < 0 or group_spaced_start_abs > group_spaced_end_abs:
                continue

            group_spaced_text = full_text[group_spaced_start_abs:group_spaced_end_abs + 1]
            group_name = group_spaced_text[0::2].strip()
            reconstructed.append({
                "SessionTabGroupTag": tag_text,
                "GroupSpaced": group_spaced_text,
                "SessionTabGroup": group_name,
                "TagFirstPosAbs": first_abs,
                "GroupStartAbs": group_spaced_start_abs,
                "GroupEndAbs": group_spaced_end_abs
            })
        reconstructed.sort(key=lambda x: x["TagFirstPosAbs"])
        session_tags_and_groups = reconstructed

    # ---------------- Build mapping of all tag occurrences ----------------
    tag_to_all_occurrences = {}
    if session_tags_and_groups and session_text_with_pipes:
        full_text = session_text_with_pipes
        for ent in session_tags_and_groups:
            tag = ent["SessionTabGroupTag"]
            all_positions = find_non_overlapping_positions_in_text(full_text, tag)
            tag_to_all_occurrences[tag] = sorted(all_positions)

    # ---------------- Find simple URLs (in the session text) ----------------
    url_regex = re.compile(r'https?://[^' + re.escape(REPLACEMENT_CHAR_PIPE) + r'\s]+', re.IGNORECASE)
    simple_url_matches = []
    if session_text_with_pipes:
        for m in url_regex.finditer(session_text_with_pipes):
            simple_url_matches.append((m.start(), m.end(), m.group()))

    # ---------------- Confirm interleaved twin for each simple URL in the session text ----------------
    confirmed_interleaved_records = []

    # Helper to check if any simple-url start exists strictly between a and b
    def any_simple_url_between(position_a, position_b, url_list):
        for (s, e, raw) in url_list:
            if s > position_a and s < position_b:
                return True
        return False

    for (s, e, raw_url) in simple_url_matches:
        candidate_url = raw_url
        matched = False
        # attempt: original, then trimmed-last-char
        for attempt in range(2):
            if attempt == 1:
                if len(candidate_url) > 1:
                    candidate_url = candidate_url[:-1]
                else:
                    candidate_url = ""
            if not candidate_url:
                break
            interleaved = build_pipe_interleaved_text_for_url(candidate_url)
            interleaved_idx = session_text_with_pipes.find(interleaved, e)
            if interleaved_idx == -1:
                continue
            if any_simple_url_between(e, interleaved_idx, simple_url_matches):
                continue
            confirmed_interleaved_records.append((s, e, candidate_url, interleaved_idx, interleaved_idx + len(interleaved), raw_url))
            matched = True
            break

    confirmed_interleaved_records.sort(key=lambda x: x[3])  # sort by interleaved_start

    # ---------------- Assign each confirmed interleaved URL to the first tag occurrence after interleaved end ----------------
    tag_occurrence_to_assigned_urls = {}
    combined_tag_occurrences_all = []
    # build combined list once
    for tag, occ_list in tag_to_all_occurrences.items():
        for pos in occ_list:
            combined_tag_occurrences_all.append((pos, tag))
    combined_tag_occurrences_all.sort(key=lambda x: x[0])

    # extract parallel lists for bisect usage (positions, tags)
    combined_positions = [p for (p, _) in combined_tag_occurrences_all]
    combined_tags = [t for (_, t) in combined_tag_occurrences_all]

    def find_first_tag_occurrence_after_abs_bisect(position_abs):
        """
        Use bisect on pre-sorted combined_positions to efficiently locate the first
        tag occurrence with pos > position_abs. Returns (pos, tag) or None.
        """
        idx = bisect.bisect_right(combined_positions, position_abs)
        if idx < len(combined_positions):
            return (combined_positions[idx], combined_tags[idx])
        return None

    for (simple_start, simple_end, canonical_url_used, interleaved_start, interleaved_end, raw_url_original) in confirmed_interleaved_records:
        found = find_first_tag_occurrence_after_abs_bisect(interleaved_end)
        if not found:
            continue
        tag_pos, tag_text = found
        key = (tag_text, tag_pos)
        tag_occurrence_to_assigned_urls.setdefault(key, []).append((simple_start, simple_end, canonical_url_used, raw_url_original))

    # ---------------- Build list of eligible tag occurrences (>= 5th occurrence) ----------------
    combined_tag_occurrence_list = []
    for ent in session_tags_and_groups:
        tag = ent["SessionTabGroupTag"]
        occs = tag_to_all_occurrences.get(tag, [])
        if len(occs) >= 5:
            fifth_pos = occs[4]
            occs_after_or_equal_5th = [p for p in occs if p >= fifth_pos]
            for p in occs_after_or_equal_5th:
                combined_tag_occurrence_list.append((p, tag))
    combined_tag_occurrence_list.sort(key=lambda x: x[0])

    # ---------------- Iterate eligible occurrences and produce rows with Tabs-file confirmation ----------------
    consecutive_empty_count_by_tag = {ent["SessionTabGroupTag"]: 0 for ent in session_tags_and_groups}
    finished_tags = set()
    tag_to_groupname = {e["SessionTabGroupTag"]: e["SessionTabGroup"] for e in session_tags_and_groups}

    produced_rows = []
    prev_accepted_tag_end_pos = None
    first_row_written = False

    # precompile tabs_url regex if needed
    tabs_url_regex = re.compile(r'https?://[^' + re.escape(REPLACEMENT_CHAR_PIPE) + r'\s]+', re.IGNORECASE) if tabs_text_with_pipes else None

    for (occ_pos, tag_text) in combined_tag_occurrence_list:
        if tag_text in finished_tags:
            continue
        key = (tag_text, occ_pos)
        assigned_for_occ = tag_occurrence_to_assigned_urls.get(key, [])
        if not assigned_for_occ:
            consecutive_empty_count_by_tag[tag_text] += 1
            if consecutive_empty_count_by_tag[tag_text] >= 2:
                finished_tags.add(tag_text)
            continue
        consecutive_empty_count_by_tag[tag_text] = 0
        tag_end_pos = occ_pos + len(tag_text)
        assigned_for_occ_sorted = sorted(assigned_for_occ, key=lambda x: x[0])
        for (u_start, u_end, canonical_url_used, raw_url_original) in assigned_for_occ_sorted:
            tentative_group_name = tag_to_groupname.get(tag_text, "")

            # Confirm via Tabs file if available
            final_group_name = tentative_group_name
            if tabs_text_with_pipes:
                tab_index = tabs_text_with_pipes.find(canonical_url_used)
                if tab_index != -1:
                    last_url_before = None
                    for m in list(tabs_url_regex.finditer(tabs_text_with_pipes, 0, tab_index)):
                        last_url_before = (m.start(), m.end(), m.group())
                    interleaved_group = build_pipe_interleaved_text_for_group_name(tentative_group_name)
                    last_group_interleaved_pos = tabs_text_with_pipes.rfind(interleaved_group, 0, tab_index)
                    if last_group_interleaved_pos != -1:
                        if last_url_before is None:
                            final_group_name = tentative_group_name
                        else:
                            if last_group_interleaved_pos > last_url_before[0]:
                                final_group_name = tentative_group_name
                            else:
                                final_group_name = "Ungrouped"
                    else:
                        if last_url_before is not None:
                            final_group_name = "Ungrouped"
                        else:
                            final_group_name = tentative_group_name
                else:
                    final_group_name = tentative_group_name

            # Global chronological filter: except first accepted row, require u_start > prev_accepted_tag_end_pos
            if not first_row_written:
                produced_rows.append({
                    "SessionTabGroup": final_group_name,
                    "URL": canonical_url_used,
                    "URL_Raw": raw_url_original,
                    "URL_RightContext": session_text_with_pipes[u_start:occ_pos][:URL_RIGHTCONTEXT_MAX_CHARS] if session_text_with_pipes else "",
                    "TagText": tag_text,
                    "TagOccurrencePos": occ_pos,
                    "TagEndPos": tag_end_pos,
                    "URL_StartPos": u_start,
                    "URL_EndPos": u_end
                })
                prev_accepted_tag_end_pos = tag_end_pos
                first_row_written = True
            else:
                if u_start > prev_accepted_tag_end_pos:
                    produced_rows.append({
                        "SessionTabGroup": final_group_name,
                        "URL": canonical_url_used,
                        "URL_Raw": raw_url_original,
                        "URL_RightContext": session_text_with_pipes[u_start:occ_pos][:URL_RIGHTCONTEXT_MAX_CHARS] if session_text_with_pipes else "",
                        "TagText": tag_text,
                        "TagOccurrencePos": occ_pos,
                        "TagEndPos": tag_end_pos,
                        "URL_StartPos": u_start,
                        "URL_EndPos": u_end
                    })
                    prev_accepted_tag_end_pos = tag_end_pos
                else:
                    continue

    # ------------------- Write CSV and replaced text files and bookmarks -------------------
    csv_path = parent_folder / csv_output_filename
    bookmarks_path = parent_folder / bookmarks_filename

    with open(csv_path, "w", newline="", encoding="utf-8") as csv_out:
        writer = csv.writer(csv_out)

        # metadata
        writer.writerow([f"Python code version: {code_version_string}"])
        writer.writerow([f"Session file name: {session_file if session_file else 'No file specified'}"])
        writer.writerow([f"Tabs file name: {tabs_file if tabs_file else 'No file specified'}"])
        writer.writerow([])

        # replaced-file notifications (date-prefix filenames)
        if session_file:
            writer.writerow([f"Session file contents written to {session_replaced_filename}"])
        else:
            writer.writerow(["Session file contents written to No file specified"])
        if tabs_file:
            writer.writerow([f"Tabs file contents written to {tabs_replaced_filename}"])
        else:
            writer.writerow(["Tabs file contents written to No file specified"])
        writer.writerow([])

        # SessionTagsAndGroupsTable
        writer.writerow(["SessionTagsAndGroupsTable"])
        writer.writerow([
            "The SessionTabGroupTag column contains 19-character sequences (tags) starting with '|||'. "
            "Detected tags are 19-char candidates beginning '|||' that occur exactly 5 times (non-overlapping) "
            "in the session tab-group block (the area between the first '}' and the first http(s) URL)."
        ])
        writer.writerow(["The SessionTabGroup column contains the reconstructed human-readable group name."])
        writer.writerow(["SessionTabGroupTag", "GroupSpaced", "SessionTabGroup"])
        for e in session_tags_and_groups:
            writer.writerow([e["SessionTabGroupTag"], e["GroupSpaced"], e["SessionTabGroup"]])
        writer.writerow([])

        # SessionGroupedTabsTable
        writer.writerow(["SessionGroupedTabsTable"])
        writer.writerow([
            "Each URL is assigned by locating the pipe-interleaved instance of the same URL to its right in the Session text, "
            "then taking the first tag occurrence after that interleaved instance and assigning the URL to that tag's group. "
            "If a Tabs file is provided, the Tabs file is checked: left of the first occurrence of that URL in the Tabs file, "
            "if an interleaved tab-group-name appears with no intervening URL the group is confirmed; if another URL appears between "
            "the group name and the URL then the tab is classified as 'Ungrouped'. If the URL is not found in the Tabs file, the "
            "Session-inferred group is used."
        ])
        writer.writerow(["SessionTabGroup", "URL", "URL_Raw", "URL_RightContext"])
        for r in produced_rows:
            writer.writerow([r["SessionTabGroup"], r["URL"], r["URL_Raw"], r["URL_RightContext"]])

    # write replaced session text file (full) into parent folder
    if session_file and session_text_with_pipes:
        session_replaced_path = parent_folder / session_replaced_filename
        with open(session_replaced_path, "w", encoding="utf-8", newline="\n") as sf:
            sf.write(session_text_with_pipes)
        print(f"Wrote full replaced session content to: {session_replaced_path}")

    if tabs_file and tabs_text_with_pipes:
        tabs_replaced_path = parent_folder / tabs_replaced_filename
        with open(tabs_replaced_path, "w", encoding="utf-8", newline="\n") as tf:
            tf.write(tabs_text_with_pipes)
        print(f"Wrote full replaced tabs content to:   {tabs_replaced_path}")

    print(f"Wrote CSV summary: {csv_path}")

    # ---------------- Build Netscape-format bookmarks HTML (UTF-8) ----------------
    # Organize produced rows by SessionTabGroup
    groups_to_urls = {}
    for r in produced_rows:
        grp = r["SessionTabGroup"] if r["SessionTabGroup"] else "Ungrouped"
        groups_to_urls.setdefault(grp, []).append(r["URL"])
    groups_to_urls.setdefault("Ungrouped", [])  # ensure present

    # Build Netscape-format bookmarks HTML (UTF-8)
    now = datetime.now()
    parent_folder_name = parent_folder.name
    lines = []
    lines.append("<!DOCTYPE NETSCAPE-Bookmark-file-1>")
    lines.append(f"<!-- Generated by {code_version_string} on {now.isoformat()} -->")
    lines.append('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">')
    lines.append("<TITLE>Bookmarks</TITLE>")
    lines.append("<H1>Bookmarks</H1>")
    lines.append("<DL><p>")
    lines.append(f'    <DT><H3>{html.escape(parent_folder_name)}</H3>')
    lines.append("    <DL><p>")

    for grp in sorted(groups_to_urls.keys()):
        safe_grp_for_display = html.escape(grp)
        lines.append(f'        <DT><H3>{safe_grp_for_display}</H3>')
        lines.append("        <DL><p>")
        seen = set()
        for url in groups_to_urls[grp]:
            if url in seen:
                continue
            seen.add(url)
            safe_url = html.escape(url, quote=True)
            title = html.escape(make_bookmark_title_from_url(url))
            lines.append(f'            <DT><A HREF="{safe_url}">{title}</A>')
        lines.append("        </DL><p>")

    lines.append("    </DL><p>")
    lines.append("</DL><p>")

    # write bookmarks to file inside parent folder
    bookmarks_path = parent_folder / bookmarks_filename
    with open(bookmarks_path, "w", encoding="utf-8", newline="\n") as bf:
        bf.write("\n".join(lines))
    print(f"Wrote bookmarks file to: {bookmarks_path}")

    print(f"Created dated parent folder: {parent_folder}")
    print(f"Detected {len(session_tags_and_groups)} tab groups.")
    print(f"SessionGroupedTabs rows written after filtering: {len(produced_rows)}")


if __name__ == "__main__":
    main()
