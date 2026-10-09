# ui.py
# Dashboard + browse orismoi/categories + analytics page
# Run: streamlit run ui.py

import sys, subprocess, importlib
def _ensure(pkgs):
    for p in pkgs:
        try:
            importlib.import_module(p)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", p])
_ensure(["streamlit", "pandas", "altair"])

import streamlit as st
import pandas as pd
import altair as alt
import sqlite3
from pathlib import Path
from directories import *

# ─────────────────────────── Chart palette (validated categorical/sequential set)
BLUE       = "#2a78d6"   # primary series / sequential hue
BLUE_L     = "#86b6ef"   # ordinal ramp step 250 (light)
BLUE_M     = "#3987e5"   # ordinal ramp step 400 (mid)
BLUE_D     = "#1c5cab"   # ordinal ramp step 550 (dark)
GRID       = "#e1e0d9"
AXIS       = "#c3c2b7"
INK_2ND    = "#52514e"
INK_MUTED  = "#898781"
WARNING    = "#fab219"

def style(chart, height=300):
    """Apply consistent recessive-grid / muted-axis styling to an Altair chart."""
    return (
        chart
        .properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(
            gridColor=GRID, domainColor=AXIS,
            labelColor=INK_2ND, titleColor=INK_2ND,
            labelFontSize=11, titleFontSize=12,
        )
        .configure_title(color="#0b0b0b", fontSize=14)
    )

# ─────────────────────────── Settings (change defaults if needed)
DEFAULT_ORISMOI = SPITI_PC_ORISMOI_TEST1
DEFAULT_HARVEST = SPITI_PC_HARVEST

st.set_page_config(page_title="Ορισμοί & Κατηγορίες", layout="wide", page_icon="📚")

