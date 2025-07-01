import sqlite3

# Connect to the database
conn = sqlite3.connect("orismoi.db")
cursor = conn.cursor()

# Fetch 5 definitions
cursor.execute("""
    SELECT id, definition, source_title, year, ministry, fek_id
    FROM definitions
    LIMIT 5
""")
rows = cursor.fetchall()

# Print results
print("📜 First 5 Extracted Definitions:\n")
for row in rows:
    id_, definition, title, year, ministry, fek_id = row
    print(f"ID: {id_}")
    print(f"Definition: {definition}")
    print(f"Source Title: {title}")
    print(f"Year: {year}")
    print(f"Ministry: {ministry}")
    print(f"FEK ID: {fek_id}")
    print("-" * 40)

conn.close()
