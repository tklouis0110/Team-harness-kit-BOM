"""S6: Excel 7 シート（規則 25・26・33〜37）。値のみ・色罫線なし。"""
import collections
import os
import re
from decimal import Decimal, ROUND_HALF_UP
import openpyxl
from inputs import FAMILIES, StopError, read_text, BASE
from nippo_map import MAP_COLS
from flow import split_cells, tokens, lead, code_names, K

NOTE7 = ["7. モリブデン・電鋳・ミラーブラックは元シートに日報工程コードが無いため「未設定」とし、元の工程名（同名の列は(1)(2)で区別）を工程IDの代わりに使った（2026-11-20 決定）。",
         "8. 3 ファミリーの前工程／後工程は列で分けた（モリブデン＝光源台シート検査、電鋳＝黒板シート検査、ミラーブラック＝自動外観から後工程。要確認）。",
         "9. 後工程G は実施した列の組合せで決め、番号の順は使っていない。",
         "10. 電鋳の ID 179・343・357 はセルに工程名が書かれているため、列の見出しの工程名で前工程を作り、要確認とした。",
         "11. AI が下書きした特徴には「（AI下書き・要確認）」を付けた。"]
EXTRA_A2 = "モリブデン・電鋳・ミラーブラックは日報工程コードが未設定のため工程名で代用し、前工程／後工程を列で分けた（要確認）。"
A2_3FAM = "数字（前工程）＝元の番号を工程名ごとに振り直した順番　数字（後工程）・〇・文字＝元データのまま　日報工程コードが未設定のため、工程名（同名の列は(1)(2)で区別）で代用"


def num(v):
    """数字だけの文字は整数にして書く（それ以外は文字のまま）。"""
    return int(v) if re.fullmatch(r"[0-9]+", v) else v


def column_keys(fam, map_rows):
    keys = []

    def add(k):
        if k and k not in keys:
            keys.append(k)
    for r in map_rows:
        if r["ファミリー"] != fam or int(r["使用品番数"]) < 1 or r["対応区分"] == "自由記入":
            continue
        kd = r["対応区分"]
        if kd == "1対1":
            add(r["日報コード1"])
        elif kd.startswith("連続") or kd == "択一（経路から判定）":
            for c in ("日報コード1", "日報コード2", "日報コード3"):
                add(r[c])
        elif kd.startswith("択一"):
            add(r["振り直し先の列"])
        elif kd == "コード未設定":
            add(r["振り直し先の列"])
        else:
            raise StopError(f"未知の対応区分: {kd}")
    return keys


def product_cells(d, map_rows, detail):
    """明細の行ごとに、_日報 の工程セルの辞書 {トークン: 値} と、規則 26 の検算に使う情報を作る。"""
    mrows = {(r["ファミリー"], r["元列"]): r for r in map_rows}
    cells = collections.defaultdict(list)
    for x in d["detail"]:
        cells[(x["製品ID"], x["出どころシート"])].append(x)
    out = {}
    for m in detail:
        fam, pid = m["ファミリー"], m["製品ID"]
        cs = cells[(pid, fam)]
        cols = {c["出どころ列"] for c in cs}
        free, front, back = split_cells(cs, fam)
        val = {}
        ff = m["前工程フロー"]
        if ff == "外注":
            for c in front:
                if c["値の区分"] == "外注":
                    for t in tokens(c, mrows, cols):
                        val.setdefault(t, "外注")
        elif ff != "―":
            ftoks = ff.split("→")
            allnum = all(lead(c["値（原文）"])[0] for c in front)
            if allnum:
                for k, t in enumerate(ftoks, 1):
                    val[t] = k
            else:
                for c in front:
                    for t in tokens(c, mrows, cols):
                        val.setdefault(t, c["値（原文）"].strip())
        fronts = set(val)
        for c in back:
            for t in tokens(c, mrows, cols):
                if t in fronts:
                    raise StopError(f"前工程と後工程で同じ列に当たる: {fam} {pid} {t}")
                val.setdefault(t, num(c["値（原文）"].strip()))  # 同じ列に複数なら工程列の並びが最初のセル
        out[(fam, pid)] = val
    return out


