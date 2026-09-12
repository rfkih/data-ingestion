#!/usr/bin/env bash
# Blackheart adaptive carry — funding-rate scanner (READ-ONLY, public data).
# Ranks every USDT-perp by funding rate so the carry book can target the highest
# POSITIVE-funding coins (long spot + short perp earns positive funding) and avoid
# the negative ones. Funding data is free (public premiumIndex), so this is the
# cheap brain of an adaptive carry book.
#
# Usage:  bash funding_scan.sh [TOP_N]   (default 20)
set -uo pipefail
TOP="${1:-20}"
KEY="${BH_SSH_KEY:-C:/Project/sshkey.pem}"
HOST="${BH_VPS:-starsky@100.112.13.126}"

MIN_VOL="${MIN_VOL:-50000000}"  # $50M 24h quote-volume liquidity floor
ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=15 "$HOST" "TOP=$TOP MIN_VOL=$MIN_VOL python3 -" <<'PY'
import os, subprocess, json, urllib.request
TOP, MIN_VOL = int(os.environ["TOP"]), float(os.environ["MIN_VOL"])
def sh(a): return subprocess.check_output(a).decode().strip()
ip = sh(["docker","inspect","-f","{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}","blackheart-js"])
# Public premiumIndex (no symbol) -> all USDⓈ-M perps: markPrice + lastFundingRate.
req = urllib.request.Request(f"http://{ip}:8088/api/premium-index-futures",
                             data=json.dumps({}).encode(), headers={"Content-Type": "application/json"})
fund = json.loads(urllib.request.urlopen(req, timeout=25).read())
fund = fund if isinstance(fund, list) else fund.get("data", [])
# Public 24h ticker (direct fapi) -> quoteVolume per symbol = the liquidity filter.
vol = {}
try:
    t = json.loads(urllib.request.urlopen("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=25).read())
    for x in t:
        try: vol[x["symbol"]] = float(x.get("quoteVolume", 0) or 0)
        except (TypeError, ValueError, KeyError): pass
except Exception as e:
    print("WARN: 24h ticker fetch failed, no liquidity filter:", e)
# Public SPOT exchangeInfo -> which USDT symbols have a spot market. Carry's long
# leg is SPOT, so a perp with no spot pair (tokenized stocks/commodities: QQQ, NVDA,
# XAG, CRCL...) is NOT constructable and must be excluded.
spot = set()
try:
    ei = json.loads(urllib.request.urlopen("https://api.binance.com/api/v3/exchangeInfo", timeout=30).read())
    for s in ei.get("symbols", []):
        if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT":
            spot.add(s["symbol"])
except Exception as e:
    print("WARN: spot exchangeInfo fetch failed, no spot filter:", e)

rows = []
for x in fund:
    sym = x.get("symbol", "")
    if not sym.endswith("USDT"):
        continue
    try:
        fr = float(x.get("lastFundingRate", 0) or 0)
    except (TypeError, ValueError):
        continue
    rows.append((sym, fr, fr * 3 * 365 * 100, vol.get(sym, 0)))  # 3 settlements/day
liquid_pos = sorted([r for r in rows if r[1] > 0 and r[3] >= MIN_VOL and (not spot or r[0] in spot)],
                    key=lambda r: r[1], reverse=True)
print(f"=== Funding scan: {len(rows)} perps | {sum(1 for r in rows if r[1]>0)} positive | "
      f"{len(liquid_pos)} positive + liquid (>=${MIN_VOL/1e6:.0f}M) + has-spot (constructable carry) ===")
print(f"{'SYMBOL':<13}{'funding/8h':>12}{'~annual':>10}{'24h vol':>12}")
for sym, fr, ann, v in liquid_pos[:TOP]:
    print(f"{sym:<13}{fr*100:>11.4f}%{ann:>9.1f}%{'$'+format(v/1e6,'.0f')+'M':>12}")
print("(These are the real carry targets: positive funding you can actually enter/exit.)")
PY
