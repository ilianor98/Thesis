import sqlite3, re
from bisect import bisect_right
from pathlib import Path
from directories import *

# ───────────────────── 1. Paths
SRC_DB = SPITI_PC_HARVEST
DST_DB = SPITI_PC_ORISMOI_FINAL   # νέα βάση· η orismoi_test1.db κρατά τα αποτελέσματα της προηγούμενης έκδοσης

# ───────────────────── 2. Table schema (term + explanation)
# Το πλήρες κείμενο του ΦΕΚ δεν αντιγράφεται σε κάθε γραμμή· βρίσκεται στο et.fekTEXT (fekID).
SCHEMA = """
DROP TABLE IF EXISTS definitions;
CREATE TABLE definitions (
  ID             INTEGER PRIMARY KEY AUTOINCREMENT,
  term           TEXT    NOT NULL,
  explanation    TEXT    NOT NULL,
  fekID          INTEGER NOT NULL,   -- et.ID του νομοθετήματος στο οποίο ανήκει ο ορισμός
  fekNumber      INTEGER,
  fekEtos        INTEGER,
  nomosNum       INTEGER,
  excerpt        TEXT,
  offset_start   INTEGER,            -- θέσεις μέσα στο et.fekTEXT (κείμενο ολόκληρου του φύλλου)
  offset_end     INTEGER,
  bullet         TEXT,
  pattern_tag    TEXT,               -- bullet | unquoted | verb
  scope          TEXT,               -- π.χ. «Για τους σκοπούς του παρόντος Μέρους», αν υπάρχει
  in_def_article INTEGER,            -- 1 αν βρίσκεται σε άρθρο «Ορισμοί» / «Έννοια όρων»
  act_resolved   INTEGER,            -- 1 αν το νομοθέτημα εντοπίστηκε με βεβαιότητα μέσα στο φύλλο
  lang           TEXT                -- el | other (π.χ. αγγλικό κείμενο διεθνών συμβάσεων)
);
"""

# ───────────────────── 3. Text preparation
def prep(txt: str) -> str:
    # Τα κείμενα χρησιμοποιούν \r\n, \n ή σκέτο \r για αλλαγή γραμμής, ενώ τα ^ / $ (re.M) αναγνωρίζουν μόνο \n.
    # \r\n → « \n» και \r → «\n»: το μήκος μένει ίδιο, άρα οι θέσεις (offsets) δείχνουν ακόμη στο et.fekTEXT.
    return (txt or "").replace("\r\n", " \n").replace("\r", "\n")

def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def clean_expl(s: str) -> str:
    return normalize_ws(s).lstrip(" .,:;·-–")

# ───────────────────── 4. Regex arsenal
MARK   = r"\(?(?:\d{1,3}|[α-ωάέήίόύώ]{1,3})[\).]"   # 1.  1)  (1)  α)  α.  (α)  στ)  ια)  αα)
OPEN   = r"[«\"“„]"
CLOSE  = r"[»\"”]"
TERM_Q = r"[^»\"”\n]{1,200}"
TERM_V = r"[^»\"”\n]{2,120}"
UNQ_TERM = r"[Α-ΩΆΈΉΊΌΎΏA-Z][^\n:;,·«»\"“”()]{0,79}?"     # κεφαλαίο αρχικό, χωρίς στίξη
PAREN  = r"(?:\([^)\n]{0,60}\))?"                          # π.χ. (Σ.Ε.Σ.Τ.) ή (άρθρο 2 παρ. 49 Γ.Α.Κ.)

# ρήματα που μπορεί να βρίσκονται ανάμεσα στον όρο και την επεξήγηση
LINK_VERB = (r"(?:ορίζ(?:εται|ονται)|νοείται|νοούνται|εννοείται|εννοούνται|σημαίν(?:ει|ουν)"
             r"|καθορίζ(?:εται|ονται)|θεωρείται|θεωρούνται|είναι)")

# ρήματα πρότασης ορισμού· τα ορίζεται/θεωρείται/λογίζεται μόνο με «ως» (αλλιώς σημαίνουν π.χ. «διορίζεται»)
SENT_VERB = (r"(?:νοείται|νοούνται|εννοείται|εννοούνται|σημαίν(?:ει|ουν)"
             r"|(?:ορίζ(?:εται|ονται)|θεωρείται|θεωρούνται|λογίζ(?:εται|ονται))(?=\s+ως\b))")

