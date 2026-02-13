
import sqlite3
import os

db_path = "chat_history.db"

if not os.path.exists(db_path):
    print(f"Error: Database {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    c.execute("SELECT count(*) FROM conversations")
    convs = c.fetchone()[0]
    
    c.execute("SELECT count(*) FROM messages")
    msgs = c.fetchone()[0]
    
    print(f"Conversations: {convs}")
    print(f"Messages: {msgs}")
    
except Exception as e:
    print(f"Error reading DB: {e}")

conn.close()
