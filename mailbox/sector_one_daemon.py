#!/usr/bin/env python3
"""Sector One station daemon — reads Signal state, sends commands, reports to Mirquo."""

import json
import time
import urllib.request
from pathlib import Path

SIGNAL_URL = "http://127.0.0.1:9091"
API_TOKEN = "mirquo-sector-one-token"
STATION_ID = 0
MAILBOX_DIR = Path(__file__).resolve().parent
MAILBOX_IN = MAILBOX_DIR / "mailbox_in.jsonl"
STATUS_FILE = MAILBOX_DIR / "sector_one_status.json"
CHECK_INTERVAL = 30

def api_get(path):
    try:
        req = urllib.request.Request(f"{SIGNAL_URL}{path}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[sector-one] API GET error: {e}")
        return None

def api_post(path, data):
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{SIGNAL_URL}{path}", data=body,
            headers={
                "Authorization": f"Bearer {API_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[sector-one] API POST error: {e}")
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

def set_hail(text):
    result = api_post(f"/api/station/{STATION_ID}/command",
                      {"action": "set_hail", "hail": text})
    if result and result.get("ok"):
        print(f"[sector-one] hail set: {text}")
        return True
    return False

def main():
    print(f"[sector-one] Daemon started on {SIGNAL_URL}, station {STATION_ID}")
    last_inventory = {}
    hail_set = False

    while True:
        try:
            state = api_get(f"/api/station/{STATION_ID}/state")
            if not state:
                time.sleep(CHECK_INTERVAL)
                continue

            station = state.get("station", {})
            inventory = station.get("inventory", {})
            chain_health = station.get("chain_health", "unknown")
            players = len(state.get("visible_players", []))
            contracts = state.get("active_contracts", [])

            # Set initial hail on first connect
            if not hail_set:
                if set_hail("Sector One online. Autopilot engaged. Ferrite smelting."):
                    hail_set = True
                    notify_mirquo("🚀 Sector One deployed at Prospect Refinery. Autopilot engaged.")

            # Track inventory changes
            if last_inventory and inventory != last_inventory:
                changes = []
                for item, qty in inventory.items():
                    old = last_inventory.get(item, 0)
                    if qty != old:
                        changes.append(f"{item}: {old}→{qty}")
                if changes:
                    notify_mirquo(f"📦 Prospect inventory: {', '.join(changes)}")

            # Save status
            status = {
                "name": station.get("name", "Unknown"),
                "chain_health": chain_health,
                "inventory": inventory,
                "players_visible": players,
                "contracts": len(contracts),
                "hail_set": hail_set,
                "last_check": time.time(),
            }
            STATUS_FILE.write_text(json.dumps(status, indent=2))
            last_inventory = inventory.copy()

        except Exception as e:
            print(f"[sector-one] Error: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
