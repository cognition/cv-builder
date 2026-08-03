#!/usr/bin/env python3
"""Run the CV builder MCP server (stdio transport).

Point an MCP client (Claude Desktop, Claude Code, etc.) at this command to
let it search, edit, and compose from the snippet library. See README.md
for client configuration.

Usage: python3 scripts/mcp-server.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cvbuilder.mcp_server import main

if __name__ == "__main__":
    main()
