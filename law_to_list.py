#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Break the fekTEXT of one law into a Python list of "bullet items".

Usage
-----
python law_to_list.py --id 12345 [--json out.json]

The ID is the primary key of table `et` in harvester.db
"""
import argparse, json, re, sys, sqlite3
from pathlib import Path

HARVESTER_DB = Path(r"C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/harvester.db")

# ----------------------------------------------------------------------
# Regex that finds list markers (greek letters, numbers, roman numerals)
# ----------------------------------------------------------------------
BULLET_RE = re.compile(r"""
    ^\s*                                   # line-start + optional spaces
    (                                       # ---- the marker ----
        \d+                                 #   1  2  3
        | [α-ωάέήίόύώ]                      #   α  β  γ
        | (?=[ivxlcdm]+\b) [ivxlcdm]+       #   i  iv  x  (roman)
    )
    [\).]\s+                                # delimiter  ) or .
""", re.I | re.M | re.X | re.U)

def get_fek_text(db: Path, fek_id: int) -> str:
    """Return fekTEXT for a given ID from table et."""
    conn = sqlite3.connect(db)
    cur  = conn.cursor()
    cur.execute("SELECT fekTEXT FROM et WHERE ID = ?", (fek_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        raise ValueError(f"No fekTEXT found for ID {fek_id}")
    return row[0]

def split_into_items(text: str) -> list[dict]:
    """
    Returns list of dictionaries:
        { 'marker': '1', 'body': '…', 'start': 123, 'end': 456 }
    """
    items = []
    last_pos = 0
    for m in BULLET_RE.finditer(text):
        if items:
            items[-1]["end"] = m.start()            # close previous item
        items.append({
            "marker": m.group(1),
            "body":   "",       # (filled later)
            "start":  m.end(),  # body starts right after the marker
            "end":    None
        })
        last_pos = m.end()

    # final item body extends to EOF
    if items:
        items[-1]["end"] = len(text)

    # fill bodies
    for item in items:
        item["body"] = text[item["start"]: item["end"]].strip()

    return items


def main():
    ap = argparse.ArgumentParser(description="Break one law into list items")
    ap.add_argument("--id", type=int, required=True, help="ID of law in table et")
    ap.add_argument("--json", type=Path, help="Optional JSON export filename")
    args = ap.parse_args()

    # 1. get text
    fek_text = get_fek_text(HARVESTER_DB, args.id)

    # 2. split
    items = split_into_items(fek_text)

    # 3. pretty-print
    if not items:
        print("⚠️  No bullet markers detected.")
    else:
        print(f"🗂  Found {len(items)} bullet items:\n")
        for i, it in enumerate(items, 1):
            print(f"{i}. [{it['marker']}] {it['body'][:120]}{'…' if len(it['body'])>120 else ''}\n")

    # 4. optional JSON export
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Saved full list to {args.json}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"ERROR: {exc}")
