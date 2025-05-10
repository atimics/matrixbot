import sqlite3
import os
from typing import Optional, Tuple

DATABASE_PATH = os.getenv("DATABASE_PATH", "matrix_bot.db")

def initialize_database():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channel_summaries (
        room_id TEXT PRIMARY KEY,
        summary_text TEXT,
        last_updated_timestamp REAL,
        last_event_id_summarized TEXT 
    )
    """)
    # last_event_id_summarized can help in fetching only new messages for next summary
    conn.commit()
    conn.close()
    print(f"Database initialized at {DATABASE_PATH}")

def update_summary(room_id: str, summary_text: str, last_event_id_summarized: Optional[str] = None):
    """Updates or inserts a channel summary."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO channel_summaries (room_id, summary_text, last_updated_timestamp, last_event_id_summarized)
    VALUES (?, ?, ?, ?)
    """, (room_id, summary_text, time.time(), last_event_id_summarized))
    conn.commit()
    conn.close()
    print(f"[{room_id}] Summary updated in DB. Last event summarized: {last_event_id_summarized}")

def get_summary(room_id: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    Retrieves the latest summary and the last event ID summarized for a room.
    Returns (summary_text, last_event_id_summarized) or None.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT summary_text, last_event_id_summarized FROM channel_summaries WHERE room_id = ?", (room_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None

# Helper for migrations or direct DB access if needed in future
if __name__ == "__main__":
    import time # for initialize_database if run directly
    initialize_database()
    # Example usage (optional)
    # update_summary("!exampleRoom:matrix.org", "Initial summary text here.", "event123")
    # summary_data = get_summary("!exampleRoom:matrix.org")
    # if summary_data:
    #     print(f"Retrieved summary: {summary_data[0]}, Last event: {summary_data[1]}")