"""
match_contact_ids.py
--------------------
Match a mailing list against a Salesforce Contact export and append the
Salesforce Contact ID (plus a match-status column) to the mailing list.

How matching works
------------------
* The mailing CSV has no "First Name" column, so the first name is parsed
  out of the "Formal Greeting" field: salutations (Mr., Mrs., Dr., ...) are
  dropped, and joint greetings like "Mrs. Timothy and Mrs. Julie Cremins"
  yield BOTH first names (Timothy, Julie), each tried against the export.
* Candidates are found by First Name + Last Name (case/punctuation-insensitive).
* When several Salesforce contacts share that name, the one whose address
  best matches the mailing address is chosen ("best match").
* A "Match Status" column records how many name-matches were found for the
  row: a number (1, 2, 3, ...) or the word "none".

Usage
-----
1. Set the three file paths in the CONFIG section below.
2. Run in VS Code (or: `python match_contact_ids.py`).
3. A new CSV is written; your original mailing file is never modified.

No third-party packages required (standard library only).
"""

import csv
import re
import sys
from difflib import SequenceMatcher

# ============================ CONFIG ============================
# Edit these three paths, then run the file.

MAILING_CSV = "mailing.csv"                 # CSV #1: names + addresses for the mailing
SALESFORCE_CSV = "salesforce_contacts.csv"  # CSV #2: Salesforce Contact export
OUTPUT_CSV = "mailing_with_contact_ids.csv" # New file to create (original is untouched)

# --- Column headers ---------------------------------------------------------
# If your real export uses slightly different header text, change it here.

# Mailing CSV (CSV #1) columns used for matching:
MAIL_FORMAL_GREETING = "Formal Greeting"   # first name is parsed from this field
MAIL_LAST_NAME = "Last Name"
MAIL_STREET = "Street"
MAIL_CITY = "City"
MAIL_STATE = "State/Province"
MAIL_ZIP = "Zip/Postal Code"

# Salesforce CSV (CSV #2) columns:
SF_FIRST_NAME = "First Name"
SF_LAST_NAME = "Last Name"
SF_STREET = "Street"
SF_CITY = "City"
SF_STATE = "State/Province"
SF_ZIP = "Zip/Postal Code"
SF_CONTACT_ID = "Contact ID"

# Names of the columns that will be added to the output file:
OUT_CONTACT_ID = "Contact ID"
OUT_MATCH_STATUS = "Match Status"
OUT_MATCHED_NAME = "Matched Contact"  # QA helper (matched SF name) -- delete if unwanted
# ================================================================


# Salutations to strip from the Formal Greeting (compared lowercased, no dots).
SALUTATIONS = {
    "mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "rev",
    "reverend", "sir", "madam", "madame", "mister", "fr", "father", "hon",
    "honorable", "capt", "captain", "lt", "col", "sgt", "gen", "rabbi",
    "pastor", "deacon", "elder", "bishop", "the",
}

# Common US street-type abbreviations, normalized so "Street" == "St", etc.
STREET_ABBREV = {
    "street": "st", "avenue": "ave", "av": "ave", "boulevard": "blvd",
    "drive": "dr", "road": "rd", "lane": "ln", "court": "ct", "circle": "cir",
    "place": "pl", "terrace": "ter", "trail": "trl", "parkway": "pkwy",
    "highway": "hwy", "square": "sq", "suite": "ste", "apartment": "apt",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}


def norm_text(value):
    """Lowercase, drop punctuation, collapse whitespace. Safe on None."""
    if value is None:
        return ""
    text = str(value).lower()
    text = re.sub(r"[^\w\s]", " ", text)   # punctuation -> space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def norm_name(value):
    """Normalize a first/last name for comparison."""
    return norm_text(value)


def norm_street(value):
    """Normalize a street line, expanding common abbreviations."""
    tokens = norm_text(value).split()
    tokens = [STREET_ABBREV.get(tok, tok) for tok in tokens]
    return " ".join(tokens)


