"""IZ-002 API の本体。serve_local と、IZ-003 の Vercel で同じものを使う。
STORE（LocalStore か GitHubStore）は serve_local が入れる。無ければ GitHub の設定（環境変数）から作る。"""
import json, sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bomlib  # noqa: E402
import store as storemod  # noqa: E402

STORE = None


def get_store():
    global STORE
    if STORE is None:
        STORE = storemod.GitHubStore(storemod.load_env(Path(__file__).resolve()))
    return STORE


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 標準のログに URL・内容を出さない
        pass

    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _api_get(self, path, q):
        st = get_store()
        with st.reading() as (c, v):
            if path == "/api/meta":
                return self._send(200, bomlib.meta(c, v))
            if path == "/api/canvas.svg":
                return self._send(200, bomlib.canvas_svg(c, v).encode("utf-8"), "image/svg+xml; charset=utf-8")
            if path == "/api/tree":
                return self._send(200, bomlib.tree(c, v))
            if path == "/api/items":
                return self._send(200, bomlib.items(c, v))
            if path == "/api/product":
                d = bomlib.product(c, v, (q.get("id") or [""])[0])
                return self._send(200 if d else 404, d or {"error": "その品番はありません"})
            if path == "/api/group":
                d = bomlib.group(c, v, (q.get("id") or [""])[0])
                return self._send(200 if d else 404, d or {"error": "そのグループはありません"})
        return self._send(404, {"error": "見つかりません"})

    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path.startswith("/api/"):
                return self._api_get(u.path, parse_qs(u.query))
            return self._send(404, {"error": "見つかりません"})
        except storemod.StoreError as e:
            return self._send(502, {"ok": False, "error": str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/edit":
            return self._send(404, {"error": "見つかりません"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else None
        except Exception:
            body = None
        if not isinstance(body, dict) or body.get("op") not in bomlib.OPS:
            return self._send(400, {"ok": False, "error": "操作が読めないか、知らない操作です"})
        if not isinstance(body.get("base_version"), str) or not body["base_version"]:
            return self._send(400, {"ok": False, "error": "base_version がありません（画面を読み込み直してください）"})
        try:
            res = get_store().edit(body)
            res["ok"] = True
            return self._send(200, res)
        except storemod.Conflict as e:
            return self._send(409, {"ok": False, "error": "conflict", "version": e.version})
        except bomlib.BadRequest as e:
            return self._send(400, {"ok": False, "error": str(e)})
        except storemod.StoreError as e:
            return self._send(502, {"ok": False, "error": str(e)})
