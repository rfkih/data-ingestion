"""``python -m idx_mcp`` serves the desk over stdio (what Claude Code launches); ``--smoke`` just calls the ingest API
once and prints the desk status, to check the wiring without an MCP client."""
from __future__ import annotations

import argparse
import json
import sys

from .client import IdxApiError
from .server import api, server


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="idx-mcp", description="Blackheart IDX desk MCP server")
    p.add_argument("--smoke", action="store_true", help="call /idx/ops once and print a summary, then exit")
    args = p.parse_args(argv)
    if args.smoke:
        try:
            d = api().get("/ops")
        except IdxApiError as e:
            print(f"FAIL {e}", file=sys.stderr)
            return 1
        tools = [t.name for t in server._tool_manager.list_tools()] if hasattr(server, "_tool_manager") else []
        print(json.dumps({"api": api().base_url, "last_bar_date": d.get("last_bar_date"), "open_alerts": len(d.get("open_alerts") or []),
                          "active_listings": d.get("active_listings"), "tools": len(tools)}, indent=1))
        return 0
    server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
