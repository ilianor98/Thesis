import sqlite3, re
from pathlib import Path
from directories import *

# optional progress bar
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# ───────────────────── 1. Paths
SRC_DB = SPITI_PC_HARVEST
DST_DB = SPITI_PC_ORISMOI_TEST

src = sqlite3.connect(SRC_DB)
dst = sqlite3.connect(DST_DB)
s, d = src.cursor(), dst.cursor()

# ───────────────────── 2. Table schema (term + explanation)
d.executescript("""
DROP TABLE IF EXISTS definitions;
CREATE TABLE definitions (
  ID             INTEGER PRIMARY KEY AUTOINCREMENT,
  term           TEXT    NOT NULL,
  explanation    TEXT    NOT NULL,
  fekID          INTEGER NOT NULL,
  fekNumber      INTEGER,
  fekText        TEXT,
  fekEtos        INTEGER,
  nomosNum       INTEGER,
  excerpt        TEXT,
  offset_start   INTEGER,
  offset_end     INTEGER,
  bullet         TEXT,
  pattern_tag    TEXT
);
""")

# ───────────────────── 3. Regex arsenal

# quotes (covers « », ", “ ”, ‘ ’, „ ‟)
QO = r"[«\"“„‘]"
QC = r"[»\"”‟’]"

# bullet id: digits or greek letters (1–2 chars to cover στ, ζα etc)
BUL_ID = r"(?:\d{1,3}|[α-ωάέήίόύώ]{1,2})"

# bullet prefix at line start:
#   10.   10)   α.   α)   στ.   (α)   (10)
BUL_PREFIX_NAMED = fr"(?:\(\s*)?(?P<bullet>{BUL_ID})(?:(?:\s*\))|[\).])"
BUL_PREFIX_PLAIN = fr"(?:\(\s*)?(?:{BUL_ID})(?:(?:\s*\))|[\).])"

# match “term in quotes”
TERM_QUOTED = re.compile(fr"{QO}([^»\"”‟’]+?){QC}", re.U)

verb_core = r"(?:ορίζ(?:εται|ονται)|νοείτ(?:αι|ουν)|εννοείτ(?:αι|ουν)|σημαίν(?:ει|ουν)|θεωρείτ(?:αι|ουν)|καθορίζ(?:εται|ονται))"

# keep your verb_rgx as-is (minimal change), but expand quotes
verb_rgx = re.compile(fr"""
\b{QO}(?P<term>[^»\"”‟’]+){QC}\s+       # «Όρος»
{verb_core}\s+ως\s*:?\s*               # ρήμα + «ως»
(?P<expl>.{{10,400}}?)\.\s*            # ως … .
""", re.I | re.S | re.X | re.U)

# IMPORTANT FIX:
# Stop only when next bullet+quotes starts (new definition), not when α) sub-bullet starts
bullet_rgx = re.compile(fr"""
^\s*{BUL_PREFIX_NAMED}\s*
{QO}(?P<term>[^»\"”‟’]+){QC}\s*
(?:ορίζεται|νοείται|εννοείται|σημαίνει|καθορίζεται|θεωρείται)?\s*
[:;,]?\s*
(?P<expl>.*?)
(?=
    ^\s*{BUL_PREFIX_PLAIN}\s*{QO}      # next definition bullet must have quotes
  | ^\s*Άρθρο\b
  | ^\s*ΑΡΘΡΟ\b
  | \Z
)
""", re.I | re.M | re.S | re.X | re.U)

# SCOPE FIX:
# Capture explanation too, and allow multiple quoted terms before the verb
scope_rgx = re.compile(fr"""
(?:για\s+τους\s+σκοπούς.*?|στο\s+πλαίσιο.*?|για\s+την\s+εφαρμογή.*?)
(?:\s+του\s+παρόντος|\s+της\s+παρούσας|\s+της\s+παρούσης|\s+της\s+συμφωνίας|\s+του\s+νόμου|\s+κεφαλαίου|\s+άρθρου)?   # optional
.{0,200}?
(?:ως|ο\s+όρος)\s*
(?P<terms>(?:{QO}[^»\"”‟’]+{QC}\s*(?:,|\s+και\s+|\s+ή\s+)?\s*){{1,8}})
(?:,|\s)*\s*
{verb_core}\s*
[:;,]?\s*
(?P<expl>.*?)
(?=
    ^\s*{BUL_PREFIX_PLAIN}\s*(?:ως\s+)?{QO}   # next scoped item, often (β) ως "..."
  | ^\s*Άρθρο\b
  | ^\s*ΑΡΘΡΟ\b
  | \Z
)
""", re.I | re.M | re.S | re.X | re.U)

# ───────────────────── 4. Extraction helper
def extract_defs(txt: str):
    res = []
    if not txt:
        return res

    # bullets
    for m in bullet_rgx.finditer(txt):
        start, end = m.span()
        res.append({
            "term":        m.group('term').strip(),
            "explanation": m.group('expl').strip(),
            "offset_start": start,
            "offset_end":   end,
            "excerpt": txt[max(0, start-120):min(len(txt), end+120)],
            "bullet": m.group('bullet'),
            "tag": "bullet"
        })

    # verb-based
    for m in verb_rgx.finditer(txt):
        start, end = m.span()
        res.append({
            "term":        m.group('term').strip(),
            "explanation": m.group('expl').strip(),
            "offset_start": start,
            "offset_end":   end,
            "excerpt": txt[max(0, start-120):min(len(txt), end+120)],
            "bullet": None,
            "tag": "verb"
        })

    # scope-based (NOW with explanation + multi-term split)
    for m in scope_rgx.finditer(txt):
        start, end = m.span()
        expl = (m.group('expl') or "").strip()
        terms_block = m.group('terms') or ""
        terms = [t.strip() for t in TERM_QUOTED.findall(terms_block)]

        # if somehow no terms extracted, skip
        for term in terms:
            res.append({
                "term": term,
                "explanation": expl,
                "offset_start": start,
                "offset_end": end,
                "excerpt": txt[max(0, start-120):min(len(txt), end+120)],
                "bullet": None,
                "tag": "scope"
            })

    return res

# ───────────────────── 5. Scan & insert (with progress)
total = s.execute("SELECT COUNT(*) FROM et").fetchone()[0]
rows = s.execute("SELECT ID, fekNumber, fekTEXT, fekEtos, nomosNum FROM et")

it = rows
if tqdm is not None:
    it = tqdm(rows, total=total, desc="Extracting definitions")

inserted = 0
for fekID, fekNumber, fekText, fekEtos, nomosNum in it:
    for rec in extract_defs(fekText):
        d.execute("""
        INSERT INTO definitions
          (term, explanation, fekID, fekNumber, fekText, fekEtos,
           nomosNum, excerpt, offset_start, offset_end, bullet, pattern_tag)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rec["term"], rec["explanation"], fekID, fekNumber, fekText, fekEtos,
            nomosNum, rec["excerpt"], rec["offset_start"], rec["offset_end"],
            rec["bullet"], rec["tag"]
        ))
        inserted += 1

dst.commit()
src.close(); dst.close()
print(f"[+] Αποθηκεύτηκαν {inserted} ορισμοί σε '{Path(DST_DB).name}'")
