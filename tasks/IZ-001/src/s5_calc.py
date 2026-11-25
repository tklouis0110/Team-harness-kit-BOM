"""IZ-001 S5: 日報Map（規則 C）と品番別ルーティング（規則 D）。data/ の CSV だけから作る（原本は読まない）。
out/nippo_map.csv と out/item_steps.csv を出す。out/item_routing.csv は D で決まる列（route_sheet・flow・flow_code・判定・根拠）だけ
先に出す（C17 が判定を読むため）。E の列（グループ関連）は空欄のまま。S6 が全部を上書きして完成させる。"""
import csv, re, unicodedata
from collections import Counter
from s1_fetch import TASK, DATA, SHEETS

OUT = TASK / "out"
CODE = re.compile(r"[A-Z]{1,2}[0-9]{2}")
CODE_PAT = re.compile(r"([A-Z]{1,2})([0-9]{2})\s*[〜～~]\s*(?:[A-Z]{1,2})?([0-9]{2})|[A-Z]{1,2}[0-9]{2}")
NUM = re.compile(r"-?[0-9０-９]+([.．][0-9０-９]+)?")
CODEN = re.compile(r"[A-Z]{1,2}[0-9]{2}([・,、/／〜～~ ]+[A-Z]{1,2}[0-9]{2})*")
MARK = {"〇", "○", "◯"}
UNUSED = {"-", "－", "無", "無し", "なし", "×"}
RANK = {"一致": 0, "類推": 1, "要確認": 2}


def ws_(s):
    return re.sub(r"\s", "", s)


def rd(f):
    return list(csv.DictReader(open(DATA / f, encoding="utf-8-sig")))


