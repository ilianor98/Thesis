#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
category.py  (one API call per law, skip blank explanations)
"""

import sqlite3, requests, time
from pathlib import Path

ORISMOI_DB   = Path("orismoi.db")
HARVESTER_DB = Path(r"C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/harvester.db")
API_URL      = "http://147.102.74.52:8080/api/predict"
MODEL        = "el"
DELAY_SEC    = 0.3

# ───────── helpers ───────────────────────────────────────────────────────
def api_predict(title, text):
    r = requests.post(API_URL,
                      json={"model": MODEL, "title": title, "text": text},
                      timeout=40)
    r.raise_for_status()
    return r.json()

def best3(preds):
    preds = sorted(preds, key=lambda p: p["score"], reverse=True)[:3]
    while len(preds) < 3:
        preds.append({"description": "", "score": None})
    return [(p["description"],
             round(p["score"], 4) if p["score"] is not None else None)
            for p in preds]

# ───────── main ──────────────────────────────────────────────────────────
def main():
    or_con = sqlite3.connect(ORISMOI_DB)
    or_cur = or_con.cursor()
    et_con = sqlite3.connect(HARVESTER_DB)
    et_cur = et_con.cursor()

    or_cur.executescript("""
    CREATE TABLE IF NOT EXISTS category (
        defID  INTEGER PRIMARY KEY,
        cat1   TEXT, score1 REAL,
        cat2   TEXT, score2 REAL,
        cat3   TEXT, score3 REAL,
        FOREIGN KEY(defID) REFERENCES definitions(ID)
    );
    """)

    # ► pick distinct laws where *some* definition (with explanation) lacks category
    or_cur.execute("""
        SELECT DISTINCT d.fekID
        FROM definitions d
        LEFT JOIN category c ON c.defID = d.ID
        WHERE c.defID IS NULL
          AND d.explanation IS NOT NULL
          AND trim(d.explanation) != ''
    """)
    fek_ids = [row[0] for row in or_cur.fetchall()]
    total = len(fek_ids)
    print(f"⏳  {total} laws to classify (non‑empty explanations)")

    for idx, fek_id in enumerate(fek_ids, 1):
        et_cur.execute("SELECT nomosTitle, fekTEXT FROM et WHERE ID = ?", (fek_id,))
        title, fek_text = et_cur.fetchone() or ("", "")

        try:
            preds = api_predict(title or "", fek_text or "")
        except Exception as e:
            print(f"⚠️  fekID {fek_id}: API error → {e}")
            continue

        (c1,s1), (c2,s2), (c3,s3) = best3(preds)

        # definitions of this law missing category & with non‑empty explanation
        or_cur.execute("""
            SELECT d.ID
            FROM definitions d
            LEFT JOIN category c ON c.defID = d.ID
            WHERE d.fekID = ?
              AND c.defID IS NULL
              AND d.explanation IS NOT NULL
              AND trim(d.explanation) != ''
        """, (fek_id,))
        def_ids = [r[0] for r in or_cur.fetchall()]

        or_cur.executemany("""
            INSERT INTO category
                (defID, cat1, score1, cat2, score2, cat3, score3)
            VALUES  (?,     ?,    ?,      ?,    ?,      ?,    ?)
        """, [(did, c1, s1, c2, s2, c3, s3) for did in def_ids])

        if idx % 50 == 0:
            print(f"  …{idx}/{total} laws processed")
            or_con.commit()

        time.sleep(DELAY_SEC)

    or_con.commit()
    or_con.close(); et_con.close()
    print("✅  Finished.")

if __name__ == "__main__":
    main()
