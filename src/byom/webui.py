"""Tiny local control page (stdlib only) to see and switch the active model."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import state

PORT = 4001

PAGE = """<!doctype html><meta charset=utf-8><title>BYOM</title>
<style>body{font:16px system-ui;max-width:520px;margin:3rem auto}
button{display:block;width:100%;padding:.7rem;margin:.4rem 0;font:inherit;cursor:pointer;
border:1px solid #888;border-radius:8px;background:#fff;text-align:left}
button.on{background:#0a7;color:#fff;border-color:#0a7}</style>
<h2>Copilot BYOM</h2><div id=m></div>
<script>
async function load(){const r=await (await fetch('/api')).json();
m.innerHTML='';for(const a of r.models){const b=document.createElement('button');
b.textContent=(a==r.active?'\\u25cf ':'\\u25cb ')+a;if(a==r.active)b.className='on';
b.onclick=async()=>{await fetch('/api/use',{method:'POST',body:a});load()};m.append(b)}}
load();setInterval(load,3000);
</script>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, ctype: str = "application/json", code: int = 200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path == "/api":
            body = {"active": state.get_active(), "models": state.list_aliases()}
            self._send(json.dumps(body))
        else:
            self._send(PAGE, "text/html")

    def do_POST(self):  # noqa: N802
        # Reject cross-site requests: only the page served from this origin may switch models.
        origin = self.headers.get("Origin")
        if origin and origin != f"http://127.0.0.1:{PORT}":
            return self._send("forbidden", "text/plain", 403)
        if self.path != "/api/use":
            return self._send("not found", "text/plain", 404)
        alias = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        try:
            state.set_active(alias)
        except ValueError as e:
            return self._send(str(e), "text/plain", 400)
        self._send(json.dumps({"active": alias}))

    def log_message(self, *args):
        pass


def serve() -> None:
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