# α) «Όρος»: …   1. «Όρος» σημαίνει …   (ιβ) «Όρος», …
bullet_rgx = re.compile(rf"""
^[ \t]*(?P<mk>{MARK})[ \t]*
{OPEN}(?P<term>{TERM_Q}){CLOSE}
[ \t]*(?:(?:θα[ \t]+)?{LINK_VERB}\b)?[ \t]*(?:ως\b)?[ \t]*[:;,]?[ \t]*
""", re.I | re.M | re.X | re.U)

# α) Όρος: …   1. Όρος είναι …   (χωρίς εισαγωγικά· μόνο μέσα σε άρθρα ορισμών)
unquoted_rgx = re.compile(rf"""
^[ \t]*(?P<mk>{MARK})[ \t]*
(?P<term>{UNQ_TERM})[ \t]*{PAREN}[ \t]*
(?: : | [ \t](?:θα[ \t]+)?(?:είναι|νοείται|νοούνται|σημαίν(?:ει|ουν))\b )[ \t]*
""", re.M | re.X | re.U)

# Ως «Όρος» νοείται …   «Όρος» σημαίνει …   «Όρος» ορίζεται ως …
verb_rgx = re.compile(rf"""
(?:\b(?:ως|με\s+τον\s+όρο|με\s+τον\s+χαρακτηρισμό)\s+)?
{OPEN}(?P<term>{TERM_V}){CLOSE}[ \t]*,?[ \t]*
(?:θα\s+)?{SENT_VERB}\s+(?:ως\b\s*:?\s*)?
(?!ότι\b)
""", re.I | re.X | re.U)

# τέλος πρότασης για τους ρηματικούς ορισμούς
SENT_END = re.compile(r"[.;·](?=[ \t]*(?:\n|$|[Α-ΩΆΈΉΊΌΎΏA-Z«\"“(]|\(?(?:\d{1,3}|[α-ωάέήίόύώ]{1,3})[\).]\s))|\n[ \t]*\n")

# επικεφαλίδες νομοθετημάτων μέσα σε ένα φύλλο ΦΕΚ
act_rgx = re.compile(r"""
(?P<bol>^[ \t]*(?:\(\d+\)[ \t]*)?)?          # αρχή γραμμής, ίσως με «(1)» μπροστά
\b(?:
    (?P<n>[ΝN][ΟO][ΜM][ΟO]Σ)
  | (?P<pd>ΠΡΟΕΔΡΙΚΟ\s+ΔΙΑΤΑΓΜΑ)
  | (?P<pnp>ΠΡΑΞΗ\s+ΝΟΜΟΘΕΤΙΚΟΥ\s+ΠΕΡΙΕΧΟΜΕΝΟΥ)
)(?:(?:[ \t]+[ΥY]Π\W{0,3})?[ \t]*[ΑA]Ρ[ΙI]Θ[ΜM]?\.?[ \t]*(?P<num>\d+))?
""", re.M | re.X | re.U)

# επικεφαλίδες άρθρων: «Άρθρο 5», «ΑΡΘΡΟ 12», «Άρθρο πρώτο»
article_rgx = re.compile(r"^[ \t]*(?:Άρθρο|ΑΡΘΡΟ|ΆΡΘΡΟ|Αρθρο)[ \t]+(?:\d+\w*|[α-ωά-ώ]+|[Α-Ω]{1,4}΄?)", re.M | re.U)
DEF_TITLE = re.compile(r"Ορισμοί|ΟΡΙΣΜΟΙ|Έννοια\s+(?:των\s+)?όρων|ΕΝΝΟΙΑ\s+(?:ΤΩΝ\s+)?ΟΡΩΝ"
                       r"|Ερμηνεία\s+(?:των\s+)?όρων|Ορολογία|Definitions|DEFINITIONS")

# «Για τους σκοπούς του παρόντος νόμου, νοούνται ως:» → ακολουθεί λίστα ορισμών
# (η γραμμή πρέπει να αναγγέλλει ορισμούς· αλλιώς το «:» εισάγει έντυπα, καταλόγους κ.λπ.)
scope_intro_rgx = re.compile(r"(?:Για|για)\s+(?:τους\s+σκοπούς|την\s+εφαρμογή)[^\n]{0,250}:[ \t]*$", re.M | re.U)
DEF_CUE = re.compile(r"νοε[ίι]ται|νοούνται|ορισμ|ορίζ|σημαίν|έννοια|\bόρο[ιςυ]|\bόρων", re.I | re.U)
scope_rgx = re.compile(r"Για\s+(?:τους\s+σκοπούς|την\s+εφαρμογή)\s+[^,:;.\n]{0,120}", re.U)   # μόνο στην αρχή πρότασης
SCOPE_CUT = re.compile(r"\s+(?:νοε|νοού|εννοε|ισχύ|ορίζ|σημαίν|θεωρ|ως\b|οι\s+ακόλουθ|ο\s+όρος|οι\s+όροι|με\s+τον\s+όρο|[«\"“])")

