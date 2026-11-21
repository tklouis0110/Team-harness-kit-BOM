"""S2: 入力を読む部品（規則 1〜6）。入力は読むだけ。"""
import csv
import os
from decimal import Decimal

FAMILIES = ["モリブデン", "電鋳", "ミラーブラック", "シングル", "ハイブリッド"]
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)  # tasks/IZ-002
IZ1 = os.path.join(os.path.dirname(BASE), "IZ-001")


class StopError(Exception):
    pass


def read_text(path):
    """規則 1: 1 行目の N rows x M columns に従い、タブで M 個に分ける。
    '[1 empty row]' は空の 1 行。Formulas: より後は読まない。セルは strip。"""
    lines = open(path, encoding="utf-8-sig").read().split("\n")
    h = lines[0].split(" ")
    n, m = int(h[4]), int(h[7])
    body = lines[1:1 + n]
    if len(body) != n:
        raise StopError(f"{path}: 宣言 {n} 行に足りない")
    rows = []
    for x in body:
        if "empty row" in x:
            rows.append([""] * m)
            continue
        c = [v.strip() for v in x.split("\t")]
        if len(c) > m:
            raise StopError(f"{path}: {m} 列を超える行")
        rows.append(c + [""] * (m - len(c)))
    return rows


def read_csv(path):
    """規則 3: 列名で読み、値は文字のまま。"""
    return list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))


def to_int(s):
    """規則 2: カンマを除いて整数。"""
    return int(s.replace(",", "").strip())


def load_inputs():
    raw = os.path.join(BASE, "data", "raw")
    iz1raw = os.path.join(IZ1, "data", "raw")
    detail = read_csv(os.path.join(IZ1, "out", "工順明細.csv"))
    products = read_csv(os.path.join(IZ1, "out", "製品一覧.csv"))
    iz1sum = {r["項目"]: r["値"] for r in read_csv(os.path.join(IZ1, "out", "summary.csv"))}
    s1 = read_text(os.path.join(iz1raw, "sheet1_Sheet1.txt"))
    budget = {}
    for r in s1[1:]:
        if r[0] in budget:
            raise StopError(f"Sheet1 の ID 重複: {r[0]}")
        budget[r[0]] = r[5]  # 文字のまま（前後空白除去済み）。丸めない
    prod = {p["製品ID"]: p for p in products}
    if len(prod) != len(products):
        raise StopError("製品一覧の製品ID重複")

    # 規則 4: 対象 = (製品ID, 出どころシート) のうち 製造国=日本 かつ ファミリー=シート
    pairs = sorted({(d["製品ID"], d["出どころシート"]) for d in detail}, key=lambda k: (int(k[0]), k[1]))
    targets, excluded = [], []
    for pid, sh in pairs:
        p = prod[pid]
        if p["製造国"].strip() == "日本" and p["製品ファミリー"].strip() == sh:
            targets.append((pid, sh))
        else:
            excluded.append((pid, sh))
    missing_budget = [pid for pid, _ in targets if pid not in budget]
    if missing_budget:
        raise StopError(f"予算金額が Sheet1 に無い: {missing_budget[:5]}")
    no_order = [p for p in products if p["工順の有無"] != "あり"]

    # 見本
    ids2 = [r[0] for r in read_text(os.path.join(raw, "見本_sheet2_シングル_日報.txt"))[5:]]
    ids3 = [r[0] for r in read_text(os.path.join(raw, "見本_sheet3_ハイブリッド_日報.txt"))[5:]]
    smap = [r for r in read_text(os.path.join(raw, "見本_sheet4_日報Map.txt"))[3:]]
    smap = [r for r in smap if r[0]]
    return {
        "detail": detail, "products": prod, "iz1_summary": iz1sum, "budget": budget,
        "targets": targets, "excluded": excluded, "no_order_count": len(no_order),
        "sample_ids": {"シングル": ids2, "ハイブリッド": ids3}, "sample_map": smap,
    }
