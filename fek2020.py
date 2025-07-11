"""
Copy every table structure from harvester.db into a new SQLite file
and move **only** the rows from `et` whose fekEtos > 2020.  
(If you also need rows from `legis` that match those IDs, add the
optional block at the end.)
"""
import sqlite3

SRC_DB = "C:/Users/Ilias/Desktop/ΣΧΟΛΗ/diplo/harvester/harvester.db"
DST_DB = "harvester_2021plus.db"

src = sqlite3.connect(SRC_DB)
dst = sqlite3.connect(DST_DB)
src_cur, dst_cur = src.cursor(), dst.cursor()

# 1. Re-create all user tables (skip internal sqlite_%)
for name, ddl in src_cur.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
    dst_cur.execute(ddl)

# 2. Copy laws after 2020 from table et
dst_cur.execute("""
    INSERT INTO et
    SELECT * FROM et WHERE fekEtos > 2020
""",)  # uses et definition already cloned

dst.commit()

# ── Optional: bring matching rows from legis ──
"""
ids = [row[0] for row in dst.execute("SELECT ID FROM et")]
placeholders = ",".join("?"*len(ids))
dst_cur.execute(f"INSERT INTO legis SELECT * FROM legis WHERE id IN ({placeholders})", ids)
dst.commit()
"""

src.close()
dst.close()
print("New DB ready:", DST_DB)