# ─────────────────────────── Basic helpers / DB utilities
def _conn(path: Path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con

@st.cache_data(show_spinner=False, ttl=60)
def table_exists(db_path: Path, table: str) -> bool:
    with _conn(db_path) as con:
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()
    return row is not None

@st.cache_data(show_spinner=False, ttl=60)
def get_year_bounds(orismoi_db: Path):
    with _conn(orismoi_db) as con:
        row = con.execute("SELECT MIN(fekEtos), MAX(fekEtos) FROM definitions").fetchone()
    return (row[0], row[1]) if row else (None, None)

@st.cache_data(show_spinner=False, ttl=60)
def get_distinct_tags(orismoi_db: Path):
    with _conn(orismoi_db) as con:
        rows = con.execute("SELECT DISTINCT pattern_tag FROM definitions ORDER BY 1").fetchall()
    return [r[0] for r in rows if r[0]]

def build_query(filters):
    where = ["1=1"]
    params = []

    if filters["only_with_cats"]:
        where.append("c.defID IS NOT NULL")
    if filters["q"]:
        where.append("(d.term LIKE ? OR d.explanation LIKE ?)")
        like = f"%{filters['q']}%"
        params += [like, like]
    if filters["year_min"] is not None and filters["year_max"] is not None:
        where.append("d.fekEtos BETWEEN ? AND ?")
        params += [filters["year_min"], filters["year_max"]]
    if filters["tags"]:
        where.append("d.pattern_tag IN (%s)" % ",".join("?"*len(filters["tags"])))
        params += list(filters["tags"])
    if filters["cat_q"]:
        where.append("(c.cat1 LIKE ? OR c.cat2 LIKE ? OR c.cat3 LIKE ?)")
        like = f"%{filters['cat_q']}%"
        params += [like, like, like]

    order_sql = {
        "ID ↑": "d.ID ASC",
        "ID ↓": "d.ID DESC",
        "Έτος ↑": "d.fekEtos ASC, d.ID ASC",
        "Έτος ↓": "d.fekEtos DESC, d.ID DESC",
    }[filters["order"]]

    sql = f"""
    SELECT
        d.ID, d.fekID, d.fekEtos, d.term, d.explanation,
        d.pattern_tag, d.bullet,
        c.cat1, c.score1, c.cat2, c.score2, c.cat3, c.score3
    FROM definitions d
    LEFT JOIN category c ON c.defID = d.ID
    WHERE {' AND '.join(where)}
    ORDER BY {order_sql}
    LIMIT ? OFFSET ?
    """
    params += [filters["page_size"], filters["page"] * filters["page_size"]]
    return sql, params

@st.cache_data(show_spinner=False, ttl=60)
def run_page_query(orismoi_db: Path, sql: str, params: list):
    with _conn(orismoi_db) as con:
        cur = con.execute(sql, params)
        rows = cur.fetchall()
    data = [dict(r) for r in rows]       # named columns
    df = pd.DataFrame.from_records(data)
    return df

@st.cache_data(show_spinner=False, ttl=60)
def count_total(orismoi_db: Path, filters):
    where = ["1=1"]
    params = []
    if filters["only_with_cats"]:
        where.append("c.defID IS NOT NULL")
    if filters["q"]:
        where.append("(d.term LIKE ? OR d.explanation LIKE ?)")
        like = f"%{filters['q']}%"; params += [like, like]
    if filters["year_min"] is not None and filters["year_max"] is not None:
        where.append("d.fekEtos BETWEEN ? AND ?")
        params += [filters["year_min"], filters["year_max"]]
    if filters["tags"]:
        where.append("d.pattern_tag IN (%s)" % ",".join("?"*len(filters["tags"])))
        params += list(filters["tags"])
    if filters["cat_q"]:
        where.append("(c.cat1 LIKE ? OR c.cat2 LIKE ? OR c.cat3 LIKE ?)")
        like = f"%{filters['cat_q']}%"; params += [like, like, like]

    sql = f"""
    SELECT COUNT(*)
    FROM definitions d
    LEFT JOIN category c ON c.defID = d.ID
    WHERE {' AND '.join(where)}
    """
    with _conn(orismoi_db) as con:
        total = con.execute(sql, params).fetchone()[0]
    return int(total)

@st.cache_data(show_spinner=False, ttl=60)
def get_title_and_text(harvester_db: Path, fek_id: int):
    with _conn(harvester_db) as con:
        row = con.execute("SELECT nomosTitle, fekTEXT FROM et WHERE ID = ?", (fek_id,)).fetchone()
    return (row[0], row[1]) if row else ("", "")

# ─────────────────────────── Analytics helpers (Category Overview page)
@st.cache_data(show_spinner=False, ttl=60)
def load_categorised(orismoi_db: Path, year_min: int, year_max: int) -> pd.DataFrame:
    """
    Load definitions joined with categories within year filter.
    Returns wide table with cat1..score3.
    """
    if not table_exists(orismoi_db, "category"):
        return pd.DataFrame()
    with _conn(orismoi_db) as con:
        rows = con.execute(
            """
            SELECT d.ID as defID, d.fekEtos,
                   c.cat1, c.score1, c.cat2, c.score2, c.cat3, c.score3
            FROM definitions d
            JOIN category c ON c.defID = d.ID
            WHERE d.fekEtos BETWEEN ? AND ?
            """,
            (year_min, year_max)
        ).fetchall()
    df = pd.DataFrame.from_records([dict(r) for r in rows])
    return df

def melt_categories(df: pd.DataFrame, only_rank1: bool = False) -> pd.DataFrame:
    """
    Convert wide cat1..score3 into long rows: (defID, year, rank, category, score)
    """
    if df.empty:
        return df
    records = []
    for _, r in df.iterrows():
        for rk in (1,2,3):
            if only_rank1 and rk != 1:
                continue
            cat = r.get(f"cat{rk}")
            sc  = r.get(f"score{rk}")
            if pd.isna(cat):
                continue
            records.append({
                "defID": int(r["defID"]),
                "fekEtos": int(r["fekEtos"]) if not pd.isna(r["fekEtos"]) else None,
                "rank": rk,
                "category": str(cat),
                "score": float(sc) if sc is not None and not pd.isna(sc) else 0.0
            })
    return pd.DataFrame.from_records(records)

def aggregate_categories(melt: pd.DataFrame, weight_by_score: bool, cat_filter: str):
    """
    Return (agg_df, totals) where agg_df has: category, count, mean_score, rank1, rank2, rank3
    """
    if melt.empty:
        return pd.DataFrame(), dict(total_defs=0, defs_with_cats=0, unique_cats=0, total_assignments=0)

    if cat_filter:
        mask = melt["category"].str.contains(cat_filter, case=False, na=False)
        melt = melt[mask]

    # Totals
    total_assignments = len(melt)
    defs_with_cats = melt["defID"].nunique()
    unique_cats = melt["category"].nunique()

    # Weight
    weights = melt["score"] if weight_by_score else 1.0

    # Aggregations
    grp = melt.copy()
    grp["w"] = weights
    agg = grp.groupby("category").agg(
        count=("w", "sum"),           # weighted count (or plain count)
        appearances=("category", "size"),
        mean_score=("score", "mean"),
        rank1=("rank", lambda s: (s==1).sum()),
        rank2=("rank", lambda s: (s==2).sum()),
        rank3=("rank", lambda s: (s==3).sum()),
    ).reset_index()

    # Rename for clarity
    agg = agg.rename(columns={
        "count": "weighted_count",
        "appearances": "occurrences"
    })

    totals = dict(
        total_defs=defs_with_cats,
        defs_with_cats=defs_with_cats,
        unique_cats=unique_cats,
        total_assignments=total_assignments
    )
    return agg, totals

# ─────────────────────────── Dashboard data helpers
@st.cache_data(show_spinner=False, ttl=60)
def get_dashboard_stats(orismoi_db: Path, harvester_db: Path):
    stats = {}

    if harvester_db.exists():
        with _conn(harvester_db) as con:
            row = con.execute(
                "SELECT COUNT(*), SUM(CASE WHEN fekTEXT IS NOT NULL AND LENGTH(fekTEXT) > 100 THEN 1 ELSE 0 END) FROM et"
            ).fetchone()
        stats["laws_total"] = row[0] or 0
        stats["laws_with_text"] = row[1] or 0
    else:
        stats["laws_total"] = None
        stats["laws_with_text"] = None

    with _conn(orismoi_db) as con:
        stats["defs_total"] = con.execute("SELECT COUNT(*) FROM definitions").fetchone()[0]
        stats["laws_with_defs"] = con.execute("SELECT COUNT(DISTINCT fekID) FROM definitions").fetchone()[0]
        stats["distinct_terms"] = con.execute(
            "SELECT COUNT(DISTINCT LOWER(TRIM(term))) FROM definitions"
        ).fetchone()[0]

        if table_exists(orismoi_db, "category"):
            stats["defs_categorised"] = con.execute(
                "SELECT COUNT(DISTINCT defID) FROM category"
            ).fetchone()[0]
            stats["unique_categories"] = con.execute("""
                SELECT COUNT(DISTINCT c) FROM (
                  SELECT cat1 c FROM category WHERE cat1 IS NOT NULL AND cat1 != ''
                  UNION SELECT cat2 FROM category WHERE cat2 IS NOT NULL AND cat2 != ''
                  UNION SELECT cat3 FROM category WHERE cat3 IS NOT NULL AND cat3 != ''
                )
            """).fetchone()[0]
        else:
            stats["defs_categorised"] = None
            stats["unique_categories"] = None

        if table_exists(orismoi_db, "score_2"):
            score_table = "score_2"
        elif table_exists(orismoi_db, "score"):
            score_table = "score"
        else:
            score_table = None
        stats["score_table"] = score_table

        if score_table:
            row = con.execute(
                f"SELECT ROUND(AVG(confidence),3), SUM(needs_review), COUNT(*) FROM {score_table}"
            ).fetchone()
            stats["avg_confidence"] = row[0]
            stats["needs_review"] = row[1] or 0
            stats["scored_total"] = row[2]
        else:
            stats["avg_confidence"] = None
            stats["needs_review"] = None
            stats["scored_total"] = None

    return stats

@st.cache_data(show_spinner=False, ttl=60)
def get_pattern_tag_stats(orismoi_db: Path) -> pd.DataFrame:
    with _conn(orismoi_db) as con:
        rows = con.execute(
            "SELECT pattern_tag, COUNT(*) FROM definitions GROUP BY pattern_tag ORDER BY 2 DESC"
        ).fetchall()
    return pd.DataFrame(rows, columns=["pattern_tag", "count"])

@st.cache_data(show_spinner=False, ttl=60)
def get_confidence_series(orismoi_db: Path, score_table: str) -> pd.DataFrame:
    if not score_table:
        return pd.DataFrame(columns=["confidence"])
    with _conn(orismoi_db) as con:
        rows = con.execute(f"SELECT confidence FROM {score_table}").fetchall()
    return pd.DataFrame([r[0] for r in rows], columns=["confidence"])

@st.cache_data(show_spinner=False, ttl=60)
def get_review_threshold(orismoi_db: Path, score_table: str):
    # το όριο επανελέγχου = ο μικρότερος βαθμός που ΔΕΝ σημειώθηκε για έλεγχο (ίδιο για κάθε έκδοση βαθμολόγησης)
    with _conn(orismoi_db) as con:
        row = con.execute(f"SELECT MIN(confidence) FROM {score_table} WHERE needs_review = 0").fetchone()
    return row[0] if row else None

@st.cache_data(show_spinner=False, ttl=60)
def get_defs_per_year(orismoi_db: Path) -> pd.DataFrame:
    with _conn(orismoi_db) as con:
        rows = con.execute(
            "SELECT fekEtos, COUNT(*) FROM definitions WHERE fekEtos IS NOT NULL GROUP BY fekEtos ORDER BY fekEtos"
        ).fetchall()
    return pd.DataFrame(rows, columns=["year", "count"])

@st.cache_data(show_spinner=False, ttl=60)
def get_top_terms(orismoi_db: Path, top_n: int = 15) -> pd.DataFrame:
    with _conn(orismoi_db) as con:
        rows = con.execute("""
            SELECT term, COUNT(*) c FROM (
                SELECT TRIM(term) AS term FROM definitions WHERE term IS NOT NULL AND TRIM(term) != ''
            )
            GROUP BY LOWER(term)
            ORDER BY c DESC
            LIMIT ?
        """, (top_n,)).fetchall()
    return pd.DataFrame(rows, columns=["term", "count"])

@st.cache_data(show_spinner=False, ttl=60)
def get_top_categories_simple(orismoi_db: Path, top_n: int = 15) -> pd.DataFrame:
    if not table_exists(orismoi_db, "category"):
        return pd.DataFrame(columns=["category", "count"])
    with _conn(orismoi_db) as con:
        rows = con.execute("""
            SELECT cat1, COUNT(*) c FROM category
            WHERE cat1 IS NOT NULL AND cat1 != ''
            GROUP BY cat1 ORDER BY c DESC LIMIT ?
        """, (top_n,)).fetchall()
    return pd.DataFrame(rows, columns=["category", "count"])

@st.cache_data(show_spinner=False, ttl=60)
def get_highlight_examples(orismoi_db: Path, n: int = 6) -> pd.DataFrame:
    has_cat = table_exists(orismoi_db, "category")
    has_score = table_exists(orismoi_db, "score_2")
    with _conn(orismoi_db) as con:
        if has_cat and has_score:
            rows = con.execute("""
                SELECT d.term, d.explanation, c.cat1, s.confidence
                FROM definitions d
                JOIN category c ON c.defID = d.ID
                JOIN score_2 s ON s.def_id = d.ID
                WHERE s.confidence >= 0.6 AND LENGTH(d.explanation) BETWEEN 40 AND 400
                ORDER BY RANDOM() LIMIT ?
            """, (n,)).fetchall()
            cols = ["term", "explanation", "category", "confidence"]
        elif has_cat:
            rows = con.execute("""
                SELECT d.term, d.explanation, c.cat1
                FROM definitions d JOIN category c ON c.defID = d.ID
                WHERE LENGTH(d.explanation) BETWEEN 40 AND 400
                ORDER BY RANDOM() LIMIT ?
            """, (n,)).fetchall()
            cols = ["term", "explanation", "category"]
        else:
            rows = con.execute("""
                SELECT term, explanation FROM definitions
                WHERE LENGTH(explanation) BETWEEN 40 AND 400
                ORDER BY RANDOM() LIMIT ?
            """, (n,)).fetchall()
            cols = ["term", "explanation"]
    return pd.DataFrame(rows, columns=cols)

# ─────────────────────────── Dashboard page
def render_dashboard(orismoi_db: Path, harvester_db: Path):
    st.title("📚 Επισήμανση Νομικών Ορισμών — Επισκόπηση Έργου")
    st.caption(
        "Εξαγωγή ορισμών από την Ελληνική Νομοθεσία (ΦΕΚ) με κανόνες (regex) "
        "και κατηγοριοποίηση μέσω εξωτερικού μοντέλου."
    )

    stats = get_dashboard_stats(orismoi_db, harvester_db)

    # ── KPI rows
    c1, c2, c3 = st.columns(3)
    c1.metric("Νόμοι στο corpus", f"{stats['laws_total']:,}" if stats["laws_total"] else "—")
    c2.metric("Νόμοι με ≥1 ορισμό", f"{stats['laws_with_defs']:,}")
    c3.metric("Εξαγόμενοι ορισμοί", f"{stats['defs_total']:,}")

    c4, c5, c6 = st.columns(3)
    if stats["defs_categorised"] is not None and stats["defs_total"]:
        pct = stats["defs_categorised"] / stats["defs_total"] * 100
        c4.metric("Κατηγοριοποιημένοι ορισμοί", f"{stats['defs_categorised']:,}", f"{pct:.0f}% του συνόλου")
    else:
        c4.metric("Κατηγοριοποιημένοι ορισμοί", "—")
    c5.metric("Διακριτοί όροι", f"{stats['distinct_terms']:,}")
    if stats["avg_confidence"] is not None:
        c6.metric(
            "Μέσος βαθμός εμπιστοσύνης",
            f"{stats['avg_confidence']:.2f}",
            f"{stats['needs_review']:,} χρειάζονται έλεγχο" if stats["needs_review"] else None,
            delta_color="off",
        )
    else:
        c6.metric("Μέσος βαθμός εμπιστοσύνης", "—")

    st.divider()

    # ── Pipeline funnels
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        st.subheader("Από το Corpus στους Νόμους με Ορισμούς")
        if stats["laws_total"]:
            stages = ["Σύνολο ΦΕΚ", "Με αναγνώσιμο κείμενο", "Με ≥1 ορισμό"]
            counts = [stats["laws_total"], stats["laws_with_text"], stats["laws_with_defs"]]
            funnel_laws = pd.DataFrame({"stage": stages, "count": counts, "order": range(len(stages))})
            chart = alt.Chart(funnel_laws).mark_bar(cornerRadiusEnd=4).encode(
                y=alt.Y("stage:N", sort=stages, title=None),
                x=alt.X("count:Q", title="Πλήθος νόμων"),
                color=alt.Color("order:O", scale=alt.Scale(domain=list(range(len(stages))), range=[BLUE_L, BLUE_M, BLUE_D]), legend=None),
                tooltip=[alt.Tooltip("stage:N", title="Στάδιο"), alt.Tooltip("count:Q", title="Πλήθος", format=",")]
            )
            st.altair_chart(style(chart, height=200), use_container_width=True)
        else:
            st.info("Δεν βρέθηκε harvester.db για τον υπολογισμό.")

    with fcol2:
        st.subheader("Από τους Ορισμούς στην Κατηγοριοποίηση")
        stages = ["Εξήχθησαν"]
        counts = [stats["defs_total"]]
        if stats["defs_categorised"] is not None:
            stages.append("Κατηγοριοποιήθηκαν"); counts.append(stats["defs_categorised"])
        if stats["scored_total"] is not None:
            passed = stats["scored_total"] - (stats["needs_review"] or 0)
            stages.append("Πέρασαν τον έλεγχο ποιότητας"); counts.append(passed)
        funnel_defs = pd.DataFrame({"stage": stages, "count": counts, "order": range(len(stages))})
        colors = [BLUE_L, BLUE_M, BLUE_D][:len(stages)]
        chart = alt.Chart(funnel_defs).mark_bar(cornerRadiusEnd=4).encode(
            y=alt.Y("stage:N", sort=stages, title=None),
            x=alt.X("count:Q", title="Πλήθος ορισμών"),
            color=alt.Color("order:O", scale=alt.Scale(domain=list(range(len(stages))), range=colors), legend=None),
            tooltip=[alt.Tooltip("stage:N", title="Στάδιο"), alt.Tooltip("count:Q", title="Πλήθος", format=",")]
        )
        st.altair_chart(style(chart, height=200), use_container_width=True)

    st.divider()

    # ── Pattern tag + confidence histogram
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        st.subheader("Κατανομή ανά Μοτίβο Εξαγωγής")
        tag_df = get_pattern_tag_stats(orismoi_db)
        if not tag_df.empty:
            chart = alt.Chart(tag_df).mark_bar(cornerRadiusEnd=4, color=BLUE).encode(
                y=alt.Y("pattern_tag:N", sort="-x", title=None),
                x=alt.X("count:Q", title="Πλήθος ορισμών"),
                tooltip=[alt.Tooltip("pattern_tag:N", title="Μοτίβο"), alt.Tooltip("count:Q", title="Πλήθος", format=",")]
            )
            st.altair_chart(style(chart, height=200), use_container_width=True)
        else:
            st.info("Δεν υπάρχουν δεδομένα.")

    with pcol2:
        st.subheader("Κατανομή Βαθμού Εμπιστοσύνης")
        conf_df = get_confidence_series(orismoi_db, stats["score_table"])
        if not conf_df.empty:
            threshold = get_review_threshold(orismoi_db, stats["score_table"]) or 0.5
            hist = alt.Chart(conf_df).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2, color=BLUE).encode(
                x=alt.X("confidence:Q", bin=alt.Bin(maxbins=20), title="Βαθμός εμπιστοσύνης"),
                y=alt.Y("count():Q", title="Πλήθος ορισμών"),
                tooltip=[alt.Tooltip("count():Q", title="Πλήθος")]
            )
            rule = alt.Chart(pd.DataFrame({"x": [threshold]})).mark_rule(
                color=WARNING, strokeDash=[4, 3], size=2
            ).encode(x="x:Q")
            st.altair_chart(style(hist + rule, height=200), use_container_width=True)
            st.caption("Η διακεκομμένη γραμμή δείχνει το όριο επανελέγχου (needs_review).")
        else:
            st.info("Δεν βρέθηκε πίνακας βαθμολόγησης (score / score_2) σε αυτή τη βάση.")

    st.divider()

    # ── Definitions per year
    st.subheader("Ορισμοί ανά Έτος ΦΕΚ")
    year_df = get_defs_per_year(orismoi_db)
    if not year_df.empty:
        chart = alt.Chart(year_df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, color=BLUE).encode(
            x=alt.X("year:O", title="Έτος"),
            y=alt.Y("count:Q", title="Πλήθος ορισμών"),
            tooltip=[alt.Tooltip("year:O", title="Έτος"), alt.Tooltip("count:Q", title="Πλήθος", format=",")]
        )
        st.altair_chart(style(chart, height=260), use_container_width=True)
    else:
        st.info("Δεν υπάρχουν δεδομένα ετών.")

    st.divider()

    # ── Top categories + top terms
    tcol1, tcol2 = st.columns(2)
    with tcol1:
        st.subheader("Συχνότερες Κατηγορίες")
        cat_df = get_top_categories_simple(orismoi_db, 15)
        if not cat_df.empty:
            chart = alt.Chart(cat_df).mark_bar(cornerRadiusEnd=4, color=BLUE).encode(
                y=alt.Y("category:N", sort="-x", title=None),
                x=alt.X("count:Q", title="Πλήθος ορισμών"),
                tooltip=[alt.Tooltip("category:N", title="Κατηγορία"), alt.Tooltip("count:Q", title="Πλήθος", format=",")]
            )
            st.altair_chart(style(chart, height=420), use_container_width=True)
        else:
            st.info("Δεν βρέθηκε πίνακας κατηγοριών σε αυτή τη βάση.")

    with tcol2:
        st.subheader("Συχνότερα (Επανα-)οριζόμενοι Όροι")
        term_df = get_top_terms(orismoi_db, 15)
        if not term_df.empty:
            chart = alt.Chart(term_df).mark_bar(cornerRadiusEnd=4, color=BLUE).encode(
                y=alt.Y("term:N", sort="-x", title=None),
                x=alt.X("count:Q", title="Πλήθος εμφανίσεων"),
                tooltip=[alt.Tooltip("term:N", title="Όρος"), alt.Tooltip("count:Q", title="Πλήθος", format=",")]
            )
            st.altair_chart(style(chart, height=420), use_container_width=True)
        else:
            st.info("Δεν υπάρχουν όροι.")

    st.divider()

    # ── Highlight examples
    st.subheader("Ενδεικτικοί Ορισμοί")
    examples = get_highlight_examples(orismoi_db, 6)
    if not examples.empty:
        cols = st.columns(3)
        for i, row in examples.reset_index(drop=True).iterrows():
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{row['term']}**")
                    expl = row["explanation"] or ""
                    if len(expl) > 260:
                        expl = expl[:260].rstrip() + "…"
                    st.write(expl)
                    badges = []
                    if "category" in row and pd.notna(row.get("category")):
                        badges.append(f":blue-background[{row['category']}]")
                    if "confidence" in row and pd.notna(row.get("confidence")):
                        badges.append(f":green-background[conf {row['confidence']:.2f}]")
                    if badges:
                        st.markdown(" ".join(badges))
    else:
        st.info("Δεν βρέθηκαν παραδείγματα με τα τρέχοντα κριτήρια.")

    st.divider()
    bcol1, bcol2 = st.columns(2)
    if bcol1.button("🔎 Μετάβαση στην Περιήγηση", width='stretch'):
        st.session_state["page"] = "browse"; st.rerun()
    if bcol2.button("📈 Λεπτομερής Ανάλυση Κατηγοριών", width='stretch'):
        st.session_state["page"] = "overview"; st.rerun()

