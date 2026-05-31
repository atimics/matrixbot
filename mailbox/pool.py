#!/usr/bin/env python3
"""Minimal constant-product AMM pool for SECTOR/SOL on devnet.

Uses the existing SPL Token program for transfers.
Pool state: a JSON file tracking reserves, fees, and swaps.
Swap math: x * y = k, 0.3% fee.
"""

import json
import subprocess
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent
POOL_FILE = DIR / "pool_state.json"

# Token addresses
SECTOR_MINT = "4Cry7D6MrrJo5GBXqfZedJRk5Zgp58zAr8jYpHkqrzDU"
SECTOR_ACCOUNT = "4jfYBmvYPmWDd5HyX1GfK9ba2yU4jpKpiGzYhxVnQXEE"
FEE_ACCOUNT = SECTOR_ACCOUNT  # For simplicity, fees go back to treasury

FEE_BPS = 30  # 0.3%
SOL_DECIMALS = 9
SECTOR_DECIMALS = 6

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def load_state():
    try:
        return json.loads(POOL_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"reserve_sector": 100000, "reserve_sol": 10.0,
                "total_fees_sector": 0, "total_swaps": 0}

def save_state(s):
    POOL_FILE.write_text(json.dumps(s, indent=2))

def get_amount_out(amount_in, reserve_in, reserve_out):
    """Constant product: dy = y * dx / (x + dx), with fee."""
    amount_in_with_fee = amount_in * (10000 - FEE_BPS) / 10000
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee
    return numerator / denominator

def swap_sector_for_sol(amount_sector):
    s = load_state()
    sol_out = get_amount_out(amount_sector, s["reserve_sector"], s["reserve_sol"])
    fee = amount_sector * FEE_BPS / 10000

    s["reserve_sector"] += amount_sector
    s["reserve_sol"] -= sol_out
    s["total_fees_sector"] += fee
    s["total_swaps"] += 1
    s["last_swap"] = time.time()
    save_state(s)

    print(f"🔁 Swapped {amount_sector} SECTOR → {sol_out:.9f} SOL (fee: {fee} SECTOR)")
    print(f"   Pool: {s['reserve_sector']:.0f} SECTOR | {s['reserve_sol']:.9f} SOL")
    return sol_out

def swap_sol_for_sector(amount_sol):
    s = load_state()
    sector_out = get_amount_out(amount_sol, s["reserve_sol"], s["reserve_sector"])
    fee = amount_sol * FEE_BPS / 10000

    s["reserve_sol"] += amount_sol
    s["reserve_sector"] -= sector_out
    s["total_fees_sector"] += fee
    s["total_swaps"] += 1
    s["last_swap"] = time.time()
    save_state(s)

    print(f"🔁 Swapped {amount_sol:.9f} SOL → {sector_out:.0f} SECTOR (fee: {fee:.9f} SOL)")
    print(f"   Pool: {s['reserve_sector']:.0f} SECTOR | {s['reserve_sol']:.9f} SOL")
    return sector_out

def price():
    s = load_state()
    if s["reserve_sector"] == 0:
        return 0
    return s["reserve_sol"] / s["reserve_sector"]

def status():
    s = load_state()
    p = price()
    print(f"=== Sector Pool ===")
    print(f"SECTOR: {s['reserve_sector']:,.0f}  SOL: {s['reserve_sol']:,.9f}")
    print(f"Price:  {p:.9f} SOL/SECTOR  ({1/p:,.0f} SECTOR/SOL)")
    print(f"Fees:   {s['total_fees_sector']:,.0f} SECTOR  |  Swaps: {s['total_swaps']}")
    if s.get('last_swap'):
        print(f"Last:   {time.ctime(s['last_swap'])}")
    return s

def simulate_activity(cycles=3):
    """Simulate trading activity to generate fees."""
    for i in range(cycles):
        print(f"\n--- Cycle {i+1} ---")
        # Random-ish trade sizes
        swap_sector_for_sol(50 + i * 10)
        time.sleep(0.5)
        swap_sol_for_sector(0.005 + i * 0.001)
    print(f"\n=== Final State ===")
    status()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "swap_sector" and len(sys.argv) > 2:
            swap_sector_for_sol(float(sys.argv[2]))
        elif cmd == "swap_sol" and len(sys.argv) > 2:
            swap_sol_for_sector(float(sys.argv[2]))
        elif cmd == "simulate":
            cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            simulate_activity(cycles)
        elif cmd == "status":
            status()
        elif cmd == "price":
            print(f"{price():.9f} SOL/SECTOR")
        else:
            print("Usage: pool.py [status|price|swap_sector <amt>|swap_sol <amt>|simulate [n]]")
    else:
        status()
