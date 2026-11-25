"""IZ-002 規則 A・B: IZ-001 の out から SQLite の DB を作る。
python src/build_db.py --src <IZ-001 の out> --out <DB のパス>   （--out が既にあれば何も書かず終了コード 1）"""
import argparse, csv, hashlib, os, sqlite3, sys
from collections import defaultdict
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

FILES = ["item_routing.csv", "groups.csv", "item_steps.csv", "nippo_map.csv", "summary.csv"]
SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE product_groups(group_id TEXT PRIMARY KEY, family TEXT NOT NULL, front_g TEXT NOT NULL, front_section TEXT NOT NULL, front_feature TEXT NOT NULL, back_g TEXT NOT NULL, back_section TEXT NOT NULL, group_flow TEXT NOT NULL, sort_key INTEGER NOT NULL UNIQUE, origin TEXT NOT NULL);
CREATE TABLE products(product_id TEXT PRIMARY KEY, product_name TEXT NOT NULL, family TEXT NOT NULL, group_id TEXT NOT NULL REFERENCES product_groups(group_id), judge TEXT NOT NULL, template_group TEXT NOT NULL, sort_key INTEGER NOT NULL UNIQUE, origin TEXT NOT NULL);
CREATE TABLE processes(process_code TEXT PRIMARY KEY, name TEXT NOT NULL, origin TEXT NOT NULL);
CREATE TABLE routing_steps(product_id TEXT NOT NULL REFERENCES products(product_id), seq INTEGER NOT NULL, process_code TEXT NOT NULL REFERENCES processes(process_code), src_key TEXT NOT NULL, origin TEXT NOT NULL, PRIMARY KEY(product_id, seq));
CREATE TABLE items(item_code TEXT PRIMARY KEY, item_type TEXT NOT NULL, name TEXT NOT NULL, origin TEXT NOT NULL);
CREATE TABLE bom_lines(line_id INTEGER PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(product_id), seq INTEGER NOT NULL, item_code TEXT NOT NULL REFERENCES items(item_code), qty REAL NOT NULL CHECK(qty > 0), unit TEXT NOT NULL, origin TEXT NOT NULL, UNIQUE(product_id, seq));
CREATE TABLE notes(note_id INTEGER PRIMARY KEY, scope TEXT NOT NULL CHECK(scope IN ('global','group','product','column')), target_id TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, origin TEXT NOT NULL, UNIQUE(scope, target_id, kind));
"""
JD, GR = "判定", "根拠"
CK, INF, NEW = "要確認", "類推", "新規"
UN = "未入力_"
NONIPPO = ("モリブデン", "電鋳", "ミラーブラック")
O = "IZ-001"


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def make_notes(R, G, N, S):
    n = []

    def add(scope, tid, kind, text):
        n.append((scope, tid, kind, text))

    iv = lambda k: int(float(S[k]))
    add("global", "", "scope", f"対象は製造国=日本の {iv('n_items_jp')} 品番。日本以外の {iv('n_items_overseas')} 品番と、製造国が欠けた {iv('n_items_country_missing')} 品番は対象外（IZ-001）。")
    gf = {g["group_routing"]: g["family"] for g in G}
    tf = defaultdict(list)
    for r in R:
        if r["template_group"].strip():
            tf[gf[r["group_routing"]]].append(r)
    for f, L in tf.items():
        nt = len(L)
        ns = sum(1 for r in L if r["template_group"] == r["group_routing"])
        add("global", f, "template_match", f"{f}: お手本（FY26_GroupRouting）にある {nt} 品番のうち、お手本と同じ Group Routing になったのは {ns} 品番。残りの {nt - ns} 品番は更新後の工程表で照合が合わず、別の Group Routing にした（IZ-001 の仮定。2026-11-25 に仮定のまま進めると決定）。")
    gp = defaultdict(list)
    for r in R:
        gp[r["group_routing"]].append(r)
    for g in G:
        k = g["group_routing"]
        if NEW in (g["front_section"], g["back_section"]):
            add("group", k, "new_g", f"前工程G {g['front_g']}（{g['front_section']}）・後工程G {g['back_g']}（{g['back_section']}）。「新規」はお手本に無い並びのため IZ-001 で新しく番号を振ったもの（IZ-001 規則 E4-4）。")
        if k.startswith(UN):
            add("group", k, "unentered", "工程の元データが無い品番のまとめ（工程表に値なし）。工程（Routing）は空（IZ-001 の 2026-11-23 決定）。")
        elif g["family"] in NONIPPO:
            add("group", k, "no_nippo_code", "日報コードの行が無い工程シートのため、工程は元の列名でつないだ（IZ-001 の 2026-11-23 決定）。")
        kk = sum(1 for r in gp[k] if r[JD] == CK)
        if kk:
            add("group", k, "check_products", f"このグループの全 {len(gp[k])} 品番のうち {kk} 品番が要確認（品番の注記を見る）。")
    for r in R:
        if r[JD] in (CK, INF):
            add("product", r["id"], "judge", f"IZ-001 の判定: {r[JD]}。根拠: {r[GR]}")
        if r["template_group"].strip() and r["template_group"] != r["group_routing"]:
            add("product", r["id"], "template_diff", f"お手本では {r['template_group']}。更新後の工程表では {r['group_routing']} になった（IZ-001 の仮定）。")
    for m in N:
        if m[JD] == CK:
            add("column", m["src_key"], "map_check", f"工程列 {m['src_key']}（{m['col_name']}）の日報コードは要確認。根拠: {m[GR]}")
    return n


def build(src, out):
    src = Path(src)
    R, G, T, N = (rd(src / f) for f in FILES[:4])
    S = {r["key"]: r["value"] for r in rd(src / "summary.csv")}
    c = sqlite3.connect(out)
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SCHEMA)
    c.executemany("INSERT INTO product_groups VALUES(?,?,?,?,?,?,?,?,?,?)",
                  [(g["group_routing"], g["family"], g["front_g"], g["front_section"], g["front_feature"], g["back_g"], g["back_section"], g["group_flow"], i, O) for i, g in enumerate(G, 1)])
    c.executemany("INSERT INTO products VALUES(?,?,?,?,?,?,?,?)",
                  [(r["id"], r["product"], r["family"], r["group_routing"], r[JD], r["template_group"], i, O) for i, r in enumerate(R, 1)])
    U = [t for t in T if t["in_flow"] == "1"]
    nm = {}
    for m in sorted(N, key=lambda m: int(m["col_no"])):
        for k in (m["code1"], m["code2"], m["code3"]):
            if k.strip() and m["col_name"].strip() and m["col_name"] not in nm.setdefault((m["sheet"], k), []):
                nm[(m["sheet"], k)].append(m["col_name"])

    def pname(s, t):
        if t.startswith("[") and t.endswith("]"):
            return t[1:-1]
        return "／".join(nm[(s, t)]) if (s, t) in nm else t

    procs = {}
    for t in U:
        procs.setdefault(t["sheet"] + "|" + t["token"], pname(t["sheet"], t["token"]))
    c.executemany("INSERT INTO processes VALUES(?,?,?)", [(k, v, O) for k, v in procs.items()])
    c.executemany("INSERT INTO routing_steps VALUES(?,?,?,?,?)", [(t["id"], int(t["seq"]), t["sheet"] + "|" + t["token"], t["src_key"], O) for t in U])
    c.executemany("INSERT INTO notes(scope,target_id,kind,text,origin) VALUES(?,?,?,?,?)", [x + (O,) for x in make_notes(R, G, N, S)])
    c.execute("INSERT INTO meta VALUES('schema_version','1')")
    c.executemany("INSERT INTO meta VALUES(?,?)", [("source_sha256:" + f, hashlib.sha256((src / f).read_bytes()).hexdigest()) for f in FILES])
    c.commit()
    c.execute("VACUUM")
    c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        print(f"{a.out} は既にあります。上書きしません。", file=sys.stderr)
        return 1
    try:
        build(a.src, a.out)
    except Exception as e:
        if os.path.exists(a.out):
            os.remove(a.out)
        print(f"DB を作れませんでした: {e}", file=sys.stderr)
        return 1
    print("作成:", a.out, os.path.getsize(a.out), "バイト")
    return 0


if __name__ == "__main__":
    sys.exit(main())
