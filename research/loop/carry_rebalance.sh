#!/usr/bin/env bash
# Blackheart self-improvement loop — spot<->futures wallet auto-balancer (#9).
# Binance keeps SPOT and FUTURES wallets separate; a carry pair needs spot USDT
# for the long leg and futures USDT for the perp margin. This ensures the futures
# wallet holds at least a target amount, moving USDT from spot when short (and
# optionally sweeping idle futures cash back to spot). Universal transfer is
# already proven working (Permits-Universal-Transfer is enabled on the key).
#
# Usage:
#   bash carry_rebalance.sh                 # report-only: print the split
#   bash carry_rebalance.sh --ensure-futures 30   # top up futures wallet to >= $30 from spot
#   bash carry_rebalance.sh --sweep-idle 10       # if futures FREE > $10 above need, sweep excess to spot
set -uo pipefail
KEY="${BH_SSH_KEY:-C:/Project/sshkey.pem}"
HOST="${BH_VPS:-starsky@100.112.13.126}"
ACCT="${BH_ACCOUNT_ID:-76fac4b6-ea6b-44cc-a9ec-382ac3c2f4a2}"
MODE="report"; TARGET=0
case "${1:-}" in
  --ensure-futures) MODE="ensure"; TARGET="${2:-0}";;
  --sweep-idle)     MODE="sweep";  TARGET="${2:-0}";;
esac

ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 "$HOST" "MODE=$MODE TARGET=$TARGET ACCT=$ACCT python3 -" <<'PY'
import os, base64, subprocess, json, urllib.request, urllib.parse, hmac, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MODE, TARGET, ACCT = os.environ["MODE"], float(os.environ["TARGET"]), os.environ["ACCT"]

def sh(a): return subprocess.check_output(a).decode().strip()
key = base64.b64decode(sh(["docker","exec","blackheart-app","printenv","DB_ENCRYPTION_KEY"]))
row = sh(["docker","exec","blackheart-postgres","psql","-U","postgres","-d","trading_db","-t","-A","-F","|",
          "-c", f"select api_key,api_secret from accounts where account_id='{ACCT}';"])
ek, es = row.split("|")
dec = lambda v: AESGCM(key).decrypt(base64.b64decode(v[7:])[:12], base64.b64decode(v[7:])[12:], None).decode() if v.startswith("enc:v1:") else v
ak, sk = dec(ek), dec(es)
ip = sh(["docker","inspect","-f","{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}","blackheart-js"])

def signed_spot(path, params, method="GET"):
    st = json.loads(urllib.request.urlopen("https://api.binance.com/api/v3/time", timeout=15).read())["serverTime"]
    params = {**params, "recvWindow": "5000", "timestamp": str(st)}
    q = urllib.parse.urlencode(params)
    sig = hmac.new(sk.encode(), q.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"https://api.binance.com{path}?{q}&signature={sig}",
                                 data=b"" if method == "POST" else None, method=method,
                                 headers={"X-MBX-APIKEY": ak})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except urllib.error.HTTPError as e:
        return {"_err": e.code, "_body": e.read().decode()[:200]}

def spot_usdt():
    acct = signed_spot("/api/v3/account", {})
    u = [b for b in acct.get("balances", []) if b["asset"] == "USDT"]
    return float(u[0]["free"]) if u else 0.0

def fut():
    r = urllib.request.Request(f"http://{ip}:8088/api/account-futures",
                               data=json.dumps({"apiKey": ak, "apiSecret": sk}).encode(),
                               headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=20).read())
    return float(d.get("availableBalance", 0)), float(d.get("totalWalletBalance", 0))

def transfer(direction, amount):
    # MAIN_UMFUTURE = spot->futures ; UMFUTURE_MAIN = futures->spot
    return signed_spot("/sapi/v1/asset/transfer",
                       {"type": direction, "asset": "USDT", "amount": f"{amount:.2f}"}, method="POST")

s = spot_usdt(); favail, ftot = fut()
print(f"BEFORE  spot=${s:.2f}  futures_avail=${favail:.2f}  futures_total=${ftot:.2f}")

if MODE == "ensure" and TARGET > favail:
    need = round(TARGET - favail + 0.01, 2)
    if need > s:
        print(f"SKIP: need ${need:.2f} spot->futures but only ${s:.2f} free in spot.")
    else:
        r = transfer("MAIN_UMFUTURE", need)
        print(f"TRANSFER spot->futures ${need:.2f} -> {('tranId '+str(r.get('tranId'))) if 'tranId' in r else r}")
elif MODE == "sweep" and favail - TARGET > 0:
    excess = round(favail - TARGET, 2)
    r = transfer("UMFUTURE_MAIN", excess)
    print(f"SWEEP futures->spot ${excess:.2f} -> {('tranId '+str(r.get('tranId'))) if 'tranId' in r else r}")
elif MODE != "report":
    print("No action: target already satisfied.")

if MODE != "report":
    s2 = spot_usdt(); fa2, ft2 = fut()
    print(f"AFTER   spot=${s2:.2f}  futures_avail=${fa2:.2f}  futures_total=${ft2:.2f}")
PY
