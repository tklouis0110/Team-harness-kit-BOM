"""S4: 前工程・後工程フロー、グループ記号、明細（判定は c・d まで）、グループ一覧（規則 7・11〜23・28c/d・29）。"""
import collections
import csv
import os
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from inputs import FAMILIES, StopError, read_text, BASE
from nippo_map import BACK_START, zone

PFX = {"モリブデン": "MO", "電鋳": "DE", "ミラーブラック": "MB", "シングル": "S", "ハイブリッド": "H"}
DASH = "―"
SEP = "　｜　"
DETAIL_COLS = ["製品ID", "製造国", "製品名", "顧客名", "ファミリー", "予算金額", "Group Routing", "前工程G", "後工程G",
               "区分", "前工程フロー", "後工程フロー", "日報工程フロー（前工程｜後工程）", "前工程フロー（工程名）",
               "後工程フロー（工程名）", "追加工程（自由記入）", "備考", "見本との照合", "判定", "根拠"]
GROUP_COLS = ["表", "ファミリー", "グループ記号", "区分", "並び順", "前工程G", "後工程G", "特徴", "特徴の出どころ",
              "品番数", "予算金額", "金額構成比", "品番名", "日報工程フロー", "日報工程フロー（工程名）"]


def K(code):
    n = int(code[-2:])
    return 100 if n == 0 else 101 if n == 99 else n


def lead(v):
    w = unicodedata.normalize("NFKC", v).strip()
    n = len(w) - len(w.lstrip("0123456789"))
    return w[:n], w[n:]


