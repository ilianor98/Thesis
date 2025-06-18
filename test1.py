import sqlite3

# Connect to orismoi.db
conn = sqlite3.connect("orismoi.db")
cursor = conn.cursor()

# Query distinct ministry names (excluding NULL/empty)
cursor.execute("""
    SELECT DISTINCT ministry
    FROM definitions
    WHERE ministry IS NOT NULL AND TRIM(ministry) != ''
    ORDER BY ministry ASC
""")

ministries = cursor.fetchall()

print("Unique Ministries:\n")
for i, (ministry,) in enumerate(ministries, 1):
    print(f"{i}. {ministry}")

conn.close()
 