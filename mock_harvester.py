import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:/Users/User B/Desktop/ilias/thesis/vasi/harvester.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

# Drop & recreate tables (minimal set: et + legis + sqlite_sequence is auto)
cur.executescript("""
DROP TABLE IF EXISTS et;
DROP TABLE IF EXISTS legis;

-- et table (matches the schema you showed)
CREATE TABLE et (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    fekNumber INTEGER NOT NULL,
    fekReleaseDate DATE,
    fekIssueLektiko VARCHAR(20),
    fekIssueNumber INTEGER,
    fekEtos INTEGER NOT NULL,
    fekDate DATE NOT NULL,
    fekSumPage INTEGER,
    fekArxeio INTEGER NOT NULL,
    fekTEXT TEXT,
    fekTEXTSize INTEGER DEFAULT 0,
    fekTEXTorig INTEGER DEFAULT 0,
    nomosTitle TEXT,
    nomosNum INTEGER,
    nomosCategory VARCHAR(30),
    fileLocalName VARCHAR(30),
    fileLocalPath TEXT,
    fileLocalSize INTEGER,
    fileLocalExists INTEGER DEFAULT 0,
    fileLocalDowDate DATE,
    filePerilipsi INTEGER,
    fileRemote TEXT,
    fileRemotePerilipsi TEXT,
    ministry TEXT,
    fekID INTEGER
);

-- legis table (minimal columns based on your schema; not required by ui, but included)
CREATE TABLE legis (
    phase TEXT,
    reportCommission TEXT,
    fekNumber NUMERIC,
    votingDate DATE,
    passedArticleBill TEXT,
    passedBill TEXT,
    title TEXT,
    type TEXT,
    depositDate DATE,
    report TEXT,
    commission TEXT,
    href TEXT,
    id TEXT PRIMARY KEY,
    phaseDate DATE,
    ministry TEXT,
    ministryNEW TEXT,
    lawNumber INTEGER,
    committeeMeetings TEXT,
    tropologies TEXT,
    relevantFiles TEXT,
    speakers TEXT,
    plenarySession TEXT
);
""")

# 10 mock laws for et
laws = [
    dict(
        fekNumber=6, fekReleaseDate="2023-01-19", fekIssueLektiko="A", fekIssueNumber=10,
        fekEtos=2023, fekDate="2023-01-19", fekSumPage=12, fekArxeio=20230100006,
        nomosTitle="ΣΥΣΤΑΣΗ ΔΙΕΥΘΥΝΣΗΣ ΔΙΚΑΣΤΙΚΗΣ ΑΣΤΥΝΟΜΙΑΣ ΚΑΙ ΚΑΘΟΡΙΣΜΟΣ ΑΡΜΟΔΙΟΤΗΤΩΝ.",
        nomosNum=6, nomosCategory="Π.Δ.", ministry="Υπουργείο Δικαιοσύνης",
        fileLocalName="FEK_20230100006.pdf", fileLocalPath="D:/data/fek/",
        fileRemote="https://example.com/fek/20230100006",
        fekTEXT=(
            "ΠΡΟΕΔΡΙΚΟ ΔΙΑΤΑΓΜΑ ΥΠ’ ΑΡΙΘΜ. 6\n"
            "Άρθρο 1\n"
            "Σύσταση Διεύθυνσης Δικαστικής Αστυνομίας\n"
            "1. Για την υλοποίηση του θεσμού της Δικαστικής Αστυνομίας συστήνεται μία (1) Διεύθυνση...\n"
            "Άρθρο 2\n"
            "Σύσταση περιφερειακής υπηρεσίας...\n"
        )
    ),
    dict(
        fekNumber=1, fekReleaseDate="2020-02-10", fekIssueLektiko="A", fekIssueNumber=25,
        fekEtos=2020, fekDate="2020-02-10", fekSumPage=8, fekArxeio=20200100001,
        nomosTitle="ΚΥΡΩΣΗ ΣΥΜΦΩΝΙΑΣ ΠΡΟΣΤΑΣΙΑΣ ΕΠΕΝΔΥΣΕΩΝ.",
        nomosNum=4500, nomosCategory="Ν.", ministry="Υπουργείο Εξωτερικών",
        fileLocalName="FEK_20200100001.pdf", fileLocalPath="D:/data/fek/",
        fileRemote="https://example.com/fek/20200100001",
        fekTEXT=(
            "ΑΡΘΡΟ 1 Ορισμοί\n"
            "Για τους σκοπούς της παρούσας Συμφωνίας:\n"
            "1. \"Επένδυση\" σημαίνει κάθε είδους περιουσιακό στοιχείο...\n"
            "α) κινητή και ακίνητη ιδιοκτησία...\n"
            "β) μετοχές...\n"
            "2. \"Απόδοση\" σημαίνει τα έσοδα που αποφέρει μία επένδυση...\n"
            "3. \"Επενδυτής\" σημαίνει σε σχέση με κάθε Συμβαλλόμενο Μέρος...\n"
        )
    ),
    dict(
        fekNumber=45, fekReleaseDate="2022-06-01", fekIssueLektiko="A", fekIssueNumber=110,
        fekEtos=2022, fekDate="2022-06-01", fekSumPage=20, fekArxeio=20220100045,
        nomosTitle="ΜΕΤΡΑ ΒΙΩΣΙΜΗΣ ΑΣΤΙΚΗΣ ΚΙΝΗΤΙΚΟΤΗΤΑΣ (Σ.Β.Α.Κ.).",
        nomosNum=5010, nomosCategory="Ν.", ministry="Υπουργείο Υποδομών και Μεταφορών",
        fileLocalName="FEK_20220100045.pdf", fileLocalPath="D:/data/fek/",
        fileRemote="https://example.com/fek/20220100045",
        fekTEXT=(
            "Για την εφαρμογή του νόμου ορίζονται ως:\n"
            "1. «Σχέδιο Βιώσιμης Αστικής Κινητικότητας (Σ.Β.Α.Κ.)», το στρατηγικό σχέδιο κινητικότητας...\n"
            "2. «Περιοχή παρέμβασης», η περιοχή στην οποία θα εφαρμοσθούν τα μέτρα...\n"
            "3. «Φορέας εκπόνησης», ο αρμόδιος για την περιοχή παρέμβασης ΟΤΑ...\n"
        )
    ),
    dict(
        fekNumber=99, fekReleaseDate="2019-12-01", fekIssueLektiko="A", fekIssueNumber=200,
        fekEtos=2019, fekDate="2019-12-01", fekSumPage=35, fekArxeio=20190100099,
        nomosTitle="ΚΩΔΙΚΑΣ ΠΟΙΝΙΚΗΣ ΔΙΚΟΝΟΜΙΑΣ (ΑΠΟΣΠΑΣΜΑ).",
        nomosNum=4620, nomosCategory="Ν.", ministry="Υπουργείο Δικαιοσύνης",
        fileLocalName="FEK_20190100099.pdf", fileLocalPath="D:/data/fek/",
        fileRemote="https://example.com/fek/20190100099",
        fekTEXT=(
            "«Δικαστήριο» ορίζεται ως το αρμόδιο κρατικό όργανο παροχής δικαστικής προστασίας.\n"
            "«Κατηγορούμενος» ορίζεται ως το πρόσωπο στο οποίο αποδίδεται αξιόποινη πράξη.\n"
        )
    ),
]

