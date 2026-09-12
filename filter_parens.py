#!/usr/bin/env python3
"""Filter a CSV, keeping only lines that contain an open or close parenthesis.

Just set the two paths below, then hit the Run button in VS Code.
"""

# ---------------------------------------------------------------------------
# EDIT THESE TWO LINES:
INPUT_FILE = "yourfile.csv"     # <- paste the path to your input CSV here
OUTPUT_FILE = None              # <- set to "output.csv" to save, or leave None to just print
# ---------------------------------------------------------------------------


def main():
    with open(INPUT_FILE, "r", newline="") as f:
        matches = [line for line in f if "(" in line or ")" in line]

    if OUTPUT_FILE:
        with open(OUTPUT_FILE, "w", newline="") as f:
            f.writelines(matches)
        print(f"Wrote {len(matches)} matching line(s) to {OUTPUT_FILE}")
    else:
        for line in matches:
            print(line, end="")


if __name__ == "__main__":
    main()
