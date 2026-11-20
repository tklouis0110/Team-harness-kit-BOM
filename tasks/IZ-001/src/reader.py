"""S1: 原本 6 ファイルを読む部品（規則 1〜6）。原本は読むだけ。"""
import glob
import os
import unicodedata  # noqa: F401  (後の手順で使う)

FAMILY_ORDER = ["モリブデン", "電鋳", "ミラーブラック", "シングル", "ハイブリッド"]


class StopError(Exception):
    """止まって人に報告する（C01 / C02）。"""


def col_letter(i):
    """0 始まりの列番号 -> A, B, ... Z, AA ..."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def read_sheet(path):
    """戻り値: dict(name, n, m, rows)。rows[k] は Excel の k+1 行目のセル（str のリスト、M 個）。"""
    lines = open(path, encoding="utf-8-sig").read().split("\n")
    head = lines[0].split(" ")
    name, n, m = head[2], int(head[4]), int(head[7])
    if "(A1:" not in lines[0] or len(lines) <= n:
        raise StopError(f"C01 {path}: 見出しの宣言と合わない")
    rows = [x.split("\t") for x in lines[1:1 + n]]
    bad = [k + 1 for k, r in enumerate(rows) if len(r) != m]
    if bad:
        raise StopError(f"C01 {name}: M={m} 個に分かれない行 {bad[:5]}")
    extra = [x for x in lines[1 + n:] if x.strip()]
    if extra and extra[0] != "Formulas:":
        raise StopError(f"C01 {name}: N 行より後に Formulas: 以外の文字: {extra[0][:30]!r}")
    return {"name": name, "n": n, "m": m, "rows": rows}


def header_index(rows):
    """見出し行（A 列が ID の最初の行）の 0 始まり添字。"""
    for k, r in enumerate(rows):
        if r[0].strip() == "ID":
            return k
    raise StopError("見出し行（A 列が ID）が無い")


def process_start(rows, h):
    """工程列の開始（0 始まり）。G 列が『F列全体割合』なら H(7) から、他は G(6) から。"""
    return 7 if rows[h][6].strip() == "F列全体割合" else 6


def load(raw_dir):
    """戻り値: (sheet1 の製品リスト, ファミリーシートのリスト)。
    製品: dict(id, country, name, customer, family, row)。
    ファミリー: dict(name, rows, h, start, ncols, products=[(excel行, 行のセル)])"""
    files = sorted(glob.glob(os.path.join(raw_dir, "sheet[1-6]_*.txt")))
    if len(files) != 6:
        raise StopError(f"C01 原本が 6 ファイルでない: {len(files)}")
    s1 = read_sheet(files[0])
    if [x for x in s1["rows"][0]] != ["ID", "製造国", "製品名", "顧客名", "製品ファミリー", "予算金額"]:
        raise StopError("C01 Sheet1 の列名が想定と違う")
    products = [dict(id=r[0], country=r[1], name=r[2], customer=r[3], family=r[4], row=i + 2)
                for i, r in enumerate(s1["rows"][1:])]
    ids = [p["id"] for p in products]
    if len(products) != 1216 or len(set(ids)) != 1216 or not all(i.strip() for i in ids):
        raise StopError("C01 Sheet1 が 1,216 件・ID 重複なし・ID 空欄なし、でない")
    fams = []
    for f in files[1:]:
        sh = read_sheet(f)
        h = header_index(sh["rows"])
        s = process_start(sh["rows"], h)
        prods = [(k + 1, r) for k, r in enumerate(sh["rows"]) if k > h]
        if len(prods) != 1216:
            raise StopError(f"C01 {sh['name']}: 製品の行が {len(prods)} 行")
        fams.append(dict(name=sh["name"], rows=sh["rows"], h=h, start=s, ncols=sh["m"], products=prods))
    if [x["name"] for x in fams] != FAMILY_ORDER:
        raise StopError(f"シート名の並びが想定と違う: {[x['name'] for x in fams]}")
    return products, fams


def entries(fam):
    """工程の記入がある行 = 工程列に空でないセルが 1 つ以上ある製品の行。(excel行, ID, セル)"""
    return [(xr, r[0].strip(), r) for xr, r in fam["products"] if any(v.strip() for v in r[fam["start"]:])]


def name_index(products):
    """(製造国, 製品名, 顧客名)（前後の空白を除く）-> その Sheet1 の ID のリスト（規則 5）。"""
    idx = {}
    for p in products:
        idx.setdefault((p["country"].strip(), p["name"].strip(), p["customer"].strip()), []).append(p["id"].strip())
    return idx


def link_product(idx, r):
    """ファミリーシートの 1 行 r -> (候補, 製品ID または None)。規則 5。
    候補 1 つ -> その ID。2 つ以上 -> 元のID（A 列）が候補にあればそれ、無ければ None。0 件 -> None。"""
    cand = idx.get(tuple(v.strip() for v in r[1:4]), [])
    if len(cand) == 1:
        return cand, cand[0]
    if len(cand) >= 2 and r[0].strip() in cand:
        return cand, r[0].strip()
    return cand, None


def check_link(products, fams):
    """規則 6（C02）。(a)(b) を確かめ、外れた分を返す。
    戻り値: (外れのリスト, 結び付き dict[(シート名, excel行)] = 製品ID, IDずれの件数)"""
    idx = name_index(products)
    problems, links, shifted = [], {}, 0
    for fam in fams:
        seen = {}
        for xr, i, r in entries(fam):
            cand, pid = link_product(idx, r)
            if pid is None:
                problems.append((fam["name"], xr, i, f"(a) 名前が一致する Sheet1 の行が {len(cand)} 件で決まらない"))
                continue
            links[(fam["name"], xr)] = pid
            if pid != i:
                shifted += 1
            if pid in seen:
                problems.append((fam["name"], xr, i, f"(b) 同じ製品ID {pid} の記入行が重複（{seen[pid]}行目）"))
            seen[pid] = xr
    return problems, links, shifted


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    prods, fams = load(os.path.join(here, "..", "data", "raw"))
    print("Sheet1 製品", len(prods))
    for fam in fams:
        e = entries(fam)
        print(fam["name"], "見出し行", fam["h"] + 1, "工程列開始", col_letter(fam["start"]),
              "工程列数", fam["ncols"] - fam["start"], "製品行", len(fam["products"]), "記入のある行", len(e))
    pr, links, shifted = check_link(prods, fams)
    print("記入行", len(links) + len(pr), "つながった", len(links), "IDずれ", shifted)
    print("C02 外れ", len(pr), pr[:5])
