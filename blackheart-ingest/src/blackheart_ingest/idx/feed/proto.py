"""Wire codec for the Stockbit datafeed websocket (``wss://wss-jkt.trading.stockbit.com/ws``, subprotocol ``web``).

The feed speaks protobuf (``securities.transactional.datafeed.v1``); the message shapes below were read from the web
app's generated descriptors on 2026-09-21. Only the handful of fields the collector needs are modelled, with a small
hand-written encoder/decoder so the package carries no generated code and no protobuf dependency.

Client -> server: ``WebsocketRequest``
    1 user_id (string)   2 channel (WebsocketChannel)   3 key (string)   4 ping (PingRequest{1 message})   5 access_token (string)
``WebsocketChannel`` (all repeated string unless noted)
    1 watchlist  2 order_book  3 running_trade  4 is_hotlist (bool)  5 running_trade_batch  6 liveprice  7 iepiev  8 intraday
    9 best_bid_offer  12 liveprice_v3  13 order_book_v3  14 intraday_v3
Server -> client: ``WebsocketWrapMessageChannel`` (oneof message_channel)
    2 ping (PingResponse{1 message})   7 error (Error{1 code enum, 2 message})
    9 liveprice (LivePrice)   10 orderbook (Orderbook)   12 intraday (Intraday)   others ignored
``LivePrice``: 1 stock_code  2 lastprice(d)  3 volume(d)  4 high(d)  5 low(d)  6 open(d)  7 frequency(d)  8 frg_buy(d)
    9 frg_sell(d)  10 average(d)  11 date(s, ISO with offset)  12 close(d)  13 prev(d)  14 value(d)  15 change{1 value 2 pct}
    16 order_verb(s)  17 quantity(i64)  18 is_index  19 sequence_number(i64)  20 order_book_id  21 order_number
    22 match_number  23 board(enum)  24 source(enum)  25 switch_reset  26 itch_incoming_time(s)  27 trade_trigger  28 lot(d)
``Orderbook``: 1 stock_code  2 body(s: ``#O|CODE|BID|price;orders;volume|...``, one side per message)  3 sequence_number
    4 order_book_id  5 datetime(s)  6 source  7 switch_reset  8 board  9 itch_incoming_time(s)
``Intraday``: 1 stock_code  2 datetime  3 open  4 high  5 low  6 close  7 volume  8 change  9 lot
"""
from __future__ import annotations

import struct
from typing import Any

# ---- low level ------------------------------------------------------------------------------------------------------


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    shift, n = 0, 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def _ld(no: int, payload: bytes) -> bytes:
    return _varint((no << 3) | 2) + _varint(len(payload)) + payload


def _str(no: int, s: str) -> bytes:
    return _ld(no, s.encode("utf-8"))


def _bool(no: int, v: bool) -> bytes:
    return _varint(no << 3) + _varint(1 if v else 0)


def decode(buf: bytes) -> list[tuple[int, int, Any]]:
    """Raw fields of one message: (field number, wire type, value). Length-delimited values stay bytes; 64-bit values
    come back as the raw 8 bytes (the caller knows whether that is a double or a fixed int)."""
    out: list[tuple[int, int, Any]] = []
    i = 0
    while i < len(buf):
        tag, i = _read_varint(buf, i)
        no, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = _read_varint(buf, i)
        elif wt == 1:
            v, i = buf[i:i + 8], i + 8
        elif wt == 2:
            ln, i = _read_varint(buf, i)
            v, i = buf[i:i + ln], i + ln
        elif wt == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wt} for field {no}")
        out.append((no, wt, v))
    return out


def fields(buf: bytes) -> dict[int, list[Any]]:
    d: dict[int, list[Any]] = {}
    for no, _, v in decode(buf):
        d.setdefault(no, []).append(v)
    return d


def as_double(v: Any) -> float | None:
    if isinstance(v, (bytes, bytearray)) and len(v) == 8:
        return struct.unpack("<d", v)[0]
    return None


def as_str(v: Any) -> str:
    return v.decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else str(v)


# ---- requests -------------------------------------------------------------------------------------------------------

CHANNEL_FIELDS = {"watchlist": 1, "order_book": 2, "running_trade": 3, "running_trade_batch": 5, "liveprice": 6, "iepiev": 7,
                  "intraday": 8, "best_bid_offer": 9, "liveprice_v3": 12, "order_book_v3": 13, "intraday_v3": 14}


