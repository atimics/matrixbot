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
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS image_cache (
                    cache_key TEXT PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    s3_url TEXT NOT NULL,
                    timestamp REAL NOT NULL
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

async def get_tool_states(db_path: str, room_id: str) -> Dict[str, Any]:
    """Get tool-specific states from room states. Tool states are stored with keys prefixed by tool names."""
    try:
        all_states = await get_room_states(db_path, room_id)
        # Filter for tool states - these could be direct tool names or prefixed keys
        tool_states = {}
        
        # Look for known tool state patterns
        for key, value in all_states.items():
            # Check if it's a direct tool state (key is a tool name or ends with tool-related suffix)
            if any(tool_indicator in key for tool_indicator in [
                'tool_states', 'manage_user_memory', 'manage_system_prompt', 
                'manage_channel_summary', 'describe_image', 'get_room_info',
                'send_reply', 'react_to_message', 'do_not_respond'
            ]):
                tool_states[key] = value
        
        return tool_states
    except Exception as e:
        logger.error(f"Error fetching tool states for room '{room_id}': {e}")
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

async def store_image_cache(db_path: str, cache_key: str, original_url: str, s3_url: str) -> bool:
    """Store an image cache mapping in the database."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO image_cache (cache_key, original_url, s3_url, timestamp) VALUES (?, ?, ?, ?)",
                (cache_key, original_url, s3_url, time.time()),
            )
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"SQLite error storing image cache for key '{cache_key}': {e}")
        return False

async def get_image_cache(db_path: str, cache_key: str) -> Optional[Tuple[str, str, str, float]]:
    """Retrieve cached image data by cache key."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT cache_key, original_url, s3_url, timestamp FROM image_cache WHERE cache_key = ?",
                (cache_key,),
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result[0], result[1], result[2], result[3]
                return None
    except aiosqlite.Error as e:
        logger.error(f"SQLite error fetching image cache for key '{cache_key}': {e}")
        return None

async def delete_image_cache(db_path: str, cache_key: str) -> bool:
    """Delete an image cache entry."""
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "DELETE FROM image_cache WHERE cache_key = ?",
                (cache_key,),
            )
            await db.commit()
            return cursor.rowcount > 0
    except aiosqlite.Error as e:
        logger.error(f"SQLite error deleting image cache for key '{cache_key}': {e}")
        return False

async def cleanup_old_image_cache(db_path: str, max_age_seconds: int = 86400 * 30) -> int:
    """Clean up image cache entries older than max_age_seconds (default 30 days)."""
    try:
        cutoff_time = time.time() - max_age_seconds
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "DELETE FROM image_cache WHERE timestamp < ?",
                (cutoff_time,),
            )
            await db.commit()
            return cursor.rowcount
    except aiosqlite.Error as e:
        logger.error(f"SQLite error cleaning up old image cache entries: {e}")
        return 0

