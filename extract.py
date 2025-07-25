import sqlite3, re
from pathlib import Path

# ───────────────────── 1. Paths
SRC_DB = Path(r"C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/harvester.db")
DST_DB = Path("orismoi.db")

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
verb_core = r"(?:ορίζ(?:εται|ονται)|νοείτ(?:αι|ουν)|σημαίν(?:ει|ουν)|θεωρείτ(?:αι|ουν)|καθορίζ(?:εται|ονται))"

verb_rgx = re.compile(fr"""
\b[«"](?P<term>[^»"]+)[»"]\s+          # «Όρος»
{verb_core}\s+ως\s*:?\s*               # ρήμα + «ως»
(?P<expl>[^.{{10,400}}]*?)\.\s*        # ως … .
""", re.I | re.S | re.X | re.U)

bullet_rgx = re.compile(r"""
^\s*
(?: (\d+)|([α-ωάέήίόύώ]))[\).]\s*      # 1)   ή α)
[«"](?P<term>[^»"]+)[»"]\s*            # «Όρος»
(?:ορίζεται|νοείται|σημαίνει|καθορίζεται|θεωρείται)?\s*
[:;,]?\s*
(?P<expl>.*?)                          # περιγραφή
(?= ^\s*(?:\d+|[α-ωάέήίόύώ])[\).] | ^\s*Άρθρο | \Z )
""", re.I | re.M | re.S | re.X | re.U)

scope_rgx = re.compile(r"""
για\s+τους\s+σκοπούς[^.]{0,120}?
[«"](?P<term>[^»"]+)[»"]               # μόνο ο όρος
""", re.I | re.S | re.X | re.U)

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
            "excerpt": txt[max(0,start-120):min(len(txt),end+120)],
            "bullet": m.group(1) or m.group(2),
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
            "excerpt": txt[max(0,start-120):min(len(txt),end+120)],
            "bullet": None,
            "tag": "verb"
        })

    # scope-based  (μόνο το term∙ explanation κενό)
    for m in scope_rgx.finditer(txt):
        start, end = m.span()
        res.append({
            "term":        m.group('term').strip(),
            "explanation": "",
            "offset_start": start,
            "offset_end":   end,
            "excerpt": txt[max(0,start-120):min(len(txt),end+120)],
            "bullet": None,
            "tag": "scope"
        })
    return res

# ───────────────────── 5. Scan & insert
s.execute("SELECT ID, fekNumber, fekTEXT, fekEtos, nomosNum FROM et")

inserted = 0
for fekID, fekNumber, fekText, fekEtos, nomosNum in s.fetchall():
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
print(f"[+] Αποθηκεύτηκαν {inserted} ορισμοί σε '{DST_DB.name}'")