# Fill up to 10 with additional simple mock records
while len(laws) < 10:
    i = len(laws) + 1
    laws.append(dict(
        fekNumber=100+i, fekReleaseDate=f"2021-03-{i:02d}", fekIssueLektiko="A", fekIssueNumber=50+i,
        fekEtos=2021, fekDate=f"2021-03-{i:02d}", fekSumPage=5+i, fekArxeio=20210100000 + i,
        nomosTitle=f"ΕΝΔΕΙΚΤΙΚΟΣ ΝΟΜΟΣ #{i} (MOCK).",
        nomosNum=4700+i, nomosCategory="Ν.", ministry="Υπουργείο Εσωτερικών",
        fileLocalName=f"FEK_202101000{i:02d}.pdf", fileLocalPath="D:/data/fek/",
        fileRemote=f"https://example.com/fek/202101000{i:02d}",
        fekTEXT=(
            f"Άρθρο 1\n"
            f"Για τους σκοπούς του παρόντος, «Όρος {i}» σημαίνει μία δοκιμαστική έννοια.\n"
            f"Άρθρο 2\n"
            f"Διατάξεις εφαρμογής...\n"
        )
    ))

# Insert
for law in laws:
    fek_text = law["fekTEXT"]
    fek_text_size = len(fek_text.encode("utf-8")) if fek_text else 0

    cur.execute("""
        INSERT INTO et (
            fekNumber, fekReleaseDate, fekIssueLektiko, fekIssueNumber,
            fekEtos, fekDate, fekSumPage, fekArxeio,
            fekTEXT, fekTEXTSize, fekTEXTorig,
            nomosTitle, nomosNum, nomosCategory,
            fileLocalName, fileLocalPath, fileLocalSize, fileLocalExists, fileLocalDowDate,
            filePerilipsi, fileRemote, fileRemotePerilipsi, ministry, fekID
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
    """, (
        law["fekNumber"], law["fekReleaseDate"], law["fekIssueLektiko"], law["fekIssueNumber"],
        law["fekEtos"], law["fekDate"], law["fekSumPage"], law["fekArxeio"],
        fek_text, fek_text_size, 0,
        law["nomosTitle"], law["nomosNum"], law["nomosCategory"],
        law.get("fileLocalName", ""), law.get("fileLocalPath", ""), law.get("fileLocalSize", None),
        law.get("fileLocalExists", 0), law.get("fileLocalDowDate", None),
        law.get("filePerilipsi", 0), law.get("fileRemote", ""), law.get("fileRemotePerilipsi", ""),
        law.get("ministry", ""), law.get("fekID", None),
    ))

con.commit()
con.close()

print(f"[✓] Mock harvester.db created at:\n{DB_PATH}")
print("Inserted laws in et:", len(laws))
