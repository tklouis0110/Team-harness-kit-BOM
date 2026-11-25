"""IZ-002 規則 E: 保存先。LocalStore = 手元のファイル、GitHubStore = GitHub の contents API（方式 A）。
どちらも「版 = DB ファイルの git blob SHA-1」。編集は一時ファイルに当ててから書き戻す。トークンは画面・ログ・エラーに出さない。"""
import base64, json, os, shutil, sqlite3, tempfile, threading, urllib.error, urllib.request
from contextlib import contextmanager
from pathlib import Path

import bomlib


class Conflict(Exception):
    def __init__(self, version):
        self.version = version


class StoreError(Exception):
    """利用者に見せてよい理由（トークンを含めない）。"""


def _connect(path, ro=False):
    if ro:
        c = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    else:
        c = sqlite3.connect(str(path))
    c.execute(bomlib.FOREIGN)
    return c


def _apply(tmp, body):
    """一時ファイルの DB に編集を当てる。BadRequest ならそのまま上へ（tmp は呼び出し側が捨てる）。"""
    c = _connect(tmp)
    try:
        res, target = bomlib.apply_edit(c, body)
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return res, target


class LocalStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _version(self):
        return bomlib.blob_sha1(self.path.read_bytes())

    @contextmanager
    def reading(self):
        with self.lock:
            c = _connect(self.path, ro=True)
            try:
                yield c, self._version()
            finally:
                c.close()

    def edit(self, body):
        with self.lock:
            v = self._version()
            if body["base_version"] != v:
                raise Conflict(v)
            fd, tmp = tempfile.mkstemp(suffix=".db", dir=str(self.path.parent))
            os.close(fd)
            try:
                shutil.copyfile(self.path, tmp)
                res, _ = _apply(tmp, body)
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            res["version"] = self._version()
            return res


def load_env(start):
    """環境変数が無ければ、リポジトリの直下の .env を読む（中身は表示しない）。"""
    env = dict(os.environ)
    p = Path(start).resolve()
    for d in [p] + list(p.parents):
        f = d / ".env"
        if f.is_file():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break
    return env


class GitHubStore:
    API = "https://api.github.com"

    def __init__(self, env):
        self.token = env.get("GITHUB_TOKEN", "")
        self.repo = env.get("GITHUB_REPO", "")
        self.branch = env.get("GITHUB_BRANCH") or "main"
        self.path = env.get("GITHUB_DB_PATH") or "tasks/IZ-002/data/bom.db"
        if not self.token or not self.repo:
            raise StoreError("GITHUB_TOKEN と GITHUB_REPO の設定がありません（環境変数か .env）")
        self.cache = Path(tempfile.gettempdir()) / "bom-web-cache"
        self.cache.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self._sha = None

    def _req(self, method, url, body=None, accept="application/vnd.github+json"):
        h = {"Authorization": "Bearer " + self.token, "Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "bom-web"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        rq = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(rq, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:  # 接続の失敗など。トークンは文に入れない
            raise StoreError("GitHub に接続できませんでした: " + type(e).__name__)

    def _url(self):
        from urllib.parse import quote
        return f"{self.API}/repos/{self.repo}/contents/{quote(self.path)}"

    def _remote_sha(self):
        from urllib.parse import quote
        st, b = self._req("GET", self._url() + "?ref=" + quote(self.branch))
        if st != 200:
            raise StoreError(f"GitHub からファイルの版を読めませんでした（{st}）")
        return json.loads(b)["sha"]

    def _file(self, sha):
        """sha の中身を一時ファイルに（同じ版の間は使い回す）。"""
        from urllib.parse import quote
        f = self.cache / (sha + ".db")
        if not f.exists():
            st, b = self._req("GET", self._url() + "?ref=" + quote(self.branch), accept="application/vnd.github.raw")
            if st != 200:
                raise StoreError(f"GitHub から DB を読めませんでした（{st}）")
            f.write_bytes(b)
        return f

    @contextmanager
    def reading(self):
        with self.lock:
            sha = self._remote_sha()
            c = _connect(self._file(sha), ro=True)
            try:
                yield c, sha
            finally:
                c.close()

    def edit(self, body):
        with self.lock:
            sha = self._remote_sha()
            if body["base_version"] != sha:
                raise Conflict(sha)
            fd, tmp = tempfile.mkstemp(suffix=".db", dir=str(self.cache))
            os.close(fd)
            try:
                shutil.copyfile(self._file(sha), tmp)
                res, target = _apply(tmp, body)
                data = Path(tmp).read_bytes()
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            st, b = self._req("PUT", self._url(), {"message": f"bom-web: {body['op']} {target}", "content": base64.b64encode(data).decode("ascii"), "sha": sha, "branch": self.branch})
            if st in (409, 422):
                raise Conflict(self._remote_sha())
            if st not in (200, 201):
                raise StoreError(f"GitHub に保存できませんでした（{st}）")
            new = json.loads(b)["content"]["sha"]
            (self.cache / (new + ".db")).write_bytes(data)
            res["version"] = new
            return res
