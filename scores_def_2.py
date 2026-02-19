# rescore_to_score2.py
import sqlite3, re, json
from directories import *

DB = SPITI_PC_ORISMOI_TEST1  # same DB that has definitions + score

# ───────────────────────── Regex helpers
GREEK_RE = re.compile(r"[Α-Ωα-ωάέήίόύώ]")

STOP_HDR_RE = re.compile(
    r"(?:^|¶)\s*(Άρθρο|ΑΡΘΡΟ|ΚΕΦΑΛΑΙΟ|ΤΜΗΜΑ|ΜΕΡΟΣ|ΠΑΡΑΡΤΗΜΑ|ΠΡΩΤΟΚΟΛΛΟ|ΚΑΤΑΛΟΓΟΣ|ΠΙΝΑΚΑΣ)\b",
    re.I
)
NESTED_BULLET_RE = re.compile(r"(?:^|¶)\s*[α-ωάέήίόύώ]{1,2}[\)\.]", re.I)

DEF_VERB_RE = re.compile(
    r"\b(ορίζ(?:εται|ονται)|νοείτ(?:αι|ουν)|σημαίν(?:ει|ουν)|θεωρείτ(?:αι|ουν)|καθορίζ(?:εται|ονται))\b",
    re.I
)
SCOPE_PHRASE_RE = re.compile(r"\b(για\s+τους\s+σκοπούς|για\s+την\s+εφαρμογή|νοούνται\s+ως|νοείται\s+ως)\b", re.I)
ARTICLE_HDR_RE = re.compile(r"(?:^|¶)\s*Άρθρο\b|(?:^|¶)\s*ΑΡΘΡΟ\b", re.I)
BIG_HDR_RE = re.compile(r"(?:^|¶)\s*(ΚΕΦΑΛΑΙΟ|ΤΜΗΜΑ|ΜΕΡΟΣ|ΠΑΡΑΡΤΗΜΑ|ΠΡΩΤΟΚΟΛΛΟ|ΚΑΤΑΛΟΓΟΣ|ΠΙΝΑΚΑΣ)\b", re.I)
AMEND_RE = re.compile(r"\b(αντικαθίσταται|τροποποιείται|καταργείται|προστίθεται|διαγράφονται)\b", re.I)

PARA_SPLIT_RE = re.compile(r"(?:\n+|¶+)")

# ───────────────────────── Small utils
def clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)

def greek_ratio(s: str) -> float:
    if not s:
        return 0.0
    greek = len(GREEK_RE.findall(s))
    return greek / max(1, len(s))

def cut_at_first(pattern, text: str) -> str:
    m = pattern.search(text)
    return text[:m.start()].rstrip() if m else text

def clean_expl(expl: str) -> str:
    if not expl:
        return ""
    e = expl.strip()
    e = cut_at_first(STOP_HDR_RE, e)
    m = NESTED_BULLET_RE.search(e)
    if m and m.start() > 0:
        e = e[:m.start()].rstrip()
    return e.strip(" \t\r\n¶:")

def ends_clean(text: str) -> tuple[bool, str]:
    if not text:
        return (False, "")
    last = text.strip()[-1]
    return (last in ".;»”\"", last)

def is_term_suspicious(term: str) -> bool:
    t = (term or "").strip()
    if not t:
        return True
    if "¶" in t or "\n" in t:
        return True
    if not GREEK_RE.search(t):
        return True
    if len(t) > 140:
        return True
    if len(t.split()) > 14:
        return True
    digits = sum(ch.isdigit() for ch in t)
    if digits >= 10:
        return True
    return False

def has_term_quoted_in_excerpt(term: str, excerpt: str) -> int:
    if not term or not excerpt:
        return 0
    t = re.escape(term.strip())
    # «TERM» or "TERM"
    if re.search(rf"«\s*{t}\s*»", excerpt):
        return 1
    if re.search(rf"\"\s*{t}\s*\"", excerpt):
        return 1
    # fallback: any guillemets present near definitions
    if "«" in excerpt and "»" in excerpt:
        return 1
    return 0

