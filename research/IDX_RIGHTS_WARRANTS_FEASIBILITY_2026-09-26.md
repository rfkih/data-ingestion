# IDX rights (HMETD) and warrants: can the desk get their prices? (2026-09-26)

Read-only feasibility check. Nothing was built, written to the database, or committed. Network use: about 12 IDX
requests through the ingest's own `curl_cffi` transport (5 JSON API calls, 3 page HTMLs, 16 static JS bundles to
find the API names), 4 Stockbit GETs using the stored session (no token printed or saved), 2 Yahoo GETs, and 2 KSEI
pages.

## Verdict

**GO for a later arbitrage study.** Daily OHLCV history for rights and warrants is available from Stockbit, back to
at least 2020 and including expired codes. The endpoint is the one `jobs/bar_open.py` already calls. The universe of
codes comes from IDX's monthly statistics. The terms (exercise price, ratio, window) are the weak part. For live
securities they can be read from KSEI. For historical ones they have to be parsed from announcement PDFs. Intraday
prices are unverified.

## 1. What the desk ingests today: nothing for rights or warrants

- `idx.daily_summary` has 0 codes containing '-'. This is **not an ETL filter**. The raw IDX
  `TradingSummary/GetStockSummary` payloads in bronze (`C:/Project/data/idx/bronze/stock_summary/...`) contain no
  rights or warrant rows. I checked 2021-06-15, and 2026-07-10/15/20, which fall inside the BNBR-R/PADI-R/SINI-R
  trading windows. The only non-alpha codes are preferred shares (`GOTOM`, `MAMIP`, `MYRXP`).
- `ListedCompany/GetTradingInfoSS?code=KOCI-W` and `?code=BNBR-R` both return HTTP 200 with `replies: []`. The
  per-code IDX history has no data for these securities.
- IDX has **no public daily per-security summary** for rights or warrants. The only daily "Ringkasan" pages are for
  stocks, indices, brokers and structured warrants (the `DR`/`HD`/`BQ` issuers' SWs, which are a different
  instrument). What IDX does publish, all through `primary/DigitalStatistic/GetApiDataPaginated?urlName=...&periodYear=Y&periodMonth=M&periodType=monthly&isPrint=False&cumulative=false&pageSize=500&pageNumber=1`,
  is listed below. It worked through the impersonating client with the API headers.

| urlName | What it returns | Useful for |
|---|---|---|
| `LINK_TRADING_SUMMARY_WARRANT` | One row per warrant per **month**: `Name, Code, High, Low, Close, Volume, Value, Freq, Day` (days traded). 2026-07: 15 warrants. 2020-06: 67 warrants. | The **warrant universe per month** from 2020 onward, plus sanity checks against Stockbit's monthly high/low |
| `LINK_TRADING_SUMMARY_RIGHT` | Same shape for rights, split by `Board` (RG/TN/NG). Codes carry the expiry date, e.g. `PEGE-R20260717`, `BNBR-R20260727`. 2026-07: 9 rights. | The **rights universe** and the last trading date per issue. This matters because `XXXX-R` is reused across issues. |
| `LINK_DAILY_RIGHT_CERTIFICATE` | Daily **market-wide aggregates** only (rightsVol/Value/Freq, warrantVol/Value/Freq, ETF, REIT...) | Not useful for prices |
| `LINK_RIGHT_OFFERING` | The schema is right (`code, issuerName, ratio, rightCert, sharesIssued, exPrice, fundRaised, exDate, recDate`), but it returned **0 rows** for 2026-07 and 2025-07 | Would be the historical terms table if the right parameters are found (another `periodType`?). Not resolved. |

## 2. Stockbit: works, and this is the price source

`GET https://exodus.stockbit.com/company-price-feed/historical/summary/{CODE}?period=HS_PERIOD_DAILY&start_date=&end_date=&limit=50&page=N`
uses the same bearer, headers and pacing as `bar_open.fetch_stockbit`. The codes are the plain exchange codes.

| Code | Result |
|---|---|
| `ISAP-W` (live warrant) | 200. 50 rows per page from 2026-07-16 to 2026-09-25 |
| `BNBR-R` (July 2026 right, now expired) | 200. 14 rows, with trading on 2026-07-14 (Rp 31 bn value) |
| `BRPT-W` (2020 warrant, long gone) | 200. 50 rows covering 2020-05 to 2020-07 |
| `FORU-R` (right trading today) | 200. The 2026-09-25 row |

