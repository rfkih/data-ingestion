#!/usr/bin/env bash
# Blackheart self-improvement loop — execution-health monitor (READ-ONLY).
# Regularly checks trade history + execution path for FAILED / blocked executions
# and surfaces the root-cause bucket. No token / no writes — pure diagnostics.
#
# Usage:  bash exec_health_check.sh [LOOKBACK_HOURS]   (default 24)
set -uo pipefail
HOURS="${1:-24}"
KEY="${BH_SSH_KEY:-C:/Project/sshkey.pem}"
HOST="${BH_VPS:-starsky@100.112.13.126}"
PSQL="docker exec blackheart-postgres psql -U postgres -d trading_db -P pager=off -c"

ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=15 "$HOST" "HOURS=$HOURS bash -s" <<'REMOTE'
PSQL="docker exec blackheart-postgres psql -U postgres -d trading_db -P pager=off -c"
echo "===== EXEC-HEALTH @ $(date -u +%FT%TZ)  (lookback ${HOURS}h) ====="

echo "--- 1. live trades in window (by account/strategy/status) ---"
$PSQL "select a.username, t.strategy_name, t.status, count(*) n, coalesce(sum(t.realized_pnl_amount),0)::numeric(18,4) pnl from trades t left join accounts a on a.account_id=t.account_id where t.created_time > now() - interval '${HOURS} hours' group by 1,2,3 order by 1,2,3;"

echo "--- 2. carry_pair failures (any time, last 10) ---"
$PSQL "select symbol,status,simulated,updated_time,updated_by from carry_pair where status in ('FAILED','ERROR') order by updated_time desc limit 10;"

echo "--- 3. order-level rejects / blockers in app log ---"
docker logs blackheart-app --since "${HOURS}h" 2>&1 | grep -aoiE "margin is insufficient|insufficient balance|order failed|-2010|-4164|-1013|-1111 |precision" | sort | uniq -c | sort -rn | head -15
echo "   (empty = no order-execution rejects logged)"

echo "--- 4. live decision mix (HOLD vs entries) ---"
docker logs blackheart-app --since "${HOURS}h" 2>&1 | grep -aoE "decision=(HOLD|OPEN_LONG|OPEN_SHORT|CLOSE_LONG|CLOSE_SHORT)" | sort | uniq -c | sort -rn
echo "   (all HOLD = strategies alive but no qualified setup = signal/edge gap, NOT an exec bug)"

echo "--- 5. top HOLD reasons ---"
docker logs blackheart-app --since "${HOURS}h" 2>&1 | grep -aoE "reason=[^|]+score" | sed -E 's/ score$//' | sort | uniq -c | sort -rn | head -10
echo "===== END ====="
REMOTE
