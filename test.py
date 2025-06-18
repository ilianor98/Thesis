import sqlite3

# Connect to old and new DBs
src_conn = sqlite3.connect("harvester.db")
src_cursor = src_conn.cursor()

dst_conn = sqlite3.connect("laws.db")
dst_cursor = dst_conn.cursor()

# Create your new table
dst_cursor.execute('''
CREATE TABLE IF NOT EXISTS laws (
    id INTEGER PRIMARY KEY,
    year INTEGER,
    title TEXT,
    pdf_filename TEXT,
    ministry TEXT,
    permalink TEXT
)
''')

# Read from old table
src_cursor.execute("SELECT ID, fekEtos, nomosTitle, fileLocalName, ministry, fileRemote FROM et")  # replace 'main' with actual table name

rows = src_cursor.fetchall()

# Insert into new DB
dst_cursor.executemany('''
INSERT INTO laws (id, year, title, pdf_filename, ministry, permalink)
VALUES (?, ?, ?, ?, ?, ?)
''', rows)

dst_conn.commit()
print(f"[+] Migrated {len(rows)} records.")

# Close
src_conn.close()
dst_conn.close()
