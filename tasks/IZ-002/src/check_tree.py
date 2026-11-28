"""検査 C13: /api/tree が DB の全グループ・全品番・注記・件数をそのまま返すこと（DB から数え直して照合）。"""
import atexit, hashlib, http.client, json, os, socket, sqlite3, subprocess, sys, time
from pathlib import Path

T = Path(__file__).resolve().parent.parent
db = T / "out" / "_chk13.db"
db.parent.mkdir(exist_ok=True)
db.unlink(missing_ok=True)
subprocess.run([sys.executable, str(T / "src" / "build_db.py"), "--src", str(T.parent / "IZ-001" / "out"), "--out", str(db)], check=True, stdout=subprocess.DEVNULL)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
p = subprocess.Popen([sys.executable, str(T / "src" / "serve_local.py"), "--db", str(db), "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(p.kill)
for _ in range(80):
    if socket.socket().connect_ex(("127.0.0.1", port)) == 0:
        break
    time.sleep(0.25)


def H(m, u):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request(m, u)
    r = c.getresponse()
    return r.status, r.read()


st, body = H("GET", "/api/tree")
J = json.loads(body)
c = sqlite3.connect(db)
q = lambda x, *a: c.execute(x, a).fetchall()
blob = (lambda d: hashlib.sha1(b"blob " + str(len(d)).encode() + b"\x00" + d).hexdigest())(db.read_bytes())
G = q("select group_id, family, front_g, back_g, front_section, front_feature, back_section, group_flow from product_groups order by sort_key")
GN = {}
for t, k, x in q("select target_id, kind, text from notes where scope='group' order by note_id"):
    GN.setdefault(t, []).append([k, x])
PN = dict(q("select target_id, count(*) from notes where scope='product' group by target_id"))
RN = dict(q("select product_id, count(*) from routing_steps group by product_id"))
BN = dict(q("select product_id, count(*) from bom_lines group by product_id"))
PR = {}
for pid, name, judge, gid in q("select product_id, product_name, judge, group_id from products order by sort_key"):
    PR.setdefault(gid, []).append([pid, name, judge, RN.get(pid, 0), BN.get(pid, 0), PN.get(pid, 0)])
fam = []
for g in G:
    if g[1] not in fam:
        fam.append(g[1])
bad = []
if st != 200 or J.get("version") != blob:
    bad.append("status/version")
if J.get("families") != fam:
    bad.append("families")
if [list((x["group_id"], x["family"], x["front_g"], x["back_g"], x["front_section"], x["front_feature"], x["back_section"], x["group_flow"])) for x in J.get("groups", [])] != [list(g) for g in G]:
    bad.append("groups")
for x in J.get("groups", []):
    if [[n["kind"], n["text"]] for n in x["notes"]] != GN.get(x["group_id"], []):
        bad.append("notes:" + x["group_id"])
    if [[p["product_id"], p["product_name"], p["judge"], p["routing_n"], p["bom_n"], p["notes_n"]] for p in x["products"]] != PR.get(x["group_id"], []):
        bad.append("products:" + x["group_id"])
n = q("select count(*) from products")[0][0]
if sum(len(x["products"]) for x in J.get("groups", [])) != n or not n:
    bad.append("product total")
st2, mb = H("GET", "/api/meta")
M = json.loads(mb)
if J.get("counts") != M["counts"] or J.get("global_notes") != M["global_notes"]:
    bad.append("counts/global_notes")
if H("POST", "/api/tree")[0] != 404:
    bad.append("POST not 404")
print("groups", len(J.get("groups", [])), "products", n, "bad", bad[:5])
sys.exit(1 if bad else 0)