def para_stats(excerpt: str) -> tuple[int, float]:
    if not excerpt:
        return 0, 0.0
    parts = [p for p in PARA_SPLIT_RE.split(excerpt) if p.strip()]
    pc = len(parts)
    density = pc / max(1.0, (len(excerpt) / 1000.0))
    return pc, float(density)

# ───────────────────────── Scoring
def score_row(term: str, expl: str, excerpt: str, pattern_tag: str):
    expl_clean = clean_expl(expl)
    L = len(expl_clean)

    flags = {}
    flags["has_quotes"] = has_term_quoted_in_excerpt(term, excerpt)
    flags["has_def_verb"] = int(bool(DEF_VERB_RE.search(expl or "") or DEF_VERB_RE.search(excerpt or "")))
    flags["has_scope_phrase"] = int(bool(SCOPE_PHRASE_RE.search(expl or "") or SCOPE_PHRASE_RE.search(excerpt or "")))
    flags["has_nested_bullets"] = int(bool(NESTED_BULLET_RE.search(expl or "") or NESTED_BULLET_RE.search(excerpt or "")))

    # check headers/amendments on cleaned explanation (to avoid nuking good defs)
    flags["contains_article_header"] = int(bool(ARTICLE_HDR_RE.search(expl_clean)))
    flags["contains_big_header"] = int(bool(BIG_HDR_RE.search(expl_clean)))
    flags["contains_amendment"] = int(bool(AMEND_RE.search(expl_clean)))

    flags["term_suspicious"] = int(is_term_suspicious(term))
    flags["expl_empty"] = int(L == 0)
    flags["expl_too_short"] = int(0 < L < 20)
    flags["expl_too_long"] = int(L > 1200)  # generous

    ec, ew = ends_clean(expl_clean)
    flags["ends_clean"] = int(ec)
    flags["ends_with"] = ew

    # Base score
    contrib = {}
    score = 0.20
    contrib["base"] = 0.20

    # Tag priors
    if pattern_tag == "bullet":
        score += 0.10; contrib["tag_bullet"] = 0.10
    elif pattern_tag == "verb":
        score += 0.08; contrib["tag_verb"] = 0.08
    elif pattern_tag == "scope":
        score += 0.04; contrib["tag_scope"] = 0.04

    # Signals
    if flags["has_quotes"]:
        score += 0.12; contrib["has_quotes"] = 0.12
    if flags["has_def_verb"]:
        score += 0.22; contrib["has_def_verb"] = 0.22
    if flags["has_scope_phrase"]:
        score += 0.06; contrib["has_scope_phrase"] = 0.06
    if flags["ends_clean"]:
        score += 0.04; contrib["ends_clean"] = 0.04

    # Length sweet spot
    if 40 <= L <= 900:
        score += 0.10; contrib["expl_good_len"] = 0.10
    elif flags["expl_too_short"]:
        score -= 0.18; contrib["expl_too_short"] = -0.18
    elif flags["expl_too_long"]:
        score -= 0.08; contrib["expl_too_long"] = -0.08

    # Penalties (soft)
    if flags["contains_article_header"]:
        score -= 0.06; contrib["contains_article_header"] = -0.06
    if flags["contains_big_header"]:
        score -= 0.06; contrib["contains_big_header"] = -0.06
    if flags["contains_amendment"]:
        score -= 0.10; contrib["contains_amendment"] = -0.10
    if flags["has_nested_bullets"]:
        score -= 0.05; contrib["has_nested_bullets"] = -0.05

    if flags["expl_empty"]:
        score -= 0.35; contrib["expl_empty"] = -0.35
    if flags["term_suspicious"]:
        score -= 0.40; contrib["term_suspicious"] = -0.40

    # Strong-def floor (prevents good treaty defs from going to ~0)
    strong_def = (flags["has_def_verb"] == 1 and flags["term_suspicious"] == 0 and flags["expl_empty"] == 0)
    if strong_def:
        score = max(score, 0.35)
        contrib["strong_def_floor"] = 0.35

    conf = clamp01(score)
    needs_review = int(conf < 0.35)

    # extra stats for future analysis
    term_len = len((term or "").strip())
    expl_len = len((expl or "").strip())
    term_gr = round(greek_ratio(term or ""), 3)
    expl_gr = round(greek_ratio(expl_clean), 3)

    pc, pd = para_stats(excerpt or "")

    payload = {
        "contrib": contrib,
        "meta": {
            "term_len": term_len,
            "expl_len": expl_len,
            "expl_len_clean": L,
            "term_greek_ratio": term_gr,
            "expl_greek_ratio": expl_gr,
            "para_count": pc,
            "para_density": round(pd, 3),
        },
        "expl_clean": expl_clean,
    }

    return conf, needs_review, flags, pc, pd, term_len, expl_len, L, term_gr, expl_gr, payload

