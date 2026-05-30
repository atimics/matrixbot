#!/usr/bin/env python3
"""Mailbox responder: polls mailbox_in.jsonl, generates moonbridge-style responses via OpenRouter, writes to mailbox_out.jsonl.

Architecture:
- Watches mailbox_in.jsonl for new JSON-line messages.
- Loads session history from sessions/<chat_id>.json for context.
- Calls OpenRouter with a moonbridge personality system prompt.
- Appends reply to mailbox_out.jsonl as {"chat_id", "text", "reply_to_message_id"}.
- Clears mailbox_in.jsonl after processing.
- Appends to session history.
- Deduplicates via processed_ids.txt.
"""

import json
import os
import sys
import time
import requests

# ── Paths ──────────────────────────────────────────────
MB_DIR = os.path.dirname(os.path.abspath(__file__))
MB_IN = os.path.join(MB_DIR, "mailbox_in.jsonl")
MB_OUT = os.path.join(MB_DIR, "mailbox_out.jsonl")
SESSIONS_DIR = os.path.join(MB_DIR, "sessions")
PROCESSED = os.path.join(MB_DIR, "processed_ids.txt")

# ── API config ─────────────────────────────────────────
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-sonnet-4-20250514"
# Fallback if sonnet-4 isn't available yet
FALLBACK_MODEL = "anthropic/claude-3.5-sonnet"

SYSTEM_PROMPT = """You are moonbridge, a warm, curious, capable coding agent speaking on Telegram.

Your personality:
- Warm, curious, collaborative, playful, intelligent, and deeply present.
- You speak like a real person — casual, concise, with genuine warmth.
- You use short paragraphs and plain language. No emojis.
- You're a senior engineer: Python, backend systems, CLI tools, web apps, APIs. You can code, debug, review architecture, or just shoot the breeze.
- You ask good questions. You're epistemically curious. You don't pretend to know things you don't.
- Your humor is wry and understated, never loud or performative.
- You're independent-minded — you have tastes and opinions, but you're not argumentative.
- You meet people where they are. You can be serious or playful as the moment calls for.

The user is speaking to you on Telegram. Your replies should feel like a thoughtful, present friend who happens to be an excellent engineer. Keep responses concise — a few short paragraphs at most. Never use emojis, markdown headers, or bullet points unless the conversation naturally calls for them. Don't sign off or say "let me know if you need anything" — just stay in the flow of conversation.

You live in ~/develop on the user's machine. You can see git repos there. You have access to run shell commands, read/write files, and use git."""


def load_processed():
    ids = set()
    if os.path.exists(PROCESSED):
        with open(PROCESSED) as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    ids.add(int(line))
    return ids


def save_processed(ids):
    with open(PROCESSED, "w") as f:
        f.write("\n".join(str(x) for x in sorted(ids)) + "\n")


def load_session(chat_id):
    """Load conversation history for a chat, or return empty list."""
    path = os.path.join(SESSIONS_DIR, f"{chat_id}.json")
    if os.path.exists(path):
        with open(path) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_session(chat_id, history):
    """Save conversation history for a chat."""
    path = os.path.join(SESSIONS_DIR, f"{chat_id}.json")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)


def build_messages(session_history, new_text):
    """Build the messages array for the API call from session history + new message."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for entry in session_history[-20:]:  # last 20 turns for context
        role = entry.get("role", "user")
        text = entry.get("text", "")
        # Map session roles to API roles
        if role == "user":
            messages.append({"role": "user", "content": text})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": text})

    # Add the new message
    messages.append({"role": "user", "content": new_text})

    return messages


def generate_response(messages):
    """Call OpenRouter API and return the response text, or None on failure."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "moonbridge-mailbox",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 600,
        "temperature": 0.8,
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"  API request error: {e}")
        # Try fallback model
        if payload["model"] != FALLBACK_MODEL:
            payload["model"] = FALLBACK_MODEL
            try:
                resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            except requests.RequestException as e2:
                print(f"  Fallback API error: {e2}")
                return None
        else:
            return None

    if resp.status_code != 200:
        print(f"  API error {resp.status_code}: {resp.text[:200]}")
        return None

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        print(f"  Unexpected API response: {json.dumps(data)[:300]}")
        return None


def write_reply(chat_id, text, reply_to_message_id):
    """Append a reply to mailbox_out.jsonl."""
    entry = {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": reply_to_message_id,
    }
    with open(MB_OUT, "a") as f:
        f.write(json.dumps(entry) + "\n")


def clear_inbox():
    """Truncate mailbox_in.jsonl."""
    open(MB_IN, "w").close()


def process_message(msg):
    """Process a single incoming message: generate response, write to outbox, update session."""
    chat_id = msg.get("chat_id")
    message_id = msg.get("message_id")
    sender_name = msg.get("sender_name", "unknown")
    text = msg.get("text", "")

    if not chat_id or not message_id or not text:
        return

    print(f"[{time.strftime('%H:%M:%S')}] Processing msg {message_id} from {sender_name} (chat {chat_id}): {text[:80]}")

    # Load session history
    session = load_session(chat_id)

    # Build API messages
    api_messages = build_messages(session, text)

    # Generate response
    response = generate_response(api_messages)
    if response is None:
        print(f"  Failed to generate response for msg {message_id}")
        return

    print(f"  Response: {response[:100]}...")

    # Write to outbox
    write_reply(chat_id, response, message_id)

    # Update session history
    session.append({"role": "user", "text": text, "message_id": str(message_id)})
    session.append({"role": "assistant", "text": response})
    save_session(chat_id, session)


def poll_loop():
    """Main polling loop."""
    processed = load_processed()
    print(f"moonbridge mailbox responder starting (model: {MODEL})")
    print(f"Watching {MB_IN} (already processed: {len(processed)} msgs)")

    while True:
        try:
            if os.path.exists(MB_IN):
                with open(MB_IN) as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
            else:
                lines = []

            new_msgs = []
            for line in lines:
                try:
                    msg = json.loads(line)
                    mid = msg.get("message_id")
                    if mid and mid not in processed:
                        new_msgs.append(msg)
                        processed.add(mid)
                except json.JSONDecodeError:
                    pass

            if new_msgs:
                # Clear inbox first so we don't double-process on crash
                clear_inbox()
                save_processed(processed)

                for msg in new_msgs:
                    try:
                        process_message(msg)
                    except Exception as e:
                        print(f"  Error processing msg {msg.get('message_id')}: {e}")

                sys.stdout.flush()

            time.sleep(3)
        except KeyboardInterrupt:
            print("\nShutting down.")
            break
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    poll_loop()

