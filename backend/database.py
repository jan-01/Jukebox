import sqlite3

DB_FILE = 'reviews.db'
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

# Add updatedAt column if it doesn't exist
try:
    c.execute("ALTER TABLE reviews ADD COLUMN updatedAt TEXT")
    print("updatedAt column added")
except sqlite3.OperationalError:
    print("updatedAt column already exists")

conn.commit()
conn.close()
