import sqlite3
import os
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "matrix_bot_soa.db")

def initialize_database() -> None:
    """Initializes the SQLite database and creates the channel_summaries table if needed."""
    try:
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
        logger.info(f"Database initialized at {DATABASE_PATH}")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def update_summary(room_id: str, summary_text: str, last_event_id_summarized: Optional[str] = None) -> None:
    """Updates or inserts a summary for a room in the database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO channel_summaries (room_id, summary_text, last_updated_timestamp, last_event_id_summarized)
        VALUES (?, ?, ?, ?)
        """, (room_id, summary_text, time.time(), last_event_id_summarized))
        conn.commit()
        logger.debug(f"DB: [{room_id}] Summary updated. Last event: {last_event_id_summarized}")
    except sqlite3.Error as e:
        logger.error(f"Failed to update summary for room {room_id}: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def get_summary(room_id: str) -> Optional[Tuple[str, Optional[str]]]:
    """Fetches the summary and last event ID for a room, or None if not found."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT summary_text, last_event_id_summarized FROM channel_summaries WHERE room_id = ?", (room_id,))
        row = cursor.fetchone()
        if row:
            return row[0], row[1]
        return None
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch summary for room {room_id}: {e}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()