"""News collection and consensus snapshots: the pure parts."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from blackheart_ingest.idx import consensus as CS
from blackheart_ingest.idx import news as NW

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>BBRI cetak laba Rp 30 triliun</title><link>https://x/1</link><description>&lt;p&gt;Bank Rakyat Indonesia naik&lt;/p&gt;</description>
<pubDate>Mon, 14 Sep 2026 10:00:00 +0700</pubDate></item>
<item><title>Tanpa link</title></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Elnusa raih kontrak</title>
<link href="https://x/2"/><summary>ELSA dapat kontrak baru</summary><published>2026-09-14T03:00:00Z</published></entry></feed>"""


def test_parse_rss_and_atom() -> None:
    items = NW.parse_feed(RSS)
    assert len(items) == 1 and items[0]["url"] == "https://x/1" and items[0]["summary"] == "Bank Rakyat Indonesia naik"
    assert items[0]["published_at"].hour == 10
    atom = NW.parse_feed(ATOM)
    assert atom[0]["url"] == "https://x/2" and atom[0]["published_at"].year == 2026
    assert NW.parse_feed(b"not xml") == []


def test_tag_codes_by_ticker_and_by_name() -> None:
    aliases = {"bank rakyat indonesia": "BBRI", "elnusa": "ELSA"}
    tickers = {"BBRI", "ELSA", "GJTL"}
    assert NW.tag_codes("Bank Rakyat Indonesia naik, GJTL turun", aliases, tickers) == ["BBRI", "GJTL"]
    assert NW.tag_codes("Elnusa raih kontrak", aliases, tickers) == ["ELSA"]
    assert NW.tag_codes("KATA biasa saja", aliases, tickers) == []            # a 4-letter word that is not a ticker


def test_consensus_snapshot_row() -> None:
    row = CS.snapshot_row("BBNI", {"currentPrice": 3680, "targetMeanPrice": 4449, "numberOfAnalystOpinions": 23, "recommendationMean": 1.9,
                                   "recommendationKey": "buy", "forwardPE": 5.5}, date(2026, 9, 14))
    assert row["n_analysts"] == 23 and row["reco_key"] == "buy" and round(row["upside_pct"], 1) == Decimal("20.9")
    assert CS.snapshot_row("GJTL", {"currentPrice": 1335}, date(2026, 9, 14)) is None
