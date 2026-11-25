"""IZ-001 S7: Excel・summary.csv・source_sheets.csv を出す（規則 F5・4 節）。data/ と out/ だけから作る（原本はシート名と sha256 の確認だけ）。
様式: meltec-excel 0.9.1 の型 B（集計レポート型）＋日本語の決まり（文字 Noto Sans JP 9・数 Arial 9・中身の行 14.25pt）。
LibreOffice が無い PC では再計算・post_fix を通せない（検算の数式は Excel で開くと計算される）。"""
import csv, json, sys, os
from collections import Counter, defaultdict
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter as L

KIT = Path(os.environ.get("FMX_DIR") or (Path.home() / ".claude/plugins/cache/excel-format/meltec-excel/0.9.1/skills/finance-excel/scripts"))
sys.path.insert(0, str(KIT))
import fmx  # noqa: E402

from s1_fetch import DATA  # noqa: E402
from s5_calc import OUT, rd, write_out  # noqa: E402

KIT_VERSION = "meltec-excel 0.9.1（型 B 集計レポート型＋日本語の決まり）"
XLSX = OUT / "261124_GroupRouting_JP_v1.xlsx"
FAMS = ["シングル", "ハイブリッド", "モリブデン", "電鋳", "ミラーブラック"]
SHEET_NAME = {"シングル": "20_シングル_日報", "ハイブリッド": "21_ハイブリッド_日報", "モリブデン": "22_モリブデン_工程",
              "電鋳": "23_電鋳_工程", "ミラーブラック": "24_ミラーブラック_工程"}
SP, CK, NEW = "特別枠", "要確認", "新規"


def rdo(f):
    return list(csv.DictReader(open(OUT / f, encoding="utf-8-sig")))


def fl(v):
    return float(v) if str(v).strip() else 0.0


def jp_ja(v):
    return isinstance(v, str) and any(ord(ch) > 127 for ch in v)


# ---------------------------------------------------------------- source_sheets / summary
def build_source_sheets():
    m = json.load(open(DATA / "_manifest.json", encoding="utf-8"))
    rows = []
    for k, v in m.items():
        if not k.endswith(".xlsx"):
            continue
        fname = k[5:]
        for s in load_workbook(v["source"], read_only=True).sheetnames:
            if "GroupRouting" in fname:
                use, why = "お手本", "お手本（出力の形・既存のグループ。読むだけ）"
            elif s == "Sheet1":
                use, why = "対象", "品番・製造国・製品ファミリー・予算金額の元（1216 品番。日本 1032 を対象）"
            elif s in FAMS:
                use, why = "対象", "工程シート（2026-11-23 決定: 5 枚すべて含める）"
            else:
                use, why = "対象外", "財務シート群（工程の情報ではない。2026-11-23 決定: 対象外）"
            rows.append([fname, s, use, why])
    write_out("source_sheets.csv", ["file", "sheet", "use", "reason"], rows)
    return m, rows


