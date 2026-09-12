#!/usr/bin/env python3
# Blackheart self-improvement loop — DAILY INTELLIGENCE CYCLE (VPS-resident, cron, no Claude).
# =============================================================================================
# The hourly heartbeat.py is the fast SAFETY net (detect + Telegram-alert naked legs / FAILED
# trades). This is the slower THINKING net: it runs the intelligent steps that previously needed
# a Claude session, once per day, then posts ONE consolidated report to loop_report + Telegram.
#
# Three jobs:
#   (A) CARRY PROFIT     re-rank sustained funding (hysteresis-aware) vs the live carry book and,
#                        when armed, EXECUTE the rotation over operator-seeded FCARRY rows. The
#                        carry book is the platform's only live profit engine, so keeping it on the
#                        highest sustained positive funding IS "best profitability possible" here.
#   (B) ALPHA UNLOCK     free-data alpha is exhausted (proven). The ONLY unlock is new orthogonal
#                        data. Watch the Deribit options-skew / vol-term *effective* depth; only
#                        worth spawning research once it crosses the first-screen depth.
#   (C) CIRCUIT-BREAKER  naked legs + CARRY BOOK MTM (funding+basis, from the JVM book endpoint) +
#                        hedge-drift + realized loss vs the daily-loss cap; FAILED trades (6h).
#
# Execution modes (BH_LOOP_MODE): report (default, NO API calls) | sim (paper) | armed (real, needs
# BOTH BH_LOOP_MODE=armed AND a .armed token file). Never throws: each section is isolated.
import os, base64, subprocess, json, urllib.request, urllib.parse, hmac, hashlib, datetime, time, math, sys

# ---- config / caps (mirror research/SELF_IMPROVEMENT_LOOP.md §2) -----------------------------
ACCT          = os.environ.get("BH_ACCOUNT_ID", "76fac4b6-ea6b-44cc-a9ec-382ac3c2f4a2")  # starsky
ADMIN_EMAIL   = os.environ.get("ADMIN_EMAIL", "rfkih23@gmail.com")
ADMIN_USERID  = os.environ.get("ADMIN_USERID", "8ff655fa-2d13-4c65-98b9-8dd1e37ef23a")
# Execution mode: report (recommend only, NO API calls — cron default) | sim (call the carry
# endpoints with simulated=true, paper, NO capital — proves wiring) | armed (simulated=false, REAL).
MODE          = os.environ.get("BH_LOOP_MODE", "report").lower()
LOOP_DIR      = "/home/starsky/blackheart/loop"
ROTATION_STATE = f"{LOOP_DIR}/.last_rotation"   # 1 rotation/day rate-limit
ARM_TOKEN_FILE = f"{LOOP_DIR}/.armed"           # R2: real execution needs BOTH env AND this file
HEARTBEAT_LOG = f"{LOOP_DIR}/heartbeat.log"     # R1: dead-man's check on the hourly cron
# R2 two-key arm: armed real trading requires MODE=armed AND a deliberately-created .armed token
# file, so a stray cron edit/typo cannot move real capital on its own.
_ARM_TOKEN_OK = os.path.exists(ARM_TOKEN_FILE)
ARMED         = (MODE == "armed") and _ARM_TOKEN_OK
ARM_BLOCKED   = (MODE == "armed") and not _ARM_TOKEN_OK   # armed asked but token missing → safe no-op
LEV           = float(os.environ.get("BH_CARRY_LEV", "2"))
MIN_NOTIONAL  = float(os.environ.get("BH_MIN_NOTIONAL", "20"))   # Binance futures floor
MIN_VOL       = float(os.environ.get("BH_MIN_VOL", "50000000"))  # $50M 24h liquidity floor
MIN_MCAP      = float(os.environ.get("BH_MIN_MCAP", "100000000"))  # C3: $100M mkt-cap quality floor (ENTRY only)
CAP_PAIRS     = int(os.environ.get("BH_CARRY_CAP", "8"))         # book-breadth cap
# D4: gross-funding floor (%/yr). 4% barely cleared the ~2%/yr rebalance drag + flip + basis ⇒ could
# rotate into NET-negative carry. Raise to a level whose net is comfortably positive (~10%/yr gross).
MIN_FUNDING_PCT = float(os.environ.get("BH_MIN_FUNDING_PCT", "10"))   # ENTRY floor (rotate INTO)
EXIT_FUNDING_PCT = float(os.environ.get("BH_EXIT_FUNDING_PCT", "3"))  # EXIT floor (hold vs cash); below → close
ROTATE_HYST   = float(os.environ.get("BH_ROTATE_HYST", "1.25"))  # D5: challenger must beat incumbent ×this
MAX_PAIR_NOTIONAL = float(os.environ.get("BH_MAX_PAIR_NOTIONAL", "0"))  # C3/R2: per-pair $ ceiling (0=off)
DAILY_LOSS_CAP_PCT = float(os.environ.get("BH_DAILY_LOSS_CAP_PCT", "4"))  # circuit-breaker
UNLOCK_DAYS   = int(os.environ.get("BH_UNLOCK_DAYS", "365"))            # robust-screen depth
FIRSTSCREEN_DAYS = int(os.environ.get("BH_UNLOCK_FIRSTSCREEN_DAYS", "90"))  # first-look IC-screen depth
CAPITAL_PER_PAIR = (MIN_NOTIONAL * 1.10) * (1 + 1 / LEV)

