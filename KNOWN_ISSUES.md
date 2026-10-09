# Known issues

Recorded 2026-10-08. Decision: keep the code as it is and document these in the thesis (Ch4 Υλοποίηση, Ch5 Αποτίμηση, Ch6 Επίλογος) rather than fix them.

**Update 2026-10-09:** `extract_junk.py` was rewritten, and its output now goes to a new database, `vasi/orismoi_final.db`. Issues 1 and 3 and the first and last points of issue 2 are fixed there. Sections 1–3 still describe the previous results in `orismoi_test1.db` correctly; those are the results the thesis text and the current scores and categories use. Section 4 lists what the new version still does not handle.

## 1. The definitional-verb rule almost never matches

**Where:** `verb_rgx` in `extract.py`, `extract_re.py` and `extract_junk.py`.

**Cause:** the pattern starts with a word boundary before the opening quote:

```
\b[«"](?P<term>[^»"]+)[»"]\s+{verb_core}\s+ως ...
```

`\b` only matches between a word character and a non-word character. In normal text the opening `«` follows a space, and both are non-word characters, so there is no boundary and the rule fails before it reaches the verb.

**Reproduction:**

```python
import re
s = 'Για την εφαρμογή του παρόντος «Επενδυτής» ορίζεται ως κάθε φυσικό πρόσωπο που επενδύει.'
re.search(r'\b[«"](?P<term>[^»"]+)[»"]\s+ορίζεται\s+ως', s)  # -> None
re.search(r'[«"](?P<term>[^»"]+)[»"]\s+ορίζεται\s+ως', s)    # -> matches «Επενδυτής» ορίζεται ως
```

**Impact on the data:**

| Run (output DB) | bullet | scope | verb |
|---|---|---|---|
| `extract_re.py` → `orismoi_test.db` | 9,077 | 694 | 3 |
| `extract_junk.py` → `orismoi_test1.db` (final) | 6,755 | 880 | 0 |

The final dataset therefore contains no definitions found through definitional verbs (`ορίζεται`, `νοείται`, `σημαίνει`, `θεωρείται`, `καθορίζεται`).

**Likely fix (not applied):** remove the leading `\b`, then rerun extraction, `scores_def_2.py` and `category1.py` (the last needs the KEVLAR container running).

## 2. Related observations (not bugs, but the thesis must describe them accurately)

- **Scope definitions have no explanation in the final data.** `extract_junk.py`'s scope rule stores only the term (`explanation = ""`), so all 880 scope rows in `orismoi_test1.db` are empty and score low in `score_2` (mean 0.181 vs 0.576 for bullet rows). `extract_re.py`'s scope rule did capture explanations (694/694 non-empty).
- **There is no separate nested-bullet merging step.** Sub-items such as `α)`, `β)` end up inside an explanation only because the bullet rule's lookahead stops at the next bullet that starts with a quoted term.
- **Unquoted definitions are not covered.** The bullet and verb rules both require the term in quotes. Example: Ν. 4048/2012 (ΦΕΚ Α΄ 34, `et.ID` 3463), whose Άρθρο 1 «Ορισμοί» contains "α. Ρύθμιση είναι …", "β. Καλή νομοθέτηση είναι …", yields 0 extracted definitions.

## 3. Acts published in the same ΦΕΚ issue share one text, so definitions are stored more than once

Recorded 2026-10-09. Not a code change; the thesis numbers must account for it.

**Where:** `harvester.db`, table `et`. There is one row per act (`nomosNum`), but `fekTEXT` holds the full text of the whole ΦΕΚ issue (φύλλο), with every act published in it. Every act of the same issue (`fekNumber`, `fekEtos`) has the identical text. Example: ΦΕΚ Α΄ 19/1992 (π.δ. 38–47/1992) is stored as 10 rows with the same 34,728-character text.

**Effect:** the extraction scripts loop over `et` rows, so a definition inside a shared issue is inserted once per act of that issue, each time with a different `fekID`/`nomosNum` but the same `fekNumber`, `fekEtos` and offsets. It is also attributed to acts that do not contain it (e.g. «Προϊσταμένη Αρχή» belongs to π.δ. 47/1992 but is also linked to π.δ. 38–46/1992).

