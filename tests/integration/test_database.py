import pytest
import pytest_asyncio
import sqlite3
import os
# The plan mentioned a SummaryData Pydantic model, but database.py currently returns a tuple.
# For now, tests will be adjusted to the tuple output.
# from database import initialize_database, update_summary, get_summary, SummaryData # Assuming SummaryData if it were used
from database import initialize_database, update_summary, get_summary

@pytest_asyncio.fixture
async def test_db_path(tmp_path):
    """Fixture to provide a temporary database path and initialize the DB."""
    db_file = tmp_path / "test_matrix_bot.db"
    await initialize_database(str(db_file))
    return str(db_file)

@pytest.mark.asyncio
async def test_initialize_database(test_db_path):
    """Test if the database and channel_summaries table are created."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    # Corrected table name
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channel_summaries';")
    assert cursor.fetchone() is not None, "channel_summaries table should exist"
    conn.close()

@pytest.mark.asyncio
async def test_update_summary_new(test_db_path):
    """Test inserting a new summary."""
    room_id = "!new_room:host"
    summary_text = "This is a new summary."
    last_event_id = "$event_new"
    await update_summary(test_db_path, room_id, summary_text, last_event_id)

    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    # Corrected table name
    cursor.execute("SELECT summary_text, last_event_id_summarized FROM channel_summaries WHERE room_id = ?", (room_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None, "Summary should have been inserted"
    assert row[0] == summary_text
    assert row[1] == last_event_id

@pytest.mark.asyncio
async def test_update_summary_existing(test_db_path):
    """Test updating an existing summary."""
    room_id = "!existing_room:host"
    initial_summary = "Initial summary text."
    initial_event_id = "$event_initial"
    await update_summary(test_db_path, room_id, initial_summary, initial_event_id) # Insert first

    updated_summary = "Updated summary text."
    updated_event_id = "$event_updated"
    await update_summary(test_db_path, room_id, updated_summary, updated_event_id) # Update

    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    # Corrected table name
    cursor.execute("SELECT summary_text, last_event_id_summarized FROM channel_summaries WHERE room_id = ?", (room_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None, "Summary should exist"
    assert row[0] == updated_summary, "Summary text should be updated"
    assert row[1] == updated_event_id, "Last event ID should be updated"

@pytest.mark.asyncio
async def test_get_summary_exists(test_db_path):
    """Test retrieving an existing summary."""
    room_id = "!room_with_summary:host"
    summary_text = "Summary to be fetched."
    last_event_id = "$event_fetch"
    await update_summary(test_db_path, room_id, summary_text, last_event_id)

    retrieved_summary_tuple = await get_summary(test_db_path, room_id)

    assert retrieved_summary_tuple is not None, "Summary should be found"
    # Access by index for tuple
    assert retrieved_summary_tuple[0] == summary_text
    assert retrieved_summary_tuple[1] == last_event_id

@pytest.mark.asyncio
async def test_get_summary_not_exists(test_db_path):
    """Test retrieving a non-existent summary."""
    room_id = "!room_without_summary:host"
    retrieved_summary = await get_summary(test_db_path, room_id)
    assert retrieved_summary is None, "Summary should not be found"

@pytest.mark.asyncio
async def test_get_summary_fields(test_db_path):
    """Verify both summary_text and last_event_id_summarized are returned correctly."""
    room_id = "!room_fields_test:host"
    summary_text = "Detailed summary text for field check."
    last_event_id = "$event_fields_check"
    await update_summary(test_db_path, room_id, summary_text, last_event_id)

    retrieved_summary_tuple = await get_summary(test_db_path, room_id)

    assert retrieved_summary_tuple is not None
    # Check tuple structure and content
    assert isinstance(retrieved_summary_tuple, tuple), "get_summary should return a tuple"
    assert len(retrieved_summary_tuple) == 2, "Tuple should have two elements"
    assert retrieved_summary_tuple[0] == summary_text
    assert retrieved_summary_tuple[1] == last_event_id

