import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")


def get_connection():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the conversations table if it doesn't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            emotion TEXT DEFAULT 'neutral'
        )
    """)
    conn.commit()
    conn.close()


def save_message(role, message, emotion="neutral"):
    """
    Save a single message to the database.
    role: 'user' or 'assistant'
    """
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (timestamp, role, message, emotion) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), role, message, emotion),
    )
    conn.commit()
    conn.close()


def get_recent_history(n=10):
    """
    Get the last n conversation exchanges as a list of dicts.
    Returns: [{"role": "user"/"assistant", "message": "...", "emotion": "..."}]
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, message, emotion FROM conversations ORDER BY id DESC LIMIT ?",
        (n,),
    ).fetchall()
    conn.close()

    # Reverse so oldest first (chronological order)
    history = [{"role": r["role"], "message": r["message"], "emotion": r["emotion"]} for r in reversed(rows)]
    return history


def clear_memory():
    """Clear all conversation history."""
    conn = get_connection()
    conn.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()