# ─────────────────────────── Sidebar / Routing
if "page" not in st.session_state:
    st.session_state["page"] = "dashboard"

st.sidebar.header("Ρυθμίσεις βάσεων")
orismoi_path = st.sidebar.text_input("orismoi.db", value=str(DEFAULT_ORISMOI))
harvest_path = st.sidebar.text_input("harvester.db", value=str(DEFAULT_HARVEST))

orismoi_db = Path(orismoi_path)
harvester_db = Path(harvest_path)

if not orismoi_db.exists():
    st.error(f"Δεν βρέθηκε το orismoi DB: {orismoi_db}")
    st.stop()

PAGE_LABELS = ["📊 Επισκόπηση", "🔎 Περιήγηση", "📈 Επισκόπηση Κατηγοριών"]
PAGE_KEYS = ["dashboard", "browse", "overview"]
page_choice = st.sidebar.radio(
    "Σελίδα",
    PAGE_LABELS,
    index=PAGE_KEYS.index(st.session_state["page"])
)
st.session_state["page"] = PAGE_KEYS[PAGE_LABELS.index(page_choice)]

# Shared year bounds
miny, maxy = get_year_bounds(orismoi_db)
miny = int(miny or 1800); maxy = int(maxy or 2100)

# ─────────────────────────── PAGE 0: Dashboard
if st.session_state["page"] == "dashboard":
    render_dashboard(orismoi_db, harvester_db)