TS = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
TODAY = datetime.datetime.utcnow().strftime("%Y-%m-%d")

# ---- low-level helpers (proven in heartbeat.py / carry_adaptive.sh / post_report.sh) ---------
def sh(a):
    return subprocess.check_output(a, stderr=subprocess.DEVNULL).decode().strip()

def psql(q):
    return sh(["docker", "exec", "blackheart-postgres", "psql", "-U", "postgres", "-d",
               "trading_db", "-t", "-A", "-F", "|", "-c", q]).strip()

def load_env():
    env = {}
    try:
        for line in open("/home/starsky/blackheart/.env"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); env[k] = v
    except Exception:
        pass
    return env

ENV = load_env()
TG_TOKEN, TG_CHAT = ENV.get("TELEGRAM_BOT_TOKEN", ""), ENV.get("TELEGRAM_CHAT_ID", "")

def tg(msg):
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=15)
    except Exception:
        pass

def gw_ip():
    return sh(["docker", "inspect", "-f",
               "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", "blackheart-js"])

def gw(ip, path, body):
    r = urllib.request.Request(f"http://{ip}:8088{path}", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=25).read())

def pub(url, timeout=25):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())

def base_sym(s):
    # Binance perp symbol -> CoinGecko base ticker (DEXEUSDT->DEXE, 1000PEPEUSDT->PEPE).
    b = s[:-4] if s.endswith("USDT") else s
    if b.startswith("1000"):
        b = b[4:]
    return b.upper()

def mcap_map():
    # C3: CoinGecko top-500 by mcap -> {BASE_TICKER: market_cap_usd}. First (largest) wins on ticker
    # collisions. Returns {} if even page 1 fails -> caller treats empty as "floor disabled" (fail open,
    # so a CoinGecko outage never empties the book). Free endpoint, ~2 calls, no key.
    out = {}
    for page in (1, 2):
        try:
            for c in pub(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
                         f"&order=market_cap_desc&per_page=250&page={page}", 30):
                sym = (c.get("symbol") or "").upper()
                if sym and sym not in out:
                    out[sym] = float(c.get("market_cap") or 0)
        except Exception:
            break   # keep page 1 if page 2 fails
    return out

def decrypt_creds():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = base64.b64decode(sh(["docker", "exec", "blackheart-app", "printenv", "DB_ENCRYPTION_KEY"]))
    row = psql(f"select api_key||chr(124)||api_secret from accounts where account_id='{ACCT}';")
    ek, es = row.split("|")
    def dec(v):
        if not v.startswith("enc:v1:"):
            return v
        blob = base64.b64decode(v[7:])
        return AESGCM(key).decrypt(blob[:12], blob[12:], None).decode()
    return dec(ek), dec(es)

def signed_spot(ak, sk, path, params, method="GET"):
    st = pub("https://api.binance.com/api/v3/time", 15)["serverTime"]
    params = {**params, "recvWindow": "5000", "timestamp": str(st)}
    q = urllib.parse.urlencode(params)
    sig = hmac.new(sk.encode(), q.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"https://api.binance.com{path}?{q}&signature={sig}",
                                 data=b"" if method == "POST" else None, method=method,
                                 headers={"X-MBX-APIKEY": ak})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())

# ---- JVM admin (carry open/close) — JWT minted on-host, loopback only --------------------------
def jvm_jwt(ttl=600):
    import jwt
    k = base64.b64decode(sh(["docker", "exec", "blackheart-app", "printenv", "JWT_SECRET"]))
    n = int(time.time())
    return jwt.encode({"sub": ADMIN_EMAIL, "userId": ADMIN_USERID, "role": "ADMIN",
                       "iat": n, "exp": n + ttl}, k, algorithm="HS512")

def jvm_post(path, body):
    req = urllib.request.Request(f"http://localhost:8080{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {jvm_jwt()}"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=35).read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, f"err: {e}"

