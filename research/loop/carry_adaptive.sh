#!/usr/bin/env bash
# Blackheart adaptive carry — allocation planner (DRY_RUN by default).
# Joins the funding scan (positive + liquid + has-spot) with the live wallet and
# open carry pairs, then recommends the optimal carry book: which high-funding
# coins to hold, and which low/negative-funding pairs to rotate out of. The carry
# edge IS funding harvesting, so chasing the highest sustainable positive funding
# across a diversified set is exactly the right objective.
#
# DRY_RUN only — prints the plan, never trades. (Arming would execute via the
# already-built open/close + carry_rebalance transfer primitives.)
#
# Usage:  bash carry_adaptive.sh [MAX_PAIRS_CAP]   (cap on book breadth, default 8)
set -uo pipefail
CAP="${1:-8}"
KEY="${BH_SSH_KEY:-C:/Project/sshkey.pem}"
HOST="${BH_VPS:-starsky@100.112.13.126}"
ACCT="${BH_ACCOUNT_ID:-76fac4b6-ea6b-44cc-a9ec-382ac3c2f4a2}"

ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 "$HOST" "CAP=$CAP ACCT=$ACCT python3 -" <<'PY'
import os, subprocess, json, urllib.request, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
CAP, ACCT = int(os.environ["CAP"]), os.environ["ACCT"]
MIN_NOTIONAL = 20.0          # Binance futures floor
LEV = 2.0                    # carry leverage cap
MIN_VOL = 50_000_000         # liquidity floor
CAPITAL_PER_PAIR = (MIN_NOTIONAL * 1.10) * (1 + 1 / LEV)  # spot notional + perp margin, with buffer

def sh(a): return subprocess.check_output(a).decode().strip()
def psql(q): return sh(["docker","exec","blackheart-postgres","psql","-U","postgres","-d","trading_db","-t","-A","-c",q]).strip()
ip = sh(["docker","inspect","-f","{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}","blackheart-js"])

def gw(path, body):
    r = urllib.request.Request(f"http://{ip}:8088{path}", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=25).read())

# --- 1. funding scan: positive + liquid + has-spot ---
fund = gw("/api/premium-index-futures", {})
fund = fund if isinstance(fund, list) else fund.get("data", [])
vol = {}
try:
    for x in json.loads(urllib.request.urlopen("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=25).read()):
        try: vol[x["symbol"]] = float(x.get("quoteVolume", 0) or 0)
        except Exception: pass
except Exception: pass
spot = set()
try:
    for s in json.loads(urllib.request.urlopen("https://api.binance.com/api/v3/exchangeInfo", timeout=30).read()).get("symbols", []):
        if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT":
            spot.add(s["symbol"])
except Exception: pass
cands = []
for x in fund:
    s = x.get("symbol", "")
    try: fr = float(x.get("lastFundingRate", 0) or 0)
    except Exception: continue
    if s.endswith("USDT") and fr > 0 and vol.get(s, 0) >= MIN_VOL and (not spot or s in spot):
        cands.append((s, fr))
cands.sort(key=lambda r: r[1], reverse=True)
# Rank on SUSTAINED funding (last 12 settlements ~4d), not a single print: a snapshot can
# be a squeeze spike (BICO printed +11% once but averages -50%/yr). Carry needs funding that
# is positive ON AVERAGE and rarely flips negative — that's a real edge, not a momentary one.
def hist(s):
    try:
        h = json.loads(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={s}&limit=24", timeout=12).read())
        ann = [float(x["fundingRate"]) * 3 * 365 * 100 for x in h]
        return (sum(ann) / len(ann), min(ann), sum(1 for a in ann if a > 0), len(ann)) if ann else None
    except Exception:
        return None
ranked = []
for s, _ in cands[:25]:  # bound the history calls to the 25 highest-snapshot candidates
    h = hist(s)
    if not h:
        continue
    avg, mn, pos, n = h
    # Robust over ~8 days: meaningfully positive on average, rarely negative, no deep dips.
    # (A recent streak isn't enough — PUMP printed +11% once but is 0.3%/-16% over 8 days.)
    if avg > 4 and pos >= int(n * 0.8) and mn > -10:
        ranked.append((s, None, avg))
ranked.sort(key=lambda r: r[2], reverse=True)  # by sustained avg funding (%/yr)
fundpct = {s: a for s, _, a in ranked}

# --- 2. capital + open pairs ---
key = base64.b64decode(sh(["docker","exec","blackheart-app","printenv","DB_ENCRYPTION_KEY"]))
row = psql(f"select api_key||chr(124)||api_secret from accounts where account_id='{ACCT}';")
ek, es = row.split("|")
dec = lambda v: AESGCM(key).decrypt(base64.b64decode(v[7:])[:12], base64.b64decode(v[7:])[12:], None).decode() if v.startswith("enc:v1:") else v
ak, sk = dec(ek), dec(es)
fa = gw("/api/account-futures", {"apiKey": ak, "apiSecret": sk})
fut_avail = float(fa.get("availableBalance", 0) or 0)
import urllib.parse, hmac, hashlib
st = json.loads(urllib.request.urlopen("https://api.binance.com/api/v3/time", timeout=15).read())["serverTime"]
q = urllib.parse.urlencode({"recvWindow": "5000", "timestamp": str(st)})
sig = hmac.new(sk.encode(), q.encode(), hashlib.sha256).hexdigest()
acct = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"https://api.binance.com/api/v3/account?{q}&signature={sig}", headers={"X-MBX-APIKEY": ak}), timeout=20).read())
spot_usdt = next((float(b["free"]) for b in acct.get("balances", []) if b["asset"] == "USDT"), 0.0)
open_rows = psql(f"select symbol from carry_pair where account_id='{ACCT}' and status in ('OPEN','OPENING','PENDING','REBALANCING','CLOSING');")
open_syms = [s for s in open_rows.splitlines() if s.strip()]

