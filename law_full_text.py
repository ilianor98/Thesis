#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetch the complete fekTEXT of one law from harvester.db.

Usage
-----
python law_full_text.py --id 87321
python law_full_text.py --id 87321 --out law_87321.txt
"""
import argparse, sqlite3, sys
from pathlib import Path

HARVESTER_DB = Path(r"C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/harvester.db")

# ────────────────────────────────────────────────────────
def get_full_text(fek_id: int) -> str:
    con = sqlite3.connect(HARVESTER_DB)
    cur = con.cursor()
    cur.execute("SELECT fekTEXT FROM et WHERE ID = ?", (fek_id,))
    row = cur.fetchone()
    con.close()
    if not row or not row[0]:
        raise ValueError(f"No fekTEXT found for ID {fek_id}")
    return row[0]

# ────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Print / save full fekTEXT")
    ap.add_argument("--id", type=int, required=True, help="ID from table et")
    ap.add_argument("--out", type=Path, help="Optional output .txt file")
    args = ap.parse_args()

    try:
        text = get_full_text(args.id)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")

    # 1. console output
    print(f"\n-----  FULL TEXT for ID {args.id}  -----\n")
    print(text)

    # 2. optional file save
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"\n✅  Saved full text to {args.out}")

# ────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
