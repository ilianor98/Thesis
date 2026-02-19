# score_defs.py
# Computes a confidence score for each row in definitions and stores it in a new table: score
# Usage:
#   python score_defs.py                         (uses a default DB from directories.py if found)
#   python score_defs.py "C:\path\to\orismoi.db"  (explicit DB path)

import re
import json
import sqlite3
import sys
import time
from pathlib import Path
from directories import *

# ───────────────────── 0. Try to get a default DB path from directories.py (optional)
DEFAULT_DB = SPITI_PC_ORISMOI_TEST1
try:
    from directories import *  # noqa: F401,F403

    # Try common names you've used before (extend this list if needed)
    for _name in (
        "SPITI_PC_ORISMOI_TEST",
        "SPITI_PC_ORISMOI",
        "STRATOS_PC_ORISMOI",
        "SPITI_PC_ORISMOI_NLP",
    ):
        if _name in globals():
            DEFAULT_DB = globals()[_name]
            break
except Exception:
    pass


# ───────────────────── 1. Patterns / signals
DEF_VERBS = [
    "ορίζεται", "ορίζονται",
    "νοείται", "νοούνται",
    "σημαίνει", "σημαίνουν",
    "εννοείται", "εννοούνται",
    "καθορίζεται", "καθορίζονται",
    "θεωρείται", "θεωρούνται",
]

SCOPE_PHRASES = [
    "Για τους σκοπούς",
    "για τους σκοπούς",
    "Για την εφαρμογή",
    "για την εφαρμογή",
    "νοούνται ως",
    "νοείται ως",
    "νοούνται:",
    "νοείται:",
]

ARTICLE_HEADERS_RGX = re.compile(r"\b(ΑΡΘΡΟ|Άρθρο|ΚΕΦΑΛΑΙΟ|ΤΜΗΜΑ|ΠΑΡΑΡΤΗΜΑ)\b")
BIG_HEADERS_RGX = re.compile(r"\b(ΝΟΜΟΣ|ΠΡΟΕΔΡΟΣ|ΚΥΒΕΡΝΗΣΗ|ΔΗΜΟΚΡΑΤΙΑ|ΦΕΚ)\b")
AMENDMENT_RGX = re.compile(
    r"\b(αντικαθίσταται|τροποποιείται|διαγράφονται|προστίθεται|καταργείται|αναριθμούνται|όπου\s+αναγράφεται)\b",
    re.I,
)

NESTED_BULLETS_RGX = re.compile(
    r"(\b[α-ωάέήίόύώ]{1,2}\)|\b\d+\)|\bζ[α-ωάέήίόύώ]\))",
    re.I,
)

TERM_SUS_RGX = re.compile(
    r"\b(ορίζεται|νοείται|σημαίνει|εννοείται|καθορίζεται|θεωρείται|δύναται|μπορεί)\b",
    re.I,
)


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def ends_clean(expl: str):
    t = (expl or "").strip()
    if not t:
        return (0, "")
    last = t[-1]
    # "clean" endings for definitions
    if last in ".;»”":
        return (1, last)
    # suspicious endings
    if last in ":,":
        return (0, last)
    return (0, last)


def find_window(excerpt: str, term: str, window_after: int = 260) -> str:
    if not excerpt or not term:
        return excerpt or ""
    idx = excerpt.find(term)
    if idx == -1:
        # try case-insensitive find (Greek case can be tricky, but this helps)
        low_ex = excerpt.lower()
        low_term = term.lower()
        idx = low_ex.find(low_term)
        if idx == -1:
            return excerpt
    return excerpt[idx : min(len(excerpt), idx + window_after)]


def has_term_in_quotes(excerpt: str, term: str) -> int:
    if not excerpt or not term:
        return 0
    # try exact-term-in-quotes check
    pat = re.compile(rf'[«"]\s*{re.escape(term)}\s*[»"]')
    return 1 if pat.search(excerpt) else 0


def has_def_verb_near(excerpt: str, term: str) -> int:
    w = find_window(excerpt or "", term or "")
    wl = w.lower()
    return 1 if any(v in wl for v in DEF_VERBS) else 0


def has_scope_phrase(excerpt: str) -> int:
    if not excerpt:
        return 0
    return 1 if any(p in excerpt for p in SCOPE_PHRASES) else 0


