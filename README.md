# Thesis helper: Extract → Score → Categorize (ΦΕΚ / Νομικοί ορισμοί)

Μικρό project για τη διπλωματική μου: **εντοπίζω νομικούς ορισμούς μέσα σε κείμενα ΦΕΚ**, τους αποθηκεύω σε SQLite και μετά τους “βαθμολογώ” + τους **κατηγοριοποιώ θεματικά** με Kevlar.

## Τι περιέχει

### 1) Πηγή δεδομένων: `harvester.db`
Χρησιμοποιώ τη βάση Harvester (SQLite). Τα κείμενα βρίσκονται στον πίνακα `et` (π.χ. `ID`, `fekTEXT`, κ.λπ.).

### 2) Εξαγωγή ορισμών: `extract.py`
Διαβάζει το `et.fekTEXT` και εξάγει ορισμούς με regex κανόνες (bullets/εισαγωγικά/ρήματα “ορίζεται/νοείται/σημαίνει” κτλ.).
Τα αποτελέσματα πάνε σε νέα SQLite βάση στον πίνακα:

- `definitions`  
  `term`, `explanation`, `fekID` + βοηθητικά (`excerpt`, offsets, `bullet`, `pattern_tag`)

### 3) Confidence scoring: `score_2`
Περνάω κάθε εγγραφή του `definitions` από heuristics και βγάζω:
- `confidence` (0..1)
- `needs_review` (flag για χειροκίνητο έλεγχο)
- extra flags (π.χ. πολύ μεγάλο/πολύ μικρό κείμενο, nested bullets, ύποπτος όρος, κτλ.)
Αποθηκεύονται σε πίνακα `score_2` με `def_id` → `definitions.ID`.

### 4) Κατηγοριοποίηση (Kevlar): `category.py`
Τρέχω Kevlar **τοπικά** με Docker και για κάθε definition στέλνω:
- `title = term`
- `text = explanation`

Kevlar επιστρέφει λίστα κατηγοριών με scores. Κρατάω top-3 και τα γράφω σε πίνακα `category` (ή `category_2`) με FK στο `definitions.ID`.

## Kevlar local setup
```bash
docker run --rm --name kevlar -p 8080:80 kevlar:latest