def jvm_get(path):
    req = urllib.request.Request(f"http://localhost:8080{path}",
                                 headers={"Authorization": f"Bearer {jvm_jwt()}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, f"err: {e}"

def carry_open(strategy_id, symbol, qty, lev, simulated):
    return jvm_post("/api/v1/carry/open-pair", {
        "accountStrategyId": strategy_id, "symbol": symbol,
        "targetBaseQty": round(qty, 8), "leverage": lev, "simulated": simulated})

def carry_close(pair_id):
    return jvm_post("/api/v1/carry/close-pair", {"carryPairId": pair_id})

def ensure_futures_margin(ak, sk, ip, target):
    # Carry's perp leg needs futures-wallet USDT; move from spot when short. Caps the move at
    # spot-free. Universal-transfer permission is enabled on the key (proven 2026-06-22).
    try:
        fa = gw(ip, "/api/account-futures", {"apiKey": ak, "apiSecret": sk})
        favail = float(fa.get("availableBalance", 0) or 0)
        if favail >= target:
            return f"futures margin ${favail:.2f} ≥ need ${target:.2f} (no transfer)"
        need = round(target - favail + 0.01, 2)
        acct = signed_spot(ak, sk, "/api/v3/account", {})
        s = next((float(b["free"]) for b in acct.get("balances", []) if b["asset"] == "USDT"), 0.0)
        if need > s:
            return f"SKIP transfer: need ${need:.2f} spot→futures but only ${s:.2f} free"
        r = signed_spot(ak, sk, "/sapi/v1/asset/transfer",
                        {"type": "MAIN_UMFUTURE", "asset": "USDT", "amount": f"{need:.2f}"}, "POST")
        return f"transferred ${need:.2f} spot→futures (tranId {r.get('tranId')})"
    except Exception as e:
        return f"margin transfer error: {e}"

def rotated_today():
    try:
        return open(ROTATION_STATE).read().strip() == TODAY
    except Exception:
        return False

def stamp_rotated():
    try:
        open(ROTATION_STATE, "w").write(TODAY)
    except Exception:
        pass

# =============================================================================================
# EXECUTE — turn the carry plan into real open/close calls (mode-gated, capped, 1/day)
# =============================================================================================
def job_execute(plan, ip, ak, sk):
    out = {"lines": [], "problems": []}
    simulated = not ARMED  # sim mode -> paper; armed -> real capital
    if rotated_today():
        out["lines"].append("rotation already executed today (1/day rate-limit) — skipping")
        return out
    closes, opens = plan["closes"], plan["opens"]
    lev, pn = plan["lev"], plan["pair_notional"]
    # resolve ids
    pair_ids = {}
    for ln in psql(f"select symbol||chr(124)||carry_pair_id from carry_pair where account_id='{ACCT}' "
                   "and status in ('OPEN','OPENING','PENDING','REBALANCING','CLOSING');").splitlines():
        if "|" in ln: s, i = ln.split("|"); pair_ids[s] = i
    strat_ids = {}
    for ln in psql(f"select symbol||chr(124)||account_strategy_id from account_strategy where account_id='{ACCT}' "
                   "and strategy_code='FCARRY' and is_deleted=false;").splitlines():
        if "|" in ln: s, i = ln.split("|"); strat_ids.setdefault(s, i)

    out["lines"].append(f"EXECUTE mode={MODE} (simulated={simulated}) — {len(closes)} close, {len(opens)} open")
    # 1) CLOSE stale pairs first (de-risking). Abort the whole rotation on any failure.
    for sym in closes:
        pid = pair_ids.get(sym)
        if not pid:
            out["lines"].append(f"  CLOSE {sym}: no open pair id — skip"); continue
        res, err = carry_close(pid)
        if err:
            # C2: do NOT stamp — leave the rotation un-rate-limited so the next run retries
            # instead of parking capital for a day. Book is flat/safe (no naked leg).
            out["problems"].append(f"CLOSE {sym} failed: {err} — ABORT rotation (not stamped; retries next run)")
            return out
        out["lines"].append(f"  CLOSE {sym}: {res.get('data', {}).get('status')}")
    # 2) ensure margin for the opens
    if opens:
        out["lines"].append("  " + ensure_futures_margin(ak, sk, ip, len(opens) * (pn / lev) * 1.1))
    # 3) OPEN new top-funding pairs (only over operator-seeded FCARRY rows; never invent strategies)
    for sym in opens:
        sid = strat_ids.get(sym)
        if not sid:
            out["lines"].append(f"  OPEN {sym}: SKIP — no operator-seeded FCARRY row (seed one to add {sym})")
            continue
        mark, step = plan["marks"].get(sym, 0), plan["steps"].get(sym, 0)
        if mark <= 0:
            out["lines"].append(f"  OPEN {sym}: no mark — skip"); continue
        qty = pn / mark
        if step > 0:
            qty = math.floor(qty / step) * step
        if qty * mark < MIN_NOTIONAL:
            out["lines"].append(f"  OPEN {sym}: size ${qty*mark:.2f} < min ${MIN_NOTIONAL:.0f} — skip"); continue
        res, err = carry_open(sid, sym, qty, lev, simulated)
        if err:
            # C2: a close may already have freed capital; not stamping lets the next run finish the
            # open (capital is idle, not at risk). Loud alert via the problem → CRITICAL.
            out["problems"].append(f"OPEN {sym} failed: {err} — ABORT (capital may be idle; retries next run)")
            return out
        st = res.get("data", {}).get("status")
        out["lines"].append(f"  OPEN {sym} {qty}@{lev:.0f}x sim={simulated}: {st}")
        if st == "FAILED":
            out["problems"].append(f"OPEN {sym} returned FAILED (leg/rollback) — check naked-leg guard")
    stamp_rotated()
    return out

# ---- SIM self-test: prove the open/close wiring end-to-end with ZERO capital ------------------
def selftest():
    ip = gw_ip(); ak, sk = decrypt_creds()
    # LINKUSDT FCARRY strategy with no open pair = a safe sim target
    sid = None
    for ln in psql(f"select symbol||chr(124)||account_strategy_id from account_strategy where account_id='{ACCT}' "
                   "and strategy_code='FCARRY' and symbol='LINKUSDT' and is_deleted=false limit 1;").splitlines():
        if "|" in ln: sid = ln.split("|")[1]
    if not sid:
        print("SELFTEST FAIL: no LINKUSDT FCARRY strategy to test on"); return 1
    fund = gw(ip, "/api/premium-index-futures", {"symbol": "LINKUSDT"})
    mark = float((fund[0] if isinstance(fund, list) else fund).get("markPrice", 0) or 0)
    qty = round((MIN_NOTIONAL * 1.2) / mark, 2) if mark else 2.0
    print(f"SELFTEST: open SIM pair LINKUSDT qty={qty} (mark {mark}) on {sid} ...")
    res, err = carry_open(sid, "LINKUSDT", qty, 2, True)   # simulated=TRUE -> no capital
    if err:
        print("SELFTEST FAIL open:", err); return 1
    pair = res.get("data", {})
    print(f"  -> status={pair.get('status')} pairId={pair.get('carryPairId')} spot={pair.get('spotQty')} perp={pair.get('perpQty')} sim={pair.get('simulated')}")
    pid = pair.get("carryPairId")
    if pair.get("status") != "OPEN" or not pid:
        print("SELFTEST FAIL: sim open did not return OPEN"); return 1
    res2, err2 = carry_close(pid)
    if err2:
        print("SELFTEST FAIL close:", err2); return 1
    print(f"  -> close status={res2.get('data', {}).get('status')}")
    ok = res2.get("data", {}).get("status") == "CLOSED"
    print("SELFTEST PASS ✅" if ok else "SELFTEST FAIL: did not CLOSE")
    return 0 if ok else 1

# =============================================================================================
# (A) CARRY PROFIT — adaptive funding-harvest plan (DRY_RUN)
# =============================================================================================
def job_carry(ip, ak, sk):
    out = {"lines": [], "metrics": {}, "action": False, "problems": []}
    try:
        fund = gw(ip, "/api/premium-index-futures", {})
        fund = fund if isinstance(fund, list) else fund.get("data", [])
        marks = {}
        for x in fund:
            try: marks[x["symbol"]] = float(x.get("markPrice", 0) or 0)
            except Exception: pass
        vol = {}
        try:
            for x in pub("https://fapi.binance.com/fapi/v1/ticker/24hr"):
                try: vol[x["symbol"]] = float(x.get("quoteVolume", 0) or 0)
                except Exception: pass
        except Exception: pass
        spot = set()
        try:
            for s in pub("https://api.binance.com/api/v3/exchangeInfo", 30).get("symbols", []):
                if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT":
                    spot.add(s["symbol"])
        except Exception: pass
        mcaps = mcap_map()  # C3 quality floor (empty = CoinGecko down → floor disabled, fail open)

        cands = []
        for x in fund:
            s = x.get("symbol", "")
            try: fr = float(x.get("lastFundingRate", 0) or 0)
            except Exception: continue
            if s.endswith("USDT") and fr > 0 and vol.get(s, 0) >= MIN_VOL and (not spot or s in spot):
                cands.append((s, fr))
        cands.sort(key=lambda r: r[1], reverse=True)

        # sustained-funding stats over ~8d: (avg %/yr, min, positive-count, n). Computed for the top
        # candidates here, and topped up for current holdings after open_syms is known below.
        def hist(s):
            try:
                h = pub(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={s}&limit=24", 12)
                ann = [float(x["fundingRate"]) * 3 * 365 * 100 for x in h]
                if not ann: return None
                return (sum(ann) / len(ann), min(ann), sum(1 for a in ann if a > 0), len(ann))
            except Exception:
                return None
        stat = {}
        for s, _ in cands[:25]:
            h = hist(s)
            if h: stat[s] = h
        def sustained(s):
            h = stat.get(s)
            return bool(h) and h[2] >= int(h[3] * 0.8) and h[1] > -10   # pos≥80%, no deep dip

        # capital
        fa = gw(ip, "/api/account-futures", {"apiKey": ak, "apiSecret": sk})
        fut_avail = float(fa.get("availableBalance", 0) or 0)
        fut_total = float(fa.get("totalWalletBalance", 0) or 0)
        acct = signed_spot(ak, sk, "/api/v3/account", {})
        spot_usdt = next((float(b["free"]) for b in acct.get("balances", []) if b["asset"] == "USDT"), 0.0)
        open_rows = psql(f"select symbol from carry_pair where account_id='{ACCT}' and "
                         "status in ('OPEN','OPENING','PENDING','REBALANCING','CLOSING');")
        open_syms = [s for s in open_rows.splitlines() if s.strip()]
        for s in open_syms:                       # evaluate incumbents even if off the top-25 snapshot
            if s not in stat:
                h = hist(s)
                if h: stat[s] = h

        free_capital = spot_usdt + fut_avail
        total_usable = free_capital + len(open_syms) * CAPITAL_PER_PAIR
        capacity = min(CAP_PAIRS, int(total_usable // CAPITAL_PER_PAIR)) if CAPITAL_PER_PAIR else 0
        pair_notional = (total_usable / max(capacity, 1)) / (1 + 1 / LEV) if capacity else MIN_NOTIONAL * 1.1
        if MAX_PAIR_NOTIONAL > 0:                      # C3/R2: bound single-name blast radius
            pair_notional = min(pair_notional, MAX_PAIR_NOTIONAL)

        # hedge-precision filter: drop coins whose perp lot is too coarse for clean delta-neutral
        steps = {}
        try:
            ei = gw(ip, "/api/exchange-info-futures", {})
            syms = ei.get("symbols", []) if isinstance(ei, dict) else ei
            for sd in syms:
                for f in sd.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        try: steps[sd["symbol"]] = float(f["stepSize"])
                        except Exception: pass
        except Exception: pass
        def hedgeable(sym):
            stp, mk = steps.get(sym, 0), marks.get(sym, 0)
            return stp > 0 and mk > 0 and (stp * mk) / pair_notional <= 0.08
        fundpct = {s: stat[s][0] for s in stat}              # display: avg funding for any evaluated sym
        # C3: market-cap quality floor — ENTRY-ONLY (never force-closes an incumbent; that's the
        # funding band's job). Fails open when CoinGecko is unavailable (mcaps empty → no filter).
        def mcap_ok(s):
            return (not mcaps) or mcaps.get(base_sym(s), 0) >= MIN_MCAP
        # ENTRY candidates: clear the HIGHER entry floor + sustained + hedgeable + mcap, ranked by funding.
        ranked = sorted([(s, stat[s][0]) for s in stat
                         if stat[s][0] > MIN_FUNDING_PCT and sustained(s) and hedgeable(s) and mcap_ok(s)],
                        key=lambda r: r[1], reverse=True)
        if not mcaps:
            out["lines"].append(f"⚠️ CoinGecko mcap unavailable — ${MIN_MCAP/1e6:.0f}M quality floor SKIPPED (fail-open)")
        else:
            dropped = [s for s in stat if stat[s][0] > MIN_FUNDING_PCT and sustained(s)
                       and hedgeable(s) and not mcap_ok(s)]
            if dropped:
                out["lines"].append(f"Dropped < ${MIN_MCAP/1e6:.0f}M mcap (too fragile to enter): "
                                    + ", ".join(f"{s.replace('USDT','')} ${mcaps.get(base_sym(s),0)/1e6:.0f}M" for s in dropped))
        # D4+D5 asymmetric band: HOLD an incumbent while it's sustained AND above the LOWER exit floor
        # (beats sitting in cash); only ENTER names above the higher floor; swap on hysteresis only.
        def hold_ok(s):
            return sustained(s) and stat.get(s, (0,))[0] >= EXIT_FUNDING_PCT and hedgeable(s)
        keep = [s for s in open_syms if hold_ok(s)]
        drop = [s for s in open_syms if not hold_ok(s)]      # negative / unsustainable / below exit floor
        challengers = [s for s, _ in ranked if s not in open_syms]
        free_slots = max(0, capacity - len(keep))
        opens = challengers[:free_slots]
        rest = challengers[free_slots:]
        if not free_slots and keep and rest:                 # full: allow ONE strong swap only
            weakest = min(keep, key=lambda s: stat.get(s, (0,))[0])
            if stat[rest[0]][0] > stat.get(weakest, (0,))[0] * ROTATE_HYST:
                keep.remove(weakest); drop.append(weakest); opens.append(rest[0])
        if len(keep) > capacity:                             # capacity shrank → shed weakest kept
            for s in sorted(keep, key=lambda s: stat.get(s, (0,))[0])[:len(keep) - capacity]:
                keep.remove(s); drop.append(s)
        closes, target = drop, keep + opens
        out["plan"] = {"closes": closes, "opens": opens, "pair_notional": pair_notional,
                       "marks": marks, "steps": steps, "lev": LEV}

        out["metrics"] = {
            "spotUsdt": round(spot_usdt, 2), "futuresAvail": round(fut_avail, 2),
            "equityUsd": round(spot_usdt + fut_total, 2), "openCarryPairs": len(open_syms),
            "bookCapacity": capacity, "perPairNeedUsd": round(CAPITAL_PER_PAIR, 2),
        }
        out["lines"].append(f"Capital: spot ${spot_usdt:.2f} + futures ${fut_avail:.2f} free "
                            f"(equity ~${spot_usdt+fut_total:.2f}) | per-pair ~${CAPITAL_PER_PAIR:.0f} @ {LEV:.0f}x")
        out["lines"].append(f"Capacity at this capital: ~{capacity} pair(s) (cap {CAP_PAIRS})")
        out["lines"].append("Open now: " + (", ".join(
            f"{s} ({fundpct.get(s,0):.1f}%/yr" + (f", ${mcaps.get(base_sym(s),0)/1e6:.0f}M mcap" if mcaps else "") + ")"
            for s in open_syms) or "(none)"))
        out["lines"].append("Funding leaders (sustained+liquid+hedgeable): "
                            + (", ".join(f"{s.replace('USDT','')} {a:.1f}%" for s, a in ranked[:8]) or "(none qualify)"))
        if closes or opens:
            out["action"] = True
            for s in closes:
                why = ("funding NOT sustained / negative" if not sustained(s) else
                       f"below exit floor {EXIT_FUNDING_PCT:.0f}%/yr" if fundpct.get(s, 0) < EXIT_FUNDING_PCT else
                       "rotated out for a higher-funding name")
                out["lines"].append(f"  CLOSE {s} ({fundpct.get(s,0):.1f}%/yr) — {why}")
            for s in opens:
                out["lines"].append(f"  OPEN  {s} ({fundpct.get(s,0):.1f}%/yr) — top sustained funding")
            new_book = [s for s in open_syms if s in target] + opens
            if new_book:
                avg = sum(fundpct.get(s, 0) for s in new_book) / len(new_book)
                out["lines"].append(f"Resulting book: {', '.join(s.replace('USDT','') for s in new_book)} | avg ~{avg:.1f}%/yr")
            out["lines"].append("Execution mode=" + MODE + (
                " — ARMED (real capital, .armed token present)" if ARMED else
                " — armed-BLOCKED (no .armed token; recommendation only)" if ARM_BLOCKED else
                " — sim (paper, no capital)" if MODE == "sim" else
                " — report only (recommendation; set BH_LOOP_MODE + .armed token to execute)"))
        else:
            out["lines"].append("  HOLD — live book already matches the sustained-funding leaders within capacity.")
        out["metrics"]["carryBookAvgFundingPct"] = round(
            sum(fundpct.get(s, 0) for s in open_syms) / len(open_syms), 2) if open_syms else 0
    except Exception as e:
        out["problems"].append(f"carry job error: {e}")
    return out

# =============================================================================================
# (B) ALPHA UNLOCK WATCH — is a new orthogonal research input ready to screen?
# =============================================================================================
def job_unlock():
    # Free-data alpha is exhausted (proven repeatedly). The one orthogonal family pending is the
    # Deribit options-skew + vol-term-structure. The full pipeline (deribit_options source ->
    # macro_raw -> feature_values) IS WORKING and accruing hourly since 2026-06-15 — it's just
    # YOUNG. This watch reads feature_values (where the research orchestrator screens), reports
    # accrual in days, and fires when it crosses a first-screen depth. NOTE: read feature_values,
    # NOT feature_store (whose rr25_skew_30d wide column is a separate, unwired path = always 0).
    out = {"lines": [], "metrics": {}, "unlock_ready": False}
    feats = ["btc_rr25_skew_30d", "btc_vol_term_spread"]  # base options-demand feats (accrue before z-scores)
    try:
        rows_tot, max_span = 0, 0
        for fn in feats:
            r = psql(f"select count(*), coalesce((max(ts)::date - min(ts)::date),0) "
                     f"from feature_values where feature_name='{fn}';")
            try:
                rows, span = r.split("|"); rows, span = int(rows), int(span)
            except Exception:
                rows, span = 0, 0
            # R4: effective depth = min(date-span, rows/24) — one stray old backfilled row can't
            # fake a 1yr span (the feed is hourly ⇒ ~24 rows/day).
            eff = min(span, rows // 24) if rows else 0
            rows_tot += rows; max_span = max(max_span, eff)
            state = ("ABSENT — pipeline broken, investigate" if rows == 0 else
                     "ROBUST-screenable" if eff >= UNLOCK_DAYS else
                     "first-screen viable" if eff >= FIRSTSCREEN_DAYS else
                     f"{eff}/{FIRSTSCREEN_DAYS}d to first screen")
            out["lines"].append(f"{fn}: {rows} rows, ~{eff}d eff ({state})")
        out["metrics"]["skewHistoryDays"] = max_span
        out["unlock_ready"] = rows_tot > 0 and max_span >= FIRSTSCREEN_DAYS
        out["metrics"]["researchUnlockReady"] = out["unlock_ready"]
        if rows_tot == 0:
            out["lines"].append("⛔ Pipeline regressed: options-skew features stopped writing to feature_values "
                                "(was accruing since 2026-06-15). Investigate the deribit_options compute.")
        elif max_span >= UNLOCK_DAYS:
            out["lines"].append("✅ ROBUST UNLOCK — spawn quant-researcher on options-skew/vol-term with full "
                                f"~1yr history ({max_span}d).")
        elif max_span >= FIRSTSCREEN_DAYS:
            out["lines"].append(f"✅ FIRST IC-SCREEN VIABLE ({max_span}d ≥ {FIRSTSCREEN_DAYS}d) — worth a first "
                                "quant-researcher look at the options-skew family (orthogonal, NON-price). "
                                f"Robust significance still wants ~{UNLOCK_DAYS}d.")
        else:
            out["lines"].append(f"Accruing correctly ({max_span}/{FIRSTSCREEN_DAYS}d to first screen; pipeline "
                                "healthy since 2026-06-15). Stay data-gated; don't re-grind dead free-data families.")
    except Exception as e:
        out["lines"].append(f"unlock watch error: {e}")
    return out

# =============================================================================================
# (C) CIRCUIT-BREAKER / HYGIENE
# =============================================================================================
def job_breaker(ip, ak, sk, equity_usd):
    # critical = naked leg OR daily-loss breach (real, capital-threatening).
    # warns    = recent (6h) FAILED trades/pairs — informational; the hourly heartbeat owns the
    #            urgent 1h window, and resolved bring-up failures age out of the 6h window.
    out = {"lines": [], "metrics": {}, "critical_problems": [], "warns": [], "critical": False}
    try:
        # R1 dead-man's: if the hourly heartbeat's log hasn't been touched in >2h, its cron is dead.
        try:
            age_h = (time.time() - os.path.getmtime(HEARTBEAT_LOG)) / 3600
            if age_h > 2:
                out["warns"].append(f"hourly heartbeat stale ({age_h:.1f}h) — its cron may be dead")
        except Exception:
            pass
        n_lt = psql("select count(*) from trades where created_time > now() - interval '24 hours';")
        n_lt = int(n_lt) if n_lt else 0
        n_ft = psql("select count(*) from trades where status in ('FAILED','ERROR') "
                    "and created_time > now() - interval '6 hours';")
        n_ft = int(n_ft) if n_ft else 0
        n_fc = psql("select count(*) from carry_pair where status in ('FAILED','ERROR') "
                    "and updated_time > now() - interval '6 hours';")
        n_fc = int(n_fc) if n_fc else 0
        if n_ft: out["warns"].append(f"{n_ft} FAILED trade(s) in 6h")
        if n_fc: out["warns"].append(f"{n_fc} carry pair FAILED in 6h")

        # naked futures legs (positionAmt != 0 with no live carry_pair) — CRITICAL
        naked = 0
        try:
            r = gw(ip, "/api/position-risk-futures", {"apiKey": ak, "apiSecret": sk})
            positions = r if isinstance(r, list) else r.get("data", []) or []
            for p in positions:
                amt = float(p.get("positionAmt", 0) or 0)
                if amt != 0:
                    sym = p.get("symbol")
                    live = psql(f"select count(*) from carry_pair where account_id='{ACCT}' "
                                f"and symbol='{sym}' and status not in ('CLOSED','FAILED');")
                    if not live or int(live) == 0:
                        naked += 1
                        out["critical_problems"].append(f"NAKED futures leg {sym} amt={amt} (no open carry_pair)")
        except Exception as e:
            out["warns"].append(f"position-risk read failed: {e}")

        # --- C1: CARRY BOOK MTM — the breaker MUST see the live carry pairs' P&L (funding + basis),
        # which lives in carry_pair, NOT in strategy_daily_realized_curve (0 rows for carry → the old
        # check was blind). Read the JVM's authoritative book endpoint: totalPnl = funding + basis MTM.
        cap_amt = -abs(equity_usd) * DAILY_LOSS_CAP_PCT / 100.0
        book_mtm, live_pairs = 0.0, 0
        try:
            data, err = jvm_get("/api/v1/carry/pairs")
            if err:
                out["warns"].append(f"carry book MTM read failed: {err}")
            for p in ((data or {}).get("data") or []):
                if (p.get("status") or "").upper() in ("CLOSED", "FAILED"):
                    continue
                live_pairs += 1
                tp = p.get("totalPnl")
                if tp is not None:
                    book_mtm += float(tp)
                # hedge-drift guard: a large net base delta = the hedge broke = hidden directional risk
                try:
                    nd, mk, pq = p.get("netDeltaBase"), p.get("markPrice"), p.get("perpQty")
                    if nd is not None and mk and pq:
                        dr = abs(float(nd) * float(mk)) / (abs(float(pq) * float(mk)) or 1.0)
                        if dr > 0.10:
                            out["critical_problems"].append(
                                f"CARRY HEDGE BROKEN {p.get('symbol')} — netΔ {dr*100:.0f}% of notional")
                except Exception:
                    pass
        except Exception as e:
            out["warns"].append(f"carry book MTM error: {e}")
        if book_mtm < cap_amt and equity_usd > 0:
            out["critical_problems"].append(
                f"CARRY BOOK MTM ${book_mtm:.2f} breaches {DAILY_LOSS_CAP_PCT:.0f}% cap (${cap_amt:.2f}) — HALT")

        # secondary: realized P&L booked today (closed positions; the directional book if any)
        dloss = psql("select coalesce(sum(daily_realized_pnl_amount),0) from strategy_daily_realized_curve "
                     f"where account_id='{ACCT}' and curve_date = current_date;")
        try: dloss = float(dloss)
        except Exception: dloss = 0.0
        if dloss < cap_amt and equity_usd > 0:
            out["critical_problems"].append(f"REALIZED LOSS TODAY ${dloss:.2f} breaches cap (${cap_amt:.2f}) — HALT")

        out["metrics"] = {"liveTrades24h": n_lt, "failedTrades6h": n_ft + n_fc, "nakedLegs": naked,
                          "carryBookMtmUsd": round(book_mtm, 4), "realizedPnlTodayUsd": round(dloss, 4)}
        out["critical"] = bool(out["critical_problems"])
        out["lines"].append(f"24h trades: {n_lt} | failed(6h): {n_ft+n_fc} | naked legs: {naked} | "
                            f"carry MTM ${book_mtm:.4f} ({live_pairs} live) | realized today ${dloss:.4f} "
                            f"(loss cap ${cap_amt:.2f})")
        if not out["critical_problems"] and not out["warns"]:
            out["lines"].append("Circuit-breaker: OK — no naked legs, no recent failures, within loss cap.")
    except Exception as e:
        out["critical_problems"].append(f"breaker job error: {e}")
        out["critical"] = True
    return out

# =============================================================================================
# REPORT — post to loop_report (admin JWT minted on-host) + Telegram if actionable
# =============================================================================================
def post_report(report_type, title, summary, status, metrics, body):
    try:
        secret = sh(["docker", "exec", "blackheart-app", "printenv", "JWT_SECRET"])
        import jwt
        k = base64.b64decode(secret)
        n = int(time.time())
        token = jwt.encode({"sub": ADMIN_EMAIL, "userId": ADMIN_USERID, "role": "ADMIN",
                            "iat": n, "exp": n + 600}, k, algorithm="HS512")
        payload = {"reportType": report_type, "reportDate": TODAY, "title": title,
                   "summary": summary, "status": status, "metrics": metrics, "body": body}
        req = urllib.request.Request("http://localhost:8080/api/v1/loop-reports",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {token}"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=25)
        return resp.getcode()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"err: {e}"

def main():
    ip = gw_ip()
    ak, sk = decrypt_creds()
    carry   = job_carry(ip, ak, sk)
    equity  = carry["metrics"].get("equityUsd", 0)
    breaker = job_breaker(ip, ak, sk, equity)
    unlock  = job_unlock()

    # Execute ONLY when (sim, or armed-with-token), a rotation is recommended, and the breaker is
    # clean. R2: MODE=armed without the .armed token does NOT execute — safe downgrade + alert.
    exec_out = {"lines": [], "problems": []}
    arm_warns = []
    if ARM_BLOCKED:
        arm_warns.append("MODE=armed but .armed token missing — NOT executing (touch "
                         f"{ARM_TOKEN_FILE} to arm real capital)")
    if (MODE == "sim" or ARMED) and carry.get("action") and carry.get("plan") and not breaker["critical_problems"]:
        exec_out = job_execute(carry["plan"], ip, ak, sk)

    critical = breaker["critical_problems"] + carry["problems"] + exec_out["problems"]
    warns    = breaker["warns"] + arm_warns
    status = ("CRITICAL" if critical else
              "WARN" if (warns or carry["action"] or unlock["unlock_ready"]) else "OK")

    metrics = {}
    metrics.update(carry["metrics"]); metrics.update(breaker["metrics"]); metrics.update(unlock["metrics"])

    body = (
        f"## Daily self-improvement cycle — {TODAY}\n\n"
        f"_VPS-resident, no Claude session. mode={MODE}"
        + (" ✅ARMED (real capital)" if ARMED else " ⛔armed-blocked (no .armed token)" if ARM_BLOCKED else "")
        + "._\n\n"
        "### A. Carry profit (the live engine)\n" + "\n".join(f"- {l}" for l in carry["lines"])
        + ("\n" + "\n".join(f"- {l}" for l in exec_out["lines"]) if exec_out["lines"] else "") + "\n\n"
        "### B. Alpha unlock watch\n" + "\n".join(f"- {l}" for l in unlock["lines"]) + "\n\n"
        "### C. Circuit-breaker / hygiene\n" + "\n".join(f"- {l}" for l in breaker["lines"]) + "\n\n"
        + ("### 🔴 Critical\n" + "\n".join(f"- {p}" for p in critical) + "\n\n" if critical else "")
        + ("### 🟡 Watch\n" + "\n".join(f"- {p}" for p in warns) + "\n\n" if warns else "")
        + "_Profit is capital-gated (cents at this size) and alpha is data-gated — the two real "
          "levers are operator inputs: fund the book, accrue/buy orthogonal data._\n"
    )
    summary = (f"{status}: {metrics.get('openCarryPairs',0)} carry pair(s), "
               f"{metrics.get('liveTrades24h',0)} trades/24h, {metrics.get('failedTrades6h',0)} failed/6h, "
               f"{metrics.get('nakedLegs',0)} naked; skew hist {metrics.get('skewHistoryDays',0)}/{UNLOCK_DAYS}d; "
               f"carry " + ("ROTATE" if carry["action"] else "HOLD"))

    code = post_report("DAILY", f"Daily cycle — {TODAY}", summary, status, metrics, body)
    print(TS, "report ->", code, "|", summary)

    # Optional always-on dead-man's-switch: ping a healthchecks.io-style URL on each successful run.
    # No-op unless BH_DEADMAN_URL is set; if the ping stops, that external service alerts the operator
    # (covers the case where even the off-host dev-PC watcher is down). Complements, not replaces it.
    dm = os.environ.get("BH_DEADMAN_URL", "")
    if dm and str(code) in ("200", "201"):
        try: urllib.request.urlopen(dm, timeout=10)
        except Exception: pass

    if status != "OK":
        flag = "🔴" if status == "CRITICAL" else "🟡"
        detail = ("\n".join("- " + p for p in (critical or warns)) if (critical or warns) else
                  ("rotate recommended" if carry["action"] else
                   "research unlock ready" if unlock["unlock_ready"] else ""))
        tg(f"{flag} Blackheart daily cycle {TS}\n{summary}\n{detail}")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