**Numbers (verified with read-only queries):**

| | rows / records | unique |
|---|---|---|
| `et` rows with text > 100 chars | 10,868 | 6,898 distinct issue texts |
| `definitions` rows in `orismoi_test1.db` | 7,635 | 6,961 unique occurrences (issue + offsets) |
| by tag | bullet 6,755 / scope 880 | bullet 6,137 / scope 824 |
| acts / issues with ≥1 definition | 1,063 `fekID` | 831 distinct issues |
| `category` rows (non-blank explanation sent to KEVLAR) | 6,716 | 6,694 got ≥1 category; 6,095 unique occurrences |
| «Προϊσταμένη Αρχή» | 64 rows | 21 occurrences in 19 issues |
| «Διευθύνουσα Υπηρεσία» | 64 rows | 22 occurrences in 20 issues |
| «μόνιμη εγκατάσταση» | 28 rows | 28 occurrences in 28 issues |

**Likely fix (not applied):** run extraction once per distinct (`fekNumber`, `fekEtos`) text, or deduplicate on (`fekNumber`, `fekEtos`, `offset_start`, `offset_end`) before scoring and categorization. Assigning each definition to the correct act would require splitting the issue text at the act headings (e.g. `ΠΡΟΕΔΡΙΚΟ ΔΙΑΤΑΓΜΑ ΥΠ' ΑΡΙΘ. 47`).

## 4. The rewritten extraction (2026-10-09): what changed and what it still misses

**Changes in `extract_junk.py`:**

- **Line breaks:** all line endings are normalized (`\r\n` → ` \n`, lone `\r` → `\n`, so every offset stays the same). In a 400-issue sample, 55 texts (14%) used lone `\r` and had produced no list definitions at all. In `\r\n` texts, sentence ends and lines ending in «…:» were not recognized.
- **Item markers:** `στ)`, `ια)`, `αα)`, `(α)`, `(1)` and `ιζ.` are now accepted. The old rule missed 99 of the 369 quoted items in the sampled «Ορισμοί» articles and merged each one into the explanation of the previous item; the new one catches all 369.
- **Curly quotes:** “ ” and „ are accepted as quotes.
- **Words after the term:** «είναι», «σημαίνουν», «εννοείται», «νοούνται» and «ως» may appear between the term and the explanation.
- **End of an explanation:** it stops at the next item, at an article heading, at ΚΕΦΑΛΑΙΟ/ΜΕΡΟΣ/ΤΜΗΜΑ/ΤΙΤΛΟΣ/ΠΑΡΑΡΤΗΜΑ/Article/Regulation, at a new numbered paragraph, at the next act heading or at the signatures. A safety cap of 5,000 characters applies.
- **Unquoted terms** (`pattern_tag = 'unquoted'`): accepted only inside articles titled «Ορισμοί»/«Έννοια όρων», or after a line such as «Για τους σκοπούς του παρόντος, νοούνται ως:». That line must announce definitions (νοείται/νοούνται, ορισμοί/ορίζονται, σημαίνει, έννοια or όροι); otherwise its «:» usually introduces forms or lists. A filter rejects terms that look like the start of a sentence.
- **Verb rule** (`pattern_tag = 'verb'`): it now works. It covers «Χ» (θα) νοείται/σημαίνει … and ως «Χ» νοείται …; ορίζεται, θεωρείται and λογίζεται count only when followed by «ως».
- **Empty explanations** are dropped.
- **Scope:** the old scope rule (term only, empty explanation) is removed. The scope phrase is stored in the new `scope` column of the definitions that follow it.
- **Shared ΦΕΚ text:** the script runs once per ΦΕΚ issue, and each definition is assigned to the act whose heading precedes it (`act_resolved = 1`).
- **New columns:** `in_def_article` and `lang` (`el`/`other`). The full ΦΕΚ text is no longer copied into every row, which brings the database from 2.9 GB down to about 38 MB.

**Full run (about 30 s):**