def compute_confidence(row: dict):
    """
    Returns:
      confidence (float),
      features (dict),
      contributions (dict)
    """
    term = row.get("term") or ""
    expl = row.get("explanation") or ""
    excerpt = row.get("excerpt") or ""
    tag = (row.get("pattern_tag") or "").strip()
    bullet = row.get("bullet") or ""

    term_len = len(term.strip())
    expl_len = len(expl.strip())
    excerpt_len = len(excerpt)

    f_has_quotes = has_term_in_quotes(excerpt, term)
    f_has_verb = has_def_verb_near(excerpt, term)
    f_scope_phrase = has_scope_phrase(excerpt)
    f_nested = 1 if NESTED_BULLETS_RGX.search(expl) else 0

    f_article_hdr = 1 if ARTICLE_HEADERS_RGX.search(expl) else 0
    f_big_hdr = 1 if BIG_HEADERS_RGX.search(expl) else 0
    f_amendment = 1 if AMENDMENT_RGX.search(expl) else 0

    para_count = excerpt.count("¶")
    para_density = para_count / max(1.0, (excerpt_len / 200.0))

    f_term_susp = 1 if (TERM_SUS_RGX.search(term) or term_len > 120 or term.count(" ") > 12) else 0
    f_expl_empty = 1 if expl_len == 0 else 0
    f_expl_too_short = 1 if (0 < expl_len < 20) else 0
    f_expl_too_long = 1 if expl_len > 3500 else 0

    f_ends_clean, ends_with = ends_clean(expl)

    # ───────────────────── scoring (rule-based)
    score = 0.10
    contrib = {"base": 0.10}

    # tag reliability
    if tag == "bullet":
        score += 0.20; contrib["tag_bullet"] = 0.20
    elif tag == "verb":
        score += 0.15; contrib["tag_verb"] = 0.15
    elif tag == "scope":
        score += 0.05; contrib["tag_scope"] = 0.05
    else:
        contrib["tag_other"] = 0.0

    # structural cues
    if f_has_quotes:
        score += 0.15; contrib["has_quotes"] = 0.15
    if f_has_verb:
        score += 0.20; contrib["has_def_verb"] = 0.20
    if f_scope_phrase:
        score += 0.05; contrib["has_scope_phrase"] = 0.05
    if f_nested:
        score += 0.05; contrib["has_nested_bullets"] = 0.05

    # explanation length quality
    if f_expl_empty:
        score -= 0.40; contrib["expl_empty"] = -0.40
    elif f_expl_too_short:
        score -= 0.25; contrib["expl_too_short"] = -0.25
    elif expl_len < 40:
        score -= 0.10; contrib["expl_shortish"] = -0.10
    elif 40 <= expl_len <= 2000:
        score += 0.10; contrib["expl_good_len"] = 0.10
    elif expl_len > 2500:
        score -= 0.05; contrib["expl_very_long"] = -0.05

    # ending cleanliness
    if f_ends_clean:
        score += 0.05; contrib["ends_clean"] = 0.05
    else:
        if ends_with in [":", ","]:
            score -= 0.10; contrib["ends_suspicious"] = -0.10

    # bleed / wrong-boundary cues
    if f_article_hdr:
        score -= 0.25; contrib["contains_article_header"] = -0.25
    if f_big_hdr:
        score -= 0.25; contrib["contains_big_header"] = -0.25
    if f_amendment:
        score -= 0.15; contrib["contains_amendment"] = -0.15

    # too many paragraph markers often means “swallowed more than needed”
    if para_density > 4.0:
        score -= 0.10; contrib["high_para_density"] = -0.10

    # suspicious term shape
    if f_term_susp:
        score -= 0.25; contrib["term_suspicious"] = -0.25

    if f_expl_too_long:
        score -= 0.10; contrib["expl_too_long"] = -0.10

    score = clamp01(score)

    features = {
        "pattern_tag": tag,
        "bullet": bullet,
        "term_len": term_len,
        "expl_len": expl_len,
        "excerpt_len": excerpt_len,
        "has_quotes": f_has_quotes,
        "has_def_verb": f_has_verb,
        "has_scope_phrase": f_scope_phrase,
        "has_nested_bullets": f_nested,
        "ends_clean": f_ends_clean,
        "ends_with": ends_with,
        "contains_article_header": f_article_hdr,
        "contains_big_header": f_big_hdr,
        "contains_amendment": f_amendment,
        "para_count": para_count,
        "para_density": para_density,
        "term_suspicious": f_term_susp,
        "expl_empty": f_expl_empty,
        "expl_too_short": f_expl_too_short,
        "expl_too_long": f_expl_too_long,
    }

    return score, features, contrib