# σημεία όπου τελειώνει η επεξήγηση μιας περίπτωσης
stop_rgx = re.compile(r"""
^[ \t]*(?:
    (?:Άρθρο|ΑΡΘΡΟ|ΆΡΘΡΟ|Αρθρο)[ \t]+\S
  | (?:ΚΕΦΑΛΑΙΟ|ΜΕΡΟΣ|ΤΜΗΜΑ|ΤΙΤΛΟΣ|ΠΑΡΑΡΤΗΜΑ)\b
  | (?:Article|ARTICLE|Regulation|REGULATION)[ \t]+\S
  | [ΝN][ΟO][ΜM][ΟO]Σ[ \t]+[ΥY]Π | ΠΡΟΕΔΡΙΚΟ\s+ΔΙΑΤΑΓΜΑ | ΠΡΑΞΗ\s+ΝΟΜΟΘΕΤΙΚΟΥ
  | \d{1,3}\.[ \t]+[Α-ΩΆΈΉΊΌΎΏ]          # νέα αριθμημένη παράγραφος
  | Αθήνα,                                # υπογραφές
  | Θεωρήθηκε\s+και\s+τέθηκε
)
""", re.M | re.X | re.U)

MAX_EXPL = 5000      # όριο ασφαλείας για επεξηγήσεις που δεν βρίσκουν φυσικό τέλος
MAX_VERB_EXPL = 1500

# ───────────────────── 5. Sanity helpers (filters)
BAD_TERM_TOKENS = ("Άρθρο", "ΑΡΘΡΟ", "ΚΕΦΑΛΑΙΟ", "ΤΜΗΜΑ", "ΜΕΡΟΣ", "ΠΑΡΑΡΤΗΜΑ")

def term_is_junk(term: str) -> bool:
    t = normalize_ws(term)
    if not t:
        return True
    if "¶" in t:
        return True
    if any(tok in t for tok in BAD_TERM_TOKENS):
        return True
    # conservative thresholds to kill huge paragraph-captures
    if len(t) > 180:
        return True
    if (t.count(" ") + 1) > 14:
        return True
    # punctuation-heavy = likely sentence/section, not a term
    if sum(t.count(ch) for ch in ".;:") >= 2:
        return True
    return False

# Όροι χωρίς εισαγωγικά: απορρίπτονται όσοι μοιάζουν με αρχή πρότασης και όχι με όρο
UNQ_BAD_FIRST = {"Για", "Κατά", "Με", "Από", "Σε", "Στο", "Στη", "Στην", "Στον", "Στα", "Στις", "Στους",
                 "Όπου", "Όταν", "Εφόσον", "Αν", "Εάν", "Ως", "Ο", "Η", "Το", "Οι", "Τα", "Τον", "Την",
                 "Του", "Της", "Των", "Κάθε", "Ένας", "Μία", "Μια", "Ένα", "Αντικείμενο", "Σκοπός",
                 "Δεν", "Δε", "Μη", "Μην", "Είναι", "Επίσης", "Ειδικότερα", "Ιδίως", "Δύναται",
                 "Αυτός", "Αυτή", "Αυτό", "Αυτοί", "Αυτές", "Αυτά", "Θα",
                 "Οποιοσδήποτε", "Οποιαδήποτε", "Οποιοδήποτε"}
UNQ_BAD_WORD = re.compile(r"\b(?:που|οποί\w*|όπως|όταν|εφόσον|ισχύ\w*)\b", re.U)

def unquoted_term_ok(term: str) -> bool:
    words = term.split()
    return (1 <= len(words) <= 10 and words[0] not in UNQ_BAD_FIRST
            and not UNQ_BAD_WORD.search(term))

GREEK_RE = re.compile(r"[Ͱ-Ͽἀ-῿]")
LATIN_RE = re.compile(r"[A-Za-z]")

def lang_of(s: str) -> str:
    return "el" if len(GREEK_RE.findall(s)) >= len(LATIN_RE.findall(s)) else "other"

