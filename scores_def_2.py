# scores_def_2.py — βαθμός αξιοπιστίας για κάθε ορισμό του πίνακα definitions (πίνακας score_2)
import sqlite3, re, json
from directories import *

DB = SPITI_PC_ORISMOI_FINAL  # βάση της εξαγωγής του extract_junk.py (definitions με scope / in_def_article / lang)

RULE_VERSION = "v3_structure"
REVIEW_THRESHOLD = 0.50      # κάτω από αυτό: needs_review = 1

# ───────────────────────── Regex helpers
# Η επεξήγηση ξεκινά συνήθως με ονοματική φράση («η αρχή…», «κάθε πρόσωπο…») ή με ρήμα ορισμού.
NP_START_RE = re.compile(
    r"^(?:(?:η|ο|το|οι|τα|τον|την|τη|τους|τις|του|της|των)\b(?!\s+οποί)"    # άρθρο, αλλά όχι «το οποίο…»
    r"|(?:κάθε|οποι(?:ος|α|ο|οι|ες)δήποτε|ένας|ένα|μία|μια|όλ(?:οι|ες|α)|εκείν(?:ος|η|ο|οι|ες|α)"
    r"|όσ(?:οι|ες|α)|είναι|σημαίν(?:ει|ουν)|νοείται|νοούνται|εννοείται)\b)",
    re.I
)
# «Όρος» ή «Άλλος όρος» …: η επεξήγηση ξεκινά με τη συνέχεια της απαρίθμησης όρων
CONTINUATION_RE = re.compile(r"^(?:ή|και|,)", re.I)

# σύνδεσμος ανάμεσα στον όρο και την επεξήγηση: «:» ή ρήμα ορισμού
CONNECTOR_RE = re.compile(
    r"^[\s»\"”]*(?::|(?:ορίζ(?:εται|ονται)|νοείται|νοούνται|εννοείται|σημαίν(?:ει|ουν)"
    r"|καθορίζ(?:εται|ονται)|θεωρείται|είναι)\b)",
    re.I
)
# επικεφαλίδες μέσα στην επεξήγηση = η επεξήγηση «κατάπιε» κείμενο του επόμενου άρθρου/κεφαλαίου
HEADING_INSIDE_RE = re.compile(r"\b(?:ΚΕΦΑΛΑΙΟ|ΜΕΡΟΣ|ΤΜΗΜΑ|ΠΑΡΑΡΤΗΜΑ|ΑΡΘΡΟ|ΤΙΤΛΟΣ)\b|\bΆρθρο\s+\d+\s+[Α-ΩΆΈΉΊΌΎΏ]")
# δεύτερος ορισμός μέσα στην ίδια επεξήγηση
SECOND_DEF_RE = re.compile(r"[«\"“][^»\"”]{1,80}[»\"”]\s*,?\s+(?:νοείται|νοούνται|σημαίν(?:ει|ουν)|ορίζεται\s+ως)")
AMEND_RE = re.compile(
    r"\b(?:αντικαθίστα(?:ται|νται)|τροποποιείται|τροποποιούνται|καταργ(?:είται|ούνται)"
    r"|προστίθε(?:ται|νται)|διαγράφ(?:εται|ονται))\b"
)

# Οι περιπτώσεις μιας απαρίθμησης τελειώνουν συχνά με «,» ή «·»· το «?» προέρχεται από χαμένους
# χαρακτήρες του αρχικού κειμένου και όχι από πραγματικό ερωτηματικό.
CLEAN_ENDINGS = set(".;·,»”\"?)")

# ───────────────────────── Small utils
def clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)

def has_connector(term: str, excerpt: str, offset_start: int) -> bool:
    """Ο όρος ακολουθείται από «:» ή ρήμα ορισμού στο αρχικό κείμενο;"""
    if not term or not excerpt:
        return False
    k = min(120, offset_start or 0)          # το excerpt αρχίζει 120 χαρακτήρες πριν από τον ορισμό
    m = re.compile(r"\s+".join(map(re.escape, term.split()))).search(excerpt, k)
    return bool(m and CONNECTOR_RE.match(excerpt[m.end():m.end() + 40]))

