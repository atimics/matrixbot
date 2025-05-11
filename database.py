import sqlite3
import os
import time # Ensure time is imported
from typing import Optional, Tuple

DATABASE_PATH = os.getenv("DATABASE_PATH", "matrix_bot_soa.db")

def initialize_database():
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
    conn.commit()
    conn.close()
    print(f"Database initialized at {DATABASE_PATH}")

def update_summary(room_id: str, summary_text: str, last_event_id_summarized: Optional[str] = None):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO channel_summaries (room_id, summary_text, last_updated_timestamp, last_event_id_summarized)
    VALUES (?, ?, ?, ?)
    """, (room_id, summary_text, time.time(), last_event_id_summarized))
    conn.commit()
    conn.close()
    # print(f"DB: [{room_id}] Summary updated. Last event: {last_event_id_summarized}")

def get_summary(room_id: str) -> Optional[Tuple[str, Optional[str]]]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT summary_text, last_event_id_summarized FROM channel_summaries WHERE room_id = ?", (room_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None