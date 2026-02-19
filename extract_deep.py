import sqlite3
import re
import time
import sys
from pathlib import Path
from directories import *

SRC_DB = SPITI_PC_HARVEST
DST_DB = SPITI_PC_ORISMOI_DEEP

src = sqlite3.connect(SRC_DB)
dst = sqlite3.connect(DST_DB)
s, d = src.cursor(), dst.cursor()

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
  pattern_tag    TEXT,
  confidence     REAL    DEFAULT 1.0
);
""")

# Expanded verb list
verb_core = r"(?:ορίζετ(?:αι|ονται)|νοείτ(?:αι|ουν)|σημαίν(?:ει|ουν)|θεωρείτ(?:αι|ουν)|καθορίζετ(?:αι|ονται)|λογίζετ(?:αι|ονται)|εννοείτ(?:αι|ουν)|αποτελεί|συνιστά|εκλαμβάνετ(?:αι|ονται)|έχει\s+την\s+έννοια|λαμβάνετ(?:αι|ονται)\s+ως)"

# Relaxed patterns
verb_rgx = re.compile(fr"""
    (?:^|[.;:]|\n|\s{{2,}})
    \s*
    [\[(]?\s*[«"](?P<term>[^»"{{}}[\]()]{{2,100}}?)[»"]\s*[\])]?\s*
    (?:[^;.]{{0,100}}?)
    \b(?:{verb_core})\s+
    (?:ως|σαν)?\s*
    :?\s*
    (?P<expl>
        (?:[^;.]|
            (?:[.;](?!\s*[Α-Ω]|\s*$|\s*[\[\(«]|\s*\n\s*[Α-Ω]))
        ){{10,500}}?
    )
    [.;]
    (?=\s+[Α-Ω]|\s*$|\s*[\[\(«]|\s*\n\s*\S)
""", re.I | re.S | re.X | re.U)

bullet_rgx = re.compile(r"""
    (?:^|\n)
    \s*
    (?P<bullet>
        (?:\d{{1,2}}[\).])|
        (?:[α-ω][\).])|
        (?:[Α-Ω][\).])|
        (?:[ivx]+[\).])
    )
    \s*
    (?:[\[\(]?\s*[«"](?P<term>[^»"{{}}[\]()]{{2,100}}?)[»"]\s*[\])]?)?
    \s*
    (?:[:;]?\s*)?
    (?:[^;.]{{0,100}}?)?
    (?:{verb_core}\s+)?
    (?:ως|σαν)?\s*
    :?\s*
    (?P<expl>
        (?:[^;.]|
            (?:[.;](?!\s*(?:\d+|[α-ω]|[Α-Ω]|ivx)[\).]|\s*[Α-Ω]|\s*$|\s*[\[\(«]))
        )+?
    )
    (?=
        \s*(?:\n\s*(?:\d+|[α-ω]|[Α-Ω]|ivx)[\).]|
            \n\s*Άρθρο|
            \n\s*Παράγραφος|
            \s*[.;]\s*[Α-Ω]|
            $)
    )
""", re.I | re.M | re.S | re.X | re.U)

scope_rgx = re.compile(r"""
    (?:^|[.;:]|\n)
    \s*
    Για\s+τ(?:ους|ις|α)\s+σκοπούς\s+
    (?:[^;.]{{0,50}}?)?
    [«"](?P<term>[^»"]{{2,100}}?)[»"]\s*
    (?:[\[\(]?\s*[«"](?P<alt_term>[^»"]+)[»"]\s*[\])]?\s*)?
    (?:[^;.]{{0,100}}?)?
    (?:{verb_core}\s+)?
    (?:ως|σαν)?\s*
    :?\s*
    (?P<expl>
        (?:[^;.]|
            (?:[.;](?!\s*(?:Για\s+τους|Ο\s+όρος|Τα\s+ανωτέρω|Άρθρο|Παράγραφος|[Α-Ω])))
        ){{10,500}}?
    )
    [.;]
    (?=\s+(?:Για\s+τους|Ο\s+όρος|Τα\s+ανωτέρω|Άρθρο|Παράγραφος)|\s*$)
""", re.I | re.S | re.X | re.U)

kata_ennoia_rgx = re.compile(r"""
    (?:^|[.;:]|\n)
    \s*
    [«"](?P<term>[^»"]{{2,100}}?)[»"]\s*
    (?:[^;.]{{0,50}}?)?
    (?:{verb_core})\s+
    (?:ως|σαν)?\s*
    :?\s*
    (?P<expl>
        (?:[^;.]|
            (?:[.;](?!\s*[Α-Ω]|\s*Άρθρο|\s*Παράγραφος))
        ){{10,500}}?
    )
    [.;]
""", re.I | re.S | re.X | re.U)

legetai_rgx = re.compile(r"""
    (?:^|[.;:]|\n)
    \s*
    [«"](?P<term>[^»"]{{2,100}}?)[»"]\s*
    (?:[^;.]{{0,50}}?)?
    (?:λέγεται\s+)?
    (?:δε|δεν)?\s*
    (?:ως|σαν)?\s*
    :?\s*
    (?P<expl>
        (?:[^;.]|
            (?:[.;](?!\s*[Α-Ω]|\s*Άρθρο|\s*Παράγραφος))
        ){{10,500}}?
    )
    [.;]
""", re.I | re.S | re.X | re.U)

paren_rgx = re.compile(r"""
    (?:^|[.;:]|\n)
    \s*
    [«"](?P<term>[^»"]{{2,100}}?)[»"]\s*
    (?:[\[\(]\s*εφεξής\s+[«"][^»"]+[»"]\s*[\])])?\s*
    [,:;]?\s*
    \(
        (?:δηλαδή|ήτοι|τουτέστιν)\s*
        (?P<expl>[^)]{{10,500}}?)
    \)
""", re.I | re.S | re.X | re.U)

# Confidence scoring (lenient)
def calculate_confidence(rec: dict, txt: str) -> float:
    score = 1.0
    term = rec["term"]
    expl = rec["explanation"]

    if len(term) < 2:
        return 0.1
    if len(expl) < 10:
        return 0.1

    # Stopwords penalize but don't kill
    stop_terms = {'νόμος', 'άρθρο', 'παράγραφος', 'εδάφιο', 'στοιχείο', 'παρόν'}
    if term.lower().strip('«»" ') in stop_terms:
        score *= 0.6

    # Digits/special chars (allow hyphens)
    if re.search(r'\d|[^α-ωάέήίόύώΑ-Ω\s-]', term):
        score *= 0.8

    # Title case boost
    if term.istitle():
        score *= 1.2

    # Pattern tag boost
    if rec["tag"] in ("verb", "kata_ennoia", "legetai", "scope"):
        score *= 1.1

    # Reference penalty
    ref_patterns = [r'σύμφωνα με', r'βάσει των', r'κατά τα', r'όπως ορίζεται']
    for pat in ref_patterns:
        if re.search(pat, expl, re.I):
            score *= 0.8
            break

    # Word count penalty
    word_count = len(expl.split())
    if word_count < 3:
        score *= 0.5
    elif word_count < 5:
        score *= 0.8

    return max(0.2, min(2.0, score))

# Extraction helper (same as before, but confidence threshold lowered)
def extract_defs(txt: str):
    res = []
    if not txt or len(txt) < 100:
        return res

    patterns = [
        (verb_rgx, "verb"),
        (bullet_rgx, "bullet"),
        (scope_rgx, "scope"),
        (kata_ennoia_rgx, "kata_ennoia"),
        (legetai_rgx, "legetai"),
        (paren_rgx, "parenthesis")
    ]

    found_terms = set()

    for pattern, tag in patterns:
        for m in pattern.finditer(txt):
            start, end = m.span()

            term = ""
            try:
                term = m.group('term') or ""
            except IndexError:
                pass
            if not term:
                try:
                    term = m.group('alt_term') or ""
                except IndexError:
                    pass
            if not term:
                try:
                    term = m.group('bullet') or ""
                except IndexError:
                    pass
            term = term.strip()

            expl = ""
            try:
                expl = m.group('expl') or ""
            except IndexError:
                pass
            expl = expl.strip()

            if not term or len(term) < 2 or not expl:
                continue

            term_key = term.lower().strip()
            if term_key in found_terms:
                continue

            ctx_start = max(0, start - 150)
            ctx_end = min(len(txt), end + 150)
            excerpt = txt[ctx_start:ctx_end]

            bullet = None
            try:
                bullet = m.group('bullet')
            except IndexError:
                pass

            rec = {
                "term": term,
                "explanation": expl,
                "offset_start": start,
                "offset_end": end,
                "excerpt": excerpt,
                "bullet": bullet,
                "tag": tag
            }
            rec["confidence"] = calculate_confidence(rec, txt)

            if rec["confidence"] >= 0.1:      # Lowered threshold
                res.append(rec)
                found_terms.add(term_key)

    res.sort(key=lambda x: (-x["confidence"], x["offset_start"]))
    final = []
    seen = set()
    for r in res:
        key = r["term"].lower().strip()
        if key not in seen:
            seen.add(key)
            final.append(r)
    return final

# Progress reporting (same as before)
s.execute("SELECT COUNT(*) FROM et WHERE fekTEXT IS NOT NULL AND LENGTH(fekTEXT) > 500")
total_rows = s.fetchone()[0]
if total_rows == 0:
    print("No FEK texts found to process.")
    src.close()
    dst.close()
    sys.exit(0)

print(f"Total FEK texts to process: {total_rows}")

s.execute("SELECT ID, fekNumber, fekTEXT, fekEtos, nomosNum FROM et WHERE fekTEXT IS NOT NULL AND LENGTH(fekTEXT) > 500")

start_time = time.time()
processed = 0
inserted = 0
low_confidence = 0

for row in s:
    fekID, fekNumber, fekText, fekEtos, nomosNum = row
    for rec in extract_defs(fekText):
        d.execute("""
        INSERT INTO definitions
          (term, explanation, fekID, fekNumber, fekText, fekEtos,
           nomosNum, excerpt, offset_start, offset_end, bullet, pattern_tag, confidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rec["term"], rec["explanation"], fekID, fekNumber, fekText, fekEtos,
            nomosNum, rec["excerpt"], rec["offset_start"], rec["offset_end"],
            rec["bullet"], rec["tag"], rec["confidence"]
        ))
        inserted += 1
        if rec["confidence"] < 0.7:          # Keep low confidence flag
            low_confidence += 1

    processed += 1

    if processed % 10 == 0 or processed == total_rows:
        elapsed = time.time() - start_time
        percent = (processed / total_rows) * 100
        eta_seconds = (elapsed / processed) * (total_rows - processed) if processed > 0 else 0
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
        sys.stdout.write(f"\rProgress: {processed}/{total_rows} ({percent:.1f}%) | Elapsed: {elapsed_str} | ETA: {eta_str} | Definitions found: {inserted}")
        sys.stdout.flush()

dst.commit()
src.close()
dst.close()

print()
print(f"[+] Finished. Total definitions inserted: {inserted}")
if inserted > 0:
    print(f"[!] Low confidence definitions (<0.7): {low_confidence} ({low_confidence/inserted*100:.1f}% of total)")
else:
    print("[!] No definitions found.")