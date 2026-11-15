#!/usr/bin/env python3
"""Minimal MCP server (stdio, JSON-RPC 2.0): the smallest thing /dev/raid accepts as a plugin."""
import json, sys

TOOLS = [
    {"name": "echo", "description": "Return the text you send (read-only: no approval needed)",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
     "annotations": {"readOnlyHint": True}},
    {"name": "note", "description": "Pretend to save a note (not read-only: /dev/raid asks the user every time)",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
]

def reply(i, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": i}
    msg.update({"error": error} if error else {"result": result})
    print(json.dumps(msg), flush=True)

for line in sys.stdin:
    try: m = json.loads(line)
    except ValueError: continue
    i, method, p = m.get("id"), m.get("method"), m.get("params") or {}
    if method == "initialize":
        reply(i, {"protocolVersion": p.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "hello", "version": "0.1.0"}})
    elif method == "tools/list":
        reply(i, {"tools": TOOLS})
    elif method == "tools/call":
        text = (p.get("arguments") or {}).get("text", "")
        reply(i, {"content": [{"type": "text", "text": f"{p.get('name')}: {text}"}]})
    elif i is not None:
        reply(i, error={"code": -32601, "message": "unknown method"})
