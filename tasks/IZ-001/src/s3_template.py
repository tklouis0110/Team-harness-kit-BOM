"""IZ-001 S3: お手本 FY26_GroupRouting の GroupRouting・シングル_日報・ハイブリッド_日報・日報Map を data/ の CSV に写す。原本は読むだけ。
flow_code = 日報シートの「日報工程コード→」行のうち、セルに値のある（0・「-」・空欄でない）列のコードを、数値のあるものは値の小さい順（同値は列の左から）、
数値でないもの（〇 など）はその後ろに列の左から並べてつないだもの（「未設定」の列は除く。後工程の '3'・'4/5/6' などもコードとして残す）。"""
import json, re
import openpyxl
from s1_fetch import DATA, norm, empty, write_csv

GR_RE = re.compile(r"^[A-Z]+[0-9]+-[A-Z]+[0-9]+$")
UNUSED = {"-", "－", "無", "無し", "なし", "×"}


def template_path():
    m = json.load(open(DATA / "_manifest.json", encoding="utf-8"))
    return [v["source"] for k, v in m.items() if "GroupRouting" in k][0]


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    return None


def run():
    wb = openpyxl.load_workbook(template_path(), read_only=True, data_only=True)

    # 日報シート → template_items
    items = []
    for sn in ["シングル_日報", "ハイブリッド_日報"]:
        rows = [list(r) for r in wb[sn].iter_rows(values_only=True)]
        code_row = next(r for r in rows[:8] if r and norm(r[8] if len(r) > 8 else None) == "日報工程コード→")
        codes = {c: norm(code_row[c]) for c in range(9, len(code_row)) if not empty(code_row[c]) and norm(code_row[c]) != "未設定"}
        for r in rows:
            if len(r) <= 6 or empty(r[0]) or empty(r[6]) or norm(r[0]) == "ID":
                continue
            used = []
            for c, code in codes.items():
                v = r[c] if c < len(r) else None
                if empty(v) or norm(v) in UNUSED:
                    continue
                n = num(v)
                if n is not None and n <= 0:
                    continue
                used.append((0, n, c, code) if n is not None else (1, 0, c, code))
            used.sort()
            gr = norm(r[6])
            items.append([sn, norm(r[0]), gr, norm(r[7] if len(r) > 7 else None), norm(r[8] if len(r) > 8 else None),
                          "→".join(u[3] for u in used)])
    write_csv("template_items.csv", ["sheet", "id", "group_routing", "front_g", "back_g", "flow_code"], items)

    # GroupRouting シートの ① Group Routing の表（1 行 1 グループ）
    groups = []
    for r in wb["GroupRouting"].iter_rows(values_only=True):
        if r and not empty(r[0]) and GR_RE.match(norm(r[0])):
            g = norm(r[0])
            f, b = g.split("-")
            groups.append([g, norm(r[1]), f, norm(r[2]), norm(r[3]) or b, norm(r[4]), norm(r[5]), norm(r[6]), norm(r[7]), norm(r[8])])
    write_csv("template_groups.csv", ["group_routing", "family", "front_g", "front_feature", "back_g", "n_items", "budget", "budget_share", "product_names", "flow"], groups)

    # 日報Map
    mp = []
    rows = list(wb["日報Map"].iter_rows(values_only=True))
    for r in rows[3:]:
        if r and not empty(r[0]) and not empty(r[1]):
            mp.append([norm(r[0]), norm(r[1]), norm(r[2]), norm(r[3]), norm(r[4]), norm(r[6]), norm(r[8]), norm(r[10])])
    write_csv("template_map.csv", ["family", "col_letter", "col_name", "n_items", "code1", "code2", "code3", "map_type"], mp)
    print("template_items", len(items), "template_groups", len(groups), "template_map", len(mp))
