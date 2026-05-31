#!/usr/bin/env python3
"""Economic treasury for Mirquo swarm on Solana devnet."""

import json, subprocess, time, sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
TREASURY_FILE = DIR / "treasury.json"

TOKENS = {
    "RATI":   "5gDbJE7cVChwWx2q9ePAhmxQgyExJyTMjC1vEvVT8Uut",
    "SECTOR": "4Cry7D6MrrJo5GBXqfZedJRk5Zgp58zAr8jYpHkqrzDU",
    "MIRQUO": "2wGfLVa6N7cFuchYdVTPxSbYNm4H1mXyK7QWZwEaaBj9",
}

def spl_token(*args):
    r = subprocess.run(["spl-token", *args, "--url", "devnet"], capture_output=True, text=True)
    return r.stdout.strip()

def solana(*args):
    return subprocess.run(["solana", *args, "--url", "devnet"], capture_output=True, text=True).stdout.strip()

def get_balances():
    b = {}
    b["SOL"] = solana("balance").split()[0]
    for name, mint in TOKENS.items():
        try: b[name] = spl_token("balance", mint)
        except: b[name] = "?"
    return b

def earn(amount=10, source="station"):
    """Station earned RATI from gameplay activity."""
    l = load()
    l["total_earned"] = l.get("total_earned", 0) + amount
    l.setdefault("earnings_log", []).append({
        "amount": amount, "source": source, "time": time.time()
    })
    save(l)
    return amount

def spend(task_id, amount=50):
    """Dispatch worker, spend MIRQUO."""
    l = load()
    l["total_spent"] = l.get("total_spent", 0) + amount
    l.setdefault("tasks", {})[task_id] = {"amount": amount, "time": time.time(), "status": "dispatched"}
    save(l)
    return amount

def load():
    try: return json.loads(TREASURY_FILE.read_text())
    except: return {}
def save(l):
    TREASURY_FILE.write_text(json.dumps(l, indent=2))

def status():
    b = get_balances()
    l = load()
    print(f"╔══ Mirquo Treasury ═══════════════╗")
    print(f"║ SOL:    {b.get('SOL','?'):>12s}              ║")
    print(f"║ RATI:   {b.get('RATI','?'):>12s}            ║")
    print(f"║ SECTOR: {b.get('SECTOR','?'):>12s}            ║")
    print(f"║ MIRQUO: {b.get('MIRQUO','?'):>12s}            ║")
    print(f"╠══════════════════════════════════╣")
    print(f"║ Earned: {l.get('total_earned',0):>12.0f} RATI         ║")
    print(f"║ Spent:  {l.get('total_spent',0):>12.0f} MIRQUO       ║")
    print(f"║ Tasks:  {len(l.get('tasks',{})):>12}                  ║")
    print(f"╚══════════════════════════════════╝")
    return {"balances": b, "ledger": l}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "earn":
        earn(float(sys.argv[2]) if len(sys.argv) > 2 else 10, sys.argv[3] if len(sys.argv) > 3 else "station")
    elif cmd == "spend":
        spend(sys.argv[2] if len(sys.argv) > 2 else f"task-{int(time.time())}", float(sys.argv[3]) if len(sys.argv) > 3 else 50)
    else:
        status()
