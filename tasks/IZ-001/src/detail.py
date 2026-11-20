"""S3: 工順明細の抽出（規則 11〜14・23・24）。ブロック番号・判定・根拠は S4 で付ける（今は空欄）。"""
import csv
import os
import unicodedata
from decimal import Decimal  # noqa: F401
from reader import load, check_link, StopError
from columns import build_columns

COLS = ["製品ID", "製造国", "製品名", "顧客名", "製品ファミリー", "出どころシート", "出どころ列", "出どころ行",
        "元のID", "IDずれ", "工程列の並び", "工程名（原文）", "工程名（区別付き）", "日報工程コード", "日報工程名",
        "値（原文）", "値の区分", "順番", "ブロック番号", "判定", "根拠"]


def classify(v):
    w = unicodedata.normalize("NFKC", v).strip()
    if w.isascii() and w.isdigit():
        return "番号", int(w)
    if w in ("〇", "○", "◯"):
        return "丸", ""
    if w == "△":
        return "三角", ""
    if w == "外注":
        return "外注", ""
    return "その他", ""


def build_detail(products, fams):
    problems, links, _ = check_link(products, fams)
    if problems:
        raise StopError(f"C02 外れ {len(problems)} 件: {problems[:3]}")
    table = build_columns(fams)
    pmap = {p["id"]: p for p in products}
    order = {p["id"]: k for k, p in enumerate(products)}
    out = []
    for fam in fams:
        cols = table[fam["name"]]
        for xr, r in fam["products"]:
            if (fam["name"], xr) not in links:
                continue
            pid = links[(fam["name"], xr)]
            p = pmap[pid]
            for c in cols:
                v = r[fam["start"] + c["idx"] - 1]
                if not v.strip():
                    continue
                kind, seq = classify(v)
                oid = r[0].strip()
                out.append(dict(zip(COLS, [
                    pid, p["country"], p["name"], p["customer"], p["family"], fam["name"], c["col"], xr,
                    oid, "あり" if oid != pid else "なし", c["idx"], c["raw"], c["name"], c["code"], c["nikkei"],
                    v, kind, seq, "", "", ""])))
    sheets = [f["name"] for f in fams]
    out.sort(key=lambda d: (order[d["製品ID"]], sheets.index(d["出どころシート"]), d["工程列の並び"]))
    return out


def judge(rows):
    """S4: ブロック番号・判定・根拠を付ける（規則 15・16）。rows は S3 の並び（製品・シート・工程列の並び順）。"""
    groups = {}
    for d in rows:
        groups.setdefault((d["製品ID"], d["出どころシート"]), []).append(d)
    for lst in groups.values():
        nums = [d for d in lst if d["値の区分"] == "番号"]
        blk = 0
        blocks = {}
        for n, d in enumerate(nums):
            if n == 0 or d["順番"] == 1:
                blk += 1
            d["ブロック番号"] = blk
            blocks.setdefault(blk, []).append(d["順番"])
        for d in lst:
            head = f"{d['出どころシート']}!{d['出どころ列']}{d['出どころ行']}「{d['値（原文）']}」"
            reasons = []
            if d["値の区分"] != "番号":
                reasons.append(f"記号・文字の意味は要確認（区分: {d['値の区分']}）")
            else:
                b = d["ブロック番号"]
                seq = blocks[b]
                k = len(seq)
                col = ",".join(str(x) for x in seq)
                if sorted(seq) != list(range(1, k + 1)):
                    reasons.append(f"ブロック {b} の番号が 1〜{k} の連番でない（列の順: {col}）")
                elif seq != sorted(seq):
                    reasons.append(f"ブロック {b} で列の並びと番号の順が違う（列の順: {col}）")
            if not d["工程名（原文）"].strip():
                reasons.append("列名なし")
            if reasons:
                d["判定"] = "要確認"
                d["根拠"] = "; ".join([head] + reasons)
            else:
                d["判定"] = "一致"
                d["根拠"] = f"{head}; 番号 {d['順番']}（ブロック {d['ブロック番号']}、1〜{len(blocks[d['ブロック番号']])} の連番）"
    return rows


def write_detail(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    prods, fams = load(os.path.join(here, "..", "data", "raw"))
    raw_cnt = sum(1 for fam in fams for xr, r in fam["products"] for v in r[fam["start"]:] if v.strip())
    rows = judge(build_detail(prods, fams))
    write_detail(rows, os.path.join(here, "..", "out", "工順明細.csv"))
    print("原本の空でないセル", raw_cnt, "明細", len(rows))
    for s in [f["name"] for f in fams]:
        print(s, sum(1 for d in rows if d["出どころシート"] == s))
    for k in ["番号", "丸", "三角", "外注", "その他"]:
        print(k, sum(1 for d in rows if d["値の区分"] == k))
    import collections
    print("判定", collections.Counter(d["判定"] for d in rows))
    print("要確認の理由", collections.Counter(x.split("（")[0].split(" の番号")[0].split(" で列")[0] if False else
          ("区分が番号でない" if "意味は要確認" in x else "連番でない" if "連番でない" in x else "列の並びと番号の順が違う" if "順が違う" in x else x)
          for d in rows if d["判定"] == "要確認" for x in d["根拠"].split("; ")[1:]))