def clean_mark(mk: str) -> str:
    return mk.strip("().")

# ───────────────────── 6. Structure helpers (articles, scope, acts)
def find_articles(t: str):
    """[(start, end, is_definitions_article)] για κάθε επικεφαλίδα άρθρου."""
    heads = [m.start() for m in article_rgx.finditer(t)]
    arts = []
    for i, p in enumerate(heads):
        end = heads[i + 1] if i + 1 < len(heads) else len(t)
        title = "\n".join(t[p:p + 300].split("\n")[:3])
        arts.append((p, end, bool(DEF_TITLE.search(title))))
    return arts

def article_at(arts, starts, pos):
    i = bisect_right(starts, pos) - 1
    return arts[i] if i >= 0 and pos < arts[i][1] else None

def definition_zones(t: str, arts):
    """Τμήματα όπου επιτρέπονται και όροι χωρίς εισαγωγικά."""
    zones = [(s, e) for s, e, is_def in arts if is_def]
    starts = [a[0] for a in arts]
    for m in scope_intro_rgx.finditer(t):
        if not DEF_CUE.search(m.group(0)):
            continue
        art = article_at(arts, starts, m.start())
        zones.append((m.start(), art[1] if art else min(len(t), m.start() + 20000)))
    return zones

def scope_before(t: str, arts, starts, pos):
    """Η πλησιέστερη φράση πεδίου εφαρμογής πριν από τον ορισμό, μέσα στο ίδιο άρθρο."""
    art = article_at(arts, starts, pos)
    lo = art[0] if art else max(0, pos - 3000)
    last = None
    for m in scope_rgx.finditer(t, lo, pos):
        last = m.group(0)
    if not last:
        return None
    return normalize_ws(SCOPE_CUT.split(last, 1)[0]) or None

def act_headings(t: str, acts):
    """[(θέση, et.ID ή None)] για κάθε επικεφαλίδα νομοθετήματος μέσα στο φύλλο."""
    by_key = {(cat, num): ID for ID, num, cat in acts}
    pnp = [ID for ID, _, cat in acts if cat == "Π.Ν.Π."]
    out = []
    for m in act_rgx.finditer(t):
        num = int(m.group("num")) if m.group("num") else None
        if m.group("pnp"):
            ID = by_key.get(("Π.Ν.Π.", num)) or (pnp[0] if len(pnp) == 1 else None)
        elif num is None:
            continue
        else:
            ID = by_key.get(("Ν." if m.group("n") else "Π.Δ.", num))
        if ID is None and m.group("bol") is None:
            continue        # αναφορά μέσα στο κείμενο και όχι επικεφαλίδα νομοθετήματος του φύλλου
        out.append((m.start(), ID))
    return out

def owner_act(pos, heads, acts):
    """Το νομοθέτημα στο οποίο ανήκει ο ορισμός: η τελευταία επικεφαλίδα πριν από αυτόν."""
    before = [ID for p, ID in heads if p <= pos]
    if before and before[-1] is not None:
        return before[-1], 1
    if len(acts) == 1:
        return acts[0][0], 1
    return acts[0][0], 0

