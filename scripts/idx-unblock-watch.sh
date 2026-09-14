#!/usr/bin/env bash
# Wait for IDX to stop answering 403, then backfill the day the block cost us and resume the annual-report downloads
# slowly. Polls every 20 minutes for up to 18 hours; one light probe per poll (a single stock-summary request).
#   bash scripts/idx-unblock-watch.sh 2026-09-14
set -u
cd "$(dirname "$0")/.."
DAY="${1:-$(date +%F)}"
LOG=research-scratch/idx-screen/unblock_watch.log
set -a; . blackheart-ingest/idx-local.env; set +a
export INGEST_IDX_RPS=0.15
for i in $(seq 1 54); do
  code=$(blackheart-ingest/.venv/Scripts/python - <<'EOF'
import sys, datetime as dt, urllib.request, http.cookiejar
sys.path.insert(0, "blackheart-ingest/src")
from blackheart_ingest.idx import client as C
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
url = C.BASE + C.ENDPOINTS["stock_summary"][0].format(date=dt.date.today().strftime("%Y%m%d"))
req = urllib.request.Request(url, headers={"User-Agent": C.UA, "Referer": C.BASE + C.ENDPOINTS["stock_summary"][1], "Accept": "application/json"})
try:
    with opener.open(req, timeout=40) as r:
        print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print(0)
EOF
)
  echo "$(date '+%F %T') probe -> HTTP $code" >> "$LOG"
  if [ "$code" = "200" ]; then
    echo "$(date '+%F %T') IDX answers again; backfilling $DAY and resuming annual reports" >> "$LOG"
    bash scripts/idx.sh daily --date "$DAY" >> "$LOG" 2>&1
    bash scripts/idx.sh universe >> "$LOG" 2>&1
    bash scripts/idx.sh candidates >> "$LOG" 2>&1
    bash scripts/idx.sh annual download --codes NCKL,CPIN,TKIM,INKP,DEWA,AADI,ITMG,MAPI,DSNG,UNVR,KLBF,SIDO,TOWR,BBTN,BBYB --years 2025 --limit 6 >> "$LOG" 2>&1
    bash scripts/idx.sh annual extract --years 2025 >> "$LOG" 2>&1
    echo "$(date '+%F %T') done (first six annual reports; the scheduler's monthly job takes the rest)" >> "$LOG"
    exit 0
  fi
  sleep 1200
done
echo "$(date '+%F %T') gave up after 18 hours" >> "$LOG"
exit 1
