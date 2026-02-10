import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:/Users/User B/Desktop/ilias/thesis/vasi/orismoi.db")

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

# Drop & recreate tables
cur.executescript("""
DROP TABLE IF EXISTS definitions;
DROP TABLE IF EXISTS category;

CREATE TABLE definitions (
    ID            INTEGER PRIMARY KEY AUTOINCREMENT,
    term          TEXT NOT NULL,
    explanation   TEXT NOT NULL,
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

CREATE TABLE category (
    defID  INTEGER PRIMARY KEY,
    cat1   TEXT, score1 REAL,
    cat2   TEXT, score2 REAL,
    cat3   TEXT, score3 REAL,
    FOREIGN KEY(defID) REFERENCES definitions(ID)
);
""")

# Mock definitions
definitions = [
    ("Δικαστική Αστυνομία", "Υπηρεσία που υποστηρίζει το έργο της δικαιοσύνης.",
     1, 6, "ΠΡΟΕΔΡΙΚΟ ΔΙΑΤΑΓΜΑ ΥΠ’ ΑΡΙΘΜ. 6 ...", 2023, 4963, "…Δικαστική Αστυνομία…", 120, 200, "1", "bullet"),

    ("Επένδυση", "Κάθε είδους περιουσιακό στοιχείο που επενδύεται.",
     2, 1, "ΔΙΕΘΝΗΣ ΣΥΜΦΩΝΙΑ ...", 2020, 1234, "…Επένδυση σημαίνει…", 50, 180, "1", "bullet"),

    ("Επενδυτής", "Φυσικό ή νομικό πρόσωπο που πραγματοποιεί επένδυση.",
     2, 1, "ΔΙΕΘΝΗΣ ΣΥΜΦΩΝΙΑ ...", 2020, 1234, "…Επενδυτής σημαίνει…", 200, 360, "2", "bullet"),

    ("Απόδοση", "Τα έσοδα που αποφέρει μία επένδυση.",
     2, 1, "ΔΙΕΘΝΗΣ ΣΥΜΦΩΝΙΑ ...", 2020, 1234, "…Απόδοση σημαίνει…", 380, 480, "3", "bullet"),

    ("Σχέδιο Δράσης", "Έγγραφο με τα μέτρα εφαρμογής ενός σχεδίου.",
     3, 45, "ΝΟΜΟΣ ...", 2022, 5010, "…Σχέδιο δράσης…", 60, 190, "α", "bullet"),

    ("Ομάδα Εργασίας", "Σύνολο προσώπων με αρμοδιότητα εκπόνησης σχεδίου.",
     3, 45, "ΝΟΜΟΣ ...", 2022, 5010, "…Ομάδα εργασίας…", 200, 320, "β", "bullet"),

    ("Δείκτες Παρακολούθησης", "Μετρήσιμα μεγέθη αξιολόγησης.",
     3, 45, "ΝΟΜΟΣ ...", 2022, 5010, "…Δείκτες…", 340, 460, "γ", "bullet"),

    ("Δικαστήριο", "Κρατικό όργανο απονομής δικαιοσύνης.",
     4, 99, "ΚΩΔΙΚΑΣ ...", 2019, 4620, "…Δικαστήριο…", 20, 120, None, "verb"),

    ("Κατηγορούμενος", "Πρόσωπο στο οποίο αποδίδεται αξιόποινη πράξη.",
     4, 99, "ΚΩΔΙΚΑΣ ...", 2019, 4620, "…Κατηγορούμενος…", 140, 260, None, "verb"),

    ("Αρμόδια Αρχή", "Η αρχή που είναι υπεύθυνη για την εφαρμογή του νόμου.",
     5, 12, "ΚΑΝΟΝΙΣΜΟΣ ...", 2021, 4800, "…Αρμόδια αρχή…", 80, 200, None, "scope"),
]

cur.executemany("""
INSERT INTO definitions
(term, explanation, fekID, fekNumber, fekText, fekEtos,
 nomosNum, excerpt, offset_start, offset_end, bullet, pattern_tag)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
""", definitions)

# Mock categories (top-3)
categories = [
    (1, "justice", 0.82, "public administration", 0.41, "law enforcement", 0.22),
    (2, "investment", 0.91, "finance", 0.44, "economy", 0.30),
    (3, "investment", 0.88, "finance", 0.39, "economy", 0.25),
    (4, "investment income", 0.86, "finance", 0.40, "economy", 0.28),
    (5, "public policy", 0.77, "planning", 0.51, "administration", 0.29),
    (6, "public policy", 0.74, "planning", 0.49, "administration", 0.31),
    (7, "monitoring", 0.69, "evaluation", 0.52, "statistics", 0.33),
    (8, "justice", 0.90, "courts", 0.60, "law", 0.35),
    (9, "criminal law", 0.87, "justice", 0.55, "procedure", 0.38),
    (10,"administration", 0.71, "regulation", 0.50, "governance", 0.34),
]

cur.executemany("""
INSERT INTO category
(defID, cat1, score1, cat2, score2, cat3, score3)
VALUES (?,?,?,?,?,?,?)
""", categories)

con.commit()
con.close()

print(f"[✓] Mock orismoi.db created at:\n{DB_PATH}")
