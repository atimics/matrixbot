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
            # Farcaster bot state table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS farcaster_bot_state (
                    id INTEGER PRIMARY KEY,
                    farcaster_persistent_summary TEXT,
                    last_feed_retrieval_timestamp REAL,
                    last_notification_check_timestamp REAL,
                    processed_notification_ids TEXT,
                    recent_mentions_summary TEXT,
                    last_updated REAL NOT NULL
                )
                """
            )
            # Initialize default Farcaster bot state if not exists
            try:
                await db.execute(
                    """
                    INSERT INTO farcaster_bot_state 
                    (farcaster_persistent_summary, last_feed_retrieval_timestamp, 
                     last_notification_check_timestamp, processed_notification_ids, 
                     recent_mentions_summary, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "No Farcaster activity yet.",
                        0.0,
                        0.0,
                        "[]",
                        "",
                        time.time()
                    ),
                )
            except aiosqlite.IntegrityError:
                pass

            # Create unified channel system tables
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS unified_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    channel_type TEXT NOT NULL,  -- 'matrix', 'farcaster_home', 'farcaster_notifications'
                    display_name TEXT NOT NULL,
                    last_message_timestamp REAL DEFAULT 0,
                    last_checked_by_ai REAL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,  -- Matrix event ID or Farcaster cast hash
                    message_type TEXT NOT NULL,  -- 'matrix_message', 'farcaster_cast', 'farcaster_notification'
                    sender_id TEXT,  -- Matrix user ID or Farcaster FID
                    sender_display_name TEXT,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata TEXT,  -- JSON for additional data (replies, reactions, etc.)
                    replied_to_message_id TEXT,  -- For tracking reply chains
                    ai_has_replied BOOLEAN DEFAULT FALSE,  -- Track if AI has already replied
                    created_at REAL NOT NULL,
                    FOREIGN KEY (channel_id) REFERENCES unified_channels(channel_id),
                    UNIQUE(channel_id, message_id)
                )
                """
            )
            
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_messages_channel_timestamp 
                ON channel_messages(channel_id, timestamp DESC)
                """
            )
            
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_messages_ai_replied 
                ON channel_messages(channel_id, ai_has_replied, timestamp DESC)
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

# Farcaster-specific database functions

async def get_farcaster_bot_state(db_path: str) -> Dict[str, Any]:
    """Get the current Farcaster bot state."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                """
                SELECT farcaster_persistent_summary, last_feed_retrieval_timestamp, 
                       last_notification_check_timestamp, processed_notification_ids, 
                       recent_mentions_summary, last_updated
                FROM farcaster_bot_state ORDER BY id DESC LIMIT 1
                """
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    processed_ids = json.loads(result[3]) if result[3] else []
                    return {
                        "farcaster_persistent_summary": result[0] or "",
                        "last_feed_retrieval_timestamp": result[1] or 0.0,
                        "last_notification_check_timestamp": result[2] or 0.0,
                        "processed_notification_ids": processed_ids,
                        "recent_mentions_summary": result[4] or "",
                        "last_updated": result[5]
                    }
                else:
                    # Return default state if no record exists
                    return {
                        "farcaster_persistent_summary": "No Farcaster activity yet.",
                        "last_feed_retrieval_timestamp": 0.0,
                        "last_notification_check_timestamp": 0.0,
                        "processed_notification_ids": [],
                        "recent_mentions_summary": "",
                        "last_updated": time.time()
                    }
    except aiosqlite.Error as e:
        logger.error(f"SQLite error fetching Farcaster bot state: {e}")
        return {}

async def update_farcaster_bot_state(db_path: str, 
                                    persistent_summary: Optional[str] = None,
                                    last_feed_timestamp: Optional[float] = None,
                                    last_notification_timestamp: Optional[float] = None,
                                    processed_notification_ids: Optional[List[str]] = None,
                                    recent_mentions_summary: Optional[str] = None) -> bool:
    """Update specific fields in the Farcaster bot state."""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Get current state first
            current_state = await get_farcaster_bot_state(db_path)
            
            # Update only provided fields
            updated_summary = persistent_summary if persistent_summary is not None else current_state.get("farcaster_persistent_summary", "")
            updated_feed_timestamp = last_feed_timestamp if last_feed_timestamp is not None else current_state.get("last_feed_retrieval_timestamp", 0.0)
            updated_notification_timestamp = last_notification_timestamp if last_notification_timestamp is not None else current_state.get("last_notification_check_timestamp", 0.0)
            updated_processed_ids = processed_notification_ids if processed_notification_ids is not None else current_state.get("processed_notification_ids", [])
            updated_mentions_summary = recent_mentions_summary if recent_mentions_summary is not None else current_state.get("recent_mentions_summary", "")
            
            # Clear existing state and insert updated state
            await db.execute("DELETE FROM farcaster_bot_state")
            
            await db.execute(
                """
                INSERT INTO farcaster_bot_state 
                (farcaster_persistent_summary, last_feed_retrieval_timestamp, 
                 last_notification_check_timestamp, processed_notification_ids, 
                 recent_mentions_summary, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    updated_summary,
                    updated_feed_timestamp,
                    updated_notification_timestamp,
                    json.dumps(updated_processed_ids),
                    updated_mentions_summary,
                    time.time()
                ),
            )
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"SQLite error updating Farcaster bot state: {e}")
        return False

