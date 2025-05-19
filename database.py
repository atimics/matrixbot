import sqlite3
import os
import time
import logging
from typing import Optional, Tuple, List, Dict, Any
from pydantic import BaseModel
import json

logger = logging.getLogger(__name__)

# Default prompts
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant. Your primary goal is to assist users by selecting and executing tools. 
Always choose a tool to respond to the user. If no other tool is appropriate, you can use 'send_message' to send a textual response, or 'do_not_respond' if no response is needed.
Consider the conversation history, global summaries, user-specific memories, and current tool states to make informed decisions. Be concise and helpful."""
DEFAULT_SUMMARIZATION_PROMPT = """Summarize the following conversation transcript. Focus on key topics, decisions, and action items. Be concise and accurate. 
If a previous summary is provided, integrate the new information from the transcript to produce an updated, coherent summary. Do not repeat information already in the previous summary unless it is being updated or elaborated upon.
Output only the summary text itself, without any introductory or concluding phrases like 'Here is the summary' or 'This concludes the summary'."""

class SummaryData(BaseModel):
    room_id: str
    summary: str
    updated_at: Optional[str] = None

def initialize_database(db_path: str) -> None:
    """Initializes the SQLite database and creates the channel_summaries table if needed."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_summaries (
            room_id TEXT PRIMARY KEY,
            summary_text TEXT,
            last_updated_timestamp REAL,
            last_event_id_summarized TEXT 
        )
        """)
        logger.info("Ensured 'channel_summaries' table exists.")

        # Create prompts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prompts (
                prompt_name TEXT PRIMARY KEY,
                prompt_text TEXT NOT NULL,
                last_updated REAL NOT NULL
            )
        ''')
        logger.info("Ensured 'prompts' table exists.")

        # Populate default prompts if they don't exist
        try:
            cursor.execute("INSERT INTO prompts (prompt_name, prompt_text, last_updated) VALUES (?, ?, ?)", 
                        ("system_default", DEFAULT_SYSTEM_PROMPT, time.time()))
            logger.info("Inserted default system prompt.")
        except sqlite3.IntegrityError:
            logger.info("Default system prompt already exists.")

        try:
            cursor.execute("INSERT INTO prompts (prompt_name, prompt_text, last_updated) VALUES (?, ?, ?)", 
                        ("summarization_default", DEFAULT_SUMMARIZATION_PROMPT, time.time()))
            logger.info("Inserted default summarization prompt.")
        except sqlite3.IntegrityError:
            logger.info("Default summarization prompt already exists.")

        # Create global_summaries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_text TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        ''')
        logger.info("Ensured 'global_summaries' table exists.")

        # Create user_memories table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_memories (
                memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                memory_text TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        ''')
        logger.info("Ensured 'user_memories' table exists.")

        # Create room_states table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS room_states (
                room_id TEXT NOT NULL,
                state_key TEXT NOT NULL,
                state_value TEXT NOT NULL, -- JSON encoded string
                last_updated REAL NOT NULL,
                PRIMARY KEY (room_id, state_key)
            )
        ''')
        logger.info("Ensured 'room_states' table exists.")

        conn.commit()
        logger.info(f"Database initialized at {db_path}")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def update_summary(db_path: str, room_id: str, summary_text: str, last_event_id_summarized: Optional[str] = None) -> None:
    """Updates or inserts a summary for a room in the database."""
    try:
        conn = sqlite3.connect(db_path)
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

def get_summary(db_path: str, room_id: str) -> Optional[Tuple[str, Optional[str]]]:
    """Fetches the summary and last event ID for a room, or None if not found."""
    try:
        conn = sqlite3.connect(db_path)
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

def get_prompt(db_path: str, prompt_name: str) -> Optional[Tuple[str, float]]:
    """Fetches a prompt and its last update time from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT prompt_text, last_updated FROM prompts WHERE prompt_name = ?", (prompt_name,))
        result = cursor.fetchone()
        if result:
            logger.debug(f"Retrieved prompt '{prompt_name}' from database.")
            return result[0], result[1]
        else:
            logger.warning(f"Prompt '{prompt_name}' not found in database.")
            return None
    except sqlite3.Error as e:
        logger.error(f"SQLite error fetching prompt '{prompt_name}': {e}")
        return None
    finally:
        conn.close()

def update_prompt(db_path: str, prompt_name: str, prompt_text: str) -> bool:
    """Updates a prompt in the database or inserts it if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO prompts (prompt_name, prompt_text, last_updated) VALUES (?, ?, ?)",
                  (prompt_name, prompt_text, time.time()))
        conn.commit()
        logger.info(f"Prompt '{prompt_name}' updated in the database.")
        return True
    except sqlite3.Error as e:
        logger.error(f"SQLite error updating prompt '{prompt_name}': {e}")
        return False
    finally:
        conn.close()

def add_global_summary(db_path: str, summary_text: str) -> Optional[int]:
    """Adds a new global summary to the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO global_summaries (summary_text, timestamp) VALUES (?, ?)", 
                  (summary_text, time.time()))
        conn.commit()
        last_id = cursor.lastrowid
        logger.info(f"Added global summary with ID: {last_id}")
        return last_id
    except sqlite3.Error as e:
        logger.error(f"SQLite error adding global summary: {e}")
        return None
    finally:
        conn.close()

