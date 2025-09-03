# ui.py
# Browse orismoi + categories and a separate analytics page
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

# ─────────────────────────── Settings (change defaults if needed)
DEFAULT_ORISMOI = Path(r"C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/orismoi.db")
DEFAULT_HARVEST = Path(r"C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/harvester.db")

st.set_page_config(page_title="Ορισμοί & Κατηγορίες", layout="wide")

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

# ─────────────────────────── Analytics helpers
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

# ─────────────────────────── Sidebar / Routing
if "page" not in st.session_state:
    st.session_state["page"] = "browse"  # or 'overview'

st.sidebar.header("Ρυθμίσεις βάσεων")
orismoi_path = st.sidebar.text_input("orismoi.db", value=str(DEFAULT_ORISMOI))
harvest_path = st.sidebar.text_input("harvester.db", value=str(DEFAULT_HARVEST))

orismoi_db = Path(orismoi_path)
harvester_db = Path(harvest_path)

if not orismoi_db.exists():
    st.error(f"Δεν βρέθηκε το orismoi DB: {orismoi_db}")
    st.stop()

page_choice = st.sidebar.radio(
    "Σελίδα",
    ["🔎 Περιήγηση", "📈 Επισκόπηση Κατηγοριών"],
    index=0 if st.session_state["page"] == "browse" else 1
)
st.session_state["page"] = "browse" if page_choice.startswith("🔎") else "overview"

# Shared year bounds
miny, maxy = get_year_bounds(orismoi_db)
miny = int(miny or 1800); maxy = int(maxy or 2100)

# ─────────────────────────── PAGE 1: Browse
if st.session_state["page"] == "browse":
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

    st.dataframe(df[available], use_container_width=True, height=420)

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
                .mark_bar()
                .encode(
                    x=alt.X("score:Q", title="Confidence"),
                    y=alt.Y("category:N", sort='-x', title="Κατηγορία"),
                    tooltip=["category", alt.Tooltip("score:Q", format=".3f")]
                )
            )
            st.altair_chart(bar, use_container_width=True)
        else:
            st.info("Δεν υπάρχουν κατηγορίες για αυτή την εγγραφή.")

    st.divider()
    if st.button("📈 Μετάβαση στην Επισκόπηση Κατηγοριών"):
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
        .mark_bar()
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
    st.altair_chart(chart, use_container_width=True)

    # Full table
    st.subheader("Αναλυτικός πίνακας κατηγοριών")
    show_cols = ["category", "occurrences", "weighted_count", "mean_score", "rank1", "rank2", "rank3"]
    st.dataframe(agg.sort_values(measure, ascending=False)[show_cols], use_container_width=True, height=420)

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
    if st.button("🔎 Επιστροφή στην Περιήγηση"):
        st.session_state["page"] = "browse"
        st.rerun()

st.caption("Tip: Χρησιμοποίησε το sidebar για εναλλαγή σελίδων, φίλτρα και επιλογές.")
