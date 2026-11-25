"""IZ-001 S1: 更新対象 Sheet1 と工程シート 5 枚を data/ の CSV に写す（規則 A・B1〜B6）。原本は読むだけ。"""
import csv, json, re
from pathlib import Path
import openpyxl

TASK = Path(__file__).resolve().parent.parent
DATA = TASK / "data"
SHEETS = ["シングル", "ハイブリッド", "モリブデン", "電鋳", "ミラーブラック"]
BASE_HEADERS = {"ID", "製造国", "製品名", "顧客名", "製品ファミリー", "予算金額"}
CODE_RE = re.compile(r"[A-Z]{1,2}[0-9]{2}")


def norm(v):
    """規則 A2: ID・値の文字の形。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    if isinstance(v, (int, float)):
        return str(v)
    return str(v).strip()


def empty(v):  # 規則 A3
    return v is None or str(v).strip() == ""


def col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def write_csv(name, header, rows):
    with open(DATA / name, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def source_path():
    m = json.load(open(DATA / "_manifest.json", encoding="utf-8"))
    return [v["source"] for k, v in m.items() if "jpn_03" in k][0]


def run():
    wb = openpyxl.load_workbook(source_path(), read_only=True, data_only=True)

    # B1: Sheet1 の全行
    ws = wb["Sheet1"]
    items = []
    for i, r in enumerate(ws.iter_rows(min_row=1, values_only=True), 1):
        if i == 1 or empty(r[0] if r else None):
            continue
        g = lambda j: r[j] if j < len(r) else None
        b = g(5)
        budget = "" if isinstance(b, bool) or not isinstance(b, (int, float)) else repr(b) if isinstance(b, float) else str(b)
        items.append([i, norm(r[0]), norm(g(1)), norm(g(2)), norm(g(3)), norm(g(4)), budget])
    write_csv("items_src.csv", ["src_row", "id", "country", "product", "customer", "family", "budget"], items)
    ids = {x[1] for x in items}

    psheets, pcols, steps = [], [], []
    for sn in SHEETS:
        rows = [list(r) for r in wb[sn].iter_rows(values_only=True)]
        hdr = next(i for i, r in enumerate(rows[:12], 1) if r and norm(r[0]) == "ID")  # B4: 見出し行
        H = rows[hdr - 1]
        items_rows = [(i, r) for i, r in enumerate(rows, 1) if i > hdr and r and not empty(r[0]) and norm(r[0]) in ids]
        ncol = max(len(r) for r in rows)
        base_end = 6
        if len(H) > 6 and norm(H[6]).endswith("全体割合"):
            base_end = 7
        cols = []
        for c in range(base_end + 1, ncol + 1):
            h = H[c - 1] if c <= len(H) else None
            has_val = any(c <= len(r) and not empty(r[c - 1]) for _, r in items_rows)
            if empty(h) and not has_val:
                continue
            code_notes, name_notes = [], []
            for rr in range(1, hdr):
                v = rows[rr - 1][c - 1] if c <= len(rows[rr - 1]) else None
                if empty(v):
                    continue
                t = norm(v)
                (code_notes if CODE_RE.fullmatch(t) else name_notes).append(t)
            cols.append(c)
            pcols.append([sn, c, col_letter(c), f"{sn}|{c}", "" if h is None else str(h), norm(h),
                          "／".join(code_notes), "／".join(name_notes)])
        for i, r in items_rows:
            for c in cols:
                if c <= len(r) and not empty(r[c - 1]):
                    steps.append([sn, i, norm(r[0]), c, f"{sn}|{c}", norm(r[c - 1])])
        psheets.append([sn, 1, hdr, hdr + 1, len(items_rows), len(cols)])

    write_csv("process_sheets.csv", ["sheet", "id_col", "header_row", "first_item_row", "n_item_rows", "n_process_cols"], psheets)
    write_csv("process_columns.csv", ["sheet", "col_no", "col_letter", "src_key", "header_raw", "col_name", "nippo_code_note", "nippo_name_note"], pcols)
    write_csv("steps_src.csv", ["sheet", "src_row", "id", "col_no", "src_key", "value"], steps)
    print("items", len(items), "process_sheets", psheets, "process_cols", len(pcols), "steps", len(steps))