def encode_channel(channels: dict[str, list[str]], *, hotlist: bool = False) -> bytes:
    out = bytearray()
    for name, codes in channels.items():
        no = CHANNEL_FIELDS[name]
        for c in codes:
            out += _str(no, c)
    if hotlist:
        out += _bool(4, True)
    return bytes(out)


def encode_request(*, user_id: str | None = None, key: str | None = None, access_token: str | None = None,
                   channels: dict[str, list[str]] | None = None, ping: str | None = None) -> bytes:
    """``WebsocketRequest``. Auth = user_id + key + access_token; subscribe = the same plus channels; ping = ping only."""
    out = bytearray()
    if user_id is not None:
        out += _str(1, user_id)
    if channels is not None:
        out += _ld(2, encode_channel(channels))
    if key is not None:
        out += _str(3, key)
    if ping is not None:
        out += _ld(4, _str(1, ping))
    if access_token is not None:
        out += _str(5, access_token)
    return bytes(out)


# ---- responses ------------------------------------------------------------------------------------------------------

LIVEPRICE_DOUBLES = {2: "lastprice", 3: "volume", 4: "high", 5: "low", 6: "open", 7: "frequency", 8: "frg_buy", 9: "frg_sell",
                     10: "average", 12: "close", 13: "prev", 14: "value", 28: "lot"}
LIVEPRICE_STRINGS = {1: "stock_code", 11: "date", 16: "order_verb", 26: "itch_incoming_time"}
LIVEPRICE_INTS = {17: "quantity", 19: "sequence_number", 20: "order_book_id", 21: "order_number", 22: "match_number", 23: "board", 24: "source"}


def decode_liveprice(buf: bytes) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for no, wt, v in decode(buf):
        if no in LIVEPRICE_DOUBLES and wt == 1:
            d[LIVEPRICE_DOUBLES[no]] = as_double(v)
        elif no in LIVEPRICE_STRINGS and wt == 2:
            d[LIVEPRICE_STRINGS[no]] = as_str(v)
        elif no in LIVEPRICE_INTS and wt == 0:
            d[LIVEPRICE_INTS[no]] = v
        elif no == 15 and wt == 2:
            ch = fields(v)
            d["change"] = as_double(ch.get(1, [None])[0]) if 1 in ch else None
            d["change_pct"] = as_double(ch.get(2, [None])[0]) if 2 in ch else None
        elif no == 27 and wt == 2:
            tt = fields(v)
            d["trade_trigger"] = {"quantity": tt.get(2, [None])[0], "price": as_double(tt.get(3, [None])[0]) if 3 in tt else None,
                                  "timestamp": as_str(tt[6][0]) if 6 in tt else None}
    return d


def decode_orderbook(buf: bytes) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for no, wt, v in decode(buf):
        if no == 1 and wt == 2:
            d["stock_code"] = as_str(v)
        elif no == 2 and wt == 2:
            d["body"] = as_str(v)
        elif no == 3 and wt == 0:
            d["sequence_number"] = v
        elif no == 5 and wt == 2:
            d["datetime"] = as_str(v)
        elif no == 8 and wt == 0:
            d["board"] = v
        elif no == 9 and wt == 2:
            d["itch_incoming_time"] = as_str(v)
    return d


def decode_intraday(buf: bytes) -> dict[str, Any]:
    names = {3: "open", 4: "high", 5: "low", 6: "close", 7: "volume", 9: "lot"}
    d: dict[str, Any] = {}
    for no, wt, v in decode(buf):
        if no == 1 and wt == 2:
            d["stock_code"] = as_str(v)
        elif no == 2 and wt == 2:
            d["datetime"] = as_str(v)
        elif no in names and wt == 1:
            d[names[no]] = as_double(v)
    return d


def decode_frame(buf: bytes) -> dict[str, Any]:
    """One server frame -> {"kind": ping|error|liveprice|orderbook|intraday|other, ...payload}."""
    for no, wt, v in decode(buf):
        if wt != 2:
            continue
        if no == 2:
            f = fields(v)
            return {"kind": "ping", "message": as_str(f[1][0]) if 1 in f else ""}
        if no == 7:
            f = fields(v)
            return {"kind": "error", "code": f.get(1, [None])[0], "message": as_str(f[2][0]) if 2 in f else ""}
        if no == 9:
            return {"kind": "liveprice", **decode_liveprice(v)}
        if no == 10:
            return {"kind": "orderbook", **decode_orderbook(v)}
        if no == 12:
            return {"kind": "intraday", **decode_intraday(v)}
        return {"kind": "other", "field": no, "len": len(v)}
    return {"kind": "empty"}