def get_latest_global_summary(db_path: str) -> Optional[Tuple[str, float]]:
    """Fetches the most recent global summary from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT summary_text, timestamp FROM global_summaries ORDER BY timestamp DESC LIMIT 1")
        result = cursor.fetchone()
        if result:
            logger.debug("Retrieved latest global summary from database.")
            return result[0], result[1]
        else:
            logger.info("No global summaries found in database.")
            return None
    except sqlite3.Error as e:
        logger.error(f"SQLite error fetching latest global summary: {e}")
        return None
    finally:
        conn.close()

def add_user_memory(db_path: str, user_id: str, memory_text: str) -> Optional[int]:
    """Adds a memory for a specific user."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO user_memories (user_id, memory_text, timestamp) VALUES (?, ?, ?)",
                  (user_id, memory_text, time.time()))
        conn.commit()
        last_id = cursor.lastrowid
        logger.info(f"Added memory for user '{user_id}' with ID: {last_id}")
        return last_id
    except sqlite3.Error as e:
        logger.error(f"SQLite error adding memory for user '{user_id}': {e}")
        return None
    finally:
        conn.close()

def get_user_memories(db_path: str, user_id: str) -> List[Tuple[int, str, str, float]]:
    """Retrieves all memories for a specific user, ordered by timestamp."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT memory_id, user_id, memory_text, timestamp FROM user_memories WHERE user_id = ? ORDER BY timestamp DESC", 
                  (user_id,))
        memories = cursor.fetchall()
        logger.debug(f"Retrieved {len(memories)} memories for user '{user_id}'.")
        return memories
    except sqlite3.Error as e:
        logger.error(f"SQLite error fetching memories for user '{user_id}': {e}")
        return []
    finally:
        conn.close()

def delete_user_memory(db_path: str, memory_id: int) -> bool:
    """Deletes a specific memory by its ID."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM user_memories WHERE memory_id = ?", (memory_id,))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Deleted memory with ID: {memory_id}")
            return True
        else:
            logger.warning(f"No memory found with ID: {memory_id} to delete.")
            return False
    except sqlite3.Error as e:
        logger.error(f"SQLite error deleting memory ID '{memory_id}': {e}")
        return False
    finally:
        conn.close()

def update_room_state(db_path: str, room_id: str, state_key: str, state_value: Any) -> bool:
    """Updates or inserts a room-specific state value (JSON encoded)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        json_value = json.dumps(state_value)
        cursor.execute("INSERT OR REPLACE INTO room_states (room_id, state_key, state_value, last_updated) VALUES (?, ?, ?, ?)",
                  (room_id, state_key, json_value, time.time()))
        conn.commit()
        logger.info(f"Updated room state for room '{room_id}', key '{state_key}'.")
        return True
    except sqlite3.Error as e:
        logger.error(f"SQLite error updating room state for room '{room_id}', key '{state_key}': {e}")
        return False
    except TypeError as e:
        logger.error(f"JSON serialization error for room state '{room_id}', key '{state_key}': {e}")
        return False
    finally:
        conn.close()

def get_room_states(db_path: str, room_id: str) -> Dict[str, Any]:
    """Retrieves all state key-value pairs for a specific room."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    states = {}
    try:
        cursor.execute("SELECT state_key, state_value FROM room_states WHERE room_id = ?", (room_id,))
        rows = cursor.fetchall()
        for row in rows:
            try:
                states[row[0]] = json.loads(row[1])
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON for room '{room_id}', key '{row[0]}': {e}. Stored value: {row[1]}")
        logger.debug(f"Retrieved {len(states)} state entries for room '{room_id}'.")
        return states
    except sqlite3.Error as e:
        logger.error(f"SQLite error fetching room states for room '{room_id}': {e}")
        return {}
    finally:
        conn.close()

def delete_room_state(db_path: str, room_id: str, state_key: str) -> bool:
    """Deletes a specific state key for a room."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM room_states WHERE room_id = ? AND state_key = ?", (room_id, state_key))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Deleted room state for room '{room_id}', key '{state_key}'.")
            return True
        else:
            logger.warning(f"No room state found for room '{room_id}', key '{state_key}' to delete.")
            return False
    except sqlite3.Error as e:
        logger.error(f"SQLite error deleting room state for room '{room_id}', key '{state_key}': {e}")
        return False
    finally:
        conn.close()