free_capital = spot_usdt + fut_avail
# capital recoverable if we rotate out of open pairs ≈ MIN per pair (conservative)
total_usable = free_capital + len(open_syms) * CAPITAL_PER_PAIR
capacity = min(CAP, int(total_usable // CAPITAL_PER_PAIR))

# Hedge-precision filter: at the planned pair size, drop coins whose perp LOT_SIZE
# step is too coarse to match the spot leg. AAVE's 0.1 lot (~$7.5) wrecks a $22 hedge
# -> 33% net delta = a directional bet, not carry. Clean carry needs stepSize*mark to
# be a small fraction of the pair notional. This scales: big pairs make more coins
# hedge-able, which is exactly why carry wants more capital.
pair_notional = (total_usable / max(capacity, 1)) / (1 + 1 / LEV) if capacity else MIN_NOTIONAL * 1.1
marks = {}
for x in fund:
    try: marks[x["symbol"]] = float(x.get("markPrice", 0) or 0)
    except Exception: pass
steps = {}
try:
    ei = gw("/api/exchange-info-futures", {})
    syms = ei.get("symbols", []) if isinstance(ei, dict) else ei
    for sd in syms:
        for f in sd.get("filters", []):
            if f.get("filterType") == "LOT_SIZE":
                try: steps[sd["symbol"]] = float(f["stepSize"])
                except Exception: pass
except Exception: pass
def hedgeable(sym):
    st, mk = steps.get(sym, 0), marks.get(sym, 0)
    return st > 0 and mk > 0 and (st * mk) / pair_notional <= 0.08
dropped = [s for s, _, _ in ranked if not hedgeable(s)]
ranked = [r for r in ranked if hedgeable(r[0])]
fundpct = {s: a for s, _, a in ranked}
if dropped:
    print(f"(dropped — perp lot too coarse to hedge at ~${pair_notional:.0f}/pair: {', '.join(d.replace('USDT','') for d in dropped)})")
target = [s for s, _, _ in ranked[:capacity]]

print("=== ADAPTIVE CARRY PLAN (DRY_RUN) ===")
print(f"Capital: spot ${spot_usdt:.2f} + futures ${fut_avail:.2f} free  | per-pair need ~${CAPITAL_PER_PAIR:.0f} @ {LEV:.0f}x")
print(f"Book capacity at this capital: ~{capacity} pair(s)  (book-breadth cap = {CAP})")
print(f"Open now: {', '.join(f'{s} ({fundpct.get(s,0):.1f}%/yr)' for s in open_syms) or '(none)'}")
print("Funding leaders (liquid + spot):", ", ".join(f"{s.replace('USDT','')} {a:.1f}%" for s, _, a in ranked[:8]))
print("--- plan ---")
closes = [s for s in open_syms if s not in target]
opens = [s for s in target if s not in open_syms]
for s in closes:
    why = "funding no longer top-rank" if fundpct.get(s, 0) > 0 else "funding NEGATIVE"
    print(f"  CLOSE {s}  ({fundpct.get(s,0):.1f}%/yr) — {why}")
for s in opens:
    print(f"  OPEN  {s}  ({fundpct.get(s,0):.1f}%/yr) — top funding; would create FCARRY row + size ~${MIN_NOTIONAL*1.1:.0f} @ {LEV:.0f}x")
if not closes and not opens:
    print("  HOLD — current book already matches the funding leaders within capacity.")
held = [s for s in open_syms if s in target]
new_book = held + opens
if new_book:
    avg = sum(fundpct.get(s, 0) for s in new_book) / len(new_book)
    print(f"Resulting book: {', '.join(s.replace('USDT','') for s in new_book)}  | avg funding ~{avg:.1f}%/yr")
print("(ARMED=false — recommendation only. Execution uses the existing open/close + carry_rebalance primitives.)")
PY