# ─────────────────────────── PAGE 1: Browse
elif st.session_state["page"] == "browse":
    # Filters
    st.sidebar.header("Φίλτρα")
    year_min, year_max = st.sidebar.slider("Έτος (fekEtos)", miny, maxy, value=(miny, maxy))
    q = st.sidebar.text_input("Αναζήτηση σε όρο/εξήγηση", value="")
    cat_q = st.sidebar.text_input("Αναζήτηση σε κατηγορία", value="")
    tags = st.sidebar.multiselect("Μοτίβο", options=get_distinct_tags(orismoi_db))
    only_with_cats = st.sidebar.checkbox("Μόνο με κατηγορίες", value=False)
    order = st.sidebar.selectbox("Ταξινόμηση", ["ID ↓", "ID ↑", "Έτος ↓", "Έτος ↑"])
    page_size = st.sidebar.selectbox("Ανά σελίδα", [25, 50, 100], index=1)

    st.sidebar.header("Σελιδοποίηση")
    page_num = st.sidebar.number_input("Σελίδα", min_value=0, value=0, step=1)

    filters = dict(
        q=q.strip(),
        cat_q=cat_q.strip(),
        tags=tags,
        only_with_cats=only_with_cats,
        year_min=year_min,
        year_max=year_max,
        order=order,
        page=page_num,
        page_size=page_size,
    )

    total_rows = count_total(orismoi_db, filters)
    st.sidebar.markdown(f"**Σύνολο**: {total_rows:,}")

    st.title("🔎 Ορισμοί & Κατηγορίες (Περιήγηση)")
    sql, params = build_query(filters)
    df = run_page_query(orismoi_db, sql, params)

    if df.empty:
        st.info("Δεν βρέθηκαν αποτελέσματα με τα τρέχοντα φίλτρα.")
        # Quick jump button
        if st.button("📈 Μετάβαση στην Επισκόπηση Κατηγοριών"):
            st.session_state["page"] = "overview"
            st.rerun()
        st.stop()

    # Robust column selection
    show_cols = ["ID", "fekEtos", "term", "explanation", "pattern_tag",
                "cat1", "score1", "cat2", "score2", "cat3", "score3"]
    available = [c for c in show_cols if c in df.columns]
    missing = [c for c in show_cols if c not in df.columns]
    if missing:
        st.warning(f"Missing columns in query result: {missing}")

    st.dataframe(df[available], width='stretch', height=420)

    st.download_button("⬇️ Λήψη τρέχουσας σελίδας (CSV)",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="definitions_page.csv",
                    mime="text/csv")

    st.subheader("📄 Επιλογή εγγραφής για προβολή")
    sel_id = st.selectbox("Definition ID", options=df["ID"].tolist())

    sel_row = df[df["ID"] == sel_id].iloc[0]
    left, right = st.columns([1,1])

    with left:
        st.markdown(f"**ID:** {int(sel_row.ID)}  |  **Έτος:** {int(sel_row.fekEtos)}")
        st.markdown(f"**Όρος:** {sel_row.term}")
        st.markdown("**Εξήγηση:**")
        st.write(sel_row.explanation)

        if harvester_db.exists():
            title, text = get_title_and_text(harvester_db, int(sel_row.fekID))
            st.markdown("**Τίτλος νόμου (harvester):**")
            st.write(title or "—")
            with st.expander("Πλήρες κείμενο νόμου (fekTEXT)"):
                st.write(text or "—")
        else:
            st.info("Δώσε σωστή διαδρομή harvester.db στο sidebar για να προβληθεί ο τίτλος/κείμενο νόμου.")

    with right:
        st.markdown("**Κατηγορίες (Top-3)**")
        cats = []
        if "cat1" in df.columns and pd.notna(sel_row.get("cat1", None)):
            cats.append(("cat1", sel_row.get("cat1"), sel_row.get("score1")))
        if "cat2" in df.columns and pd.notna(sel_row.get("cat2", None)):
            cats.append(("cat2", sel_row.get("cat2"), sel_row.get("score2")))
        if "cat3" in df.columns and pd.notna(sel_row.get("cat3", None)):
            cats.append(("cat3", sel_row.get("cat3"), sel_row.get("score3")))
        if cats:
            chart_df = pd.DataFrame({
                "rank": [c[0] for c in cats],
                "category": [c[1] for c in cats],
                "score": [float(c[2]) if c[2] is not None else 0.0 for c in cats]
            })
            bar = (
                alt.Chart(chart_df)
                .mark_bar(cornerRadiusEnd=4, color=BLUE)
                .encode(
                    x=alt.X("score:Q", title="Confidence"),
                    y=alt.Y("category:N", sort='-x', title="Κατηγορία"),
                    tooltip=["category", alt.Tooltip("score:Q", format=".3f")]
                )
            )
            st.altair_chart(style(bar, height=180), use_container_width=True)
        else:
            st.info("Δεν υπάρχουν κατηγορίες για αυτή την εγγραφή.")

    st.divider()
    dcol1, dcol2 = st.columns(2)
    if dcol1.button("📊 Επιστροφή στην Επισκόπηση"):
        st.session_state["page"] = "dashboard"
        st.rerun()
    if dcol2.button("📈 Μετάβαση στην Επισκόπηση Κατηγοριών"):
        st.session_state["page"] = "overview"
        st.rerun()

