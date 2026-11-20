"""S5: 製品一覧と summary.csv（規則 17〜22）。明細（S3・S4 の結果）から作る。"""
import csv
import os
from reader import load, FAMILY_ORDER
from detail import build_detail, judge, write_detail

PCOLS = ["製品ID", "製造国", "製品名", "顧客名", "製品ファミリー", "出どころ行", "工順の有無", "記入シート", "記入シート数",
         "工程数", "要確認の件数", "製品ファミリーと記入シート", "判定", "根拠"]


def build_products(products, detail):
    by = {}
    for d in detail:
        by.setdefault(d["製品ID"], []).append(d)
    out = []
    for p in products:
        ds = by.get(p["id"], [])
        n = len(ds)
        q = sum(1 for d in ds if d["判定"] == "要確認")
        sheets = [s for s in FAMILY_ORDER if any(d["出どころシート"] == s for d in ds)]
        if n == 0:
            fam = "工順なし"
        else:
            fam = "一致" if p["family"] in sheets else "違う"
        reasons = []
        if n == 0:
            reasons.append("どのシートにも工程の記入なし")
        if len(sheets) >= 2:
            reasons.append("複数シートに記入: " + "|".join(sheets))
        if q >= 1:
            reasons.append(f"明細に要確認 {q} 件")
        parts = [f"Sheet1!行{p['row']}"]
        for s in sheets:
            sd = [d for d in ds if d["出どころシート"] == s]
            parts.append(f"{s}!行{sd[0]['出どころ行']}（明細 {len(sd)} 件）")
        out.append(dict(zip(PCOLS, [
            p["id"], p["country"], p["name"], p["customer"], p["family"], p["row"],
            "あり" if n else "工順なし（要確認）", "|".join(sheets), len(sheets), n, q, fam,
            "要確認" if reasons else "一致", "; ".join(parts + reasons)])))
    return out


def build_summary(plist, detail):
    items = [("製品数", len(plist)),
             ("工順ありの製品数", sum(1 for p in plist if p["工順の有無"] == "あり")),
             ("工順なしの製品数", sum(1 for p in plist if p["工順の有無"] != "あり")),
             ("明細の行数", len(detail))]
    items += [("明細の行数_" + s, sum(1 for d in detail if d["出どころシート"] == s)) for s in FAMILY_ORDER]
    items += [("記入のある製品数_" + s, len({d["製品ID"] for d in detail if d["出どころシート"] == s})) for s in FAMILY_ORDER]
    items += [("複数シートに記入のある製品数", sum(1 for p in plist if p["記入シート数"] >= 2)),
              ("明細の要確認の件数", sum(1 for d in detail if d["判定"] == "要確認")),
              ("製品の要確認の件数", sum(1 for p in plist if p["判定"] == "要確認"))]
    items += [("区分_" + k, sum(1 for d in detail if d["値の区分"] == k)) for k in ["番号", "丸", "三角", "外注", "その他"]]
    items.append(("製品ファミリーと記入シートが違う製品数", sum(1 for p in plist if p["製品ファミリーと記入シート"] == "違う")))
    assert len(items) == 23
    return items


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols] if isinstance(r, dict) else list(r))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    prods, fams = load(os.path.join(here, "..", "data", "raw"))
    detail = judge(build_detail(prods, fams))
    plist = build_products(prods, detail)
    summ = build_summary(plist, detail)
    out = os.path.join(here, "..", "out")
    write_detail(detail, os.path.join(out, "工順明細.csv"))
    write_csv(os.path.join(out, "製品一覧.csv"), PCOLS, plist)
    write_csv(os.path.join(out, "summary.csv"), ["項目", "値"], summ)
    print("取得 Sheet1", len(prods), "明細", len(detail), "製品一覧", len(plist), "工程数合計", sum(p["工程数"] for p in plist))
    for k, v in summ:
        print(k, v)
