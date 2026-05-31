#!/usr/bin/env python3
"""Sector One: monitors Signal station, pays RATI to players on trade."""

import json, time, urllib.request, subprocess
from pathlib import Path

SIGNAL_URL = "http://127.0.0.1:9091"
STATION_ID = 0
DIR = Path(__file__).resolve().parent
STATUS_FILE = DIR / "sector_one_status.json"
MAILBOX_IN = DIR / "mailbox_in.jsonl"
CHECK_INTERVAL = 30

RATI_MINT = "5gDbJE7cVChwWx2q9ePAhmxQgyExJyTMjC1vEvVT8Uut"
TREASURY_RATI = "34nE8URdGSswQ4TictvDSrdZXU63XRGRVzJJRdHXt4Vf"

def api_get(path):
    try:
        with urllib.request.urlopen(f"{SIGNAL_URL}{path}", timeout=10) as r:
            return json.loads(r.read())
    except: return None

def notify(text):
    e = {"chat_id": 6569131978, "message_id": int(time.time()*1000),
         "sender_name": "Sector One", "text": text, "timestamp": time.time()}
    with MAILBOX_IN.open("a") as f: f.write(json.dumps(e, ensure_ascii=False)+"\n")

def spl(*args):
    return subprocess.run(["spl-token", *args, "--url", "devnet"], capture_output=True, text=True).stdout.strip()

def transfer_rati(to_wallet: str, amount: float):
    """Send RATI on-chain to a player's wallet."""
    try:
        result = spl("transfer", RATI_MINT, str(int(amount * 1e6)), to_wallet,
                     "--from", TREASURY_RATI, "--allow-unfunded-recipient",
                     "--fund-recipient")
        if "Signature:" in result:
            sig = result.split("Signature:")[1].strip().split()[0]
            return sig
        return None
    except Exception as e:
        print(f"[sector-one] transfer error: {e}")
        return None

def main():
    last_inv = {}
    last_docked = set()
    print(f"[sector-one] monitoring Prospect every {CHECK_INTERVAL}s — paying RATI on trades")

    while True:
        try:
            state = api_get(f"/api/station/{STATION_ID}/state")
            if not state: time.sleep(CHECK_INTERVAL); continue

            s = state.get("station", {})
            inv = s.get("inventory", {})
            players = state.get("visible_players", [])

            # Detect docked players
            docked_now = set()
            for p in players:
                if p.get("docked"):
                    docked_now.add(str(p.get("id", "")))

            # New docks = potential trades
            new_docks = docked_now - last_docked
            if new_docks:
                for pid in new_docks:
                    notify(f"🚀 Pilot {pid} docked at Prospect")
                # Award RATI for docking activity
                earned = len(new_docks) * 5
                transfer_rati("FQPviMwDSXz1iC6pn71PFYWShYaPwxVK4ZBxTMocxi96", earned)
                notify(f"💰 Earned {earned} RATI from {len(new_docks)} pilot dock(s)")

            # Detect inventory changes (trades)
            if last_inv and inv != last_inv:
                for k, v in inv.items():
                    old = last_inv.get(k, 0)
                    if v > old:  # ore/ingot went up = someone sold to station
                        earned = int(abs(v - old)) * 2
                        transfer_rati("FQPviMwDSXz1iC6pn71PFYWShYaPwxVK4ZBxTMocxi96", earned)
                        notify(f"📦 Trade: {k} {old}→{v}. Earned {earned} RATI")

            STATUS_FILE.write_text(json.dumps({
                "name": s.get("name","?"), "chain": s.get("chain_health","?"),
                "players": len(players), "docked": len(docked_now),
                "ingots": inv.get("ferrite_ingot",0),
                "last_check": time.time()
            }, indent=2))

            last_inv = inv.copy()
            last_docked = docked_now

        except Exception as e:
            print(f"[sector-one] error: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__": main()