# ───────────────────── 7. Extraction helper
def extract_defs(txt: str):
    res = []
    if not txt:
        return res
    t = prep(txt)
    arts = find_articles(t)
    starts = [a[0] for a in arts]
    zones = definition_zones(t, arts)
    in_zone = lambda pos: any(s <= pos < e for s, e in zones)

    # (α) κεφαλές περιπτώσεων: με εισαγωγικά παντού, χωρίς εισαγωγικά μόνο σε άρθρα ορισμών
    heads = []
    for m in bullet_rgx.finditer(t):
        heads.append((m.start(), m.end(), m.group("mk"), m.group("term"), "bullet"))
    for m in unquoted_rgx.finditer(t):
        if in_zone(m.start()) and unquoted_term_ok(normalize_ws(m.group("term"))):
            heads.append((m.start(), m.end(), m.group("mk"), m.group("term"), "unquoted"))
    heads.sort()

    # (β) η επεξήγηση φτάνει ως την επόμενη περίπτωση, επικεφαλίδα ή παράγραφο
    spans = []
    for i, (start, hend, mk, term, tag) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(t)
        stop = stop_rgx.search(t, hend, end)
        if stop:
            end = stop.start()
        end = min(end, hend + MAX_EXPL)
        spans.append((start, end))
        term = normalize_ws(term)
        expl = clean_expl(t[hend:end])
        if term_is_junk(term) or not expl:
            continue
        res.append({"term": term, "explanation": expl,
                    "offset_start": start, "offset_end": end,
                    "bullet": clean_mark(mk), "tag": tag})

    # (γ) ρηματικοί ορισμοί σε συνεχές κείμενο (όχι μέσα σε περιπτώσεις που ήδη βρέθηκαν)
    for m in verb_rgx.finditer(t):
        start = m.start()
        if any(s <= start < e for s, e in spans):
            continue
        term = normalize_ws(m.group("term"))
        if term_is_junk(term):
            continue
        se = SENT_END.search(t, m.end(), m.end() + MAX_VERB_EXPL)
        if se:
            end = se.end()
        else:
            nl = t.find("\n", m.end())
            end = nl if 0 <= nl < m.end() + MAX_VERB_EXPL else min(len(t), m.end() + MAX_VERB_EXPL)
        expl = clean_expl(t[m.end():end])
        if len(expl) < 3:
            continue
        res.append({"term": term, "explanation": expl,
                    "offset_start": start, "offset_end": end,
                    "bullet": None, "tag": "verb"})

    # (δ) πεδίο εφαρμογής, άρθρο ορισμών, γλώσσα, απόσπασμα
    for rec in res:
        s, e = rec["offset_start"], rec["offset_end"]
        art = article_at(arts, starts, s)
        rec["in_def_article"] = int(bool(art and art[2]))
        rec["scope"] = scope_before(t, arts, starts, s)
        rec["lang"] = lang_of(rec["explanation"][:500] or rec["term"])   # ο όρος μπορεί να είναι λατινικό ακρωνύμιο
        rec["excerpt"] = txt[max(0, s - 120):min(len(txt), e + 120)]
    res.sort(key=lambda r: r["offset_start"])
    return res

# ───────────────────── 8. Scan & insert (μία φορά ανά φύλλο ΦΕΚ)
def main():
    src = sqlite3.connect(SRC_DB)
    dst = sqlite3.connect(DST_DB)
    s, d = src.cursor(), dst.cursor()
    d.executescript(SCHEMA)

    # Τα νομοθετήματα του ίδιου φύλλου έχουν το ίδιο fekTEXT (ολόκληρο το φύλλο),
    # γι' αυτό η εξαγωγή γίνεται μία φορά ανά (fekNumber, fekEtos).
    issues = {}
    for ID, fekNumber, fekEtos, nomosNum, cat in s.execute("""
        SELECT ID, fekNumber, fekEtos, nomosNum, nomosCategory
        FROM et WHERE fekTEXT IS NOT NULL AND length(fekTEXT) > 100
        ORDER BY fekEtos, fekNumber, ID"""):
        issues.setdefault((fekNumber, fekEtos), []).append((ID, nomosNum, cat))

    inserted, unresolved = 0, 0
    for n, ((fekNumber, fekEtos), acts) in enumerate(issues.items(), 1):
        txt = s.execute("SELECT fekTEXT FROM et WHERE ID = ?", (acts[0][0],)).fetchone()[0]
        heads = act_headings(prep(txt), acts)
        nomos_of = {ID: num for ID, num, _ in acts}
        for rec in extract_defs(txt):
            fekID, resolved = owner_act(rec["offset_start"], heads, acts)
            unresolved += 1 - resolved
            d.execute("""
            INSERT INTO definitions
              (term, explanation, fekID, fekNumber, fekEtos, nomosNum, excerpt,
               offset_start, offset_end, bullet, pattern_tag, scope, in_def_article, act_resolved, lang)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                rec["term"], rec["explanation"], fekID, fekNumber, fekEtos, nomos_of[fekID], rec["excerpt"],
                rec["offset_start"], rec["offset_end"], rec["bullet"], rec["tag"],
                rec["scope"], rec["in_def_article"], resolved, rec["lang"]
            ))
            inserted += 1
        if n % 1000 == 0:
            print(f"  …{n}/{len(issues)} φύλλα")

    dst.commit()
    by_tag = d.execute("SELECT pattern_tag, COUNT(*) FROM definitions GROUP BY 1").fetchall()
    src.close()
    dst.close()
    print(f"[+] Αποθηκεύτηκαν {inserted} ορισμοί από {len(issues)} φύλλα σε '{Path(DST_DB).name}'")
    print(f"    ανά κανόνα: {dict(by_tag)} | χωρίς βέβαιο νομοθέτημα: {unresolved}")

if __name__ == "__main__":
    main()
