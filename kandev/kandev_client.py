"""Kandev 外部 MCP 的最小客户端（只用标准库）。build_workflows.py、stage.py、verify_export.py、ma.py 共用。"""
import json
import urllib.request

DEFAULT_URL = "http://localhost:38429/mcp"
HDR = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class Kandev:
    def __init__(self, url=None, client="ma-builder", version="0"):
        self.url = url or DEFAULT_URL
        self.sid, _ = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": client, "version": version}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, self.sid)

    def _post(self, payload, sid=None):
        h = dict(HDR)
        if sid:
            h["Mcp-Session-Id"] = sid
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            sid2 = r.headers.get("Mcp-Session-Id")
            raw = r.read().decode("utf-8")
        if raw.startswith(("event:", "data:")):
            datas = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
            raw = datas[-1] if datas else "{}"
        return sid2, (json.loads(raw) if raw.strip() else None)

    def call(self, name, args):
        _, res = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                             "params": {"name": name, "arguments": args}}, self.sid)
        r = res.get("result", {})
        txt = "\n".join(c.get("text", "") for c in r.get("content", []))
        if "error" in res or r.get("isError"):
            raise RuntimeError(f"{name} failed: {txt or res}")
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            return txt