# ───────────────────── 2. DB ops
def ensure_schema(cur: sqlite3.Cursor):
    cur.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS score (
        def_id                 INTEGER PRIMARY KEY,
        confidence             REAL    NOT NULL,
        needs_review           INTEGER NOT NULL,

        pattern_tag            TEXT,
        bullet                 TEXT,

        term_len               INTEGER,
        expl_len               INTEGER,
        excerpt_len            INTEGER,

        has_quotes             INTEGER,
        has_def_verb           INTEGER,
        has_scope_phrase       INTEGER,
        has_nested_bullets     INTEGER,

        ends_clean             INTEGER,
        ends_with              TEXT,

        contains_article_header INTEGER,
        contains_big_header     INTEGER,
        contains_amendment      INTEGER,

        para_count             INTEGER,
        para_density           REAL,

        term_suspicious        INTEGER,
        expl_empty             INTEGER,
        expl_too_short         INTEGER,
        expl_too_long          INTEGER,

        rule_version           TEXT,
        contributions_json     TEXT,

        created_at             TEXT DEFAULT (datetime('now')),

        FOREIGN KEY(def_id) REFERENCES definitions(ID) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_score_confidence ON score(confidence);
    """)


def main():
    db_path = None
    if len(sys.argv) >= 2:
        db_path = sys.argv[1]
    elif DEFAULT_DB:
        db_path = DEFAULT_DB

    if not db_path:
        print("[-] No DB path provided and no default found from directories.py.")
        print('    Run: python score_defs.py "C:\\path\\to\\orismoi.db"')
        sys.exit(1)

    db_path = str(Path(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    ensure_schema(cur)
    conn.commit()

    total = cur.execute("SELECT COUNT(*) FROM definitions").fetchone()[0]
    print(f"[i] DB: {db_path}")
    print(f"[i] definitions rows: {total}")

    # Stream rows (avoid loading all in memory)
    cur2 = conn.cursor()
    cur2.execute("SELECT ID, term, explanation, excerpt, bullet, pattern_tag FROM definitions")

    insert_sql = """
    INSERT INTO score (
        def_id, confidence, needs_review,
        pattern_tag, bullet,
        term_len, expl_len, excerpt_len,
        has_quotes, has_def_verb, has_scope_phrase, has_nested_bullets,
        ends_clean, ends_with,
        contains_article_header, contains_big_header, contains_amendment,
        para_count, para_density,
        term_suspicious, expl_empty, expl_too_short, expl_too_long,
        rule_version, contributions_json
    )
    VALUES (
        ?, ?, ?,
        ?, ?,
        ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?,
        ?, ?, ?,
        ?, ?,
        ?, ?, ?, ?,
        ?, ?
    )
    ON CONFLICT(def_id) DO UPDATE SET
        confidence=excluded.confidence,
        needs_review=excluded.needs_review,
        pattern_tag=excluded.pattern_tag,
        bullet=excluded.bullet,
        term_len=excluded.term_len,
        expl_len=excluded.expl_len,
        excerpt_len=excluded.excerpt_len,
        has_quotes=excluded.has_quotes,
        has_def_verb=excluded.has_def_verb,
        has_scope_phrase=excluded.has_scope_phrase,
        has_nested_bullets=excluded.has_nested_bullets,
        ends_clean=excluded.ends_clean,
        ends_with=excluded.ends_with,
        contains_article_header=excluded.contains_article_header,
        contains_big_header=excluded.contains_big_header,
        contains_amendment=excluded.contains_amendment,
        para_count=excluded.para_count,
        para_density=excluded.para_density,
        term_suspicious=excluded.term_suspicious,
        expl_empty=excluded.expl_empty,
        expl_too_short=excluded.expl_too_short,
        expl_too_long=excluded.expl_too_long,
        rule_version=excluded.rule_version,
        contributions_json=excluded.contributions_json
    ;
    """

    BATCH = 1000
    buf = []
    t0 = time.time()
    done = 0

    RULE_VERSION = "rule_v1.0"

    for r in cur2:
        row = dict(r)
        conf, feats, contrib = compute_confidence(row)
        needs_review = 1 if conf < 0.75 else 0

        buf.append((
            row["ID"], conf, needs_review,
            feats["pattern_tag"], feats["bullet"],
            feats["term_len"], feats["expl_len"], feats["excerpt_len"],
            feats["has_quotes"], feats["has_def_verb"], feats["has_scope_phrase"], feats["has_nested_bullets"],
            feats["ends_clean"], feats["ends_with"],
            feats["contains_article_header"], feats["contains_big_header"], feats["contains_amendment"],
            feats["para_count"], feats["para_density"],
            feats["term_suspicious"], feats["expl_empty"], feats["expl_too_short"], feats["expl_too_long"],
            RULE_VERSION, json.dumps(contrib, ensure_ascii=False)
        ))

        if len(buf) >= BATCH:
            conn.executemany(insert_sql, buf)
            conn.commit()
            done += len(buf)
            buf.clear()

            # progress
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            pct = (done / total * 100.0) if total else 100.0
            print(f"\r[+] Scored {done}/{total} ({pct:.1f}%)  |  {rate:.1f} rows/s", end="")

    if buf:
        conn.executemany(insert_sql, buf)
        conn.commit()
        done += len(buf)

    print()
    print(f"[+] Done. Scored rows: {done}")
    # quick stats
    stats = conn.execute("""
        SELECT
          ROUND(AVG(confidence), 4) AS avg_conf,
          SUM(needs_review) AS needs_review_cnt,
          ROUND(AVG(CASE WHEN pattern_tag='scope' THEN confidence END), 4) AS avg_scope,
          ROUND(AVG(CASE WHEN pattern_tag='bullet' THEN confidence END), 4) AS avg_bullet,
          ROUND(AVG(CASE WHEN pattern_tag='verb' THEN confidence END), 4) AS avg_verb
        FROM score
    """).fetchone()

    print(f"[i] avg confidence: {stats[0]}")
    print(f"[i] needs_review (<0.75): {stats[1]}")
    print(f"[i] avg by tag: bullet={stats[3]} | verb={stats[4]} | scope={stats[2]}")

    conn.close()


if __name__ == "__main__":
    main()
