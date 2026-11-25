"""IZ-001 S6: グループ化と集計（規則 E・F1〜F4）。data/ と out/（S5 の成果）だけから作る（原本は読まない）。
out/item_routing.csv（E の列を埋めて上書き）と out/groups.csv を出す。"""
import csv, re, unicodedata
from collections import defaultdict
from s1_fetch import DATA
from s5_calc import OUT, rd, write_out, codes_in, CODE, RANK

SYM = {"シングル": "S", "ハイブリッド": "H", "モリブデン": "MO", "電鋳": "EF", "ミラーブラック": "MB"}
TWO = ("シングル", "ハイブリッド")
FAM_ORDER = ["シングル", "ハイブリッド", "モリブデン", "電鋳", "ミラーブラック"]
ARROW = "→"
SP = "特別枠"
import os
MK_DEDUP = bool(os.environ.get("MK_DEDUP"))
NOTE = []  # 実行ログ（報告用）
EMPTY = defaultdict(int)


def rdo(f):
    return list(csv.DictReader(open(OUT / f, encoding="utf-8-sig")))


def join(a, b):
    return ARROW.join(x for x in (a, b) if x)


def seq(s):
    return tuple(s.split(ARROW)) if s else ()


def fnum_b(v):
    return float(v) if v.strip() else 0.0