def build_summary(O, G, steps, nmap, X, T, F, B):
    S = []

    def add(k, v, note=""):
        S.append([k, v, note])

    isjp = lambda c: c.strip() == "日本"
    mis = lambda c: c.strip() == "" or "生産国欠落" in c
    J = [x for x in X if isjp(x["country"])]
    M = [x for x in X if mis(x["country"])]
    V = [x for x in X if not isjp(x["country"]) and not mis(x["country"])]
    bs = lambda Lst: sum(fl(x["budget"]) for x in Lst)
    add("n_items_src", len(X), "原本 Sheet1 の品番数")
    add("n_items_jp", len(J), "対象（製造国=日本）")
    add("budget_jp", bs(J), "対象の予算金額の合計（円）")
    add("n_items_overseas", len(V), "日本以外（フィリピン・タイ）。対象外")
    add("budget_overseas", bs(V))
    add("n_items_country_missing", len(M), "製造国の欠落。対象外")
    add("budget_country_missing", bs(M))
    fam = defaultdict(list)
    for o in O:
        fam[o["family"]].append(o)
    for f_, Lst in fam.items():
        add(f"n_family:{f_}", len(Lst), "対象の日本の品番（原本の製品ファミリー）")
    for f_, Lst in fam.items():
        add(f"budget_family:{f_}", bs(Lst))
    U = [o for o in O if o["group_routing"].startswith("未入力_")]
    add("n_items_unentered", len(U), "工程の元データが無い品番（未入力グループ。SC2 に数える）")
    add("budget_unentered", bs(U))
    K = {(t["id"], t["src_key"], t["cell_kind"]) for t in steps}
    for a, w in [("seq", "通し順"), ("mark", "印"), ("code", "コード注記"), ("note", "備考"), ("unused", "不使用")]:
        add("n_cell_" + a, sum(1 for q in K if q[2] == w), f"対象の品番の（品番, 工程列）の数: {w}")
    add("n_groups", len(G), "Group Routing の数（未入力グループを含む）")
    jc = Counter(o["判定"] for o in O)
    add("n_judge_match", jc["一致"], "品番の判定=一致")
    add("n_judge_infer", jc["類推"], "品番の判定=類推")
    add("n_judge_check", jc["要確認"], "品番の判定=要確認")
    add("n_map_rows", len(nmap), "日報Map の行数（工程列の数）")
    add("n_map_unset", sum(1 for r in nmap if r["map_type"] == "コード未設定"), "日報コードが決まっていない工程列")
    add("n_map_check", sum(1 for r in nmap if r["判定"] == CK), "日報Map で判定=要確認の行")
    add("n_multi_sheet", sum(1 for o in O if "複数のシートに値" in o["根拠"]), "2 枚以上のシートに値がある品番（D2）")
    add("n_family_sheet_mismatch", sum(1 for o in O if "と違うシートに値" in o["根拠"] or "と違うシート（" in o["根拠"]), "製品ファミリーと違うシートの品番（D2）")
    add("n_dup_apart", sum(1 for o in O if "間を挟んで" in o["根拠"]), "同じコードが間を挟んで 2 回以上出る品番の数（D6）")
    # お手本との照合（C23 と同じ数え方）
    O_by = {o["id"]: o for o in O}
    jn = lambda a, b: "→".join(x for x in (a, b) if x)
    fm = lambda t: t["sheet"].split("_")[0]
    P = [(t, O_by[t["id"]]) for t in T if t["id"] in O_by]
    ok = lambda t, o: o["route_family"] == fm(t) and o["match_key"] == jn(F[t["front_g"]]["front_key"], B[t["back_g"]]["back_key"])
    n_match = sum(1 for t, o in P if ok(t, o))
    add("n_template_items", len(T), "お手本の品番の行数（シート別 id）")
    add("n_template_changed", len(P) - n_match, f"照合対象 {len(P)} のうち、更新後の照合キーがお手本の定義と違う数（一致は {n_match}）")
    add("n_template_missing", len(T) - len(P), "お手本の品番のうち更新対象に無い行")
    add("n_budget_blank", sum(1 for o in O if not o["budget"].strip()), "予算金額が空欄の対象品番（合計では 0 扱い）")
    write_out("summary.csv", ["key", "value", "note"], S)
    return {k: v for k, v, _ in S}, n_match, len(P)


# ---------------------------------------------------------------- workbook helpers
def table(ws, r0, headers, rows, fmts, left=0, kinds=None, widths_hint=None):
    """見出し 1 行＋明細。fmts: 列ごとの number_format（None=文字）。戻り値: 最終行。"""
    fmx.header(ws, r0, 2, headers, left=left or len(headers))
    for i, row in enumerate(rows):
        r = r0 + 1 + i
        for j, v in enumerate(row):
            c = fmx.put(ws, (r, 2 + j), v if v != "" else None, "data", fmts[j])
            if fmts[j] is None and isinstance(v, str) and v != "":
                c.alignment = c.alignment.copy(horizontal="left")
    return r0 + len(rows)


def n_or_str(v):
    return int(v) if str(v).isdigit() else v


