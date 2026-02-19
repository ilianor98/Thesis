#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
category.py  (one API call per definition)
- title = term
- text  = explanation
- skips blank explanations
- writes top-3 categories into table `category` (per defID)
"""

import sqlite3
import requests
import time
from pathlib import Path
from directories import *

# Pick the DB that contains `definitions`
ORISMOI_DB = SPITI_PC_ORISMOI_TEST1   # <-- change if needed (e.g. SPITI_PC_ORISMOI_TEST)

# Local Kevlar (docker: -p 8080:80)
API_BASE = "http://localhost:8080"
API_PATH_CANDIDATES = ["/api/predict", "/predict", "/api/classify", "/classify"]  # fallback list

MODEL = "el"

# Local machine: usually no delay needed. If you want, set 0.01–0.1
DELAY_SEC = 0.0

# Commit every N rows (faster than committing each insert)
COMMIT_EVERY = 250


def pick_working_endpoint(session: requests.Session) -> str:
    """
    Try known Kevlar endpoints. We do a tiny test request; first one that responds 200 is used.
    """
    payload = {"model": MODEL, "title": "δοκιμή", "text": "δοκιμή"}
    last_err = None

    for path in API_PATH_CANDIDATES:
        url = API_BASE + path
        try:
            r = session.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                return url
            last_err = f"{url} -> HTTP {r.status_code} ({r.text[:200]})"
        except Exception as e:
            last_err = f"{url} -> {e}"

    raise RuntimeError(f"Could not find a working Kevlar endpoint. Last error: {last_err}")


def api_predict(session: requests.Session, api_url: str, title: str, text: str):
    r = session.post(
        api_url,
        json={"model": MODEL, "title": title, "text": text},
        timeout=40
    )
    r.raise_for_status()
    return r.json()


def best3(preds):
    """
    Expecting preds like:
      [{"description": "...", "score": 0.123}, ...]
    Keep top3 by score.
    """
    if not isinstance(preds, list):
        return [("", None), ("", None), ("", None)]

    preds = sorted(preds, key=lambda p: (p.get("score") is not None, p.get("score", 0)), reverse=True)[:3]

    out = []
    for p in preds:
        desc = (p.get("description") or "").strip()
        score = p.get("score", None)
        out.append((desc, round(score, 4) if isinstance(score, (int, float)) else None))

    while len(out) < 3:
        out.append(("", None))

    return out[0], out[1], out[2]


def main():
    con = sqlite3.connect(ORISMOI_DB)
    cur = con.cursor()

    # category table (per definition)
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS category (
        defID   INTEGER PRIMARY KEY,
        cat1    TEXT, score1 REAL,
        cat2    TEXT, score2 REAL,
        cat3    TEXT, score3 REAL,
        model   TEXT,
        api_url TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(defID) REFERENCES definitions(ID)
    );
    """)

    # Select definitions that:
    # - have a non-empty explanation
    # - do NOT already have category row
    cur.execute("""
        SELECT d.ID, d.term, d.explanation
        FROM definitions d
        LEFT JOIN category c ON c.defID = d.ID
        WHERE c.defID IS NULL
          AND d.explanation IS NOT NULL
          AND trim(d.explanation) != ''
        ORDER BY d.ID
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"⏳  {total} definitions to classify (non-empty explanations)")

    session = requests.Session()
    api_url = pick_working_endpoint(session)
    print(f"✅  Using Kevlar endpoint: {api_url}")

    done = 0
    for def_id, term, expl in rows:
        title = (term or "").strip()
        text = (expl or "").strip()

        try:
            preds = api_predict(session, api_url, title, text)
            (c1, s1), (c2, s2), (c3, s3) = best3(preds)
        except Exception as e:
            # If API fails for this row, skip but keep going
            print(f"⚠️  defID {def_id}: API error → {e}")
            continue

        # UPSERT (SQLite 3.24+). If your SQLite is older, tell me and I’ll switch to INSERT OR REPLACE.
        cur.execute("""
            INSERT INTO category (defID, cat1, score1, cat2, score2, cat3, score3, model, api_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(defID) DO UPDATE SET
                cat1=excluded.cat1, score1=excluded.score1,
                cat2=excluded.cat2, score2=excluded.score2,
                cat3=excluded.cat3, score3=excluded.score3,
                model=excluded.model,
                api_url=excluded.api_url,
                created_at=datetime('now')
        """, (def_id, c1, s1, c2, s2, c3, s3, MODEL, api_url))

        done += 1
        if done % COMMIT_EVERY == 0:
            con.commit()
            print(f"  …{done}/{total} definitions processed")

        if DELAY_SEC > 0:
            time.sleep(DELAY_SEC)

    con.commit()
    con.close()
    print(f"✅  Finished. Classified {done} definitions.")


if __name__ == "__main__":
    main()
