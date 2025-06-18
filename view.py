import sqlite3
import re

# Connect to harvester.db
src_conn = sqlite3.connect("harvester.db")
src_cursor = src_conn.cursor()

# Connect to orismoi.db
dst_conn = sqlite3.connect("orismoi.db")
dst_cursor = dst_conn.cursor()

# Create table
dst_cursor.execute('''
CREATE TABLE IF NOT EXISTS definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    definition TEXT NOT NULL,
    source_title TEXT,
    year INTEGER,
    ministry TEXT,
    fek_id INTEGER
)
''')

# Compile regex pattern
definition_pattern = re.compile(r'ορίζεται ως[^.]{5,200}\.', re.IGNORECASE | re.UNICODE)

# Fetch all fekTEXT fields (you can also use nomosTitle or fekTEXTorig if richer)
src_cursor.execute("SELECT fekTEXT, nomosTitle, fekEtos, ministry, ID FROM et")
rows = src_cursor.fetchall()

count = 0

for fek_text, title, year, ministry, fek_id in rows:
    if fek_text:
        matches = definition_pattern.findall(fek_text)
        for definition in matches:
            dst_cursor.execute('''
                INSERT INTO definitions (definition, source_title, year, ministry, fek_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (definition.strip(), title, year, ministry, fek_id))
            count += 1

dst_conn.commit()
print(f"[+] Extracted and saved {count} definitions.")

# Close connections
src_conn.close()
dst_conn.close()
