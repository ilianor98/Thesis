import sqlite3

# Open source and destination databases
src_conn = sqlite3.connect("C:/Users/Ilias/Desktop/sxoli/diplo/harvester/harvester.db")
src_cursor = src_conn.cursor()

dst_conn = sqlite3.connect("feksize.db")
dst_cursor = dst_conn.cursor()

# Step 1: Recreate the table schema in feksize.db
# We'll use the same CREATE TABLE structure as in harvester.db
src_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='et'")
create_table_sql = src_cursor.fetchone()[0]
dst_cursor.execute(create_table_sql)

# Step 2: Select filtered rows from source
src_cursor.execute("""
    SELECT * FROM et
    WHERE fekTEXTSize BETWEEN 3000 AND 10000
""")
filtered_rows = src_cursor.fetchall()

# Step 3: Get column count to match placeholders
src_cursor.execute("PRAGMA table_info(et)")
columns = src_cursor.fetchall()
placeholders = ", ".join(["?"] * len(columns))

# Step 4: Insert into destination table
dst_cursor.executemany(f"INSERT INTO et VALUES ({placeholders})", filtered_rows)

# Step 5: Commit and close
dst_conn.commit()
print(f"[+] Copied {len(filtered_rows)} rows into feksize.db.")

src_conn.close()
dst_conn.close()