# ───────────────────────── Scoring
def score_row(term: str, expl: str, excerpt: str, pattern_tag: str,
              in_def_article: int, scope: str, lang: str, offset_start: int):
    term = (term or "").strip()
    expl = (expl or "").strip().lstrip(" .,:;·-–")   # π.χ. «Αρχή». Ο κατάλληλος φορέας…
    words = term.split()
    L = len(expl)

    flags = {}
    flags["explicit_connector"] = int(pattern_tag in ("verb", "unquoted") or has_connector(term, excerpt, offset_start))
    flags["in_def_article"] = int(bool(in_def_article))
    flags["has_scope"] = int(bool(scope))
    digits = sum(ch.isdigit() for ch in term)
    flags["term_digit_heavy"] = int(digits > 0 and digits / max(1, len(term.replace(" ", ""))) > 0.3)
    flags["expl_np_start"] = int(bool(NP_START_RE.match(expl)))
    flags["expl_continuation"] = int(not flags["expl_np_start"] and bool(CONTINUATION_RE.match(expl)))
    flags["ends_with"] = expl[-1:] if expl else ""
    flags["ends_clean"] = int(flags["ends_with"] in CLEAN_ENDINGS)
    flags["heading_inside"] = int(bool(HEADING_INSIDE_RE.search(expl)))
    flags["contains_amendment"] = int(bool(AMEND_RE.search(expl)))
    flags["second_def_inside"] = int(bool(SECOND_DEF_RE.search(expl)))
    flags["not_greek"] = int(lang not in (None, "el"))

    contrib = {"base": 0.20}

    # 1. Κανόνας εξαγωγής. Μια περίπτωση με όρο σε εισαγωγικά μετρά ως ισχυρή ένδειξη μόνο όταν
    #    υπάρχει πλαίσιο ορισμού· αλλιώς μπορεί να είναι απλή λίστα ονομάτων.
    context = flags["in_def_article"] or flags["has_scope"] or flags["explicit_connector"]
    if pattern_tag == "verb":
        contrib["rule_verb"] = 0.15
    elif pattern_tag == "unquoted":
        contrib["rule_unquoted"] = 0.10
    elif context:
        contrib["rule_bullet"] = 0.15

    # 2. Δομή και πλαίσιο
    if flags["in_def_article"]:
        contrib["in_def_article"] = 0.15
    if flags["has_scope"]:
        contrib["has_scope"] = 0.05
    if flags["explicit_connector"]:
        contrib["explicit_connector"] = 0.10

    # 3. Όρος
    if 1 <= len(words) <= 6:
        contrib["term_short"] = 0.05
    elif len(words) > 10:
        contrib["term_long"] = -0.10
    if flags["term_digit_heavy"]:
        contrib["term_digit_heavy"] = -0.15

    # 4. Επεξήγηση
    if L < 20:
        contrib["expl_very_short"] = -0.25
    elif L < 40:
        contrib["expl_short"] = -0.05
    elif L <= 1200:
        contrib["expl_good_len"] = 0.10
    elif L < 3000:
        contrib["expl_long"] = -0.05
    else:
        contrib["expl_very_long"] = -0.15
    if flags["expl_np_start"]:
        contrib["expl_np_start"] = 0.10
    elif flags["expl_continuation"]:
        contrib["expl_continuation"] = -0.05
    if flags["ends_clean"]:
        contrib["ends_clean"] = 0.05
    elif flags["ends_with"] == ":":
        contrib["ends_colon"] = -0.05
    else:
        contrib["ends_mid_sentence"] = -0.10
    if flags["heading_inside"]:
        contrib["heading_inside"] = -0.20
    if flags["contains_amendment"]:
        contrib["contains_amendment"] = -0.10
    if flags["second_def_inside"]:
        contrib["second_def_inside"] = -0.05

    # 5. Γλώσσα (π.χ. αγγλικό κείμενο διεθνών συμβάσεων)
    if flags["not_greek"]:
        contrib["not_greek"] = -0.30

    conf = round(clamp01(sum(contrib.values())), 3)
    needs_review = int(conf < REVIEW_THRESHOLD)
    return conf, needs_review, flags, len(words), L, contrib