def build_excel(d, map_rows, detail, groups, path):
    from flow import code_names as _cn
    samp = {}
    gr_rows = read_text(os.path.join(BASE, "data", "raw", "見本_sheet1_GroupRouting.txt"))
    headers = {}
    for r in gr_rows:
        if r[0] in ("Group Routing", "前工程G", "後工程G"):
            headers[r[0]] = r
    a2_sample = gr_rows[1][0]
    notes_sample = [r[0] for r in gr_rows[145:151]]
    for fam, fn in (("シングル", "見本_sheet2_シングル_日報.txt"), ("ハイブリッド", "見本_sheet3_ハイブリッド_日報.txt")):
        rows = read_text(os.path.join(BASE, "data", "raw", fn))
        samp[fam] = rows[1][0]
    cn_res, cn_mp = code_names(d, map_rows)
    cells = product_cells(d, map_rows, detail)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GroupRouting"
    ws.append(["Group Routing（日報工程ID基準）"])
    ws.append([a2_sample + EXTRA_A2])
    ws.append([])
    tot = {f: sum(Decimal(m["予算金額"]) for m in detail if m["ファミリー"] == f) for f in FAMILIES}
    cnt = {f: sum(1 for m in detail if m["ファミリー"] == f) for f in FAMILIES}

    def pct(x, t):
        return (x / t).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP) if t else Decimal(0)

    def money(c):
        c.number_format = "#,##0"

    def fmt_row(rn):
        money(ws.cell(rn, 6))
        ws.cell(rn, 7).number_format = "0.0%"

    for title, table in (("① Group Routing（前工程G × 後工程G）", "Group Routing"), ("② 前工程グループ", "前工程G"), ("③ 後工程グループ", "後工程G")):
        ws.append([title])
        for fam in FAMILIES:
            for kubun, lab in (("通常", "通常（対象品番2以上）"), ("特別枠", "特別枠（対象品番1）")):
                ws.append([f"{fam}：{lab}"])
                ws.append(list(headers[table]))
                gs = [g for g in groups if g["表"] == table and g["ファミリー"] == fam and g["区分"] == kubun]
                if not gs:
                    ws.append(["（該当なし）"])
                for g in gs:
                    ws.append([g["グループ記号"], fam, g["特徴"], g["後工程G"] if table == "Group Routing" else "",
                               g["品番数"], g["予算金額"], g["金額構成比"], g["品番名"], g["日報工程フロー"]]
                              + ([g["日報工程フロー（工程名）"]] if table != "Group Routing" else []))
                    fmt_row(ws.max_row)
                n = sum(g["品番数"] for g in gs)
                b = sum((g["予算金額"] for g in gs), Decimal(0))
                ws.append(["小計", "", "", "", n, b, pct(b, tot[fam])])
                fmt_row(ws.max_row)
            ws.append([f"{fam} 計", "", "", "", cnt[fam], tot[fam], Decimal(1)])
            fmt_row(ws.max_row)
            ws.append([])
        if table != "後工程G":
            pass
    ws.append([])
    ws.append(["前提・確認事項"])
    for t in notes_sample + NOTE7:
        ws.append([t])

    for fam in FAMILIES:
        ws = wb.create_sheet(fam + "_日報")
        keys = column_keys(fam, map_rows)
        mp_rows = [r for r in map_rows if r["ファミリー"] == fam]
        code_row, name_row, tok = [], [], {}
        for j, k in enumerate(keys):
            if k.startswith("未設定："):
                code_row.append("未設定")
                name_row.append(k[len("未設定："):])
                tok[k[len("未設定："):]] = j
            else:
                code_row.append(k)
                nm = cn_res.get(fam, {}).get(k)
                if not nm:
                    nm = "・".join(dict.fromkeys(cn_mp.get((fam, k), [])))
                if not nm:
                    raise StopError(f"列名が決まらない: {fam} {k}")
                name_row.append(nm)
                tok[k] = j
        ms = [m for m in detail if m["ファミリー"] == fam]
        ws.append([f"{fam}：品番別ルーティング（日報工程ID基準）"])
        ws.append([samp[fam] if fam in samp else A2_3FAM])
        ws.append([f"元データ：シート「{fam}」の製造国=日本・製品ファミリー={fam}のうち工程入力がある {len(ms)} 品番。振り直しルールはシート「日報Map」参照。"])
        ws.append([""] * 8 + ["日報工程コード→"] + code_row)
        ws.append(["ID", "製造国", "製品名", "顧客名", "製品ファミリー", "予算金額", "Group Routing", "前工程G", "後工程G"] + name_row + ["追加工程（自由記入）", "備考"])
        for m in ms:
            line = [None] * len(keys)
            for t, v in cells[(fam, m["製品ID"])].items():
                if t not in tok:
                    raise StopError(f"列が無いトークン: {fam} {m['製品ID']} {t}")
                line[tok[t]] = v
            b = Decimal(m["予算金額"])
            ws.append([int(m["製品ID"]), m["製造国"], m["製品名"], m["顧客名"], fam, int(b) if b == b.to_integral_value() else b,
                       m["Group Routing"], m["前工程G"], m["後工程G"]] + line + [m["追加工程（自由記入）"], m["備考"]])
            ws.cell(ws.max_row, 6).number_format = "#,##0"
        ws.freeze_panes = "J6"

    ws = wb.create_sheet("日報Map")
    ws.append(["日報Map：元の工程列 → 日報工程コードの対応"])
    ws.append([])
    ws.append(MAP_COLS)
    for r in map_rows:
        ws.append([int(r[c]) if c == "使用品番数" else r[c] for c in MAP_COLS])
    ws.freeze_panes = "A4"
    wb.save(path)