def run():
    items = rdo("item_routing.csv")
    steps = rdo("item_steps.csv")
    pc = rd("process_columns.csv")
    tfront, tback = rd("template_front.csv"), rd("template_back.csv")
    tnames, titems, tgroups = rd("template_names.csv"), rd("template_items.csv"), rd("template_groups.csv")
    tmpl = {t["id"]: t for t in titems}
    tfam = {"シングル_日報": "シングル", "ハイブリッド_日報": "ハイブリッド"}
    F = {r["front_g"]: r for r in tfront}
    B = {r["back_g"]: r for r in tback}
    tg_set = {r["group_routing"] for r in tgroups}
    name_of = defaultdict(list)  # src_key -> 名前（②③に出る名前）
    for r in tnames:
        name_of[r["src_key"]].append(r["name"])
    total_budget = sum(fnum_b(i["budget"]) for i in items)

    # 品番ごとの照合キー（E3）。item_steps の「使う」セル（不使用でない・route_sheet のシート）を並び順のまま、重複を除かずに
    st_by = defaultdict(list)
    for s in steps:
        st_by[s["id"]].append(s)
    n_unnamed_cols = defaultdict(int)
    num_note = {}
    for p_ in pc:
        if not codes_in(p_["nippo_code_note"]):
            parts = [re.sub(r"\s", "", x) for x in p_["nippo_name_note"].split("／")]
            dg = [str(int(unicodedata.normalize("NFKC", x))) for x in parts if x and re.fullmatch(r"[0-9０-９]+", x)]
            if dg:
                num_note[p_["src_key"]] = dg

    def match_key(it):
        out = []
        for s in st_by.get(it["id"], []):
            if s["cell_kind"] == "不使用" or s["sheet"] != it["route_sheet"]:
                continue
            t = s["token"]
            if CODE.fullmatch(t):
                out.append(str(int(t[-2:])))
            else:
                dg = num_note.get(s["src_key"])
                nm = name_of.get(s["src_key"], [])
                if dg:  # 規則 E3-3（案B）: コード無しの列の注記にある数字だけの部分を、書かれた順に
                    out.extend(dg)
                elif nm:
                    out.extend(nm)
                else:
                    n_unnamed_cols[s["src_key"]] += 1
        if MK_DEDUP:  # 案B（試作）: 連続する同じ番号を 1 つにまとめる
            out = [x for i, x in enumerate(out) if i == 0 or x != out[i - 1]]
        return tuple(out)

    # 空欄のキーに使う「通常」の定義
    def normals(fam, kind):
        rows = [r for r in (tfront if kind == "F" else tback) if r["family"] == fam and r["section"] == "通常"]
        k = "front_key" if kind == "F" else "back_key"
        g = "front_g" if kind == "F" else "back_g"
        return [(r[g], seq(r[k])) for r in rows]

    NF = {fam: normals(fam, "F") for fam in TWO}
    NB = {fam: normals(fam, "B") for fam in TWO}
    max_no = {}
    for fam in TWO:
        for kind, tb, g in (("F", tfront, "front_g"), ("B", tback, "back_g")):
            max_no[(fam, kind)] = max(int(r[g][2:]) for r in tb if r["family"] == fam)

    def empty_g(fam, kind):  # 「通常」の空キーの定義の G。無ければ None（特別枠と衝突する <記号>B00 は使わず E4-4 の新番号）
        for g, k in (NF if kind == "F" else NB)[fam]:
            if not k:
                return g
        fb = SYM[fam] + kind + "00"
        return None if fb in (F if kind == "F" else B) else fb

    res = {}  # id -> dict
    newseq = defaultdict(lambda: [0.0, None])  # (fam, kind, seq) -> [budget, min id]
    n_special_conflict = 0

    def note_new(fam, kind, sq, it):
        e = newseq[(fam, kind, sq)]
        e[0] += fnum_b(it["budget"])
        e[1] = it["id"] if e[1] is None else min(e[1], it["id"])

    pending = []
    for it in items:
        fam = it["family"]
        r = {"judge": it["判定"], "why": [it["根拠"]] if it["根拠"] else [], "sec_f": "", "sec_b": ""}
        res[it["id"]] = r
        if not it["route_sheet"]:  # E6
            r["unentered"] = True
            continue
        rf = it["route_sheet"]
        r["route_family"] = rf
        mk = match_key(it)
        r["mk"] = mk
        if rf not in TWO:  # E5
            r["gf"] = it["flow_code"] or it["flow"]
            continue

        def bump(j, why):
            if RANK[j] > RANK[r["judge"]]:
                r["judge"] = j
            r["why"].append(why)

        r["bump"] = bump
        t = tmpl.get(it["id"])
        sp = None
        if t and (F[t["front_g"]]["section"] == SP or B[t["back_g"]]["section"] == SP):
            sp = t
        if sp:  # E4-1 特別枠
            fk, bk = seq(F[sp["front_g"]]["front_key"]), seq(B[sp["back_g"]]["back_key"])
            r.update(fg=sp["front_g"], bg=sp["back_g"], fs=seq(F[sp["front_g"]]["front_key"]), bs=seq(B[sp["back_g"]]["back_key"]),
                     sec_f=F[sp["front_g"]]["section"], sec_b=B[sp["back_g"]]["section"])
            if mk != fk + bk:
                bump("要確認", "更新後のフローが特別枠の定義と違う")
            continue
        # E4-2 完全一致
        pairs = [(fg, fk, bg, bk) for fg, fk in NF[rf] for bg, bk in NB[rf] if fk + bk == mk]
        if mk == () and pairs == []:
            pairs = []
        if pairs:
            if len(pairs) > 1:
                pairs.sort(key=lambda p: (0 if f"{p[0]}-{p[2]}" in tg_set else 1, -len(p[1]), p[0] + "-" + p[2]))
                bump("要確認", "完全一致の組が複数（" + "・".join(f"{p[0]}-{p[2]}" for p in pairs) + "）。" + f"{pairs[0][0]}-{pairs[0][2]} を採用")
            fg, fk, bg, bk = pairs[0]
            r.update(fg=fg, bg=bg, fs=fk, bs=bk, sec_f="通常", sec_b="通常")
            continue
        # E4-3 合わないとき
        pref = [(fg, fk) for fg, fk in NF[rf] if fk and mk[:len(fk)] == fk]
        if pref:  # a
            fg, fk = max(pref, key=lambda p: len(p[1]))
            rest = mk[len(fk):]
            r.update(fg=fg, fs=fk, sec_f="通常")
            hit = [g for g, k in NB[rf] if k == rest and rest]
            if hit:
                r.update(bg=hit[0], bs=rest, sec_b="通常")
            else:
                r.update(bs=rest)
                pending.append((it, "B", rest))
            continue
        suf = [(bg, bk) for bg, bk in NB[rf] if bk and mk[len(mk) - len(bk):] == bk]
        if suf:  # b
            bg, bk = max(suf, key=lambda p: len(p[1]))
            fs = mk[:len(mk) - len(bk)]
            r.update(bg=bg, bs=bk, sec_b="通常", fs=fs)
            pending.append((it, "F", fs))
            continue
        last = {k[-1] for _, k in NF[rf] if k}  # c
        pos = next((i for i, x in enumerate(mk) if x in last), None)
        bump("要確認", "照合キーが「通常」の定義のどれとも合わない（前工程・後工程とも新規）")
        if pos is None:
            fs, bs = mk, ()
        else:
            fs, bs = mk[:pos + 1], mk[pos + 1:]
        r.update(fs=fs, bs=bs)
        pending.append((it, "F", fs))
        pending.append((it, "B", bs))

    # 空の並びは E4-5、新しい並びは E4-4
    byid = {i["id"]: i for i in items}
    for it, kind, sq in pending:
        r = res[it["id"]]
        rf = r["route_family"]
        g = empty_g(rf, kind) if not sq else None
        if not sq and g is None:
            note_new(rf, kind, sq, it)
        elif not sq:
            r["fg" if kind == "F" else "bg"] = g
            tb = F if kind == "F" else B
            if g in tb and tb[g]["section"] == "通常":  # 特別枠の SB00 は他の品番に付けない（E4-1）。通常に空の定義が無ければ「新規」
                r["sec_f" if kind == "F" else "sec_b"] = "通常"
            else:
                r["sec_f" if kind == "F" else "sec_b"] = "新規"
            EMPTY[(rf, kind, g)] += 1
        else:
            note_new(rf, kind, sq, it)
    # 新しい番号（E4-4）
    newg = {}
    for fam in TWO:
        for kind in ("F", "B"):
            ks = sorted([(k, v) for k, v in newseq.items() if k[0] == fam and k[1] == kind], key=lambda kv: (-kv[1][0], kv[1][1]))
            n = max_no[(fam, kind)]
            for k, v in ks:
                n += 1
                newg[k] = f"{SYM[fam]}{kind}{n:02d}"
    for it, kind, sq in pending:
        if sq or empty_g(res[it["id"]]["route_family"], kind) is None:
            r = res[it["id"]]
            g = newg[(r["route_family"], kind, sq)]
            r["fg" if kind == "F" else "bg"] = g
            r["sec_f" if kind == "F" else "sec_b"] = "新規"
    # 1 段のグループ（E5）
    one = defaultdict(lambda: [0.0, None])
    for it in items:
        r = res[it["id"]]
        if r.get("route_family") and r["route_family"] not in TWO:
            e = one[(r["route_family"], r["gf"])]
            e[0] += fnum_b(it["budget"])
            e[1] = it["id"] if e[1] is None else min(e[1], it["id"])
    r_label = {}
    for fam in FAM_ORDER[2:]:
        ks = sorted([(k, v) for k, v in one.items() if k[0] == fam], key=lambda kv: (-kv[1][0], kv[1][1]))
        w = 3 if len(ks) > 100 else 2
        for n, (k, _) in enumerate(ks, 1):
            r_label[k] = f"{SYM[fam]}R{n:0{w}d}"

    # 前工程の特徴（E7）
    def code_name(num, fam):
        c = f"{SYM[fam]}{int(num):02d}"
        for p in pc:
            if p["sheet"] == fam and c in codes_in(p["nippo_code_note"]):
                return p["nippo_name_note"].strip() or c
        return c

    def new_feature(fs, fam):
        return ARROW.join(code_name(x, fam) if x.isdigit() else x for x in fs)

    # item_routing を埋める
    out_rows = []
    for it in items:
        r = res[it["id"]]
        fam = it["family"]
        tg = tmpl[it["id"]]["group_routing"] if it["id"] in tmpl else ""
        if r.get("unentered"):
            rf = fam
            vals = dict(route_family=rf, match_key="-", front_flow="-", back_flow="-", front_g="-", back_g="-", group_routing="未入力_" + fam,
                        group_flow="(工程未入力)", gsec_f="-", gsec_b="-", ffeat="-")
        elif r["route_family"] not in TWO:
            rf = r["route_family"]
            vals = dict(route_family=rf, match_key="-", front_flow="-", back_flow="-", front_g="-", back_g="-", group_routing=r_label[(rf, r["gf"])],
                        group_flow=r["gf"], gsec_f="-", gsec_b="-", ffeat="-")
        else:
            rf = r["route_family"]
            fs, bs = r["fs"], r["bs"]
            ff, bf = ARROW.join(fs), ARROW.join(bs)
            feat = F[r["fg"]]["front_feature"] if r["fg"] in F and r["sec_f"] != "新規" else (new_feature(fs, rf) if fs else "前工程 未入力")
            vals = dict(route_family=rf, match_key=ARROW.join(r["mk"]), front_flow=ff, back_flow=bf, front_g=r["fg"], back_g=r["bg"],
                        group_routing=f"{r['fg']}-{r['bg']}", group_flow=join(ff, bf) or "(工程未入力)", gsec_f=r["sec_f"], gsec_b=r["sec_b"], ffeat=feat)
        r["v"] = vals
        out_rows.append([it["id"], it["country"], it["product"], it["customer"], fam, it["budget"], it["route_sheet"], vals["route_family"], it["flow"],
                         it["flow_code"], vals["match_key"], vals["front_flow"], vals["back_flow"], vals["front_g"], vals["back_g"], vals["group_routing"],
                         vals["group_flow"], tg, r["judge"], "；".join(r["why"]) or "通し順どおり"])
    write_out("item_routing.csv", ["id", "country", "product", "customer", "family", "budget", "route_sheet", "route_family", "flow", "flow_code", "match_key",
                                   "front_flow", "back_flow", "front_g", "back_g", "group_routing", "group_flow", "template_group", "判定", "根拠"], out_rows)

    # groups.csv（F1〜F3）
    G = {}
    for it in items:
        v = res[it["id"]]["v"]
        g = G.setdefault(v["group_routing"], dict(family=v["route_family"], group_routing=v["group_routing"], front_g=v["front_g"], front_section=v["gsec_f"],
                                                  front_feature=v["ffeat"], back_g=v["back_g"], back_section=v["gsec_b"], front_flow=v["front_flow"],
                                                  back_flow=v["back_flow"], group_flow=v["group_flow"], items=[]))
        g["items"].append(it)
        for k in ("family", "front_g", "front_section", "back_g", "back_section", "front_flow", "back_flow", "group_flow"):
            kk = "route_family" if k == "family" else "gsec_f" if k == "front_section" else "gsec_b" if k == "back_section" else k
            if g[k] != v[kk]:
                NOTE.append(f"グループ内で値が食い違う: {g['group_routing']} {k} {g[k]!r} vs {v[kk]!r}（id {it['id']}）")

    def fam_rank(g):
        f = g["family"]
        return (FAM_ORDER.index(f), "") if f in FAM_ORDER else (len(FAM_ORDER), f)

    gl = []
    for g in G.values():
        its = g["items"]
        g["n_items"] = len(its)
        g["budget"] = sum(fnum_b(i["budget"]) for i in its)
        g["budget_share"] = g["budget"] / total_budget
        g["product_names"] = "、".join(i["product"] for i in sorted(its, key=lambda i: (-fnum_b(i["budget"]), i["id"])))
        gl.append(g)
    gl.sort(key=lambda g: (fam_rank(g), -g["budget"], g["group_routing"]))
    cols = ["family", "group_routing", "front_g", "front_section", "front_feature", "back_g", "back_section", "front_flow", "back_flow", "group_flow",
            "n_items", "budget", "budget_share", "product_names"]
    write_out("groups.csv", cols, [[g[c] for c in cols] for g in gl])

    from collections import Counter
    print("S6 groups", len(gl), "| items", len(out_rows), "| judge", dict(Counter(r[18] for r in out_rows)),
          "| unentered", sum(1 for r in res.values() if r.get("unentered")),
          "| new groups", {f"{k[0]}{k[1]}": newg[k] for k in newg} if len(newg) < 40 else len(newg),
          "| unnamed cols", dict(n_unnamed_cols))
    print("空の並びに付けた G（ファミリー・前後・G：品番数）", {f"{k[0]}{k[1]}:{k[2]}": v for k, v in EMPTY.items()})
    for n in NOTE:
        print("NOTE", n)
