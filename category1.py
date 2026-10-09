#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
category1.py  (one API call per definition)
- title = term
- text  = explanation
- skips blank explanations and definitions not in Greek (lang != 'el'), since the model is the Greek one
- writes top-3 categories into table `category` (per defID)
"""

import argparse
import sqlite3
import requests
from directories import DEFAULT_RESULTS

# Local Kevlar (docker run -p 8080:80 kevlar)
API_BASE = "http://localhost:8080"
API_PATH = "/api/predict"

MODEL = "el"

# Commit every N rows (faster than committing each insert)
COMMIT_EVERY = 250


def pick_working_endpoint(session: requests.Session, api_base: str = API_BASE, timeout: float = 20) -> str:
    """
    Check that Kevlar answers with a tiny test request and return the prediction URL.
    """
    url = api_base.rstrip("/") + API_PATH
    try:
        r = session.post(url, json={"model": MODEL, "title": "δοκιμή", "text": "δοκιμή"}, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"Kevlar is not reachable at {url}: {e}") from e
    if r.status_code != 200:
        raise RuntimeError(f"Kevlar at {url} answered HTTP {r.status_code} ({r.text[:200]})")
    return url


def kevlar_status(api_base: str = API_BASE, timeout: float = 3):
    """(True, url) αν το KEVLAR απαντά, αλλιώς (False, μήνυμα σφάλματος)."""
    try:
        return True, pick_working_endpoint(requests.Session(), api_base, timeout)
    except RuntimeError as e:
        return False, str(e)


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
      [{"description": "...", "score": 0.123,
        "mt": {"label": "...", "description": "..."},     # microthesaurus of the concept
        "do": {"label": "...", "description": "..."}}, ...]  # domain of the concept
    Keep top3 by score: (concept, score, microthesaurus, domain).
    """
    empty = ("", None, "", "")
    if not isinstance(preds, list):
        return empty, empty, empty

    preds = sorted(preds, key=lambda p: (p.get("score") is not None, p.get("score", 0)), reverse=True)[:3]

    out = []
    for p in preds:
        desc = (p.get("description") or "").strip()
        score = p.get("score", None)
        mt = ((p.get("mt") or {}).get("description") or "").strip()
        do = ((p.get("do") or {}).get("description") or "").strip()
        out.append((desc, round(score, 4) if isinstance(score, (int, float)) else None, mt, do))

    while len(out) < 3:
        out.append(empty)

    return out[0], out[1], out[2]


def run(db, api_base: str = API_BASE, progress=None) -> dict:
    """Κατηγοριοποιεί με το KEVLAR όσους ορισμούς της βάσης db δεν έχουν ακόμη κατηγορία.
    progress(done, total): προαιρετική συνάρτηση προόδου."""
    con = sqlite3.connect(db)
    cur = con.cursor()

    # category table (per definition)
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS category (
        defID   INTEGER PRIMARY KEY,
        cat1    TEXT, score1 REAL,
        cat2    TEXT, score2 REAL,
        cat3    TEXT, score3 REAL,
        mt1     TEXT, do1 TEXT,          -- μικροθησαυρός / πεδίο EuroVoc της κάθε έννοιας
        mt2     TEXT, do2 TEXT,
        mt3     TEXT, do3 TEXT,
        model   TEXT,
        api_url TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(defID) REFERENCES definitions(ID)
    );
    """)

    # Select definitions that:
    # - have a non-empty explanation
    # - are in Greek (if the extraction recorded the language)
    # - do NOT already have category row
    has_lang = "lang" in {r[1] for r in cur.execute("PRAGMA table_info(definitions)")}
    cur.execute(f"""
        SELECT d.ID, d.term, d.explanation
        FROM definitions d
        LEFT JOIN category c ON c.defID = d.ID
        WHERE c.defID IS NULL
          AND d.explanation IS NOT NULL
          AND trim(d.explanation) != ''
          {"AND d.lang = 'el'" if has_lang else ""}
        ORDER BY d.ID
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"⏳  {total} definitions to classify (non-empty explanations)")

    session = requests.Session()
    try:
        api_url = pick_working_endpoint(session, api_base)
    except RuntimeError:
        con.close()
        raise
    print(f"✅  Using Kevlar endpoint: {api_url}")

    done, failed = 0, 0
    for def_id, term, expl in rows:
        title = (term or "").strip()
        text = (expl or "").strip()

        try:
            preds = api_predict(session, api_url, title, text)
            (c1, s1, mt1, do1), (c2, s2, mt2, do2), (c3, s3, mt3, do3) = best3(preds)
        except Exception as e:
            # If API fails for this row, skip but keep going
            print(f"⚠️  defID {def_id}: API error → {e}")
            failed += 1
            continue

        # UPSERT (SQLite 3.24+)
        cur.execute("""
            INSERT INTO category (defID, cat1, score1, cat2, score2, cat3, score3,
                                  mt1, do1, mt2, do2, mt3, do3, model, api_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(defID) DO UPDATE SET
                cat1=excluded.cat1, score1=excluded.score1,
                cat2=excluded.cat2, score2=excluded.score2,
                cat3=excluded.cat3, score3=excluded.score3,
                mt1=excluded.mt1, do1=excluded.do1,
                mt2=excluded.mt2, do2=excluded.do2,
                mt3=excluded.mt3, do3=excluded.do3,
                model=excluded.model,
                api_url=excluded.api_url,
                created_at=datetime('now')
        """, (def_id, c1, s1, c2, s2, c3, s3, mt1, do1, mt2, do2, mt3, do3, MODEL, api_url))

        done += 1
        if done % COMMIT_EVERY == 0:
            con.commit()
            print(f"  …{done}/{total} definitions processed")
        if progress and (done % 50 == 0 or done == total):
            progress(done, total)

    con.commit()
    con.close()
    print(f"✅  Finished. Classified {done} definitions.")
    return {"classified": done, "failed": failed, "api_url": api_url, "model": MODEL}


def main():
    ap = argparse.ArgumentParser(description="Κατηγοριοποίηση ορισμών με το KEVLAR (EuroVoc).")
    ap.add_argument("--db", default=str(DEFAULT_RESULTS), help="βάση αποτελεσμάτων (προεπιλογή: %(default)s)")
    ap.add_argument("--api", default=API_BASE, help="διεύθυνση του KEVLAR (προεπιλογή: %(default)s)")
    args = ap.parse_args()
    run(args.db, args.api)


if __name__ == "__main__":
    main()