# ───────────────────────── Main
def main():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON;")
    cur = con.cursor()

    cols = {r[1] for r in cur.execute("PRAGMA table_info(definitions)")}
    missing = {"scope", "in_def_article", "lang"} - cols
    if missing:
        raise SystemExit(f"Η βάση {DB} δεν έχει τις στήλες {sorted(missing)}· τρέξε πρώτα το extract_junk.py.")

    cur.executescript("""
    DROP TABLE IF EXISTS score_2;
    CREATE TABLE score_2 (
      def_id              INTEGER PRIMARY KEY,
      confidence          REAL    NOT NULL,
      needs_review        INTEGER NOT NULL,

      pattern_tag         TEXT,
      explicit_connector  INTEGER NOT NULL,
      in_def_article      INTEGER NOT NULL,
      has_scope           INTEGER NOT NULL,

      term_words          INTEGER NOT NULL,
      term_digit_heavy    INTEGER NOT NULL,

      expl_len            INTEGER NOT NULL,
      expl_np_start       INTEGER NOT NULL,
      expl_continuation   INTEGER NOT NULL,
      ends_clean          INTEGER NOT NULL,
      ends_with           TEXT,
      heading_inside      INTEGER NOT NULL,
      contains_amendment  INTEGER NOT NULL,
      second_def_inside   INTEGER NOT NULL,
      not_greek           INTEGER NOT NULL,

      rule_version        TEXT    NOT NULL,
      contributions_json  TEXT    NOT NULL,
      created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
      FOREIGN KEY(def_id) REFERENCES definitions(ID)
    );

    CREATE INDEX idx_score2_confidence ON score_2(confidence);
    CREATE INDEX idx_score2_needs_review ON score_2(needs_review);
    """)

    rows = cur.execute("""
      SELECT ID, term, explanation, excerpt, pattern_tag, in_def_article, scope, lang, offset_start
      FROM definitions
    """).fetchall()

    inserted = 0
    for def_id, term, expl, excerpt, tag, in_def, scope, lang, off in rows:
        conf, needs_review, f, term_words, expl_len, contrib = score_row(
            term, expl, excerpt, tag, in_def, scope, lang, off
        )
        cur.execute("""
          INSERT INTO score_2 (
            def_id, confidence, needs_review,
            pattern_tag, explicit_connector, in_def_article, has_scope,
            term_words, term_digit_heavy,
            expl_len, expl_np_start, expl_continuation, ends_clean, ends_with,
            heading_inside, contains_amendment, second_def_inside, not_greek,
            rule_version, contributions_json
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            def_id, conf, needs_review,
            tag, f["explicit_connector"], f["in_def_article"], f["has_scope"],
            term_words, f["term_digit_heavy"],
            expl_len, f["expl_np_start"], f["expl_continuation"], f["ends_clean"], f["ends_with"],
            f["heading_inside"], f["contains_amendment"], f["second_def_inside"], f["not_greek"],
            RULE_VERSION, json.dumps(contrib, ensure_ascii=False)
        ))
        inserted += 1

    con.commit()
    flagged, avg = cur.execute("SELECT SUM(needs_review), ROUND(AVG(confidence), 3) FROM score_2").fetchone()
    con.close()
    print(f"[+] Inserted {inserted} rows into score_2 in: {DB}")
    print(f"    μέσος βαθμός {avg} | needs_review (< {REVIEW_THRESHOLD}): {flagged}")

if __name__ == "__main__":
    main()
