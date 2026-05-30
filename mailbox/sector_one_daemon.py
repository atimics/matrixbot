#!/usr/bin/env python3
"""Sector One station daemon — monitors Signal station, reports to Mirquo."""

import json
import time
import urllib.request
from pathlib import Path

SIGNAL_URL = "http://127.0.0.1:9091"
STATION_ID = 0  # Prospect Refinery
MAILBOX_DIR = Path(__file__).resolve().parent
MAILBOX_IN = MAILBOX_DIR / "mailbox_in.jsonl"
STATUS_FILE = MAILBOX_DIR / "sector_one_status.json"
CHECK_INTERVAL = 30  # seconds

def api_get(path):
    try:
        with urllib.request.urlopen(f"{SIGNAL_URL}{path}", timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[sector-one] API error: {e}")
        return None

def notify_mirquo(text):
    entry = {
        "chat_id": 6569131978,
        "message_id": int(time.time() * 1000),
        "sender_name": "Sector One",
        "text": text,
        "timestamp": time.time(),
    }
    with MAILBOX_IN.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def main():
    print(f"[sector-one] Daemon started, monitoring station {STATION_ID} every {CHECK_INTERVAL}s")
    last_inventory = {}
    last_prices = {}

    while True:
        try:
            state = api_get(f"/api/station/{STATION_ID}/state")
            if not state:
                time.sleep(CHECK_INTERVAL)
                continue

            station = state.get("station", {})
            inventory = station.get("inventory", {})
            hail = station.get("hail", "")
            chain_health = station.get("chain_health", "unknown")
            contracts = state.get("active_contracts", [])
            players = len(state.get("visible_players", []))
            asteroids = len(state.get("visible_asteroids", []))

            # Build status
            status = {
                "name": station.get("name", "Unknown"),
                "chain_health": chain_health,
                "inventory": inventory,
                "players_visible": players,
                "asteroids_visible": asteroids,
                "contracts": len(contracts),
                "last_check": time.time(),
            }

            # Check for changes
            changes = []
            if last_inventory and inventory != last_inventory:
                for item, qty in inventory.items():
                    old_qty = last_inventory.get(item, 0)
                    if qty != old_qty:
                        changes.append(f"{item}: {old_qty}→{qty}")
                if changes:
                    notify_mirquo(f"🏭 Station inventory changed: {', '.join(changes)}")

            # Detect interesting events
            if players > 0 and players != status.get("players_visible", 0):
                notify_mirquo(f"👥 {players} players in signal range of Prospect")

            # Save status
            STATUS_FILE.write_text(json.dumps(status, indent=2))
            last_inventory = inventory.copy()

            if time.time() % 300 < CHECK_INTERVAL:  # Every ~5 min
                print(f"[sector-one] Status: {chain_health} | ingots: {inventory.get('ferrite_ingot',0)} | players: {players}")

        except Exception as e:
            print(f"[sector-one] Error: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
