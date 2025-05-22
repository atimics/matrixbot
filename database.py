import aiosqlite
import time
import logging
import json
from typing import Optional, Tuple, List, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are AI. Your primary method of achieving your goals is by selecting and executing tools.
Always choose a tool to respond to the user. If no other tool is appropriate, you can use 'send_message' to send a textual response, or 'do_not_respond' if no response is needed.
Consider the conversation history, global summaries, user-specific memories, and current tool states to make informed decisions. Be concise and helpful."""

DEFAULT_SUMMARIZATION_PROMPT = """Summarize the following conversation transcript. Focus on key topics, decisions, and action items. Be concise and accurate.
If a previous summary is provided, integrate the new information from the transcript to produce an updated, coherent summary. Do not repeat information already in the previous summary unless it is being updated or elaborated upon.
Output only the summary text itself, without any introductory or concluding phrases like 'Here is the summary' or 'This concludes the summary'."""

class SummaryData(BaseModel):
    room_id: str
    summary: str
    updated_at: Optional[str] = None

async def initialize_database(db_path: str) -> None:
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_summaries (
                    room_id TEXT PRIMARY KEY,
                    summary_text TEXT,
                    last_updated_timestamp REAL,
                    last_event_id_summarized TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS prompts (
                    prompt_name TEXT PRIMARY KEY,
                    prompt_text TEXT NOT NULL,
                    last_updated REAL NOT NULL
                )
                """
            )
            try:
                await db.execute(
                    "INSERT INTO prompts (prompt_name, prompt_text, last_updated) VALUES (?, ?, ?)",
                    ("system_default", DEFAULT_SYSTEM_PROMPT, time.time()),
                )
            except aiosqlite.IntegrityError:
                pass
            try:
                await db.execute(
                    "INSERT INTO prompts (prompt_name, prompt_text, last_updated) VALUES (?, ?, ?)",
                    ("summarization_default", DEFAULT_SUMMARIZATION_PROMPT, time.time()),
                )
            except aiosqlite.IntegrityError:
                pass
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS global_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary_text TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_memories (
                    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    memory_text TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS room_states (
                    room_id TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    state_value TEXT NOT NULL,
                    last_updated REAL NOT NULL,
                    PRIMARY KEY (room_id, state_key)
                )
                """
            )
            await db.commit()
            logger.info(f"Database initialized at {db_path}")
    except aiosqlite.Error as e:
        logger.error(f"Database initialization failed: {e}")

async def update_summary(db_path: str, room_id: str, summary_text: str, last_event_id_summarized: Optional[str] = None) -> None:
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO channel_summaries (room_id, summary_text, last_updated_timestamp, last_event_id_summarized)
                VALUES (?, ?, ?, ?)
                """,
                (room_id, summary_text, time.time(), last_event_id_summarized),
            )
            await db.commit()
            logger.debug(f"DB: [{room_id}] Summary updated. Last event: {last_event_id_summarized}")
    except aiosqlite.Error as e:
        logger.error(f"Failed to update summary for room {room_id}: {e}")

async def get_summary(db_path: str, room_id: str) -> Optional[Tuple[str, Optional[str]]]:
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT summary_text, last_event_id_summarized FROM channel_summaries WHERE room_id = ?",
                (room_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0], row[1]
                return None
    except aiosqlite.Error as e:
        logger.error(f"Failed to fetch summary for room {room_id}: {e}")
        return None

async def get_prompt(db_path: str, prompt_name: str) -> Optional[Tuple[str, float]]:
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT prompt_text, last_updated FROM prompts WHERE prompt_name = ?",
                (prompt_name,),
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result[0], result[1]
                return None
    except aiosqlite.Error as e:
        logger.error(f"SQLite error fetching prompt '{prompt_name}': {e}")
        return None

async def update_prompt(db_path: str, prompt_name: str, prompt_text: str) -> bool:
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO prompts (prompt_name, prompt_text, last_updated) VALUES (?, ?, ?)",
                (prompt_name, prompt_text, time.time()),
            )
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"SQLite error updating prompt '{prompt_name}': {e}")
        return False

async def add_global_summary(db_path: str, summary_text: str) -> Optional[int]:
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "INSERT INTO global_summaries (summary_text, timestamp) VALUES (?, ?)",
                (summary_text, time.time()),
            )
            await db.commit()
            return cursor.lastrowid
    except aiosqlite.Error as e:
        logger.error(f"SQLite error adding global summary: {e}")
        return None

async def get_latest_global_summary(db_path: str) -> Optional[Tuple[str, float]]:
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT summary_text, timestamp FROM global_summaries ORDER BY timestamp DESC LIMIT 1"
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result[0], result[1]
                return None
    except aiosqlite.Error as e:
        logger.error(f"SQLite error fetching latest global summary: {e}")
        return None

async def add_user_memory(db_path: str, user_id: str, memory_text: str) -> Optional[int]:
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "INSERT INTO user_memories (user_id, memory_text, timestamp) VALUES (?, ?, ?)",
                (user_id, memory_text, time.time()),
            )
            await db.commit()
            return cursor.lastrowid
    except aiosqlite.Error as e:
        logger.error(f"SQLite error adding memory for user '{user_id}': {e}")
        return None

async def get_user_memories(db_path: str, user_id: str) -> List[Tuple[int, str, str, float]]:
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT memory_id, user_id, memory_text, timestamp FROM user_memories WHERE user_id = ? ORDER BY timestamp DESC",
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return rows
    except aiosqlite.Error as e:
        logger.error(f"SQLite error fetching memories for user '{user_id}': {e}")
        return []

async def delete_user_memory(db_path: str, memory_id: int) -> bool:
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "DELETE FROM user_memories WHERE memory_id = ?",
                (memory_id,),
            )
            await db.commit()
            return cursor.rowcount > 0
    except aiosqlite.Error as e:
        logger.error(f"SQLite error deleting memory ID '{memory_id}': {e}")
        return False

async def update_room_state(db_path: str, room_id: str, state_key: str, state_value: Any) -> bool:
    try:
        json_value = json.dumps(state_value)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO room_states (room_id, state_key, state_value, last_updated) VALUES (?, ?, ?, ?)",
                (room_id, state_key, json_value, time.time()),
            )
            await db.commit()
            return True
    except (aiosqlite.Error, TypeError) as e:
        logger.error(f"SQLite error updating room state for room '{room_id}', key '{state_key}': {e}")
        return False

async def get_room_states(db_path: str, room_id: str) -> Dict[str, Any]:
    states: Dict[str, Any] = {}
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT state_key, state_value FROM room_states WHERE room_id = ?",
                (room_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                for key, value in rows:
                    try:
                        states[key] = json.loads(value)
                    except json.JSONDecodeError:
                        states[key] = value
                return states
    except aiosqlite.Error as e:
        logger.error(f"SQLite error fetching room states for room '{room_id}': {e}")
        return {}

async def delete_room_state(db_path: str, room_id: str, state_key: str) -> bool:
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "DELETE FROM room_states WHERE room_id = ? AND state_key = ?",
                (room_id, state_key),
            )
            await db.commit()
            return cursor.rowcount > 0
    except aiosqlite.Error as e:
        logger.error(f"SQLite error deleting room state for room '{room_id}', key '{state_key}': {e}")
        return False