# ───────────────────────── Main
def main():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON;")
    cur = con.cursor()

    # Create score_2 fresh (keeps your existing score table untouched)
    cur.executescript("""
    DROP TABLE IF EXISTS score_2;
    CREATE TABLE score_2 (
      def_id                  INTEGER PRIMARY KEY,
      confidence              REAL    NOT NULL,
      needs_review            INTEGER NOT NULL,

      has_quotes              INTEGER NOT NULL,
      has_def_verb            INTEGER NOT NULL,
      has_scope_phrase        INTEGER NOT NULL,
      has_nested_bullets      INTEGER NOT NULL,

      ends_clean              INTEGER NOT NULL,
      ends_with               TEXT,

      contains_article_header INTEGER NOT NULL,
      contains_big_header     INTEGER NOT NULL,
      contains_amendment      INTEGER NOT NULL,

      para_count              INTEGER NOT NULL,
      para_density            REAL    NOT NULL,

      term_suspicious         INTEGER NOT NULL,
      expl_empty              INTEGER NOT NULL,
      expl_too_short          INTEGER NOT NULL,
      expl_too_long           INTEGER NOT NULL,

      term_len                INTEGER NOT NULL,
      expl_len                INTEGER NOT NULL,
      expl_len_clean          INTEGER NOT NULL,
      term_greek_ratio        REAL    NOT NULL,
      expl_greek_ratio        REAL    NOT NULL,

      rule_version            TEXT    NOT NULL,
      contributions_json      TEXT    NOT NULL,
      created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
    );

    CREATE INDEX idx_score2_confidence ON score_2(confidence);
    CREATE INDEX idx_score2_needs_review ON score_2(needs_review);
    """)

    rows = cur.execute("""
      SELECT ID, term, explanation, excerpt, pattern_tag
      FROM definitions
    """).fetchall()

    inserted = 0
    RULE_VERSION = "v2_clean_cut"

    for def_id, term, expl, excerpt, tag in rows:
        conf, needs_review, flags, pc, pd, term_len, expl_len, expl_len_clean, term_gr, expl_gr, payload = score_row(
            term or "", expl or "", excerpt or "", (tag or "")
        )

        cur.execute("""
          INSERT INTO score_2 (
            def_id, confidence, needs_review,
            has_quotes, has_def_verb, has_scope_phrase, has_nested_bullets,
            ends_clean, ends_with,
            contains_article_header, contains_big_header, contains_amendment,
            para_count, para_density,
            term_suspicious, expl_empty, expl_too_short, expl_too_long,
            term_len, expl_len, expl_len_clean, term_greek_ratio, expl_greek_ratio,
            rule_version, contributions_json
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            def_id, conf, needs_review,
            flags["has_quotes"], flags["has_def_verb"], flags["has_scope_phrase"], flags["has_nested_bullets"],
            flags["ends_clean"], flags["ends_with"],
            flags["contains_article_header"], flags["contains_big_header"], flags["contains_amendment"],
            pc, pd,
            flags["term_suspicious"], flags["expl_empty"], flags["expl_too_short"], flags["expl_too_long"],
            term_len, expl_len, expl_len_clean, term_gr, expl_gr,
            RULE_VERSION, json.dumps(payload, ensure_ascii=False)
        ))
        inserted += 1

    con.commit()
    con.close()
    print(f"[+] Inserted {inserted} rows into score_2 in: {DB}")

if __name__ == "__main__":
    main()
