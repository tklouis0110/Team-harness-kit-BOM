"""S7: 見本との照合（規則 27・30）・明細の判定 a・b・summary（規則 28・29・32）。"""
import csv
import os
import re
from decimal import Decimal, ROUND_HALF_UP
import openpyxl
from inputs import FAMILIES, BASE, IZ1, read_text, read_csv
from flow import K

SF = ["シングル", "ハイブリッド"]
SAMPLE_FILES = {"シングル": "見本_sheet2_シングル_日報.txt", "ハイブリッド": "見本_sheet3_ハイブリッド_日報.txt"}
VCOLS = ["ファミリー", "対象", "キー", "項目", "見本の値", "作り直しの値", "結果"]
TORD = ["見出し", "日報Map", "品番", "Group Routing", "前工程G", "後工程G"]
PT = {"Group Routing": "[A-Z]+F[0-9][0-9]-[A-Z]+B[0-9][0-9]", "前工程G": "[A-Z]+F[0-9][0-9]", "後工程G": "[A-Z]+B[0-9][0-9]"}


def N(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)) and v == int(v):
        return str(int(v))
    return str(v).strip()


def RI(a):
    return int(Decimal(a).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def res(ok):
    return "一致" if ok else "不一致"


def col_index(c):
    return sum((ord(ch) - 64) * 26 ** n for n, ch in enumerate(reversed(c))) - 1


def read_new_sheets(xlsx):
    wb = openpyxl.load_workbook(xlsx)
    return {f: [[N(v) for v in r] for r in wb[f + "_日報"].iter_rows(values_only=True)] for f in SF}


def cells_of(X, r):
    return sorted((X[3][j].strip(), X[4][j].strip(), r[j].strip()) for j in range(9, len(X[4])) if j < len(r) and r[j].strip())


def cells_text(cs):
    return "; ".join(f"{c}|{n}={v}" for c, n, v in cs)


def head_text(X, i):
    return "|".join(x.strip() for x in X[i][9:]).rstrip("|")


def compare(detail, groups, map_rows, xlsx):
    raw = os.path.join(BASE, "data", "raw")
    SP = {f: read_text(os.path.join(raw, SAMPLE_FILES[f])) for f in SF}
    OX = read_new_sheets(xlsx)
    rows = []  # (fam, 対象, キー, 項目, 見本, 作り直し, 結果, sortkey)

    def add(f, t, k, item, sv, ov, r, sk=None):
        rows.append((f, t, k, item, sv, ov, r, sk if sk is not None else (0, k)))

    # 見出し
    for f in SF:
        for item, i in (("日報工程コード行", 3), ("列名行", 4)):
            a, b = head_text(SP[f], i), head_text(OX[f], i)
            add(f, "見出し", f + "_日報", item, a, b, res(a == b), (0, item))
    # 日報Map
    om = {(o["ファミリー"], o["元列"]): o for o in map_rows}
    order = {(o["ファミリー"], o["元列"]): n for n, o in enumerate(map_rows)}
    rg = {}
    for fam in ("シングル", "ハイブリッド"):
        pass
    import glob
    for p in glob.glob(os.path.join(IZ1, "data", "raw", "sheet[56]_*.txt")):
        rg[open(p, encoding="utf-8-sig").readline().split(" ")[2]] = read_text(p)

    def rcode(f, c):
        return "|".join(x for x in (rg[f][2 * n][col_index(c)] for n in range(3)) if x and x != "無し")
    smap = [r for r in read_text(os.path.join(raw, "見本_sheet4_日報Map.txt"))[3:] if r[0]]
    for r in smap:
        f, c = r[0], r[1]
        sv = r[3]
        ov = om[(f, c)]["使用品番数"]
        add(f, "日報Map", c, "使用品番数", sv, ov, res(sv == ov), (order[(f, c)], 0))
        sv = "|".join(x for x in (r[4], r[6], r[8]) if x)
        ov = rcode(f, c)
        add(f, "日報Map", c, "日報コード", sv, ov, res(sv == ov), (order[(f, c)], 1))
    # 品番
    mm = {(m["ファミリー"], m["製品ID"]): m for m in detail}
    for f in SF:
        S = {N(r[0]): r for r in SP[f][5:] if r[0]}
        O = {N(r[0]): r for r in OX[f][5:] if r[0]}
        mine = {m["製品ID"] for m in detail if m["ファミリー"] == f}
        for i in set(S) | set(O):
            if i not in O:
                add(f, "品番", i, "存在", "あり", "なし", "見本のみ", (int(i), 0))
            elif i not in S:
                add(f, "品番", i, "存在", "なし", "あり", "作り直しのみ", (int(i), 0))
            else:
                m, s = mm[(f, i)], S[i]
                sc, oc = cells_of(SP[f], s), cells_of(OX[f], O[i])
                for n, (item, sv, ov) in enumerate((
                        ("前工程G", s[7], m["前工程G"]), ("後工程G", s[8], m["後工程G"]),
                        ("Group Routing", s[6], m["Group Routing"]),
                        ("予算金額", str(int(s[5].replace(",", ""))), str(RI(m["予算金額"]))),
                        ("日報の行", cells_text(sc), cells_text(oc)))):
                    ok = (sc == oc) if item == "日報の行" else (sv == ov)
                    add(f, "品番", i, item, sv, ov, res(ok), (int(i), n))
    # グループ
    GS = read_text(os.path.join(raw, "見本_sheet1_GroupRouting.txt"))
    A0 = [r[0] for r in GS]
    tb = lambda a: next((t for t, p in PT.items() if re.fullmatch(p, a)), None)
    sec = lambda i: max(j for j in range(i) if "：通常（" in A0[j] or "：特別枠（" in A0[j])
    SG = {}
    for i in range(len(A0)):
        t = tb(A0[i])
        if t:
            s = sec(i)
            kb = "通常" if "：通常（" in A0[s] else "特別枠"
            SG[(GS[i][1], t, A0[i])] = (GS[i], kb + "#" + str(len([j for j in range(s + 1, i + 1) if tb(A0[j]) == t])))
    OG = {(g["ファミリー"], g["表"], g["グループ記号"]): g for g in groups if g["ファミリー"] in SF}
    gpos = {k: n for n, k in enumerate((g["ファミリー"], g["表"], g["グループ記号"]) for g in groups)}
    for k in set(SG) | set(OG):
        f, t, sym = k
        sk0 = gpos.get(k, 10 ** 6)
        if k not in OG:
            add(f, t, sym, "存在", "あり", "なし", "見本のみ", (sk0, sym, 0))
        elif k not in SG:
            add(f, t, sym, "存在", "なし", "あり", "作り直しのみ", (sk0, sym, 0))
        else:
            r, sq = SG[k]
            g = OG[k]
            items = [("品番数", r[4], str(g["品番数"]), r[4] == str(g["品番数"])),
                     ("予算金額", str(int(r[5].replace(",", ""))), str(RI(g["予算金額"])), int(r[5].replace(",", "")) == RI(g["予算金額"])),
                     ("品番名", r[7], g["品番名"], r[7] == g["品番名"]),
                     ("日報工程フロー", r[8], g["日報工程フロー"], r[8] == g["日報工程フロー"]),
                     ("特徴", r[2], g["特徴"], r[2] == g["特徴"]),
                     ("区分と並び", sq, g["区分"] + "#" + str(g["並び順"]), sq == g["区分"] + "#" + str(g["並び順"]))]
            if t != "Group Routing":
                items.append(("日報工程フロー（工程名）", r[9], g["日報工程フロー（工程名）"], r[9] == g["日報工程フロー（工程名）"]))
            for n, (item, sv, ov, ok) in enumerate(items):
                add(f, t, sym, item, sv, ov, res(ok), (sk0, sym, n))
    rows.sort(key=lambda x: (FAMILIES.index(x[0]), TORD.index(x[1]), x[7]))
    out = [dict(zip(VCOLS, x[:7])) for x in rows]
    keys = [(v["ファミリー"], v["対象"], v["キー"], v["項目"]) for v in out]
    assert len(keys) == len(set(keys)), "見本照合のキー重複"
    return out


def apply_judgement(detail, vrows):
    """規則 27・28a/b・29。見本との照合と判定、根拠を更新。"""
    by = {}
    for v in vrows:
        if v["対象"] == "品番":
            by.setdefault((v["ファミリー"], v["キー"]), []).append(v)
    for m in detail:
        f, i = m["ファミリー"], m["製品ID"]
        vs = by.get((f, i), [])
        if f not in SF:
            st = "見本なし"
        elif not vs or any(v["項目"] == "存在" for v in vs):
            st = "見本なし"
        else:
            st = "一致" if all(v["結果"] == "一致" for v in vs) else "不一致"
        m["見本との照合"] = st
        cd_ok = m["判定"] == "一致"  # S4 で付けた c・d の結果
        b = m["根拠"]
        clean = b.endswith("; 規則どおり")
        if st == "不一致":
            bad = "・".join(v["項目"] for v in vs if v["結果"] != "一致")
            b = (b[:-len("; 規則どおり")] if clean else b) + f"; 見本と不一致: {bad}"
        elif f in SF and st == "見本なし":
            b = (b[:-len("; 規則どおり")] if clean else b) + "; 見本なし: 見本の _日報 に無い品番"
        elif f in SF and st == "一致" and clean:
            b += "; 見本と一致"
        m["根拠"] = b
        m["判定"] = "要確認" if (not cd_ok or st == "不一致" or (f in SF and st == "見本なし")) else "一致"


def write_all(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def make_summary(d, detail, groups, vrows):
    s = [("対象の品番数", len(detail))]
    s += [("対象の品番数_" + f, sum(1 for m in detail if m["ファミリー"] == f)) for f in FAMILIES]
    s += [("対象外_工順なし", d["no_order_count"]), ("対象外_日本以外またはファミリー違い", len(d["excluded"]))]
    s += [("予算金額合計", format(sum(Decimal(m["予算金額"]) for m in detail), "f"))]
    s += [("予算金額合計_" + f, format(sum((Decimal(m["予算金額"]) for m in detail if m["ファミリー"] == f), Decimal(0)), "f")) for f in FAMILIES]
    for a, k in (("GroupRouting数", "Group Routing"), ("前工程G数", "前工程G"), ("後工程G数", "後工程G")):
        s += [(a + "_" + f, sum(1 for g in groups if g["表"] == k and g["ファミリー"] == f)) for f in FAMILIES]
    s += [("特徴_AI下書き（要確認）の数", sum(1 for g in groups if g["表"] == "前工程G" and g["特徴の出どころ"] == "AI下書き（要確認）")),
          ("明細の要確認の件数", sum(1 for m in detail if m["判定"] == "要確認"))]
    for f in SF:
        s += [("照合_行数_" + f, sum(1 for v in vrows if v["ファミリー"] == f)),
              ("照合_不一致_" + f, sum(1 for v in vrows if v["ファミリー"] == f and v["結果"] != "一致"))]
    assert len(s) == 35
    return [{"項目": a, "値": str(b)} for a, b in s]
