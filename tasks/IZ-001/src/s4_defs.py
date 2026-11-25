"""IZ-001 S4: お手本 GroupRouting シートの ② 前工程グループ（行 69〜）・③ 後工程グループ（行 100〜）の定義表を data/ に取り込み、
名前（寸検 など）と工程列の対応 template_names.csv を作る（規則 E2）。S3 の成果物は変えない。原本は読むだけ。"""
import csv, re
import openpyxl
from s1_fetch import DATA, norm, empty, write_csv
from s3_template import template_path

G_RE = re.compile(r"^[A-Z]{2}[0-9]{2}$")
CODE = re.compile(r"[A-Za-z]{0,2}([0-9]+)")
ws_ = lambda s: re.sub(r"\s", "", s)


DASH = set("―—–‒-－ー─−")


def elems(raw, family="シングル"):
    """要素の列（E2-2）: 空白を除く→横線だけは除外→外注(シングル)は 1→「/」は全部コードのときだけ分ける。"""
    out = []
    for x in raw.split("→"):
        x = ws_(x)
        if not x or (len(x) == 1 and x in DASH):
            continue
        if family == "シングル" and x == "外注":
            out.append("1")
            continue
        parts = x.split("/")
        if len(parts) > 1 and all(CODE.fullmatch(q) for q in parts):
            out.extend(parts)
        else:
            out.append(x)
    return out


def key(raw, family="シングル"):
    return "→".join(str(int(CODE.fullmatch(q).group(1))) if CODE.fullmatch(q) else q for q in elems(raw, family))


def rd(f):
    return list(csv.DictReader(open(DATA / f, encoding="utf-8-sig")))


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else norm(v)


def run():
    wb = openpyxl.load_workbook(template_path(), read_only=True, data_only=True)
    rows = list(wb["GroupRouting"].iter_rows(values_only=True))
    front, back = [], []
    part = fam = sec = None
    for i, r in enumerate(rows, 1):
        if i < 69:
            continue
        a = norm(r[0]) if r and len(r) > 0 else ""
        if a.startswith("②"):
            part = "front"
        elif a.startswith("③"):
            part = "back"
        elif a.startswith("前提・確認事項"):
            break
        elif "：通常" in a or "：特別枠" in a:
            fam, sec = a.split("：")[0], ("通常" if "通常" in a else "特別枠")
        elif part and G_RE.match(a):
            c = lambda k: norm(r[k]) if len(r) > k else ""
            if part == "front":
                front.append([sec, c(1), a, c(2), c(4), c(5), c(6), c(8), key(c(8), c(1))])
            else:
                back.append([sec, c(1), a, c(4), c(5), c(6), c(8), key(c(8), c(1))])
    write_csv("template_front.csv", ["section", "family", "front_g", "front_feature", "n_items", "budget", "budget_share", "flow_raw", "front_key"], front)
    write_csv("template_back.csv", ["section", "family", "back_g", "n_items", "budget", "budget_share", "flow_raw", "back_key"], back)

    # 名前 → 工程列
    pc = rd("process_columns.csv")
    tmap = rd("template_map.csv")
    names = {}
    for fr in front:
        for q in elems(fr[7], fr[1]):
            if not CODE.fullmatch(q):
                names.setdefault((fr[1], ws_(q)), q)
    for b in back:
        for q in elems(b[6], b[1]):
            if not CODE.fullmatch(q):
                names.setdefault((b[1], ws_(q)), q)
    out, missing = [], []
    for (fam, nm) in sorted(names):
        hit = [p for p in pc if p["sheet"] == fam and ws_(p["col_name"]) == nm]
        how = "見出し一致"
        if not hit:
            letters = {t["col_letter"] for t in tmap if t["family"] == fam and ws_(t["col_name"]) == nm}
            hit = [p for p in pc if p["sheet"] == fam and p["col_letter"] in letters]
            how = "日報Map経由"
        if not hit:
            missing.append((fam, nm))
        for p in hit:
            out.append([fam, nm, p["src_key"], how])
    write_csv("template_names.csv", ["family", "name", "src_key", "how"], out)
    print("template_front", len(front), "template_back", len(back), "template_names", len(out), "names", len(names), "unmatched", missing)