def dedup(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def tokens(cell, mrows, cols):
    from nippo_map import cell_tokens
    fam, col = cell["出どころシート"], cell["出どころ列"]
    return cell_tokens(fam, col, cell["工程名（区別付き）"], mrows[(fam, col)], cols)


def split_cells(cells, fam):
    free, front, back = [], [], []
    for c in sorted(cells, key=lambda c: int(c["工程列の並び"])):
        z = zone(fam, int(c["工程列の並び"]), bool(c["工程名（原文）"].strip()))
        {"自由記入": free, "前工程": front, "後工程": back}[z].append(c)
    return free, front, back


def front_flow(front, mrows, cols):
    if any(c["値の区分"] == "外注" for c in front):
        return "外注"
    if not front:
        return DASH
    allnum = all(lead(c["値（原文）"])[0] for c in front)
    if allnum:
        front = sorted(front, key=lambda c: (int(lead(c["値（原文）"])[0]), int(c["工程列の並び"])))
    toks = dedup([t for c in front for t in tokens(c, mrows, cols)])
    return "→".join(toks)


def back_flow(back, mrows, cols):
    if not back:
        return DASH
    return "→".join(dedup([t for c in back for t in tokens(c, mrows, cols)]))


def code_names(d, map_rows):
    """規則 25 の列名: 見本 _日報 の (4 行目コード → 5 行目列名)。無ければ日報Map の日報工程名を「・」でつなぐ。"""
    from inputs import BASE as B
    res = {}
    for fam, fn in (("シングル", "見本_sheet2_シングル_日報.txt"), ("ハイブリッド", "見本_sheet3_ハイブリッド_日報.txt")):
        rows = read_text(os.path.join(B, "data", "raw", fn))
        m = {}
        for j in range(9, len(rows[3])):
            code, nm = rows[3][j], rows[4][j]
            if code and code != "未設定" and nm:
                m.setdefault(code, nm)
        res[fam] = m
    mp = {}
    for r in map_rows:
        if r["ファミリー"] in res:
            names = []
            for cc, nn in (("日報コード1", "日報工程名1"), ("日報コード2", "日報工程名2"), ("日報コード3", "日報工程名3")):
                if r[cc]:
                    mp.setdefault((r["ファミリー"], r[cc]), []).append(r[nn])
    return res, mp


def name_flow(flow, fam, side, cn):
    if flow == DASH or (side == "前" and flow == "外注"):
        return DASH
    res, mp = cn
    out = []
    for t in flow.split("→"):
        if t in res.get(fam, {}):
            out.append(res[fam][t])
        elif (fam, t) in mp:
            out.append("・".join(dedup(mp[(fam, t)])))
        else:
            out.append(t)
    return "→".join(out)


def assign(items, keyflow):
    """items: [(flow, count, budget)] → {flow: 記号の番号 文字列}。規則 18・19。"""
    pass


def number_codes(stats, fam, kind):
    """stats: {flow: (count, budget)}。kind='F'/'B'。"""
    code = {}
    rest = []
    for fl, (n, b) in stats.items():
        if fl == DASH:
            code[fl] = "00"
        elif kind == "F" and fl == "外注":
            code[fl] = "99"
        else:
            rest.append((-n, -b, fl))
    rest.sort()
    if len(rest) > 98:
        raise StopError(f"{fam} {kind}: 番号が 98 を超える")
    for i, (_, _, fl) in enumerate(rest, 1):
        code[fl] = "%02d" % i
    return {fl: PFX[fam] + kind + c for fl, c in code.items()}


def build(d, map_rows):
    mrows = {(r["ファミリー"], r["元列"]): r for r in map_rows}
    cn = code_names(d, map_rows)
    cells = collections.defaultdict(list)
    tg = set(d["targets"])
    for x in d["detail"]:
        k = (x["製品ID"], x["出どころシート"])
        if k in tg:
            cells[k].append(x)
    prods = []
    for (pid, fam), cs in cells.items():
        cols = {c["出どころ列"] for c in cs}
        free, front, back = split_cells(cs, fam)
        ff, bf = front_flow(front, mrows, cols), back_flow(back, mrows, cols)
        # 備考（規則 14）
        notes = []
        for c in front:
            ld, rest = lead(c["値（原文）"])
            if ld and rest:
                notes.append(f"{c['工程名（原文）'].strip()}：{rest}")
        # 根拠・判定 c/d（規則 28・29）
        p = d["products"][pid]
        reasons = []
        nonfree = [c for c in cs if c["工程名（原文）"].strip()]
        gaichu = [c for c in nonfree if c["値の区分"] == "外注"]
        for c in gaichu:
            reasons.append(f"外注（{c['工程名（原文）'].strip()}）")
        for c in nonfree:
            if c["値の区分"] == "三角":
                reasons.append(f"△: {c['出どころ列']} 列")
        for c in front:
            ld, rest = lead(c["値（原文）"])
            if ld and rest:
                reasons.append(f"数字＋文字: {c['出どころ列']}「{c['値（原文）'].strip()}」→ 番号 {int(ld)}、文字は備考へ")
        if fam == "電鋳":
            oth = [c for c in nonfree if c["値の区分"] == "その他"]
            if oth:
                reasons.append(f"電鋳の工程名の記入: {oth[0]['出どころ列']}〜{oth[-1]['出どころ列']} 列（列の見出しで前工程を作った）")
        iz = any(("列の並びと番号の順が違う" in c["根拠"] or "連番でない" in c["根拠"]) for c in cs)
        if iz:
            reasons.append("IZ-001: 列の並びと番号の順が違う")
        cd = bool(gaichu) or any(c["値の区分"] in ("三角", "外注", "その他") for c in nonfree) or iz
        first = min(cs, key=lambda c: int(c["工程列の並び"]))
        basis = f"{fam}!行{first['出どころ行']}（明細 {len(cs)} 件）"
        basis += "; " + ("; ".join(reasons) if reasons else "規則どおり")
        prods.append({
            "pid": pid, "fam": fam, "budget": Decimal(d["budget"][pid]), "ff": ff, "bf": bf,
            "extra": "＋".join(c["値（原文）"].strip() for c in free), "note": "; ".join(notes),
            "judge": "要確認" if cd else "一致", "basis": basis, "p": p,
        })
    # グループ記号
    fcode, bcode = {}, {}
    for fam in FAMILIES:
        ps = [x for x in prods if x["fam"] == fam]
        for key, kind, store in (("ff", "F", fcode), ("bf", "B", bcode)):
            st = collections.defaultdict(lambda: [0, Decimal(0)])
            for x in ps:
                st[x[key]][0] += 1
                st[x[key]][1] += x["budget"]
            store[fam] = number_codes({k: tuple(v) for k, v in st.items()}, fam, kind)
    for x in prods:
        x["fg"], x["bg"] = fcode[x["fam"]][x["ff"]], bcode[x["fam"]][x["bf"]]
        x["gr"] = x["fg"] + "-" + x["bg"]
        x["flow"] = x["ff"] + SEP + x["bf"]
        x["ffn"] = name_flow(x["ff"], x["fam"], "前", cn)
        x["bfn"] = name_flow(x["bf"], x["fam"], "後", cn)
    # 一覧
    groups = []
    for fam in FAMILIES:
        ps = [x for x in prods if x["fam"] == fam]
        tot = sum(x["budget"] for x in ps)
        for table, key, fkey in (("Group Routing", "gr", "flow"), ("前工程G", "fg", "ff"), ("後工程G", "bg", "bf")):
            g = collections.defaultdict(list)
            for x in ps:
                g[x[key]].append(x)
            rows = []
            for sym, xs in g.items():
                n = len(xs)
                b = sum(x["budget"] for x in xs)
                r = {"表": table, "ファミリー": fam, "グループ記号": sym, "区分": "通常" if n >= 2 else "特別枠",
                     "前工程G": xs[0]["fg"] if table != "後工程G" else "", "後工程G": xs[0]["bg"] if table != "前工程G" else "",
                     "特徴": "", "特徴の出どころ": "", "品番数": n, "予算金額": b,
                     "金額構成比": (b / tot).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
                     "品番名": xs[0]["p"]["製品名"] if n == 1 else "", "日報工程フロー": xs[0][fkey],
                     "日報工程フロー（工程名）": "" if table == "Group Routing" else xs[0]["ffn" if table == "前工程G" else "bfn"]}
                rows.append(r)
            for kubun in ("通常", "特別枠"):
                sec = [r for r in rows if r["区分"] == kubun]
                if table == "Group Routing" and kubun == "通常":
                    sk = lambda r: (-r["品番数"], K(r["前工程G"]), K(r["後工程G"]))
                elif table == "Group Routing":
                    sk = lambda r: (K(r["前工程G"]), K(r["後工程G"]))
                else:
                    sk = lambda r: (K(r["グループ記号"]),)
                sec.sort(key=sk)
                for i, r in enumerate(sec, 1):
                    r["並び順"] = i
                    groups.append(r)
    tord = {"Group Routing": 0, "前工程G": 1, "後工程G": 2}
    groups.sort(key=lambda r: (tord[r["表"]], FAMILIES.index(r["ファミリー"]), r["区分"] != "通常", r["並び順"]))
    add_features(groups, prods)
    # 明細
    kub = {(g["ファミリー"], g["グループ記号"]): g["区分"] for g in groups if g["表"] == "Group Routing"}
    prods.sort(key=lambda x: (FAMILIES.index(x["fam"]), K(x["fg"]), K(x["bg"]), -x["budget"], int(x["pid"])))
    detail = []
    for x in prods:
        p = x["p"]
        detail.append({"製品ID": x["pid"], "製造国": p["製造国"], "製品名": p["製品名"], "顧客名": p["顧客名"],
                       "ファミリー": x["fam"], "予算金額": format(x["budget"], "f"), "Group Routing": x["gr"],
                       "前工程G": x["fg"], "後工程G": x["bg"], "区分": kub[(x["fam"], x["gr"])],
                       "前工程フロー": x["ff"], "後工程フロー": x["bf"], "日報工程フロー（前工程｜後工程）": x["flow"],
                       "前工程フロー（工程名）": x["ffn"], "後工程フロー（工程名）": x["bfn"],
                       "追加工程（自由記入）": x["extra"], "備考": x["note"], "見本との照合": "未照合",
                       "判定": x["judge"], "根拠": x["basis"]})
    return detail, groups


FIXED = "固定（未入力・外注）"
AIMARK = "（AI下書き・要確認）"


def load_sample_features():
    """規則 24: 見本 ② の (ファミリー, 日報工程フロー) → 特徴。"""
    import re
    rows = read_text(os.path.join(BASE, "data", "raw", "見本_sheet1_GroupRouting.txt"))
    return {(r[1], r[8]): r[2] for r in rows if re.fullmatch("[A-Z]+F[0-9][0-9]", r[0])}


def load_drafts():
    p = os.path.join(BASE, "src", "特徴_下書き.csv")
    return {(r["ファミリー"], r["前工程フロー"]): r["特徴"] for r in csv.DictReader(open(p, encoding="utf-8-sig", newline=""))}


def add_features(groups, prods):
    """規則 24。前工程G → 特徴と出どころ。Group Routing 表は前工程G の特徴と同じ。後工程G は B00 のみ固定。"""
    sample, drafts = load_sample_features(), load_drafts()
    flow_of = {(x["fam"], x["fg"]): x["ff"] for x in prods}
    fe = {}
    for (fam, fg), ff in flow_of.items():
        if fg[-2:] == "00":
            fe[(fam, fg)] = ("前工程 未入力", FIXED)
        elif fg[-2:] == "99":
            fe[(fam, fg)] = ("前工程 外注", FIXED)
        elif fam in ("シングル", "ハイブリッド") and (fam, ff) in sample:
            fe[(fam, fg)] = (sample[(fam, ff)], "見本")
        elif (fam, ff) in drafts and drafts[(fam, ff)].strip():
            fe[(fam, fg)] = (drafts[(fam, ff)].strip() + AIMARK, "AI下書き（要確認）")
        else:
            raise StopError(f"特徴の下書きが無い前工程フロー: {fam} {fg} {ff}")
    for g in groups:
        if g["表"] == "後工程G":
            g["特徴"], g["特徴の出どころ"] = ("後工程 未入力", FIXED) if g["グループ記号"][-2:] == "00" else ("", "なし")
        else:
            fg = g["グループ記号"].split("-")[0]
            g["特徴"], g["特徴の出どころ"] = fe[(g["ファミリー"], fg)]


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: (format(v, "f") if isinstance(v, Decimal) else v) for k, v in r.items()})