def norm_zip(value):
    """Keep the first 5 digits of a ZIP/postal code."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:5]


def parse_first_names(formal_greeting):
    """
    Pull the first name(s) out of the Formal Greeting field.

    Handles salutations and joint greetings. Returns a list of candidate
    first names (usually one, two for a couple):

        "John Smith"                          -> ["john"]
        "Mr. John Smith"                      -> ["john"]
        "Mrs. Timothy and Mrs. Julie Cremins" -> ["timothy", "julie"]
        "Mr. & Mrs. John Smith"               -> ["john"]

    For each side of an "and"/"&" split, leading salutations are dropped and
    the first remaining word is taken as the first name.
    """
    text = (formal_greeting or "").strip()
    if not text:
        return []

    parts = re.split(r"(?i)\s+and\s+|\s*&\s*", text)
    names = []
    for part in parts:
        tokens = norm_text(part).split()          # lowercased, punctuation removed
        idx = 0
        while idx < len(tokens) and tokens[idx] in SALUTATIONS:
            idx += 1
        if idx < len(tokens):
            first = tokens[idx]
            if first not in names:                # de-dupe, keep order
                names.append(first)
    return names


def address_score(mail_row, sf_row):
    """
    Score how well a Salesforce contact's address matches the mailing row.
    Higher is better. Used to choose the best contact when a name is shared.
    """
    score = 0.0

    # ZIP: strong signal.
    if norm_zip(mail_row.get(MAIL_ZIP)) and \
       norm_zip(mail_row.get(MAIL_ZIP)) == norm_zip(sf_row.get(SF_ZIP)):
        score += 3.0

    # Street: fuzzy similarity (0..1) scaled up, with a bonus for exact match.
    mail_st = norm_street(mail_row.get(MAIL_STREET))
    sf_st = norm_street(sf_row.get(SF_STREET))
    if mail_st and sf_st:
        ratio = SequenceMatcher(None, mail_st, sf_st).ratio()
        score += ratio * 4.0
        if mail_st == sf_st:
            score += 1.0

    # City / State: light corroboration.
    if norm_text(mail_row.get(MAIL_CITY)) and \
       norm_text(mail_row.get(MAIL_CITY)) == norm_text(sf_row.get(SF_CITY)):
        score += 1.0
    if norm_text(mail_row.get(MAIL_STATE)) and \
       norm_text(mail_row.get(MAIL_STATE)) == norm_text(sf_row.get(SF_STATE)):
        score += 1.0

    return score


def read_csv(path):
    """Read a CSV into (list-of-dict-rows, fieldnames). Handles BOM."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            return rows, reader.fieldnames or []
    except FileNotFoundError:
        sys.exit(f"ERROR: file not found: {path}")


def require_columns(fieldnames, needed, which):
    """Fail early with a clear message if an expected header is missing."""
    missing = [c for c in needed if c not in fieldnames]
    if missing:
        sys.exit(
            f"ERROR: the {which} CSV is missing expected column(s): "
            f"{missing}\nFound columns: {fieldnames}\n"
            f"Fix the header names in the CONFIG section of this script."
        )


def build_sf_index(sf_rows):
    """Index Salesforce contacts by (first_name, last_name) -> [rows]."""
    index = {}
    for row in sf_rows:
        key = (norm_name(row.get(SF_FIRST_NAME)), norm_name(row.get(SF_LAST_NAME)))
        index.setdefault(key, []).append(row)
    return index


def main():
    mail_rows, mail_fields = read_csv(MAILING_CSV)
    sf_rows, sf_fields = read_csv(SALESFORCE_CSV)

    require_columns(mail_fields, [MAIL_FORMAL_GREETING, MAIL_LAST_NAME], "mailing")
    require_columns(sf_fields, [SF_FIRST_NAME, SF_LAST_NAME, SF_CONTACT_ID], "Salesforce")

    sf_index = build_sf_index(sf_rows)

    out_fields = list(mail_fields) + [OUT_CONTACT_ID, OUT_MATCH_STATUS, OUT_MATCHED_NAME]

    matched = 0
    multiple = 0
    unmatched = 0

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as out_fh:
        writer = csv.DictWriter(out_fh, fieldnames=out_fields)
        writer.writeheader()

        for row in mail_rows:
            first_names = parse_first_names(row.get(MAIL_FORMAL_GREETING))
            last = row.get(MAIL_LAST_NAME)

            # Gather Salesforce contacts matching last name + ANY parsed first
            # name (a joint greeting yields two), de-duplicated.
            candidates = []
            seen = set()
            for first in first_names:
                for sf in sf_index.get((norm_name(first), norm_name(last)), []):
                    if id(sf) not in seen:
                        seen.add(id(sf))
                        candidates.append(sf)

            if not candidates:
                row[OUT_CONTACT_ID] = ""
                row[OUT_MATCH_STATUS] = "none"
                row[OUT_MATCHED_NAME] = ""
                unmatched += 1
            else:
                # Choose the candidate whose address best matches the mailing row.
                best = max(candidates, key=lambda sf: address_score(row, sf))
                row[OUT_CONTACT_ID] = best.get(SF_CONTACT_ID, "")
                row[OUT_MATCH_STATUS] = str(len(candidates))
                row[OUT_MATCHED_NAME] = \
                    f"{best.get(SF_FIRST_NAME, '')} {best.get(SF_LAST_NAME, '')}".strip()
                matched += 1
                if len(candidates) > 1:
                    multiple += 1

            writer.writerow(row)

    total = len(mail_rows)
    print(f"Done. Wrote {total} rows to: {OUTPUT_CSV}")
    print(f"  Matched (1+ name match): {matched}")
    print(f"    of which had multiple name matches (best address chosen): {multiple}")
    print(f"  No match: {unmatched}")


if __name__ == "__main__":
    main()
