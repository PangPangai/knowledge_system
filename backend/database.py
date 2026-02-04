
import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional

DB_PATH = "chat_history.db"

def init_db():
    """Initialize the SQLite database with necessary tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create conversations table
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create messages table
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            role TEXT,
            content TEXT,
            sources TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    ''')
    
    conn.commit()
    conn.close()

class ChatHistoryDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        init_db()  # Ensure tables exist
        
    def _get_conn(self):
        return sqlite3.connect(self.db_path)
    
    def create_conversation(self, title: str = "New Chat") -> str:
        """Create a new conversation and return its ID"""
        conn = self._get_conn()
        c = conn.cursor()
        conv_id = str(uuid.uuid4())
        now = datetime.now()
        c.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        conn.commit()
        conn.close()
        return conv_id

    def add_message(self, conversation_id: str, role: str, content: str, sources: List[Dict] = None):
        """Add a message to a conversation"""
        conn = self._get_conn()
        c = conn.cursor()
        
        # Check if conversation exists, if not create it
        c.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,))
        if not c.fetchone():
            # Create with first user message as title (truncated)
            title = content[:30] + "..." if len(content) > 30 else content
            if role == "assistant":
                title = "New Chat"
            c.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title, datetime.now(), datetime.now())
            )
        else:
            # Update updated_at timestamp
            c.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", 
                (datetime.now(), conversation_id)
            )
            
            # If it's the first user message and title is generic, update title
            if role == "user":
                c.execute("SELECT count(*) FROM messages WHERE conversation_id = ?", (conversation_id,))
                count = c.fetchone()[0]
                if count <= 1:  # Assuming system/welcome message might exist or not
                    title = content[:30] + "..." if len(content) > 30 else content
                    c.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))

        sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
        
        c.execute(
            "INSERT INTO messages (conversation_id, role, content, sources) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, sources_json)
        )
        conn.commit()
        conn.close()

    def get_conversations(self, limit: int = 50) -> List[Dict]:
        """Get list of conversations, sorted by newest update"""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", 
            (limit,)
        )
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_messages(self, conversation_id: str) -> List[Dict]:
        """Get all messages for a specific conversation"""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC", 
            (conversation_id,)
        )
        rows = c.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            msg = dict(row)
            if msg['sources']:
                try:
                    msg['sources'] = json.loads(msg['sources'])
                except:
                    msg['sources'] = []
            result.append(msg)
        return result

    def delete_conversation(self, conversation_id: str):
        """Delete a conversation and all its messages"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        c.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        conn.close()
