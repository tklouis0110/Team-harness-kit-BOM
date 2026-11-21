"""S3: 日報Map 144 行とセルのトークン（規則 7〜10）。"""
import csv
import glob
import os
import collections
from inputs import FAMILIES, IZ1, StopError, read_text

BACK_START = {"モリブデン": 15, "電鋳": 21, "ミラーブラック": 16, "シングル": 20, "ハイブリッド": 29}
MAP_COLS = ["ファミリー", "元列", "実工程名（元の見出し）", "使用品番数", "日報コード1", "日報工程名1",
            "日報コード2", "日報工程名2", "日報コード3", "日報工程名3", "対応区分", "振り直し先の列", "備考", "前後の区分"]


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def zone(family, order, has_name):
    """規則 7: 自由記入／前工程／後工程。order は工程列の並び（1 始まり）。"""
    if not has_name:
        return "自由記入"
    return "前工程" if order < BACK_START[family] else "後工程"


def headers():
    """IZ-001 の写し 5 シートの見出し行から (ファミリー, 元列, 見出し, 並び) を元の列順で返す。"""
    out = {}
    for f in sorted(glob.glob(os.path.join(IZ1, "data", "raw", "sheet[2-6]_*.txt"))):
        fam = open(f, encoding="utf-8-sig").readline().split(" ")[2]
        rows = read_text(f)
        h = [k for k, r in enumerate(rows) if r[0] == "ID"][0]
        start = 7 if rows[h][6] == "F列全体割合" else 6
        out[fam] = [(col_letter(j), rows[h][j], j - start + 1) for j in range(start, len(rows[h]))]
    missing = [x for x in FAMILIES if x not in out]
    if missing:
        raise StopError(f"見出しが読めないシート: {missing}")
    return out


def build_map(d):
    """日報Map の 144 行（辞書）。使用品番数は対象品番を IZ-001 明細から数え直す。"""
    tg = set(d["targets"])
    used = collections.Counter((s, c) for _, s, c in
                               {(x["製品ID"], x["出どころシート"], x["出どころ列"]) for x in d["detail"]
                                if (x["製品ID"], x["出どころシート"]) in tg})
    zname = {(x["出どころシート"], x["出どころ列"]): x["工程名（区別付き）"] for x in d["detail"]}
    smap = {(r[0], r[1]): r for r in d["sample_map"]}
    hd = headers()
    rows = []
    for fam in FAMILIES:
        for col, name, order in hd[fam]:
            n = used[(fam, col)]
            zn = zone(fam, order, bool(name))
            if fam in ("シングル", "ハイブリッド"):
                r = smap.get((fam, col))
                if r is None:
                    raise StopError(f"見本の日報Map に無い列: {fam} {col}")
                row = dict(zip(MAP_COLS[:13], [fam, col, r[2], str(n)] + list(r[4:13])))
            else:
                if name:
                    kind = "コード未設定"
                    to = ("未設定：" + zname[(fam, col)]) if n else "（列なし）"
                    note = "元シートに日報工程コードなし（工程名で代用）" if n else "使用品番なしのため列を作成していない"
                else:
                    kind, to, note = "自由記入", "追加工程（自由記入）", "見出し無しの列（記入があれば追加工程へ）"
                row = dict(zip(MAP_COLS[:13], [fam, col, name or "（見出し無し）", str(n), "", "", "", "", "", "", kind, to, note]))
            row["前後の区分"] = zn
            rows.append(row)
    return rows


def write_map(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MAP_COLS)
        w.writeheader()
        w.writerows(rows)


def cell_tokens(fam, col, name_distinct, mrow, product_cols):
    """規則 8・9: セル 1 つのトークン（リスト）。自由記入は [] を返す（追加工程へ回す）。
    product_cols は、その品番で記入のある元列の集合。"""
    if mrow["前後の区分"] == "自由記入":
        return []
    if fam not in ("シングル", "ハイブリッド"):
        return [name_distinct]
    kind = mrow["対応区分"]
    if kind == "1対1":
        return [mrow["日報コード1"]]
    if kind.startswith("連続"):
        return [c for c in (mrow["日報コード1"], mrow["日報コード2"], mrow["日報コード3"]) if c]
    if kind == "択一（経路から判定）":
        if "AA" in product_cols:
            return ["H17"]
        if "AC" in product_cols:
            return ["H16"]
        return ["H15"]
    if kind.startswith("択一"):
        return [mrow["振り直し先の列"]]
    if kind == "コード未設定":
        to = mrow["振り直し先の列"]
        return [to[len("未設定："):]] if to.startswith("未設定：") else [mrow["実工程名（元の見出し）"]]
    raise StopError(f"未知の対応区分: {kind} ({fam} {col})")