# ─────────────────────────── PAGE 2: Category Overview
else:
    st.title("📈 Επισκόπηση Κατηγοριών")

    if not table_exists(orismoi_db, "category"):
        st.warning("Δεν βρέθηκε πίνακας `category` στο orismoi DB. Τρέξε πρώτα το category.py.")
        if st.button("🔎 Επιστροφή στην Περιήγηση"):
            st.session_state["page"] = "browse"
            st.rerun()
        st.stop()

    # Filters for analytics
    st.sidebar.header("Φίλτρα (Επισκόπηση)")
    year_min, year_max = st.sidebar.slider("Έτος (fekEtos)", miny, maxy, value=(miny, maxy))
    only_rank1 = st.sidebar.checkbox("Μόνο κορυφαία κατηγορία (rank1)", value=False)
    weight_by_score = st.sidebar.checkbox("Στάθμιση με score", value=False)
    cat_filter = st.sidebar.text_input("Φίλτρο στο όνομα κατηγορίας", value="")
    top_n = st.sidebar.slider("Top N για προβολή", 5, 50, value=20, step=5)

    # Load + Melt + Aggregate
    wide = load_categorised(orismoi_db, year_min, year_max)
    melt = melt_categories(wide, only_rank1=only_rank1)
    agg, totals = aggregate_categories(melt, weight_by_score=weight_by_score, cat_filter=cat_filter)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ορισμοί με κατηγορία", f"{totals.get('defs_with_cats',0):,}")
    c2.metric("Συνολικά assignments", f"{totals.get('total_assignments',0):,}")
    c3.metric("Διακριτές κατηγορίες", f"{totals.get('unique_cats',0):,}")
    c4.metric("Έτη εύρους", f"{year_min}–{year_max}")

    if agg.empty:
        st.info("Δεν υπάρχουν δεδομένα για τα τρέχοντα φίλτρα.")
        if st.button("🔎 Επιστροφή στην Περιήγηση"):
            st.session_state["page"] = "browse"
            st.rerun()
        st.stop()

    # Choose measure for bar chart
    measure = "weighted_count" if weight_by_score else "occurrences"
    title_measure = "Σταθμισμένες εμφανίσεις" if weight_by_score else "Πλήθος εμφανίσεων"

    top = agg.sort_values(measure, ascending=False).head(top_n)

    # Bar chart of top categories
    chart = (
        alt.Chart(top)
        .mark_bar(cornerRadiusEnd=4, color=BLUE)
        .encode(
            x=alt.X(f"{measure}:Q", title=title_measure),
            y=alt.Y("category:N", sort='-x', title="Κατηγορία"),
            tooltip=[
                alt.Tooltip("category:N", title="Κατηγορία"),
                alt.Tooltip("occurrences:Q", title="Εμφανίσεις"),
                alt.Tooltip("weighted_count:Q", title="Σταθμισμένες", format=".2f"),
                alt.Tooltip("mean_score:Q", title="Μ.Ο. score", format=".3f"),
                alt.Tooltip("rank1:Q", title="# rank1"),
                alt.Tooltip("rank2:Q", title="# rank2"),
                alt.Tooltip("rank3:Q", title="# rank3"),
            ]
        )
    )
    st.subheader("Top κατηγορίες")
    st.altair_chart(style(chart, height=420), use_container_width=True)

    # Full table
    st.subheader("Αναλυτικός πίνακας κατηγοριών")
    show_cols = ["category", "occurrences", "weighted_count", "mean_score", "rank1", "rank2", "rank3"]
    st.dataframe(agg.sort_values(measure, ascending=False)[show_cols], width='stretch', height=420)

    # Downloads
    st.download_button("⬇️ Λήψη αναλυτικού πίνακα (CSV)",
                       data=agg.to_csv(index=False).encode("utf-8"),
                       file_name="category_overview.csv",
                       mime="text/csv")
    st.download_button("⬇️ Λήψη αναθέσεων (melted) (CSV)",
                       data=melt.to_csv(index=False).encode("utf-8"),
                       file_name="category_assignments.csv",
                       mime="text/csv")

    st.divider()
    ecol1, ecol2 = st.columns(2)
    if ecol1.button("📊 Επιστροφή στην Επισκόπηση"):
        st.session_state["page"] = "dashboard"
        st.rerun()
    if ecol2.button("🔎 Επιστροφή στην Περιήγηση"):
        st.session_state["page"] = "browse"
        st.rerun()

st.caption("Tip: Χρησιμοποίησε το sidebar για εναλλαγή σελίδων, φίλτρα και επιλογές.")