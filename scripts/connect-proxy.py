#!/usr/bin/env python3
"""A minimal HTTP CONNECT proxy (stdlib only) for the IDX desk to reach www.idx.co.id through another host.

Runs on the VPS bound to 127.0.0.1 only; the laptop reaches it over an SSH local forward. It tunnels raw bytes, so the
TLS session is the laptop's own (nothing is decrypted here), and it only accepts CONNECT to a small allowlist of hosts.

  python3 connect-proxy.py 8118
"""
from __future__ import annotations

import select
import socket
import sys
import threading

ALLOW = {"www.idx.co.id", "idx.co.id"}
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8118


def pipe(a: socket.socket, b: socket.socket) -> None:
    socks = [a, b]
    try:
        while True:
            r, _, x = select.select(socks, [], socks, 120)
            if x or not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    finally:
        for s in socks:
            try:
                s.close()
            except OSError:
                pass


def handle(client: socket.socket) -> None:
    try:
        client.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 8192:
            chunk = client.recv(4096)
            if not chunk:
                return
            head += chunk
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = line.split()
        if len(parts) < 2 or parts[0] != "CONNECT":
            client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n\r\n")
            return
        host, _, port = parts[1].partition(":")
        if host not in ALLOW:
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            return
        upstream = socket.create_connection((host, int(port or 443)), timeout=30)
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        client.settimeout(None)
        pipe(client, upstream)
    except Exception:
        try:
            client.close()
        except OSError:
            pass


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(16)
    print(f"connect proxy on 127.0.0.1:{PORT} for {sorted(ALLOW)}", flush=True)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
