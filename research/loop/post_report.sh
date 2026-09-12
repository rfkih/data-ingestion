#!/usr/bin/env bash
# post_report.sh — write a self-improvement-loop report into the loop_report table
# via the admin API (POST /api/v1/loop-reports on the trading JVM, VPS loopback).
#
# The markdown BODY is read from STDIN; metadata comes from flags. The JWT is minted
# ON the VPS (secret never leaves the host), same pattern as the other loop scripts.
#
# Usage:
#   bash research/loop/post_report.sh \
#       --type DAILY --date 2026-06-23 --status OK \
#       --title "Daily report — 2026-06-23" \
#       --summary "0 trades, LINK carry healthy, no failures" \
#       --metrics '{"liveTrades":0,"failedTrades":0,"nakedLegs":0,"openCarryPairs":1}' \
#       <<'EOF'
#   ## Daily report
#   ...markdown...
#   EOF
#
# Flags: --type (DAILY|EXEC_HEALTH|ADHOC, default DAILY), --date (UTC today if omitted),
#        --title (required), --summary, --status (OK|WARN|CRITICAL, default OK),
#        --metrics (JSON object string, default {}).
set -euo pipefail

SSH_KEY="${SSH_KEY:-C:/Project/sshkey.pem}"
VPS="${VPS:-starsky@100.112.13.126}"
ADMIN_EMAIL="${ADMIN_EMAIL:-rfkih23@gmail.com}"
ADMIN_USERID="${ADMIN_USERID:-8ff655fa-2d13-4c65-98b9-8dd1e37ef23a}"

TYPE="DAILY"; DATE=""; TITLE=""; SUMMARY=""; STATUS="OK"; METRICS="{}"
while [ $# -gt 0 ]; do
  case "$1" in
    --type)    TYPE="$2"; shift 2;;
    --date)    DATE="$2"; shift 2;;
    --title)   TITLE="$2"; shift 2;;
    --summary) SUMMARY="$2"; shift 2;;
    --status)  STATUS="$2"; shift 2;;
    --metrics) METRICS="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$DATE" ]  || DATE="$(date -u +%F)"
[ -n "$TITLE" ] || { echo "ERROR: --title is required" >&2; exit 2; }

BODY="$(cat)"   # markdown body from stdin

# Build the JSON payload locally with python (safe escaping), then base64 for transport.
PAYLOAD_B64="$(TYPE="$TYPE" DATE="$DATE" TITLE="$TITLE" SUMMARY="$SUMMARY" STATUS="$STATUS" METRICS="$METRICS" BODY="$BODY" python3 -c '
import os, json, base64
m = os.environ.get("METRICS", "").strip()
try:
    metrics = json.loads(m) if m else None
except Exception:
    metrics = None
payload = {
    "reportType": os.environ["TYPE"],
    "reportDate": os.environ["DATE"],
    "title": os.environ["TITLE"],
    "summary": os.environ.get("SUMMARY") or None,
    "status": os.environ.get("STATUS") or "OK",
    "metrics": metrics,
    "body": os.environ.get("BODY") or None,
}
print(base64.b64encode(json.dumps(payload).encode()).decode())
')"

# Mint an admin JWT on the VPS and POST to the loopback trading JVM.
ssh -i "$SSH_KEY" -o BatchMode=yes "$VPS" \
  "PAYLOAD_B64='$PAYLOAD_B64' ADMIN_EMAIL='$ADMIN_EMAIL' ADMIN_USERID='$ADMIN_USERID' bash -s" <<'REMOTE'
set -e
SECRET="$(docker exec blackheart-app printenv JWT_SECRET)"
TOKEN="$(SECRET="$SECRET" ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_USERID="$ADMIN_USERID" python3 -c "import os,jwt,base64,time;k=base64.b64decode(os.environ['SECRET']);n=int(time.time());print(jwt.encode({'sub':os.environ['ADMIN_EMAIL'],'userId':os.environ['ADMIN_USERID'],'role':'ADMIN','iat':n,'exp':n+600},k,algorithm='HS512'))")"
echo "$PAYLOAD_B64" | base64 -d > /tmp/loop_report.json
code=$(curl -s -o /tmp/loop_report_resp.json -w '%{http_code}' -m 25 -X POST \
       -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
       --data @/tmp/loop_report.json http://localhost:8080/api/v1/loop-reports)
echo "HTTP $code"
if [ "$code" = "201" ] || [ "$code" = "200" ]; then
  python3 -c "import json;d=json.load(open('/tmp/loop_report_resp.json')).get('data',{});print('  stored id:',d.get('id'),'status:',d.get('status'),'type:',d.get('reportType'))"
else
  head -c 500 /tmp/loop_report_resp.json
fi
rm -f /tmp/loop_report.json /tmp/loop_report_resp.json
REMOTE