| | count |
|---|---|
| definitions (all unique) | 15,187 |
| bullet / unquoted / verb | 8,730 / 3,086 / 3,371 |
| ΦΕΚ issues with ≥1 definition | 1,429 (1,459 acts) |
| inside a definitions article | 9,340 |
| with a scope phrase | 10,662 |
| tagged as not Greek (`lang = 'other'`) | 227 |
| act not identified with certainty (`act_resolved = 0`) | 24 |
| explanations at the 5,000-character cap | 4 |

For comparison, the previous version produced 6,961 unique occurrences in 831 issues. These are random spot checks, not a gold standard:

| Group | Genuine definitions |
|---|---|
| verb rows | all 22 sampled (from the sample) and all 20 sampled (from the full run) |
| unquoted rows inside «Ορισμοί» articles | 21 of 22 |
| unquoted rows outside «Ορισμοί» articles (527 rows; most come after a «…νοούνται ως:» line) | about 17 of 25 |

The one bad unquoted row inside an article («Δεν») led to an added filter.

**Scoring (`scores_def_2.py`, `rule_version = 'v3_structure'`).** The score is additive and each row records its contributions:

- **Base:** 0.20.
- **Rule:** verb +0.15, unquoted +0.10, quoted list item +0.15 only when it has a definition context (definitions article, scope phrase, or «:»/definitional verb after the term).
- **Context:** definitions article +0.15, scope +0.05, explicit connector +0.10.
- **Term:** 1–6 words +0.05, more than 10 words −0.10, mostly digits −0.15.
- **Explanation:**
  - length: under 20 characters −0.25; 20–39 −0.05; 40–1,200 +0.10; 1,200–2,999 −0.05; 3,000 or more −0.15;
  - starts with a noun phrase or definitional verb +0.10;
  - starts with «ή»/«και» −0.05;
  - clean ending +0.05 («,», «·» and «?» count as clean); ends in «:» −0.05; ends mid-sentence −0.10;
  - heading inside −0.20; amendment verbs −0.10; second «Χ» νοείται inside −0.05.
- **Language:** not Greek −0.30.

The maximum is 0.95. `needs_review = confidence < 0.50`.

| | count |
|---|---|
| mean confidence | 0.779 |
| needs review | 1,272 (8.4%) |
| — of which inside a definitions article | 6 of 9,340 |
| — of which outside | 1,266 of 5,847 |
| score bands <0.30 / 0.30–0.49 / 0.50–0.69 / 0.70–0.84 / ≥0.85 | 659 / 613 / 1,451 / 4,813 / 7,651 |

Inspection of random rows per band found mostly non-definitions below 0.30, a mix between 0.30 and 0.69, and genuine definitions above 0.80. Typical non-definitions were lists of entities, form fields and English treaty text. The rows in between were real definitions with flaws, next to amendments and other provisions.

**Still not handled:**

- **Several terms in one item.** In cases like «Προϊσταμένη Αρχή» ή «Εποπτεύουσα Αρχή» είναι … or «Χ», «Υ» … έχουν την έννοια, only the first term becomes the term and the others stay at the start of the explanation.
- **Definitions inside amendment text.** Lines starting with «α) «Όρος»… (14 items in 5 of 400 sampled texts) are not extracted, as before.
- **Texts without line breaks** (e.g. ΦΕΚ Α΄ 237/2000). The list rules depend on line starts, so only the verb rule can find definitions there.
- **Inline lists** («…, ζ) ως «Διοικητής» νοείται …»). A verb-rule explanation can run into the next inline item; that item is also extracted on its own.
- **Long explanations.** 4 explanations reach the 5,000-character cap.
- **Ambiguous markers.** `ια)` can be the 11th case or a sub-case (ι → α). The rules do not track numbering sequences, so an unquoted sibling item that is not a definition can stay inside the previous explanation.
- **The score is a heuristic.** It reflects structural evidence, not meaning. A non-definition inside a definitions context, such as a provision written as «Όρος: …», can still score high. Definitions outside a definitions context score lower even when they are genuine (mean 0.618 vs 0.880 inside).
