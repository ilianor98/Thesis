import sqlite3

# Connect to orismoi.db
conn = sqlite3.connect("orismoi.db")
cursor = conn.cursor()

# Query distinct ministry names (excluding NULL/empty)
cursor.execute("""
    SELECT *
    FROM definitions
    LIMIT 10
""")

ministries = cursor.fetchall()

print("Unique Ministries:\n")
for ministry in ministries:
    print(f"{ministry}\n")

conn.close()
 