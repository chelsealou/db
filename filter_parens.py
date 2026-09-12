#!/usr/bin/env python3
"""Filter a CSV, keeping only lines that contain an open or close parenthesis.

Usage:
    python filter_parens.py input.csv            # prints matching lines
    python filter_parens.py input.csv out.csv    # writes matching lines to out.csv
"""
import sys


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("Usage: python filter_parens.py <input.csv> [output.csv]")

    infile = args[0]
    outfile = args[1] if len(args) > 1 else None

    with open(infile, "r", newline="") as f:
        matches = [line for line in f if "(" in line or ")" in line]

    if outfile:
        with open(outfile, "w", newline="") as f:
            f.writelines(matches)
        print(f"Wrote {len(matches)} matching line(s) to {outfile}")
    else:
        sys.stdout.writelines(matches)


if __name__ == "__main__":
    main()
