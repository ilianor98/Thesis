import sqlite3, re
from pathlib import Path

SRC_DB = Path(r"C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/harvester.db")
DST_DB = Path("orismoi.db")

src = sqlite3.connect(SRC_DB)
dst = sqlite3.connect(DST_DB)
s, d = src.cursor(), dst.cursor()

# Δημιουργία πίνακα definitions
d.executescript("""
DROP TABLE IF EXISTS definitions;
CREATE TABLE definitions (
    ID            INTEGER PRIMARY KEY AUTOINCREMENT,
    definition    TEXT    NOT NULL,
    fekID         INTEGER NOT NULL,
    fekNumber     INTEGER,
    fekText       TEXT,
    fekEtos       INTEGER,
    nomosNum      INTEGER,
    excerpt       TEXT,
    offset_start  INTEGER,
    offset_end    INTEGER,
    bullet        TEXT,
    pattern_tag   TEXT
);
""")

# Regex «βεντάλια»

verb_core = r"(?:ορίζ(?:εται|ονται)|νοείτ(?:αι|ουν)|σημαίν(?:ει|ουν)|θεωρείτ(?:αι|ουν)|καθορίζ(?:εται|ονται))"

verb_rgx = re.compile(fr"""
\b{verb_core}\s+ως\s*:?\s*      # …ορίζεται/ονται ως(:)
(?!\d+[\).])                    # όχι αμέσως αριθμημένο bullet
.{10,400}?                      # 10-400 χαρακτήρες (dot==\n)
\.                              # πρώτη τελεία
""", re.I | re.S | re.X | re.U)

bullet_rgx = re.compile(r"""
^\s*                                # line start
(?:                                 # main bullet:
   (\d+)|                           #   1. 2. 3.
   ([α-ωάέήίόύώ])                  #   α. β. γ.
)[\).]\s*                           #   ) or .
[«"](?P<term>[^»"]+)[»"]\s*         # «Όρος»
(?:                                 #  optional verb or colon
     (?:ορίζεται|νοείται|σημαίνει|καθορίζεται|θεωρείται)\s*
)?                                  #
[:;,]?\s*                           #  :,;  (some texts use comma)
(?P<body>.*?)                       # body of definition
(?= ^\s*\d+[\).] | ^\s*Άρθρο | \Z ) # next numeric bullet, next Article, or EOF
""", re.I | re.M | re.S | re.X | re.U)

scope_rgx = re.compile(r"""
για\s+τους\s+σκοπούς[^.]{0,120}?
[«"]([^»"]{5,200})[»"]
""", re.I | re.S | re.X | re.U)


# Συνάρτηση εξαγωγής με μετα-δεδομένα
def extract_defs(text: str):
    """Επιστρέφει λίστα dict με definition + metadata."""
    if not text:
        return []
    res = []

    # bullets (γράμματα ή αριθμοί)
    for m in bullet_rgx.finditer(text):
        term  = m.group('term').strip()
        body  = m.group('body').strip()
        defin = f"{term}: {body}"
        start, end = m.span()
        excerpt = text[max(0,start-120): min(len(text),end+120)]
        res.append({
            "definition":   defin,
            "offset_start": start,
            "offset_end":   end,
            "excerpt":      excerpt,
            "bullet":       m.group(1) or m.group(2),  # ψηφίο ή γράμμα
            "pattern_tag":  "bullet"
        })

    # verb-based
    for m in verb_rgx.finditer(text):
        start, end = m.span()
        excerpt = text[max(0,start-120): min(len(text),end+120)]
        res.append({
            "definition":   m.group(0).strip(),
            "offset_start": start,
            "offset_end":   end,
            "excerpt":      excerpt,
            "bullet":       None,
            "pattern_tag":  "verb"
        })

    # scope-based
    for m in scope_rgx.finditer(text):
        start, end = m.span(1)      # μόνο το group με τον ορισμό
        excerpt = text[max(0,start-120): min(len(text),end+120)]
        res.append({
            "definition":   m.group(1).strip(),
            "offset_start": start,
            "offset_end":   end,
            "excerpt":      excerpt,
            "bullet":       None,
            "pattern_tag":  "scope"
        })
    return res

# Σάρωση & αποθήκευση
s.execute("SELECT ID, fekNumber, fekTEXT, fekEtos, nomosNum FROM et")

inserted = 0
for fekID, fekNumber, fekText, fekEtos, nomosNum in s.fetchall():
    for rec in extract_defs(fekText):
        d.execute("""
        INSERT INTO definitions
          (definition, fekID, fekNumber, fekText, fekEtos, nomosNum,
           excerpt, offset_start, offset_end, bullet, pattern_tag)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rec["definition"], fekID, fekNumber, fekText, fekEtos, nomosNum,
            rec["excerpt"], rec["offset_start"], rec["offset_end"],
            rec["bullet"], rec["pattern_tag"]
        ))
        inserted += 1

dst.commit()
src.close(); dst.close()
print(f"[+] Ολοκληρώθηκε: καταχωρήθηκαν {inserted} ορισμοί στο '{DST_DB.name}'")