- **Fields:** `date, open, high, low, close, average, volume (lots), value (IDR), frequency, foreign_buy/sell, net_foreign, change, change_percentage`.
- **Depth:** 2020 is confirmed. Expired and delisted codes still answer. Each request returns at most 50 rows over
  about a year, and needs pagination.
- **Caveat: padded rows.** After a right stops trading, Stockbit keeps returning rows with `volume 0` and the close
  carried forward (BNBR-R on 2026-07-30/31). Keep only `volume > 0` and dates inside the official trading window.
- **Caveat: code reuse.** `XXXX-R` and `XXXX-W` are reused by later issues. Each series has to be fetched by the
  date window taken from the IDX monthly rights/warrant tables and the announcements.
- **Intraday:** not verified. The tick collector (`idx/feed/collector.py`) subscribes to whatever is in
  `idx.feed_symbol`. Whether Stockbit's websocket streams `-W`/`-R` codes is untested. Adding one warrant to
  `feed_symbol` for a day would answer it. There is no intraday history.

## 3. Public alternatives and contract terms

- **Yahoo:** `ISAP-W.JK` and `ISAPW.JK` both return "No data found". Yahoo has no IDX warrants or rights. That is a no.
- **KSEI registry pages** (`web.ksei.co.id/services/registered-securities/warrants` and `/rights`): `Kode, Deskripsi,
  Emiten, EXE Price, Maturity`, **active securities only**. Today that is 11 warrants (e.g. COCO-W 800 / 2031-07-11,
  CYBR-W 200, PYFA-W 800) and 2 rights (FORU-R 126 / 2026-10-06, BAJA-R 500 / 2026-10-07). This is good for a
  daily terms snapshot going forward. It has no ratio (warrants are normally 1:1) and no history.
- **`idx.announcement`:** 153,618 rows from 2023-07-03 to 2026-09-25. **`extracted_text` is NULL in every row**, so
  the terms are only available in the PDF attachments (`attachments[].FullSavePath`). There are 2,943 titles
  containing "waran", 890 containing "HMETD", and 52 exchange-issued codes like `KOCI-W` / `BNBR-R` (23 `-W`, 18 `-R`,
  2 `-W2`) with notices such as "Batas Akhir Perdagangan HMETD", "Peniadaan Perdagangan Waran" and delisting
  reminders. Parsing the prospectus and "Informasi kepada pemegang saham" PDFs gives the ratio, the exercise price
  and the trading/exercise windows. This coverage does not reach before 2023-07.
- **`idx.corporate_action`:** `rights_or_bonus` has **144 rows** (2020-03-30 to 2026-09-22, not the 585 the brief
  mentioned; 217 rows across all kinds). All of them come from `previous_reset`, and none has an `announcement_id`.
  They give the ex-date and the adjustment factor. You cannot solve that factor for both the ratio and the exercise
  price. It is still usable as a cross-check (TERP implied by ratio × price).

## 4. What an ingestion job would need

1. **Universe:** monthly `LINK_TRADING_SUMMARY_WARRANT` / `_RIGHT` for 2020-01..now. That is about 160 requests,
   once. Store each code with its active months, and the right's expiry suffix.
2. **Prices:** for each (code, window), page through the Stockbit `historical/summary` endpoint. At roughly 1 page per
   right and 1–3 per warrant-year, that is a few thousand requests at 0.7 s, about an hour. Write to a new
   `idx.deriv_bar(code, series_key, trade_date, ohlcv...)`, not to `idx.bar`. Drop padded zero-volume rows. Going
   forward, a nightly job does the same for codes active this month.
3. **Terms:** a daily KSEI snapshot for live securities. For history, a PDF parser over the HMETD and waran
   announcements (2023-07 onward), plus a manual or prospectus backfill for 2020–2023. Also try to make
   `LINK_RIGHT_OFFERING` return rows, since it would supply ratio, exPrice and exDate directly.
4. **Underlying:** `idx.daily_summary` / `idx.bar` already has the stock close.

## 5. What the arbitrage study must handle

Illustration only: on 2026-09-25, FORU closed at 360 and FORU-R closed at 4 (range 3–15) with an exercise price of
126. The paper intrinsic value is about 234 per right. That gap is far too large to be real edge. The causes to
examine are:

- The stock sitting in an ARA-locked or illiquid run after the ex-date, so the 360 cannot actually be sold.
- The settlement lag between exercise and the listing of the new shares, with the price exposed in between.
- Minimum lot and fee drag at Rp 1–15 prices.
- Special-monitoring (FCA) boards.

The study has to model exercise-to-sale latency and whether the stock can be sold, not just `close − strike`.
