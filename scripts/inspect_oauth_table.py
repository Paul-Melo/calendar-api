import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'app.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("PRAGMA table_info('oauth_credential')")
cols = c.fetchall()
print('columns:')
for col in cols:
    print(col)
conn.close()
