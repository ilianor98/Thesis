"""Ολόκληρη η ροή: εξαγωγή → βαθμολόγηση → (προαιρετικά) κατηγοριοποίηση με το KEVLAR.

Παραδείγματα:
    python pipeline.py --source ../vasi/harvester.db --out ../vasi/orismoi_new.db
    python pipeline.py --source ../vasi/harvester.db --out ../vasi/orismoi_new.db --categorize
    python pipeline.py --out ../vasi/orismoi_new.db --only-categorize      # κατηγορίες σε υπάρχοντα αποτελέσματα

Το UI (ui.py) εκτελεί αυτό το αρχείο στο παρασκήνιο και διαβάζει την πρόοδο από το --status-file.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import category
import extract
import score
from directories import DEFAULT_HARVESTER, DEFAULT_RESULTS

# στήλες του πίνακα et που χρειάζεται η εξαγωγή
HARVESTER_COLUMNS = ("ID", "fekNumber", "fekEtos", "nomosNum", "nomosCategory", "fekTEXT")


# ───────────────────────── Έλεγχος βάσεων
def _ro(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)


def db_kind(path) -> str:
    """'results' (έχει πίνακα definitions), 'harvester' (πίνακας et με τις απαιτούμενες στήλες) ή ''."""
    try:
        con = _ro(path)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        et_cols = {r[1] for r in con.execute("PRAGMA table_info(et)")} if "et" in tables else set()
        con.close()
    except sqlite3.Error:
        return ""
    if "definitions" in tables:
        return "results"
    if set(HARVESTER_COLUMNS) <= et_cols:
        return "harvester"
    return ""


def validate_harvester(path) -> list:
    """Λίστα προβλημάτων· κενή αν η βάση έχει το αναμενόμενο σχήμα."""
    p = Path(path)
    if not p.is_file():
        return [f"Δεν βρέθηκε το αρχείο {p}"]
    try:
        con = _ro(p)
        cols = {r[1] for r in con.execute("PRAGMA table_info(et)")}
        con.close()
    except sqlite3.Error as e:
        return [f"Το αρχείο δεν είναι έγκυρη βάση SQLite ({e})"]
    if not cols:
        return ["Η βάση δεν έχει πίνακα et"]
    missing = [c for c in HARVESTER_COLUMNS if c not in cols]
    return [f"Λείπουν στήλες του πίνακα et: {', '.join(missing)}"] if missing else []


def harvester_summary(path) -> dict:
    con = _ro(path)
    rows, with_text, y0, y1 = con.execute(
        "SELECT COUNT(*), SUM(length(fekTEXT) > 100), MIN(fekEtos), MAX(fekEtos) FROM et").fetchone()
    con.close()
    return {"rows": rows, "with_text": with_text or 0, "year_min": y0, "year_max": y1}


def read_run_info(path) -> dict:
    try:
        con = _ro(path)
        info = dict(con.execute("SELECT key, value FROM run_info").fetchall())
        con.close()
        return info
    except sqlite3.Error:
        return {}


def write_run_info(db, info: dict) -> None:
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS run_info (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany("INSERT OR REPLACE INTO run_info (key, value) VALUES (?, ?)",
                    [(k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))
                     for k, v in info.items() if v is not None])
    con.commit()
    con.close()


# ───────────────────────── Πρόοδος
class Status:
    """Γράφει την πρόοδο σε αρχείο JSON (αν δοθεί), ώστε να τη διαβάζει το UI."""

    def __init__(self, path=None, **base):
        self.path = Path(path) if path else None
        self.data = {"state": "running", "pid": os.getpid(), "started": time.time(), **base}
        self.update()

    def update(self, **values):
        self.data.update(values)
        self.data["updated"] = time.time()
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)

    def stage(self, name, message):
        print(f"── {message}")
        self.update(stage=name, done=0, total=0, message=message)
        return lambda done, total: self.update(done=done, total=total)


# ───────────────────────── Εκτέλεση
def run_pipeline(source=None, out=DEFAULT_RESULTS, categorize=False, only_categorize=False,
                 api_base=category.API_BASE, overwrite=False, status_file=None) -> dict:
    out = Path(out)
    status = Status(status_file, source=str(source) if source else None, out=str(out),
                    categorize=bool(categorize or only_categorize))
    started = time.time()
    summary = {}
    try:
        # 1. έλεγχοι (πριν αλλάξει οτιδήποτε στον δίσκο)
        if only_categorize:
            if db_kind(out) != "results":
                raise ValueError(f"Το {out} δεν είναι βάση αποτελεσμάτων (πίνακας definitions).")
        else:
            problems = validate_harvester(source)
            if problems:
                raise ValueError("; ".join(problems))
            if out.exists():
                if out.resolve() == Path(source).resolve() or db_kind(out) == "harvester":
                    raise ValueError(f"Το {out.name} είναι βάση harvester· δεν αντικαθίσταται.")
                if not overwrite:
                    raise FileExistsError(f"Το {out} υπάρχει ήδη (χρησιμοποίησε --overwrite).")
        if categorize or only_categorize:
            ok, _ = category.kevlar_status(api_base)
            if not ok:
                raise RuntimeError(f"Το KEVLAR δεν απαντά στο {api_base}. "
                                   f"Ξεκίνησέ το με: docker run -p 8080:80 kevlar")

        # 2. εκτέλεση
        if not only_categorize:
            if out.exists():
                out.unlink()
            out.parent.mkdir(parents=True, exist_ok=True)
            summary["extraction"] = extract.run(source, out, status.stage("extract", "Εξαγωγή ορισμών"))
            summary["scoring"] = score.run(out, status.stage("score", "Βαθμολόγηση"))
        if categorize or only_categorize:
            summary["categorization"] = category.run(out, api_base, status.stage("categorize", "Κατηγοριοποίηση (KEVLAR)"))

        info = {"updated_at": datetime.now().isoformat(timespec="seconds")}
        if not only_categorize:
            ext, sc = summary["extraction"], summary["scoring"]
            info.update({
                "created_at": info["updated_at"],
                "source": str(Path(source).resolve()),
                "extract_version": extract.EXTRACT_VERSION,
                "scoring_version": score.RULE_VERSION,
                "definitions": ext["definitions"], "issues": ext["issues"],
                "by_tag": ext["by_tag"], "act_unresolved": ext["act_unresolved"],
                "needs_review": sc["needs_review"], "mean_confidence": sc["mean_confidence"],
            })
        if "categorization" in summary:
            cat = summary["categorization"]
            info.update({"kevlar_model": cat["model"], "kevlar_api": cat["api_url"],
                         "classified": cat["classified"], "classification_failed": cat["failed"]})
        info["duration_s"] = round(time.time() - started, 1)
        write_run_info(out, info)

        status.update(state="done", stage="done", message="Ολοκληρώθηκε", summary=summary)
        return summary
    except Exception as e:
        status.update(state="error", message=str(e))
        raise


def main():
    ap = argparse.ArgumentParser(description="Εξαγωγή, βαθμολόγηση και κατηγοριοποίηση νομικών ορισμών.")
    ap.add_argument("--source", default=str(DEFAULT_HARVESTER), help="βάση harvester (προεπιλογή: %(default)s)")
    ap.add_argument("--out", default=str(DEFAULT_RESULTS), help="βάση αποτελεσμάτων (προεπιλογή: %(default)s)")
    ap.add_argument("--categorize", action="store_true", help="κατηγοριοποίηση με το KEVLAR (πρέπει να τρέχει)")
    ap.add_argument("--only-categorize", action="store_true", help="μόνο κατηγοριοποίηση μιας υπάρχουσας βάσης --out")
    ap.add_argument("--api", default=category.API_BASE, help="διεύθυνση του KEVLAR (προεπιλογή: %(default)s)")
    ap.add_argument("--overwrite", action="store_true", help="αντικατάσταση της --out αν υπάρχει")
    ap.add_argument("--status-file", help="αρχείο JSON για την πρόοδο (χρησιμοποιείται από το UI)")
    args = ap.parse_args()
    try:
        run_pipeline(args.source, args.out, args.categorize, args.only_categorize,
                     args.api, args.overwrite, args.status_file)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
