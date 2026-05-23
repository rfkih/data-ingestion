# Blackheart monitoring stack

Local observability for the trading + research JVMs. Brought up as part of
Stage 1 of the live-monitoring roadmap (2026-05-17). Bound to `127.0.0.1`
only — not internet-reachable.

## Components

| Service | Port | Image | Purpose |
|---|---|---|---|
| VictoriaMetrics | 127.0.0.1:8428 | `victoriametrics/victoria-metrics:v1.106.1` | Prometheus-compatible TSDB. Scrapes `/actuator/prometheus` on both JVMs every 15s. 90-day retention. |
| Grafana | 127.0.0.1:3001 | `grafana/grafana:11.3.1` | Dashboards. Default login `admin` / `admin`. |

Both run as `docker compose` services in `/c/Project/docker-compose.yml`.
Configuration files live under `/c/Project/monitoring/`:

- `victoriametrics/prometheus.yml` — scrape targets.
- `grafana/provisioning/datasources/` — auto-wires VictoriaMetrics as the
  default datasource on first boot.
- `grafana/provisioning/dashboards/` — dashboards (Stage 1e — not yet built
  at the time of writing).

## Operating cheat sheet

```bash
# Bring up
docker compose up -d victoriametrics grafana

# Tear down (data preserved in named volumes)
docker compose stop victoriametrics grafana

# Tear down and wipe data (irreversible — drops 90d of TSDB history)
docker compose down victoriametrics grafana
docker volume rm blackheart_vmdata blackheart_grafanadata

# Verify scrape state
curl -s http://127.0.0.1:8428/health
curl -s http://127.0.0.1:8428/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health, lastError: .lastError}'

# Sample a metric
curl -s 'http://127.0.0.1:8428/api/v1/query?query=blackheart_binance_ws_connected'
```

## Auth model

`/actuator/prometheus` is whitelisted **unauthenticated** in
`SecurityConfig.java`, but **only from RFC1918 private ranges + loopback**:

- `127.0.0.1` / `::1` (loopback)
- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

VictoriaMetrics scrapes via `host.docker.internal:<port>` which lands in one
of those ranges (Docker Desktop's gateway IP). Any other path (`/actuator/**`
other than `/actuator/prometheus` and the public health probes) still
requires an ADMIN JWT.

## DEPLOYMENT CAVEAT — reverse proxies

> **Read this before putting the trading JVM behind nginx / traefik / any
> reverse proxy in production.**

The IP whitelist uses `request.getRemoteAddr()`. When a reverse proxy
forwards traffic, `getRemoteAddr()` returns the proxy's IP — which will land
in `172.16.0.0/12` (Docker) or `192.168.0.0/16` (LAN). That means **anyone
who can reach the proxy can scrape `/actuator/prometheus` unauthenticated**,
including any sensitive labelled metrics.

Two ways to harden when introducing a proxy:

1. **Configure Spring's `ForwardedHeaderFilter`** (`server.forward-headers-strategy=NATIVE`)
   and have the proxy set `X-Forwarded-For` correctly. Spring will then
   use the original client IP for `getRemoteAddr()`, and the IP whitelist
   works as designed.
2. **Block `/actuator/prometheus` at the proxy layer** — never expose it
   through the proxy at all. Run a separate scrape-only socket on
   `127.0.0.1:<management.server.port>` and have Prometheus hit that
   directly.

Option 2 is the institutional default. Option 1 is acceptable if the proxy's
`X-Forwarded-For` policy is well-controlled.

## Metric inventory (Stage 1d, 2026-05-17)

| Metric | Type | Source file | Labels |
|---|---|---|---|
| `blackheart_risk_gate_denial_total` | Counter | `RiskGuardService` | gate, strategy_code, side |
| `blackheart_kill_switch_tripped_total` | Counter | `RiskGuardService` | strategy_code |
| `blackheart_binance_ws_connected` | Gauge | `BinanceWebSocketClient` | stream |
| `blackheart_binance_ws_last_message_age_seconds` | Gauge | `BinanceWebSocketClient` | stream |
| `blackheart_binance_api_latency_seconds` | Timer | `BinanceClientService` | endpoint, status |
| `blackheart_open_trades` | Gauge | `TradingDomainMetricsExporter` | strategy_code, asset, side |
| `blackheart_oldest_open_trade_age_seconds` | Gauge | `TradingDomainMetricsExporter` | strategy_code, asset |
| `blackheart_trades_closed_24h` | Gauge | `TradingDomainMetricsExporter` | strategy_code, asset |
| `blackheart_realized_pnl_24h` | Gauge | `TradingDomainMetricsExporter` | strategy_code, asset |
| `blackheart_trades_wins_24h` | Gauge | `TradingDomainMetricsExporter` | strategy_code, asset |

Plus Spring Boot defaults: JVM (heap/GC/threads), Tomcat, HikariCP, HTTP
request rates/latencies, scheduled-task execution, resilience4j circuit
breakers, and one pre-existing custom counter
(`blackheart_ml_shadow_log_persist_failed_total`).
