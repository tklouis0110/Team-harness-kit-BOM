"""入口。引数なしで実行。data/ と IZ-001 の入力から out/ を全部作り直す（S7: 見本照合・判定・summary まで）。"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import FAMILIES, load_inputs  # noqa: E402
from nippo_map import build_map, write_map  # noqa: E402
from excel_out import build_excel  # noqa: E402
from flow import build, write_csv, DETAIL_COLS, GROUP_COLS  # noqa: E402
import verify  # noqa: E402


def main():
    d = load_inputs()
    cnt = collections.Counter(sh for _, sh in d["targets"])
    print("工順明細行数", len(d["detail"]), "/ 製品一覧", len(d["products"]))
    print("対象", len(d["targets"]), {f: cnt[f] for f in FAMILIES})
    print("対象外_工順なし", d["no_order_count"])
    print("対象外_日本以外またはファミリー違い", len(d["excluded"]))
    print("見本の品番", {k: (len(v), len(set(v))) for k, v in d["sample_ids"].items()})
    mc = collections.Counter(r[0] for r in d["sample_map"])
    print("見本の日報Map", len(d["sample_map"]), dict(mc))
    rows = build_map(d)
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out"), exist_ok=True)
    write_map(rows, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "日報Map.csv"))
    print("日報Map", len(rows), dict(collections.Counter(r["ファミリー"] for r in rows)), "前後", dict(collections.Counter(r["前後の区分"] for r in rows)))
    detail, groups = build(d, rows)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
    xlsx = os.path.join(out, "261121_GroupRouting_v1.xlsx")
    build_excel(d, rows, detail, groups, xlsx)
    print("Excel", os.path.basename(xlsx))
    vrows = verify.compare(detail, groups, rows, xlsx)
    verify.apply_judgement(detail, vrows)
    write_csv(os.path.join(out, "GroupRouting明細.csv"), DETAIL_COLS, detail)
    write_csv(os.path.join(out, "グループ一覧.csv"), GROUP_COLS, groups)
    verify.write_all(os.path.join(out, "見本照合.csv"), verify.VCOLS, vrows)
    summ = verify.make_summary(d, detail, groups, vrows)
    verify.write_all(os.path.join(out, "summary.csv"), ["項目", "値"], summ)
    print("明細", len(detail), "グループ一覧", len(groups), "見本照合", len(vrows), "summary", len(summ))
    for t in ("Group Routing", "前工程G", "後工程G"):
        print(t, {f: sum(1 for g in groups if g["表"] == t and g["ファミリー"] == f) for f in FAMILIES})
    print("判定 要確認", sum(1 for x in detail if x["判定"] == "要確認"))
    ok = (len(d["targets"]) == 468 and [cnt[f] for f in FAMILIES] == [188, 14, 11, 57, 198]
          and d["no_order_count"] == 748 and len(d["excluded"]) == 0
          and [len(d["sample_ids"][k]) for k in ("シングル", "ハイブリッド")] == [57, 198]
          and len(d["sample_map"]) == 75)
    print("見込みどおり" if ok else "見込みと違う（止まって報告）")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
