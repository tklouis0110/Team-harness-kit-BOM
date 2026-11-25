"""IZ-002 手元のサーバ。
python src/serve_local.py --db <DB> --port <番号>   手元のファイルに保存（規則 E2）
python src/serve_local.py --github --port <番号>    GitHub に保存（規則 E3）
127.0.0.1 だけで待つ。--db が data/bom.db を指したら起動せず終了コード 1。"""
import argparse, sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(WEB / "api"))
import index  # noqa: E402
import store as storemod  # noqa: E402

PUBLIC = WEB / "public"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}


class Local(index.handler):
    def do_GET(self):
        p = urlparse(self.path).path
        if p in STATIC:
            name, ctype = STATIC[p]
            f = PUBLIC / name
            if f.is_file():
                return self._send(200, f.read_bytes(), ctype)
            return self._send(404, {"error": "見つかりません"})
        return super().do_GET()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--github", action="store_true")
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args()
    if bool(a.db) == a.github:
        print("--db <DB> か --github のどちらか 1 つを指定してください", file=sys.stderr)
        return 1
    if a.db:
        p = Path(a.db).resolve()
        if p == (HERE.parent / "data" / "bom.db").resolve():
            print("data/bom.db は直接開きません（正本は GitHub。手元で試すときは out/ に写したものを --db で指す）", file=sys.stderr)
            return 1
        if not p.is_file():
            print(f"DB が見つかりません: {a.db}", file=sys.stderr)
            return 1
        index.STORE = storemod.LocalStore(p)
        print("手元のファイルに保存:", p)
    else:
        try:
            index.STORE = storemod.GitHubStore(storemod.load_env(HERE))
        except storemod.StoreError as e:
            print(str(e), file=sys.stderr)
            return 1
        print("GitHub に保存:", index.STORE.repo, index.STORE.branch, index.STORE.path)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Local)
    print(f"http://127.0.0.1:{srv.server_address[1]}/ で待っています")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