def write_out(name, header, rows):
    OUT.mkdir(exist_ok=True)
    with open(OUT / name, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def codes_in(text):
    """注記・セルの文字から日報コードを左から拾う。範囲は間を補う。重複は最初だけ。"""
    out = []
    for m in CODE_PAT.finditer(text):
        if m.group(1):
            a, b = int(m.group(2)), int(m.group(3))
            cs = [f"{m.group(1)}{n:02d}" for n in range(a, b + 1)] if a <= b else [m.group(0)]
        else:
            cs = [m.group(0)]
        for c in cs:
            if c not in out:
                out.append(c)
    return out


def fnum(v):
    return float(unicodedata.normalize("NFKC", v))


def kind_of(v):  # 規則 D1
    if NUM.fullmatch(v):
        return "通し順" if fnum(v) > 0 else "不使用"
    if v in MARK:
        return "印"
    if v in UNUSED:
        return "不使用"
    if CODEN.fullmatch(v):
        return "コード注記"
    return "備考"


def build_map(pc, steps_jp):
    """規則 C。"""
    tmap = rd("template_map.csv")
    used = {}
    for s in steps_jp:
        if kind_of(s["value"]) != "不使用":
            used.setdefault(s["src_key"], set()).add(s["id"])
    rows = []
    for p in pc:
        codes = codes_in(p["nippo_code_note"])
        mt = "コード未設定" if not codes else "1対1" if len(codes) == 1 else "連続（全て計上）"
        c3 = (codes + ["", "", ""])[:3]
        sheet = p["sheet"]
        if sheet in ("モリブデン", "電鋳", "ミラーブラック"):
            j, why = "一致", "日報コードの行が無いシート（元列名でフロー。2026-11-23 決定）"
        else:
            cand = [t for t in tmap if t["family"] == sheet and p["col_name"] and ws_(t["col_name"]) == ws_(p["col_name"])]
            if len(cand) > 1:
                cand = [t for t in cand if t["col_letter"] == p["col_letter"]] or cand
            if not cand:
                cand = [t for t in tmap if t["family"] == sheet and t["col_letter"] == p["col_letter"]]
            if cand:
                t = cand[0]
                tc = [t["code1"], t["code2"], t["code3"]]
                if tc == c3 and t["map_type"] == mt:
                    j, why = "一致", f"お手本の日報Map（{t['col_letter']}列 {t['col_name']}）と同じ"
                else:
                    j = "要確認"
                    why = "更新対象の値を採用。お手本: " + ("→".join(x for x in tc if x) or "コード無し") + "／" + t["map_type"] + f"（{t['col_letter']}列 {t['col_name']}）"
            elif codes:
                j, why = "一致", "お手本に無い列。注記からコードが決まった"
            elif p["nippo_name_note"].strip() == "無し":
                j, why = "一致", "注記が「無し」と明示（コード未設定）"
            else:
                j, why = "要確認", "お手本に無い列で、注記が空（コード未設定）"
        if len(codes) > 3:
            j, why = "要確認", f"注記のコードが {len(codes)} 個（先頭 3 つを採用）。" + why
        rows.append([sheet, sheet, p["col_no"], p["col_letter"], p["src_key"], p["col_name"], len(used.get(p["src_key"], ())), *c3, mt, j, why])
    return rows


def run():
    pc = rd("process_columns.csv")
    jp = [x for x in rd("items_src.csv") if x["country"].strip() == "日本"]
    jp_ids = {x["id"] for x in jp}
    steps = [s for s in rd("steps_src.csv") if s["id"] in jp_ids]

    mrows = build_map(pc, steps)
    write_out("nippo_map.csv", ["family", "sheet", "col_no", "col_letter", "src_key", "col_name", "n_items", "code1", "code2", "code3", "map_type", "判定", "根拠"], mrows)
    mp = {r[4]: r for r in mrows}
    pcd = {p["src_key"]: p for p in pc}

    def mcodes(sk):
        return [c for c in mp[sk][7:10] if c]

    def tokens(kind, value, sk):
        if kind == "コード注記":
            return codes_in(value) or [value]
        cs = mcodes(sk)
        if cs:
            return cs
        nm = pcd[sk]["col_name"].strip()
        return [f"[{nm}]" if nm else f"[列{pcd[sk]['col_no']}]"]

    by_item = {}
    for s in steps:
        s = dict(s)
        s["kind"] = kind_of(s["value"])
        s["col_no"] = int(s["col_no"])
        by_item.setdefault(s["id"], []).append(s)

    step_rows, route_rows = [], []
    order = {s: i for i, s in enumerate(SHEETS)}
    n_dup_apart = 0
    for it in jp:
        iid, fam = it["id"], it["family"]
        cells = by_item.get(iid, [])
        use = [c for c in cells if c["kind"] != "不使用"]
        st = {"judge": "一致", "why": []}

        def bump(j, why):
            if RANK[j] > RANK[st["judge"]]:
                st["judge"] = j
            st["why"].append(why)

        usheets = sorted({c["sheet"] for c in use}, key=lambda s: order[s])
        rs = ""
        if len(usheets) == 1:
            rs = usheets[0]
        elif usheets:
            rs = fam if fam in usheets else usheets[0]
            bump("要確認", f"複数のシートに値（{'・'.join(usheets)}）。{rs}を採用、他は in_flow=0")
        if usheets and rs != fam:
            bump("要確認", f"製品ファミリー（{fam}）と違うシート（{rs}）に値あり")
        flow_cells = [c for c in use if c["sheet"] == rs]
        if flow_cells:
            if all(c["kind"] == "通し順" for c in flow_cells):
                vals = [fnum(c["value"]) for c in flow_cells]
                flow_cells.sort(key=lambda c: (fnum(c["value"]), c["col_no"]))
                if len(set(vals)) < len(vals):
                    bump("類推", "同じ通し順の値あり（列の左から）")
            else:
                flow_cells.sort(key=lambda c: c["col_no"])
                bump("類推", "〇・文字を含むため列の並びを通し順とみなした")
                sv = [fnum(c["value"]) for c in flow_cells if c["kind"] == "通し順"]
                if any(b < a for a, b in zip(sv, sv[1:])):
                    bump("要確認", "列の並びと通し順の数が食い違う")
        notes = [c for c in flow_cells if c["kind"] == "備考"]
        if notes:
            bump("要確認", "備考『" + "』『".join(dict.fromkeys(c["value"] for c in notes)) + "』を工程ありとして扱った")
        toks = []
        for c in flow_cells:
            for t in tokens(c["kind"], c["value"], c["src_key"]):
                toks.append((c, t))
            if c["kind"] == "コード注記":
                cc = codes_in(c["value"])
                if cc != mcodes(c["src_key"]):
                    bump("要確認", f"セル {'・'.join(cc)}／Map {'・'.join(mcodes(c['src_key'])) or '無し'}")
        seen, flags = {}, []
        for i, (c, t) in enumerate(toks):
            isc = bool(CODE.fullmatch(t))
            if isc and t in seen:
                flags.append(0)
                if any(CODE.fullmatch(x) and x != t for _, x in toks[seen[t] + 1:i]):
                    bump("要確認", f"同じコード {t} が間を挟んで 2 回以上")
                    n_dup_apart += 1
            else:
                flags.append(1)
                if isc:
                    seen[t] = i
        seqn, flow, flow_code = 0, [], []
        for (c, t), f in zip(toks, flags):
            seq = ""
            if f:
                seqn += 1
                seq = seqn
                flow.append(t)
                if CODE.fullmatch(t):
                    flow_code.append(t)
            step_rows.append([iid, c["sheet"], c["col_no"], c["src_key"], c["value"], c["kind"], t, seq, f])
        inflow = {id(c) for c in flow_cells}
        for c in cells:
            if id(c) not in inflow:  # 不使用・他シートのセル
                for t in tokens(c["kind"], c["value"], c["src_key"]):
                    step_rows.append([iid, c["sheet"], c["col_no"], c["src_key"], c["value"], c["kind"], t, "", 0])
        if not usheets:  # 規則 E6 の判定だけ先に付ける（S6 が上書き）
            if fam in SHEETS:
                st = {"judge": "要確認", "why": ["工程シートに値なし"]}
            else:
                st = {"judge": "一致", "why": ["工程の元データなし。未入力グループ（2026-11-23 決定）"]}
        route_rows.append([iid, it["country"], it["product"], it["customer"], fam, it["budget"], rs, "", "→".join(flow), "→".join(flow_code),
                           "", "", "", "", "", "", "", "", st["judge"], "；".join(st["why"]) or "通し順どおり"])
    write_out("item_steps.csv", ["id", "sheet", "col_no", "src_key", "value", "cell_kind", "token", "seq", "in_flow"], step_rows)
    write_out("item_routing.csv", ["id", "country", "product", "customer", "family", "budget", "route_sheet", "route_family", "flow", "flow_code", "match_key",
                                   "front_flow", "back_flow", "front_g", "back_g", "group_routing", "group_flow", "template_group", "判定", "根拠"], route_rows)
    kinds = Counter(c["kind"] for cs in by_item.values() for c in cs)
    print("nippo_map", len(mrows), dict(Counter(r[11] for r in mrows)), "| item_steps", len(step_rows), "| cells by kind", dict(kinds),
          "| items", len(route_rows), "judge", dict(Counter(r[18] for r in route_rows)), "| dup_apart", n_dup_apart,
          "| unentered", sum(1 for r in route_rows if not r[6]))
