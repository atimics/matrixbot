#!/usr/bin/env python3
"""Ship-to-wallet registry: bind Signal ship pubkeys to Solana wallets."""

import json
from pathlib import Path

DIR = Path(__file__).resolve().parent
REGISTRY = DIR / "ship_registry.json"

def load():
    try: return json.loads(REGISTRY.read_text())
    except: return {"bindings": {}}

def save(d): REGISTRY.write_text(json.dumps(d, indent=2))

def bind(ship_pubkey: str, wallet_address: str, player_name: str = ""):
    d = load()
    d["bindings"][ship_pubkey] = {
        "wallet": wallet_address,
        "name": player_name,
        "bound_at": __import__('time').time()
    }
    save(d)
    print(f"✅ Ship {ship_pubkey[:12]}... → wallet {wallet_address[:12]}...")

def lookup(ship_pubkey: str) -> str | None:
    d = load()
    binding = d["bindings"].get(ship_pubkey)
    return binding["wallet"] if binding else None

def list_all():
    d = load()
    for pk, b in d["bindings"].items():
        print(f"  {pk[:16]}... → {b['wallet'][:16]}... ({b.get('name','?')})")

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "bind" and len(sys.argv) >= 4:
        bind(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "lookup" and len(sys.argv) > 2:
        w = lookup(sys.argv[2])
        print(w or "not found")
    elif cmd == "list":
        list_all()