async def get_farcaster_tool_status(db_path: str, bot_fid: str) -> Dict[str, Any]:
    """Get Farcaster tool status for AI context."""
    try:
        state = await get_farcaster_bot_state(db_path)
        if not state:
            return {}
        
        # Calculate unread mention count (placeholder - would need actual logic)
        unread_count = 0
        
        return {
            "bot_fid": bot_fid,
            "persistent_summary": state.get("farcaster_persistent_summary", ""),
            "last_feed_retrieval_timestamp": state.get("last_feed_retrieval_timestamp", 0.0),
            "last_notification_check_timestamp": state.get("last_notification_check_timestamp", 0.0),
            "unread_mention_count": unread_count,
            "recent_mentions_summary": state.get("recent_mentions_summary", "")
        }
    except Exception as e:
        logger.error(f"Error getting Farcaster tool status: {e}")
        return {}

# Unified Channel System Functions

async def ensure_channel_exists(db_path: str, channel_id: str, channel_type: str, 
                               display_name: str) -> bool:
    """Ensure a channel exists in the unified channel system."""
    try:
        async with aiosqlite.connect(db_path) as db:
            now = time.time()
            await db.execute(
                """
                INSERT OR IGNORE INTO unified_channels 
                (channel_id, channel_type, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (channel_id, channel_type, display_name, now, now)
            )
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"Error ensuring channel exists {channel_id}: {e}")
        return False

async def add_channel_message(db_path: str, channel_id: str, message_id: str, 
                             message_type: str, sender_id: str, sender_display_name: str,
                             content: str, timestamp: float, metadata: Dict[str, Any] = None,
                             replied_to_message_id: str = None) -> bool:
    """Add a message to a channel."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO channel_messages 
                (channel_id, message_id, message_type, sender_id, sender_display_name, 
                 content, timestamp, metadata, replied_to_message_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (channel_id, message_id, message_type, sender_id, sender_display_name,
                 content, timestamp, json.dumps(metadata or {}), replied_to_message_id, time.time())
            )
            
            # Update channel's last message timestamp
            await db.execute(
                """
                UPDATE unified_channels 
                SET last_message_timestamp = ?, updated_at = ?
                WHERE channel_id = ?
                """,
                (timestamp, time.time(), channel_id)
            )
            
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"Error adding message to channel {channel_id}: {e}")
        return False

async def get_channel_messages(db_path: str, channel_id: str, limit: int = 20,
                              include_ai_replied: bool = True) -> List[Dict[str, Any]]:
    """Get recent messages from a channel."""
    try:
        async with aiosqlite.connect(db_path) as db:
            query = """
                SELECT message_id, message_type, sender_id, sender_display_name,
                       content, timestamp, metadata, replied_to_message_id, ai_has_replied
                FROM channel_messages
                WHERE channel_id = ?
            """
            params = [channel_id]
            
            if not include_ai_replied:
                query += " AND ai_has_replied = FALSE"
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                messages = []
                for row in rows:
                    metadata = {}
                    try:
                        metadata = json.loads(row[6]) if row[6] else {}
                    except json.JSONDecodeError:
                        pass
                    
                    messages.append({
                        "message_id": row[0],
                        "message_type": row[1],
                        "sender_id": row[2],
                        "sender_display_name": row[3],
                        "content": row[4],
                        "timestamp": row[5],
                        "metadata": metadata,
                        "replied_to_message_id": row[7],
                        "ai_has_replied": bool(row[8])
                    })
                
                # Return in chronological order (oldest first)
                return list(reversed(messages))
    except aiosqlite.Error as e:
        logger.error(f"Error getting messages from channel {channel_id}: {e}")
        return []

