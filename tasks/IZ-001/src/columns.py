"""S2: 工程列の表（規則 7〜10）。シート x 工程列ごとに 1 行。"""
import os
from reader import load, col_letter, StopError

LABELS = ("日報工程コード", "日報工程名")


def build_columns(fams):
    """戻り値: {シート名: [dict(col, idx, raw, name, code, nikkei, order)]}（工程列の並び順）。"""
    table = {}
    for fam in fams:
        rows, h, s = fam["rows"], fam["h"], fam["start"]
        hr = rows[h]
        m = len(hr)
        # 規則 10: 日報工程コード・名の段（1〜h 行目を 2 行ずつ。h は 0 始まりの見出し行添字）
        tiers = []
        if h > 0:
            if h % 2:
                raise StopError(f"{fam['name']}: 見出し行より上が奇数行")
            for k in range(h // 2):
                if (rows[2 * k][5].strip(), rows[2 * k + 1][5].strip()) != LABELS:
                    raise StopError(f"{fam['name']}: F 列の段の名前が想定と違う（{2*k+1}・{2*k+2} 行目）")
                tiers.append((rows[2 * k], rows[2 * k + 1]))
        stripped = [x.strip() for x in hr[s:]]
        seen = {}
        cols = []
        for j in range(s, m):
            raw = hr[j]
            x = raw.strip()
            if not x:
                name = "（列名なし）" + col_letter(j)
            elif stripped.count(x) > 1:
                seen[x] = seen.get(x, 0) + 1
                name = f"{x}({seen[x]})"
            else:
                name = x
            picked = [(c[j].strip(), n[j].strip()) for c, n in tiers if c[j].strip() or n[j].strip()]
            cols.append(dict(col=col_letter(j), idx=j - s + 1, raw=raw, name=name,
                             code="|".join(a for a, b in picked), nikkei="|".join(b for a, b in picked),
                             order=j - s + 1))
        table[fam["name"]] = cols
    return table


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    prods, fams = load(os.path.join(here, "..", "data", "raw"))
    t = build_columns(fams)
    exp = {"モリブデン": 20, "電鋳": 27, "ミラーブラック": 22, "シングル": 32, "ハイブリッド": 43}
    for n, cols in t.items():
        names = [c["name"] for c in cols]
        ok = len(cols) == exp[n] and len(set(names)) == len(names)
        print(n, "工程列", len(cols), "期待", exp[n], "区別付き名の種類", len(set(names)), "OK" if ok else "NG")
    for n in ("モリブデン", "ハイブリッド", "シングル", "電鋳"):
        print("--", n)
        for c in t[n]:
            if "(" in c["name"] or "列名なし" in c["name"] or c["raw"] != c["raw"].strip() or (n == "シングル" and c["col"] == "J"):
                print(" ", c["col"], c["idx"], repr(c["raw"]), c["name"], c["code"], c["nikkei"])
