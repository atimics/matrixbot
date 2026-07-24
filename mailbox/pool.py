#!/usr/bin/env python3
"""Constant-product AMM pool for SECTOR/SOL on devnet.
Zero dependencies — uses solana + spl-token CLIs for transfers.
x*y=k math, 0.3% fee, on-chain token accounts as vaults.
"""

import subprocess, json, time
from pathlib import Path

DIR = Path(__file__).resolve().parent
STATE_FILE = DIR / "pool_state.json"

SECTOR_MINT  = "4Cry7D6MrrJo5GBXqfZedJRk5Zgp58zAr8jYpHkqrzDU"
SOL_MINT     = "So11111111111111111111111111111111111111112"
FEE_BPS      = 30
SOL_DECIMALS = 9
SECTOR_DECIMALS = 6

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def load():
    try: return json.loads(STATE_FILE.read_text())
    except: return {"vault_sector": None, "vault_sol": None, "fee_vault": None,
                    "reserve_sector": 0, "reserve_sol": 0.0, "fees": 0.0, "swaps": 0}

def save(s): STATE_FILE.write_text(json.dumps(s, indent=2))

def get_balance(account):
    """Get on-chain token balance via CLI."""
    if not account: return 0
    out = run(f"spl-token balance {account} 2>/dev/null")
    try: return float(out)
    except: return 0

def setup():
    """Create vault token accounts for the pool."""
    s = load()
    if not s["vault_sector"]:
        s["vault_sector"] = run(f"spl-token create-account {SECTOR_MINT} 2>/dev/null | grep Creating | awk '{{print $3}}'") or "pool_sector"
    if not s["vault_sol"]:
        r = run(f"spl-token create-account {SOL_MINT} 2>/dev/null")
    if not s["fee_vault"]:
        s["fee_vault"] = run(f"spl-token create-account {SECTOR_MINT} 2>/dev/null | grep Creating | awk '{{print $3}}'") or "pool_fees"
    save(s)
    return s

def swap(amount_in: float, from_token: str, to_token: str, from_vault: str, to_vault: str,
         decimals_in: int, decimals_out: int, user_account: str):
    """Constant-product swap: dy = y * dx_fee / (x + dx_fee)."""
    s = load()
    reserve_in  = get_balance(from_vault) if from_vault else s.get("reserve_sector", 0)
    reserve_out = get_balance(to_vault) if to_vault else s.get("reserve_sol", 0)
    
    if reserve_in == 0 or reserve_out == 0:
        print("Pool empty — add liquidity first")
        return 0

    amount_in_scaled = amount_in * (10 ** decimals_in)
    amount_in_fee = amount_in_scaled * (10000 - FEE_BPS) // 10000
    reserve_in_scaled = int(reserve_in * (10 ** decimals_in))
    reserve_out_scaled = int(reserve_out * (10 ** decimals_out))
    
    amount_out_scaled = (amount_in_fee * reserve_out_scaled) // (reserve_in_scaled + amount_in_fee)
    amount_out = amount_out_scaled / (10 ** decimals_out)
    fee = amount_in * FEE_BPS / 10000

    print(f"  swap: {amount_in} {from_token} → {amount_out:.6f} {to_token}  (fee: {fee:.6f})")
    s["fees"] = s.get("fees", 0) + fee
    s["swaps"] = s.get("swaps", 0) + 1
    s["reserve_sector"] = reserve_in + amount_in if from_token == "SECTOR" else reserve_in - amount_out
    s["reserve_sol"] = reserve_out + amount_in if from_token == "SOL" else reserve_out - amount_out
    s["last_swap"] = time.time()
    save(s)
    return amount_out

def status():
    s = load()
    p = s["reserve_sol"] / s["reserve_sector"] if s["reserve_sector"] else 0
    print(f"╔══ Sector Pool ═══════════════════╗")
    print(f"║ SECTOR: {s['reserve_sector']:>12,.0f}                  ║")
    print(f"║ SOL:    {s['reserve_sol']:>12.9f}            ║")
    print(f"║ Price:  {p:>12.9f} SOL/SECTOR  ║")
    print(f"║ Fees:   {s['fees']:>12.3f}              ║")
    print(f"║ Swaps:  {s['swaps']:>12}                  ║")
    print(f"╚══════════════════════════════════╝")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        status()
    elif sys.argv[1] == "status":
        status()
    elif sys.argv[1] == "simulate":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        s = load()
        s["reserve_sector"] = 100000
        s["reserve_sol"] = 10.0
        save(s)
        for i in range(n):
            swap(50 + i*10, "SECTOR", "SOL", None, None, SECTOR_DECIMALS, SOL_DECIMALS, "")
            swap(0.005 + i*0.001, "SOL", "SECTOR", None, None, SOL_DECIMALS, SECTOR_DECIMALS, "")
        status()