async def mark_message_as_replied(db_path: str, channel_id: str, message_id: str) -> bool:
    """Mark a message as having been replied to by the AI."""
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                UPDATE channel_messages 
                SET ai_has_replied = TRUE
                WHERE channel_id = ? AND message_id = ?
                """,
                (channel_id, message_id)
            )
            await db.commit()
            return cursor.rowcount > 0
    except aiosqlite.Error as e:
        logger.error(f"Error marking message as replied {channel_id}/{message_id}: {e}")
        return False

async def update_channel_ai_check_timestamp(db_path: str, channel_id: str) -> bool:
    """Update when the AI last checked this channel."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                UPDATE unified_channels 
                SET last_checked_by_ai = ?, updated_at = ?
                WHERE channel_id = ?
                """,
                (time.time(), time.time(), channel_id)
            )
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"Error updating AI check timestamp for channel {channel_id}: {e}")
        return False

async def get_channels_needing_ai_attention(db_path: str) -> List[Dict[str, Any]]:
    """Get channels that have new messages since the AI last checked them."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                """
                SELECT channel_id, channel_type, display_name, 
                       last_message_timestamp, last_checked_by_ai
                FROM unified_channels
                WHERE last_message_timestamp > last_checked_by_ai
                ORDER BY last_message_timestamp DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                channels = []
                for row in rows:
                    channels.append({
                        "channel_id": row[0],
                        "channel_type": row[1],
                        "display_name": row[2],
                        "last_message_timestamp": row[3],
                        "last_checked_by_ai": row[4]
                    })
                return channels
    except aiosqlite.Error as e:
        logger.error(f"Error getting channels needing AI attention: {e}")
        return []

async def cleanup_old_channel_messages(db_path: str, max_messages_per_channel: int = 100) -> int:
    """Clean up old messages, keeping only the most recent ones per channel."""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Get all channels
            async with db.execute("SELECT DISTINCT channel_id FROM channel_messages") as cursor:
                channels = await cursor.fetchall()
            
            total_deleted = 0
            for (channel_id,) in channels:
                # Delete all but the most recent messages for this channel
                cursor = await db.execute(
                    """
                    DELETE FROM channel_messages
                    WHERE channel_id = ? AND id NOT IN (
                        SELECT id FROM channel_messages
                        WHERE channel_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                    """,
                    (channel_id, channel_id, max_messages_per_channel)
                )
                total_deleted += cursor.rowcount
            
            await db.commit()
            return total_deleted
    except aiosqlite.Error as e:
        logger.error(f"Error cleaning up old channel messages: {e}")
        return 0

async def mark_message_as_ai_replied(db_path: str, channel_id: str, message_id: str) -> bool:
    """Mark a message as having been replied to by AI."""
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                UPDATE channel_messages 
                SET ai_has_replied = TRUE
                WHERE channel_id = ? AND message_id = ?
                """,
                (channel_id, message_id)
            )
            await db.commit()
            return cursor.rowcount > 0
    except aiosqlite.Error as e:
        logger.error(f"Error marking message as AI replied: {e}")
        return False

async def update_channel_last_checked(db_path: str, channel_id: str, timestamp: float) -> bool:
    """Update the last time AI checked a channel."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                UPDATE unified_channels 
                SET last_checked_by_ai = ?, updated_at = ?
                WHERE channel_id = ?
                """,
                (timestamp, time.time(), channel_id)
            )
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"Error updating channel last checked: {e}")
        return False

async def get_all_channels(db_path: str) -> List[Dict[str, Any]]:
    """Get all registered channels."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                """
                SELECT channel_id, channel_type, display_name, 
                       last_message_timestamp, last_checked_by_ai,
                       created_at, updated_at
                FROM unified_channels
                ORDER BY last_message_timestamp DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                channels = []
                for row in rows:
                    channels.append({
                        "channel_id": row[0],
                        "channel_type": row[1],
                        "display_name": row[2],
                        "last_message_timestamp": row[3],
                        "last_checked_by_ai": row[4],
                        "created_at": row[5],
                        "updated_at": row[6]
                    })
                return channels
    except aiosqlite.Error as e:
        logger.error(f"Error getting all channels: {e}")
        return []

async def get_channels_with_unread_messages(db_path: str) -> List[Dict[str, Any]]:
    """Get channels that have messages AI hasn't seen."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                """
                SELECT uc.channel_id, uc.channel_type, uc.display_name,
                       uc.last_message_timestamp, uc.last_checked_by_ai,
                       COUNT(cm.id) as unread_count
                FROM unified_channels uc
                LEFT JOIN channel_messages cm ON uc.channel_id = cm.channel_id 
                    AND cm.timestamp > COALESCE(uc.last_checked_by_ai, 0)
                    AND cm.ai_has_replied = FALSE
                GROUP BY uc.channel_id, uc.channel_type, uc.display_name,
                         uc.last_message_timestamp, uc.last_checked_by_ai
                HAVING unread_count > 0 OR uc.last_checked_by_ai IS NULL
                ORDER BY uc.last_message_timestamp DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                channels = []
                for row in rows:
                    channels.append({
                        "channel_id": row[0],
                        "channel_type": row[1],
                        "display_name": row[2],
                        "last_message_timestamp": row[3],
                        "last_checked_by_ai": row[4],
                        "unread_count": row[5]
                    })
                return channels
    except aiosqlite.Error as e:
        logger.error(f"Error getting channels with unread messages: {e}")
        return []

