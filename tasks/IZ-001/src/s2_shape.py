"""IZ-001 S2: 値の種類（規則 D1）とファミリー×シートの対応（B7）。data/ の CSV だけを読む（原本には触れない）。"""
import csv, re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
CODE = r"[A-Z]{1,2}[0-9]{2}"
CODE_NOTE = re.compile(rf"{CODE}(?:[・,、/／〜～~ ]+{CODE})*")


def kind(v):
    """規則 D1。上から順に当てる。"""
    t = unicodedata.normalize("NFKC", v)
    try:
        n = float(t)
        return "通し順" if n > 0 else "不使用"
    except ValueError:
        pass
    if v in ("〇", "○", "◯"):
        return "印"
    if v in ("-", "－", "無", "無し", "なし", "×"):
        return "不使用"
    if CODE_NOTE.fullmatch(v):
        return "コード注記"
    return "備考"


def rd(n):
    return list(csv.DictReader(open(DATA / n, encoding="utf-8-sig")))


def wr(n, h, rows):
    with open(DATA / n, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(h); w.writerows(rows)


def run():
    steps = rd("steps_src.csv")
    items = rd("items_src.csv")
    cnt = Counter((s["sheet"], s["value"]) for s in steps)
    wr("cell_values.csv", ["sheet", "value", "n_cells", "cell_kind"],
       [[sh, v, n, kind(v)] for (sh, v), n in sorted(cnt.items(), key=lambda x: (x[0][0], -x[1], x[0][1]))])
    fam = {i["id"]: i["family"] for i in items}
    country = {i["id"]: i["country"] for i in items}
    used = defaultdict(set)  # id -> 使うセルのあるシート
    for s in steps:
        if kind(s["value"]) != "不使用":
            used[s["id"]].add(s["sheet"])
    fs = Counter((fam[i], sh) for i, shs in used.items() for sh in shs)
    wr("family_sheet.csv", ["family", "sheet", "n_items"], [[f, sh, n] for (f, sh), n in sorted(fs.items())])
    kc = Counter(kind(s["value"]) for s in steps)
    multi = [i for i, s in used.items() if len(s) >= 2]
    mism = [i for i, s in used.items() if len(s) >= 1 and fam[i] not in s]
    jp = lambda L: sum(country[i] == "日本" for i in L)
    print("cell_kind(セル数)", dict(kc), "| 使うセルのある品番", len(used), "(日本", jp(used), ")",
          "| 2枚以上", len(multi), "(日本", jp(multi), ")", "| ファミリー≠使うシート", len(mism), "(日本", jp(mism), ")",
          "| 使うセル無し", len(items) - len(used), "(日本", sum(c == "日本" for c in country.values()) - jp(used), ")")