def run():
    O = rdo("item_routing.csv")
    G = rdo("groups.csv")
    steps = rdo("item_steps.csv")
    nmap = rdo("nippo_map.csv")
    X = rd("items_src.csv")
    T = rd("template_items.csv")
    F = {f["front_g"]: f for f in rd("template_front.csv")}
    B = {b["back_g"]: b for b in rd("template_back.csv")}
    manifest, src_rows = build_source_sheets()
    SM, n_match, n_target = build_summary(O, G, steps, nmap, X, T, F, B)
    tot_budget = sum(fl(o["budget"]) for o in O)

    wb = Workbook()
    wb.remove(wb.active)
    fmx.set_default_font(wb)
    fmx.set_style("D")

    # ---- 10_GroupRouting
    ws = wb.create_sheet("10_GroupRouting")
    hdr = ["Group Routing", "ファミリー", "前工程G", "前工程の特徴", "後工程G", "品番数", "予算金額（JPY k）", "金額構成比（対象全体）", "品番名", "日報工程フロー", "前工程フロー", "後工程フロー"]
    fmx.setup(ws, "Group Routing（日本 1032 品番）  単位: 予算金額は JPY k", {"B": 18, "C": 12, "D": 9, "E": 30, "F": 9, "G": 8, "H": 14, "I": 12, "J": 40, "K": 50, "L": 40, "M": 24}, freeze="C6")
    fmx.band(ws, 4, 2, 13, "1. Group Routing（品番数・予算金額）")
    r = table(ws, 5, hdr, [[g["group_routing"], g["family"], g["front_g"], g["front_feature"], g["back_g"], int(g["n_items"]), fl(g["budget"]), fl(g["budget_share"]),
                            g["product_names"], g["group_flow"], g["front_flow"], g["back_flow"]] for g in G],
              [None, None, None, None, None, fmx.NUM, fmx.JPYK, fmx.PCT, None, None, None, None], left=5)
    g_first, g_last = 6, r
    # ② ③
    def defs(key_g, key_sec, key_feat, key_flow, title, r0):
        d = {}
        for g in G:
            k = (g["family"], g[key_g])
            if g[key_g]:
                d.setdefault(k, g)
        use = defaultdict(lambda: [0, 0.0])
        for o in O:
            if o[key_g.replace("front_g", "front_g").replace("back_g", "back_g")]:
                u = use[(o["route_family"], o[key_g])]
                u[0] += 1
                u[1] += fl(o["budget"])
        rows = []
        for (f_, gg), g in sorted(d.items()):
            n, b = use[(f_, gg)]
            rows.append([gg, f_, g[key_sec], g[key_feat] if key_feat else "", n, b, b / tot_budget if tot_budget else 0, g[key_flow]])
        fmx.band(ws, r0, 2, 13, title)
        rr = table(ws, r0 + 1 + 1 - 1 + 1, ["G", "ファミリー", "区分", "特徴", "品番数", "予算金額（JPY k）", "金額構成比（対象全体）", "フロー"], rows,
                   [None, None, None, None, fmx.NUM, fmx.JPYK, fmx.PCT, None], left=4)
        return rr
    r = defs("front_g", "front_section", "front_feature", "front_flow", "2. 前工程グループ（区分: 通常／特別枠／新規）", g_last + 2)
    r = defs("back_g", "back_section", None, "back_flow", "3. 後工程グループ（区分: 通常／特別枠／新規）", r + 2)

    # ---- 11_品番一覧
    ws2 = wb.create_sheet("11_品番一覧")
    fmx.setup(ws2, "品番一覧（SC2: 対象の全品番と Group Routing）  単位: 予算金額は JPY k",
              {"B": 9, "C": 26, "D": 18, "E": 14, "F": 14, "G": 16, "H": 12, "I": 12, "J": 20, "K": 14, "L": 10, "M": 70}, freeze="D6")
    fmx.band(ws2, 4, 2, 13, "1. 品番と Group Routing・判定")
    items = sorted(O, key=lambda o: (0, int(o["id"]), "") if o["id"].isdigit() else (1, 0, o["id"]))
    r2 = table(ws2, 5, ["ID", "製品名", "顧客名", "製品ファミリー", "工程シート", "Group Routing", "前工程G", "後工程G", "お手本の Group Routing", "予算金額（JPY k）", "判定", "根拠"],
               [[o["id"], o["product"], o["customer"], o["family"], o["route_sheet"], o["group_routing"], o["front_g"], o["back_g"], o["template_group"],
                 fl(o["budget"]) if o["budget"].strip() else None, o["判定"], o["根拠"]] for o in items],
               [None, None, None, None, None, None, None, None, None, fmx.JPYK, None, None], left=9)
    i_first, i_last = 6, r2

    # ---- 20〜24 工程シート
    by_item = defaultdict(list)
    for s in steps:
        by_item[s["id"]].append(s)
    fam_rows = {}
    for f_ in FAMS:
        w = wb.create_sheet(SHEET_NAME[f_])
        its = [o for o in items if o["route_sheet"] == f_]
        toks = {}
        for o in its:
            for s in by_item[o["id"]]:
                if s["in_flow"] == "1" and s["seq"]:
                    t = s["token"]
                    cn = int(s["col_no"])
                    toks[t] = min(toks.get(t, 10 ** 6), cn)
        code = lambda t: not t.startswith("[")
        order = sorted([t for t in toks if code(t)]) + sorted([t for t in toks if not code(t)], key=lambda t: toks[t])
        nb = 9
        widths = {"B": 9, "C": 12, "D": 24, "E": 14, "F": 14, "G": 14, "H": 16, "I": 9, "J": 9}
        for k in range(len(order)):
            widths[L(2 + nb + k)] = 8
        fmx.setup(w, f"{f_}（工程シート）  1 行 1 品番・セルは通し順（seq）  単位: 予算金額は JPY k", widths, freeze="E6")
        fmx.band(w, 4, 2, 1 + nb + max(len(order), 1), "1. 品番ごとの工程の流れ（日報コードは番号順、[元列] は元の列順）")
        rows = []
        for o in its:
            sq = {s["token"]: int(s["seq"]) for s in by_item[o["id"]] if s["in_flow"] == "1" and s["seq"]}
            rows.append([o["id"], o["country"], o["product"], o["customer"], o["family"], fl(o["budget"]) if o["budget"].strip() else None,
                         o["group_routing"], o["front_g"], o["back_g"]] + [sq.get(t) for t in order])
        rr = table(w, 5, ["ID", "製造国", "製品名", "顧客名", "製品ファミリー", "予算金額（JPY k）", "Group Routing", "前工程G", "後工程G"] + order, rows,
                   [None, None, None, None, None, fmx.JPYK, None, None, None] + [fmx.NUM] * len(order), left=nb)
        fam_rows[f_] = (len(its), 6, rr)

    # ---- 30 日報Map
    wm = wb.create_sheet("30_日報Map")
    fmx.setup(wm, "日報Map（1 行 1 工程列）", {"B": 14, "C": 14, "D": 8, "E": 8, "F": 26, "G": 10, "H": 8, "I": 8, "J": 8, "K": 18, "L": 10, "M": 70}, freeze="D6")
    fmx.band(wm, 4, 2, 13, "1. 工程列と日報コードの対応")
    rm = table(wm, 5, ["ファミリー", "シート", "列番号", "列", "実工程名", "使用品番数", "コード1", "コード2", "コード3", "対応区分", "判定", "根拠"],
               [[r_["family"], r_["sheet"], int(r_["col_no"]), r_["col_letter"], r_["col_name"], int(r_["n_items"]), r_["code1"], r_["code2"], r_["code3"],
                 r_["map_type"], r_["判定"], r_["根拠"]] for r_ in nmap],
               [None, None, fmx.NUM, None, None, fmx.NUM, None, None, None, None, None, None], left=5)

    # ---- 31 要確認一覧
    wc = wb.create_sheet("31_要確認一覧")
    fmx.setup(wc, "要確認一覧（判定=要確認の品番と日報Map の行）", {"B": 9, "C": 26, "D": 14, "E": 20, "F": 12, "G": 90}, freeze="C6")
    chk = [o for o in items if o["判定"] == CK]
    fmx.band(wc, 4, 2, 7, f"1. 判定=要確認の品番（{len(chk)} 件。理由に備考のセルの値を含む）")
    rc = table(wc, 5, ["ID", "製品名", "製品ファミリー", "Group Routing", "工程シート", "理由"],
               [[o["id"], o["product"], o["family"], o["group_routing"], o["route_sheet"], o["根拠"]] for o in chk], [None] * 6, left=6)
    cm = [r_ for r_ in nmap if r_["判定"] == CK]
    rb = rc + 2
    fmx.band(wc, rb, 2, 7, f"2. 判定=要確認の日報Map の行（{len(cm)} 件）")
    table(wc, rb + 1, ["ファミリー", "実工程名", "列", "コード", "対応区分", "理由"],
          [[r_["family"], r_["col_name"], r_["col_letter"], "・".join(c for c in (r_["code1"], r_["code2"], r_["code3"]) if c), r_["map_type"], r_["根拠"]] for r_ in cm],
          [None] * 6, left=6)

    # ---- 40_Checks（数式。Excel で開くと計算される）
    wk = wb.create_sheet("40_Checks")
    fmx.setup(wk, "検算（合計−明細の和＝0。OK/NG）", {"B": 8, "C": 60, "D": 16, "E": 16, "F": 14, "G": 8})
    fmx.band(wk, 4, 2, 7, "1. 検算")
    fmx.header(wk, 5, 2, ["ID", "検算", "合計側", "明細側", "差", "結果"], left=2)
    gq = f"'10_GroupRouting'!$G${g_first}:$G${g_last}"
    gb = f"'10_GroupRouting'!$H${g_first}:$H${g_last}"
    iq = f"'11_品番一覧'!$B${i_first}:$B${i_last}"
    ib = f"'11_品番一覧'!$K${i_first}:$K${i_last}"
    fam_n = "+".join(f"COUNT('{SHEET_NAME[f_]}'!$B$6:$B${max(fam_rows[f_][2], 6)})" for f_ in FAMS if fam_rows[f_][0])
    fam_b = "+".join(f"SUM('{SHEET_NAME[f_]}'!$G$6:$G${max(fam_rows[f_][2], 6)})" for f_ in FAMS if fam_rows[f_][0])
    unent = sum(1 for o in O if not o["route_sheet"])
    unent_b = sum(fl(o["budget"]) for o in O if not o["route_sheet"])
    rows_c = [
        ("CHK-01", "GroupRouting の品番数の合計 − 品番一覧の行数", f"=SUM({gq})", f"=COUNTA({iq.replace('$B$', '$B$')})", 0.5),
        ("CHK-02", "GroupRouting の予算金額の合計 − 品番一覧の予算金額の合計（円）", f"=SUM({gb})", f"=SUM({ib})", 1),
        ("CHK-03", "品番一覧の予算金額の合計 − 原本から数えた対象の合計（円）", f"=SUM({ib})", tot_budget, 1),
        ("CHK-04", "5 枚の工程シートの品番数の合計 + 工程未入力の品番数 − 品番一覧の行数", f"={fam_n}+{unent}", f"=COUNTA({iq})", 0.5),
        ("CHK-05", "5 枚の工程シートの予算金額の合計 + 工程未入力の予算金額 − 品番一覧の合計（円）", f"={fam_b}+{unent_b}", f"=SUM({ib})", 1),
        ("CHK-06", "品番一覧の行数 − 対象の品番数（summary の n_items_jp）", f"=COUNTA({iq})", int(SM["n_items_jp"]), 0.5),
        ("CHK-07", "お手本との照合: 一致 + 不一致 − 照合対象の数", n_match + int(SM["n_template_changed"]), n_target, 0.5),
    ]
    for k, (cid, name, a, b, tol) in enumerate(rows_c):
        r = 6 + k
        fmx.put(wk, (r, 2), cid, "label")
        fmx.put(wk, (r, 3), name, "label")
        fmx.put(wk, (r, 4), a, "calc", fmx.NUM)
        fmx.put(wk, (r, 5), b, "calc", fmx.NUM)
        fmx.put(wk, (r, 6), f"=D{r}-E{r}", "calc", fmx.NUM)
        fmx.put(wk, (r, 7), f'=IF(ABS(F{r})<{tol},"OK","NG")', "calc", align="center")
    fmx.red_if(wk, f"G6:G{5 + len(rows_c)}", 'G6="NG"')

    # ---- 00_README・90_Log
    fam_cnt = {f_: fam_rows[f_][0] for f_ in FAMS}
    sheets_txt = [("10_GroupRouting", "① Group Routing ごとの品番数・予算金額・金額構成比。下に ② 前工程グループ・③ 後工程グループの定義（区分: 通常／特別枠／新規）"),
                  ("11_品番一覧", "対象の全品番と Group Routing・判定・根拠（SC2 のマッピング）"),
                  ("20〜24 工程シート", "シングル・ハイブリッド・モリブデン・電鋳・ミラーブラック。1 行 1 品番、セルに通し順（seq）。" + "、".join(f"{k} {v} 品番" for k, v in fam_cnt.items())),
                  ("30_日報Map", "工程列（元の列）→日報コード。判定と根拠つき"),
                  ("31_要確認一覧", f"判定=要確認の品番 {len(chk)} 件と日報Map の行 {len(cm)} 件。理由つき"),
                  ("40_Checks", "合計と明細の突き合わせ（OK/NG）。数式。Excel で開くと計算される"),
                  ("90_Log", "様式と版・作った日・原本")]
    src_txt = "；".join(f"{r_[0]}（sha256 {m_['sha256'][:12]}）" for r_, m_ in [(("お手本 " + k[5:],), v) for k, v in manifest.items() if "GroupRouting" in k] +
                                                                              [(("更新対象 " + k[5:],), v) for k, v in manifest.items() if "jpn_03" in k])
    rules = [("対象", f"製造国=日本の {SM['n_items_jp']:.0f} 品番。対象外 {SM['n_items_overseas'] + SM['n_items_country_missing']:.0f} 件（日本以外 {SM['n_items_overseas']:.0f}・製造国の欠落 {SM['n_items_country_missing']:.0f}）。件数と金額は summary.csv"),
             ("グループ", "シングル・ハイブリッドの前工程G・後工程G はお手本の定義（②③）を基準に決める。モリブデン・電鋳・ミラーブラックは日報コードが無く、元列名でフロー。工程の元データが無い品番は「未入力_<ファミリー>」"),
             ("判定", f"一致 {SM['n_judge_match']:.0f}／類推 {SM['n_judge_infer']:.0f}／要確認 {SM['n_judge_check']:.0f}（品番）。判定の根拠は各行に付けた"),
             ("お手本との照合", f"照合対象 {n_target} 品番のうち一致 {n_match}、不一致 {SM['n_template_changed']:.0f}（更新対象で工程や並びが変わった品番。判定=要確認）。ハイブリッドは同じ工程が繰り返されるため一致 0（仮定のまま進めた。2026-11-25 人の決定）"),
             ("決定（2026-11-23〜25）", "モリブデン・電鋳・ミラーブラックを含める／工程の元データが無い品番は未入力グループ／「〇」は列の並びを通し順とみなす／照合は案B／ハイブリッドの照合は仮定のまま"),
             ("残った要確認", "原文「まてゃRouting」の意味／日報Map のお手本比較（択一・自由記入）／ハイブリッドの繰り返しの扱い。詳細は 31_要確認一覧"),
             ("色", "青＝原本・CSV から写した値、黒＝計算・ラベル")]
    _, legend = fmx.readme(wb, XLSX.name, "現状の工程のまとめ・商品グループ化・品番マッピング（IZ-001。SC1〜SC3）", "初版（v1）", "v1",
                           sheets_txt, rules,
                           ["Excel で開いて保存する（再計算のため）", "40_Checks がすべて OK か確認する", "31_要確認一覧を上長・Customer に確認する"],
                           "合計と明細が合い、全品番がいずれかの Group Routing に入っている")
    wr = wb["00_README"]
    r = wr.max_row + 2
    fmx.band(wr, r, 2, 3, "6. 出どころ")
    fmx.text_block(wr, r + 1, [("原本の版", src_txt), ("作業標準書 8 件", "このタスクでは読まない（IZ-002）")])
    fmx.log_sheet(wb, [("2026-11-26", "v1", f"初版。{KIT_VERSION}で作成。{src_txt}", "Claude（泉屋）")])

    fmx.space_all(wb)
    fmx.autofit_rows(wb)
    # 日本語の決まり: 文字は Noto Sans JP 9、数は Arial 9、中身の行は 14.25pt
    for w in wb.worksheets:
        for row in w.iter_rows():
            for c in row:
                if jp_ja(c.value):
                    f = c.font
                    c.font = Font(name="Noto Sans JP", size=f.size, bold=f.b, italic=f.i, color=f.color)
        for rr, dim in list(w.row_dimensions.items()):
            if dim.height == 12:
                dim.height = 14.25
    wb._named_styles["Normal"].font = Font(name="Noto Sans JP", size=9, color=fmx.BLACK)
    wb.calculation.fullCalcOnLoad = True
    wb.save(XLSX)
    print("S7 xlsx", XLSX.name, "sheets", len(wb.worksheets), "| summary keys", len(SM), "| source_sheets", len(src_rows),
          "| items", len(O), "groups", len(G), "| template match", n_match, "changed", SM["n_template_changed"], "target", n_target)


if __name__ == "__main__":
    run()
