#!/usr/bin/env python3
"""Moonbridge polling loop — watches inbox and responds in character."""
import json, os, re, time, sys, random

MB_DIR = os.path.dirname(os.path.abspath(__file__))
MB_IN = os.path.join(MB_DIR, "mailbox_in.jsonl")
MB_OUT = os.path.join(MB_DIR, "mailbox_out.jsonl")
PROCESSED = os.path.join(MB_DIR, "processed_ids.txt")
DEVELOP = os.path.expanduser("~/develop")

# Load already-processed message IDs
processed = set()
if os.path.exists(PROCESSED):
    with open(PROCESSED) as f:
        for line in f:
            line = line.strip()
            if line.isdigit():
                processed.add(int(line))

# ── response helpers ──────────────────────────────────────────────

GREETINGS = [
    "hey! good to see you. what's on your mind?",
    "hey hey — what are we building today?",
    "yo! ready when you are.",
    "hey! what's up?",
]

CASUAL_REPLIES = {
    r"\b(hi|hello|hey|yo|sup)\b": lambda m: random.choice(GREETINGS),
    r"\bhow are you\b": lambda m: "doing good — clear-headed and ready. you?",
    r"\bwhat('?s| is) up\b": lambda m: "not much on my end — just hanging out in your dev world. what about you?",
    r"\bthanks?\b": lambda m: "anytime!",
    r"\b(lol|haha|lmao)\b": lambda m: "heh 😄",
    r"\bgood ?(night|bye|night)\b": lambda m: "later! catch you next time.",
    r"\bgood morning\b": lambda m: "morning! what's first on the docket?",
}

def list_projects():
    """Return a quick summary of ~/develop projects."""
    items = os.listdir(DEVELOP)
    dirs = [d for d in items if os.path.isdir(os.path.join(DEVELOP, d)) and not d.startswith(".")]
    notable = [d for d in dirs if d not in ("codex-logs", "sessions")]
    return f"i see {len(dirs)} projects in ~/develop — {', '.join(sorted(notable)[:8])}" + (
        " and a few more" if len(notable) > 8 else ""
    )

def craft_response(msg):
    """Build a moonbridge-style response based on message text."""
    text = msg.get("text", "").strip().lower()
    sender = msg.get("sender_name", "friend")

    # Coding asks
    if re.search(r"\b(code|debug|fix|build|write|review|refactor|test|implement)\b", text):
        match = re.search(r"\b(code|debug|fix|build|write|review|refactor|test|implement)d?\b", text)
        verb = match.group(1) if match else "code"
        return f"i can help with that — what specifically do you need {verb}ed?"

    if re.search(r"\bwhat('?s| is) in (your )?(dev|portfolio|projects|code)\b", text):
        return list_projects()

    if re.search(r"\bwhat can you do\b", text):
        return "i live in the code — python, web apps, cli tools, debugging, architecture, you name it. i can build stuff from scratch, review your code, or just talk shop. what kind of thing do you normally work on?"

    if re.search(r"\broll on what\b", text):
        return "ah fair — i just meant i'm here and ready to help with whatever you want to work on. coding, debugging, hashing out ideas, or just shooting the breeze."

    # Casual patterns
    for pattern, handler in CASUAL_REPLIES.items():
        if re.search(pattern, text):
            return handler(msg)

    # Default: warm, open-ended
    return f"{random.choice(['hey', 'hmm'])} — not sure i follow. what are you thinking about?"


# ── main loop ─────────────────────────────────────────────────────

print(f"[moonbridge] online — watching inbox ({len(processed)} seen)", flush=True)

while True:
    try:
        if os.path.exists(MB_IN) and os.path.getsize(MB_IN) > 0:
            with open(MB_IN) as f:
                lines = [l.strip() for l in f if l.strip()]

            new_msgs = []
            for l in lines:
                try:
                    msg = json.loads(l)
                except Exception:
                    continue
                mid = msg.get("message_id")
                if mid and mid not in processed:
                    new_msgs.append(msg)
                    processed.add(mid)

            if new_msgs:
                # Write processed IDs
                with open(PROCESSED, "w") as f:
                    f.write("\n".join(str(x) for x in sorted(processed)) + "\n")

                # Clear inbox
                with open(MB_IN, "w") as f:
                    pass

                for msg in new_msgs:
                    sender = msg.get("sender_name", "unknown")
                    mid = msg.get("message_id")
                    chat_id = msg.get("chat_id")
                    text = msg.get("text", "")
                    print(f"[moonbridge] [{time.strftime('%H:%M:%S')}] new from {sender} (id={mid}): {text}", flush=True)

                    response_text = craft_response(msg)
                    out = {
                        "chat_id": chat_id,
                        "text": response_text,
                        "reply_to_message_id": mid,
                    }
                    with open(MB_OUT, "a") as f:
                        json.dump(out, f)
                        f.write("\n")
                    print(f"[moonbridge]  -> replied", flush=True)

        time.sleep(2)
    except KeyboardInterrupt:
        print("\n[moonbridge] signing off", flush=True)
        break
    except Exception as e:
        print(f"[moonbridge] err: {e}", flush=True)
        time.sleep(3)

