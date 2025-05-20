import prompt_constructor as pc


def test_system_prompt_included():
    messages = pc.build_messages_for_ai(
        historical_messages=[],
        current_batched_user_inputs=[],
        bot_display_name="TestBot",
        db_path="dummy.db",
        include_system_prompt=True,
    )
    assert messages[0]["role"] == "system"
    assert "TestBot" in messages[0]["content"]


def test_system_prompt_excluded():
    messages = pc.build_messages_for_ai(
        historical_messages=[],
        current_batched_user_inputs=[],
        bot_display_name="TestBot",
        db_path="dummy.db",
        include_system_prompt=False,
    )
    assert messages == []


def test_combined_user_inputs():
    messages = pc.build_messages_for_ai(
        historical_messages=[],
        current_batched_user_inputs=[
            {"name": "alice", "content": "Hello"},
            {"name": "bob", "content": "Hi"},
        ],
        bot_display_name="TestBot",
        db_path="dummy.db",
    )
    user_msg = messages[-1]
    assert user_msg["role"] == "user"
    assert user_msg["name"] == "alice"
    assert "alice: Hello" in user_msg["content"]
    assert "bob: Hi" in user_msg["content"]


def test_channel_summary_inserted():
    summary_text = "previous chat summary"
    messages = pc.build_messages_for_ai(
        historical_messages=[],
        current_batched_user_inputs=[],
        bot_display_name="TestBot",
        db_path="dummy.db",
        channel_summary=summary_text,
    )
    system_msg_content = messages[0]["content"]
    assert summary_text in system_msg_content
