import sqlite3

# Connect to the database
conn = sqlite3.connect("orismoi.db")
cursor = conn.cursor()

# Fetch 5 definitions
cursor.execute("""
    SELECT *
    FROM definitions
    LIMIT 10
""")
rows = cursor.fetchall()

print("Unique Ministries:\n")
for ministry in ministries:
    print(f"{ministry}\n")

conn.close()
