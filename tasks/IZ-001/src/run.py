"""入口。引数なしで data/raw から out/ の 4 ファイルをすべて作り直す。"""
import csv
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openpyxl
from reader import load
from detail import build_detail, judge, write_detail
from products import build_products, build_summary, write_csv, PCOLS

# 作った日（YYMMDD）。再現のため固定。直したら v を上げる。
STAMP = "261120"
VERSION = 1
INT_COLS = {"出どころ行", "工程列の並び", "順番", "ブロック番号", "記入シート数", "工程数", "要確認の件数", "値"}
# 「値」は summary のみ整数。他の表には無い列名。


def csv_to_sheet(ws, path, freeze):
    rows = list(csv.reader(open(path, encoding="utf-8-sig", newline="")))
    head = rows[0]
    ws.append(head)
    for r in rows[1:]:
        out = []
        for h, v in zip(head, r):
            out.append(int(v) if (h in INT_COLS and v != "") else v)
        ws.append(out)
    if freeze:
        ws.freeze_panes = "A2"
        for i, h in enumerate(head, 1):
            w = max([len(str(c)) for c in [h] + [r[i - 1] for r in rows[1:200]]] + [8])
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(w * 2 + 2, 60)
    else:
        ws.column_dimensions["A"].width = 44
        ws.column_dimensions["B"].width = 12


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "out")
    os.makedirs(out, exist_ok=True)
    prods, fams = load(os.path.join(here, "..", "data", "raw"))
    detail = judge(build_detail(prods, fams))
    plist = build_products(prods, detail)
    summ = build_summary(plist, detail)
    write_detail(detail, os.path.join(out, "工順明細.csv"))
    write_csv(os.path.join(out, "製品一覧.csv"), PCOLS, plist)
    write_csv(os.path.join(out, "summary.csv"), ["項目", "値"], summ)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    csv_to_sheet(wb.create_sheet("製品一覧"), os.path.join(out, "製品一覧.csv"), True)
    csv_to_sheet(wb.create_sheet("工順明細"), os.path.join(out, "工順明細.csv"), True)
    csv_to_sheet(wb.create_sheet("集計"), os.path.join(out, "summary.csv"), False)
    xl = os.path.join(out, f"{STAMP}_工順リスト_v{VERSION}.xlsx")
    wb.save(xl)
    print("取得 Sheet1", len(prods), "明細", len(detail), "製品一覧", len(plist), "->", os.path.basename(xl))


if __name__ == "__main__":
    main()
