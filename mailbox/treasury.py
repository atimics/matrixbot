#!/usr/bin/env python3
"""Economic treasury for the Mirquo swarm on Solana devnet."""

import json
import subprocess
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent
TREASURY_FILE = DIR / "treasury.json"

# Devnet token addresses
TOKENS = {
    "SECTOR": "4Cry7D6MrrJo5GBXqfZedJRk5Zgp58zAr8jYpHkqrzDU",
    "MIRQUO": "2wGfLVa6N7cFuchYdVTPxSbYNm4H1mXyK7QWZwEaaBj9",
}

# Token accounts (ATA addresses)
ACCOUNTS = {
    "SECTOR": "4jfYBmvYPmWDd5HyX1GfK9ba2yU4jpKpiGzYhxVnQXEE",
    "MIRQUO": "C6WQk3KzoymV13o1p2goK59Q9Dj1iz1iL9dKJxYBqbj7",
}

def solana(*args):
    result = subprocess.run(["solana", *args], capture_output=True, text=True)
    return result.stdout.strip()

def spl_token(*args):
    result = subprocess.run(["spl-token", *args], capture_output=True, text=True)
    return result.stdout.strip()

def get_balances():
    """Get on-chain balances for all treasury tokens."""
    balances = {}
    for name, mint in TOKENS.items():
        try:
            output = spl_token("balance", mint)
            balances[name] = output.strip()
        except Exception:
            balances[name] = "unknown"
    balances["SOL"] = solana("balance").split()[0] if solana("balance") else "0"
    balances["updated"] = time.time()
    return balances

def pay_station_earnings(amount: float = 10.0):
    """Simulate station earnings — in production, this comes from Signal."""
    # For now we track earnings in a local ledger since we're the only holder
    ledger = load_ledger()
    ledger["station_earnings"] = ledger.get("station_earnings", 0) + amount
    ledger["total_sector_earned"] = ledger.get("total_sector_earned", 0) + amount
    save_ledger(ledger)
    return amount

def spend_on_worker(task_id: str, amount: float = 50.0):
    """Record spending on a worker task."""
    ledger = load_ledger()
    ledger["worker_spending"] = ledger.get("worker_spending", 0) + amount
    ledger.setdefault("tasks", {})[task_id] = {
        "amount": amount,
        "time": time.time(),
        "status": "dispatched",
    }
    save_ledger(ledger)
    return amount

def load_ledger():
    try:
        return json.loads(TREASURY_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_ledger(ledger):
    TREASURY_FILE.write_text(json.dumps(ledger, indent=2))

def status():
    """Print treasury status."""
    balances = get_balances()
    ledger = load_ledger()
    print(f"=== Mirquo Treasury ===")
    print(f"SOL:        {balances.get('SOL', '?')}")
    print(f"SECTOR:     {balances.get('SECTOR', '?')}  (station earnings)")
    print(f"MIRQUO:     {balances.get('MIRQUO', '?')}  (commander treasury)")
    print(f"")
    print(f"Earned:     {ledger.get('total_sector_earned', 0):.0f} SECTOR")
    print(f"Spent:      {ledger.get('worker_spending', 0):.0f} MIRQUO")
    print(f"Tasks:      {len(ledger.get('tasks', {}))} dispatched")
    return {"balances": balances, "ledger": ledger}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "earn":
        amount = float(sys.argv[2]) if len(sys.argv) > 2 else 10
        earned = pay_station_earnings(amount)
        print(f"Station earned {earned} SECTOR")
    elif len(sys.argv) > 1 and sys.argv[1] == "spend":
        task_id = sys.argv[2] if len(sys.argv) > 2 else f"task-{int(time.time())}"
        amount = float(sys.argv[3]) if len(sys.argv) > 3 else 50
        spent = spend_on_worker(task_id, amount)
        print(f"Dispatched {task_id} for {spent} MIRQUO")
    else:
        status()
