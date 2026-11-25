"""IZ-002: DB の読み取り・キャンバスの SVG・編集の操作（規則 C・D）。標準ライブラリだけ。
接続は呼び出し側が開閉する（要求ごとに開いて閉じる）。"""
import hashlib, math, re
from collections import defaultdict
from xml.sax.saxutils import escape, quoteattr

FOREIGN = "PRAGMA foreign_keys=ON"


class BadRequest(Exception):
    pass


def blob_sha1(data: bytes) -> str:
    """git の blob の SHA-1（GitHub がファイルに付ける sha と同じ）。"""
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def rows(conn, sql, *a):
    cur = conn.execute(sql, a)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------- 読み取り
def meta(conn, version):
    q = lambda s, *a: conn.execute(s, a).fetchone()[0]
    return {
        "version": version,
        "counts": {
            "groups": q("select count(*) from product_groups"),
            "products": q("select count(*) from products"),
            "products_iz001": q("select count(*) from products where origin='IZ-001'"),
            "products_web": q("select count(*) from products where origin='web'"),
            "routing_steps": q("select count(*) from routing_steps"),
            "items": q("select count(*) from items"),
            "bom_lines": q("select count(*) from bom_lines"),
        },
        "global_notes": rows(conn, "select kind, target_id, text from notes where scope='global' order by note_id"),
    }


def notes_of(conn, scope, target):
    return rows(conn, "select kind, text from notes where scope=? and target_id=? order by note_id", scope, target)


def product(conn, version, pid):
    p = rows(conn, "select product_id, product_name, family, group_id, judge, origin from products where product_id=?", pid)
    if not p:
        return None
    p = p[0]
    routing = rows(conn, "select s.seq, s.process_code, p.name, s.src_key from routing_steps s join processes p on p.process_code=s.process_code where s.product_id=? order by s.seq", pid)
    for r in routing:
        r["notes"] = notes_of(conn, "column", r["src_key"])
    bom = rows(conn, "select l.line_id, l.seq, l.item_code, i.item_type, i.name, l.qty, l.unit from bom_lines l join items i on i.item_code=l.item_code where l.product_id=? order by l.seq", pid)
    return {"version": version, "product": p, "notes": notes_of(conn, "product", pid),
            "group_notes": notes_of(conn, "group", p["group_id"]), "routing": routing, "bom": bom}


def group(conn, version, gid):
    g = rows(conn, "select group_id, family, front_g, front_section, front_feature, back_g, back_section, group_flow from product_groups where group_id=?", gid)
    if not g:
        return None
    prods = rows(conn, "select product_id, product_name, judge from products where group_id=? order by sort_key", gid)
    return {"version": version, "group": g[0], "notes": notes_of(conn, "group", gid), "products": prods}


def items(conn, version):
    return {"version": version, "items": rows(conn, "select item_code, item_type, name, origin from items order by item_type, item_code")}


# ---------------------------------------------------------------- キャンバス（規則 C）
ROW_H, HEAD_H, GAP, PAD, TOP = 20, 58, 28, 30, 30
JUDGE_FILL = {"要確認": "#fbd5d5", "類推": "#fde6c8"}


def _tw(s, size=12):
    return sum(size * (0.58 if ord(c) < 128 else 1.0) for c in s)


def canvas_svg(conn, version):
    groups = rows(conn, "select * from product_groups order by sort_key")
    prods = defaultdict(list)
    for p in rows(conn, "select product_id, product_name, judge, group_id from products order by sort_key"):
        prods[p["group_id"]].append(p)
    rn = dict(conn.execute("select product_id, count(*) from routing_steps group by product_id").fetchall())
    bn = dict(conn.execute("select product_id, count(*) from bom_lines group by product_id").fetchall())
    nc = {(a, t): n for a, t, n in conn.execute("select scope, target_id, count(*) from notes group by scope, target_id").fetchall()}
    fam_order, by_fam = [], defaultdict(list)
    for g in groups:
        if g["family"] not in by_fam:
            fam_order.append(g["family"])
        by_fam[g["family"]].append(g)
    out, x0, W, H = [], PAD, 0, 0
    for fam in fam_order:
        # 列の幅 = その列で一番長い文字に合わせる
        colw = 360.0
        for g in by_fam[fam]:
            colw = max(colw, _tw(g["group_id"], 13) + 90, _tw(f"前工程G {g['front_g']} / 後工程G {g['back_g']}", 11) + 90)
            for p in prods[g["group_id"]]:
                colw = max(colw, _tw(f"{p['product_name']} ({p['product_id']})", 12) + 190)
        out.append(f'<text x="{x0}" y="{TOP - 10}" font-size="15" font-weight="bold" fill="#121A16">{escape(fam)}</text>')
        y = TOP
        for g in by_fam[fam]:
            gid, ps = g["group_id"], prods[g["group_id"]]
            h = HEAD_H + ROW_H * len(ps) + 8
            flow = g["group_flow"]
            if len(flow) > 60:
                flow = flow[:59] + "…"
            gn = nc.get(("group", gid), 0)
            out.append(f'<g class="group" data-group-id={quoteattr(gid)}>')
            out.append(f'<rect class="block" x="{x0}" y="{y}" width="{colw:.0f}" height="{h}" rx="6" fill="#f6f8f7" stroke="#5C7066"/>')
            out.append(f'<text x="{x0 + 10}" y="{y + 18}" font-size="13" font-weight="bold" fill="#121A16">{escape(gid)}</text>')
            out.append(f'<text x="{x0 + 10}" y="{y + 34}" font-size="11" fill="#262626">前工程G {escape(g["front_g"])} / 後工程G {escape(g["back_g"])} ・ {len(ps)} 品番</text>')
            out.append(f'<text x="{x0 + 10}" y="{y + 50}" font-size="10" fill="#5C7066"><title>{escape(g["group_flow"])}</title>{escape(flow)}</text>')
            if gn:
                out.append(f'<g class="note-mark" data-n="{gn}"><rect x="{x0 + colw - 52:.0f}" y="{y + 6}" width="44" height="18" rx="9" fill="#c00000"/><text x="{x0 + colw - 30:.0f}" y="{y + 19}" font-size="11" fill="#fff" text-anchor="middle">! {gn}</text></g>')
            ty0 = y + HEAD_H - 6
            if ps:
                out.append(f'<line x1="{x0 + 16}" y1="{y + HEAD_H - 14}" x2="{x0 + 16}" y2="{ty0 + ROW_H * (len(ps) - 1) + ROW_H / 2:.0f}" stroke="#5C7066"/>')
            for i, p in enumerate(ps):
                py = ty0 + ROW_H * i
                pid = p["product_id"]
                fill = JUDGE_FILL.get(p["judge"], "none")
                out.append(f'<line x1="{x0 + 16}" y1="{py + ROW_H / 2:.0f}" x2="{x0 + 28}" y2="{py + ROW_H / 2:.0f}" stroke="#5C7066"/>')
                out.append(f'<g class="product" data-product-id={quoteattr(pid)} data-routing-n="{rn.get(pid, 0)}" data-bom-n="{bn.get(pid, 0)}" style="cursor:pointer">')
                out.append(f'<rect x="{x0 + 28}" y="{py}" width="{colw - 40:.0f}" height="{ROW_H - 2}" rx="3" fill="{fill}" stroke="none"/>')
                out.append(f'<text x="{x0 + 34}" y="{py + 14}" font-size="12" fill="#262626">{escape(p["product_name"])} ({escape(pid)})</text>')
                out.append(f'<text x="{x0 + colw - 16:.0f}" y="{py + 14}" font-size="11" fill="#5C7066" text-anchor="end">工程 {rn.get(pid, 0)}・部品 {bn.get(pid, 0)}</text>')
                pn = nc.get(("product", pid), 0)
                if pn:
                    out.append(f'<g class="note-mark" data-n="{pn}"><text x="{x0 + 18}" y="{py + 14}" font-size="10" fill="#c00000" text-anchor="end">!{pn}</text></g>')
                out.append("</g>")
            out.append("</g>")
            y += h + GAP
        H = max(H, y)
        x0 += colw + 40
        W = x0
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H + 20:.0f}" width="{W:.0f}" height="{H + 20:.0f}" '
            f'data-version="{version}" font-family="Noto Sans JP, Arial, sans-serif">')
    return head + "".join(out) + "</svg>"


# ---------------------------------------------------------------- 編集（規則 D）
def _str(v, field, lo, hi):
    if not isinstance(v, str):
        raise BadRequest(f"{field} は文字で入力してください")
    s = v.strip()
    if not (lo <= len(s) <= hi):
        raise BadRequest(f"{field} は前後の空白を除いて {lo}〜{hi} 字で入力してください")
    return s


def _qty(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise BadRequest("数量は 0 より大きい数で入力してください")
    return float(v)


def _int(v, field):
    if isinstance(v, bool) or not isinstance(v, int):
        raise BadRequest(f"{field} は整数で入力してください")
    return v


def _line_count(conn, pid):
    return conn.execute("select count(*) from bom_lines where product_id=?", (pid,)).fetchone()[0]


def _reorder(conn, pid, line_id, position):
    """その品番の BOM の行 line_id を position（1 始まり）へ移し、seq を 1 から振り直す。"""
    ids = [r[0] for r in conn.execute("select line_id from bom_lines where product_id=? order by seq", (pid,)).fetchall()]
    ids.remove(line_id)
    ids.insert(position - 1, line_id)
    conn.execute("update bom_lines set seq=-seq where product_id=?", (pid,))
    for i, lid in enumerate(ids, 1):
        conn.execute("update bom_lines set seq=? where line_id=?", (i, lid))


def _renumber(conn, pid):
    ids = [r[0] for r in conn.execute("select line_id from bom_lines where product_id=? order by seq", (pid,)).fetchall()]
    conn.execute("update bom_lines set seq=-seq where product_id=?", (pid,))
    for i, lid in enumerate(ids, 1):
        conn.execute("update bom_lines set seq=? where line_id=?", (i, lid))


def _need_item(conn, code):
    if not isinstance(code, str) or not conn.execute("select 1 from items where item_code=?", (code,)).fetchone():
        raise BadRequest("そのアイテム（部品）はありません")


OPS = ("add_item", "add_product", "add_line", "update_line", "move_line", "delete_line")


def apply_edit(conn, body):
    """検証してから変更を当てる（検証に外れたら BadRequest。変更前に投げる）。戻り値: (200 で返す辞書, 対象の id)"""
    op = body["op"]
    if op == "add_item":
        t = _str(body.get("item_type"), "種別", 1, 20)
        code = _str(body.get("code"), "コード", 1, 40)
        name = _str(body.get("name"), "名前", 1, 100)
        if conn.execute("select 1 from items where item_code=?", (code,)).fetchone():
            raise BadRequest("そのコードのアイテム（部品）は既にあります")
        conn.execute("insert into items(item_code,item_type,name,origin) values(?,?,?,'web')", (code, t, name))
        return {"item_code": code}, code
    if op == "add_product":
        name = _str(body.get("product_name"), "製品名", 1, 100)
        gid = body.get("group_id")
        g = conn.execute("select family from product_groups where group_id=?", (gid,)).fetchone() if isinstance(gid, str) else None
        if not g:
            raise BadRequest("そのグループはありません")
        if conn.execute("select 1 from products where trim(product_name)=?", (name,)).fetchone():
            raise BadRequest("同じ製品名の品番が既にあります")
        nums = [int(r[0][1:]) for r in conn.execute("select product_id from products where origin='web'").fetchall() if re.fullmatch(r"W[0-9]{4}", r[0])]
        pid = "W%04d" % (max(nums, default=0) + 1)
        sk = conn.execute("select coalesce(max(sort_key),0)+1 from products").fetchone()[0]
        conn.execute("insert into products(product_id,product_name,family,group_id,judge,template_group,sort_key,origin) values(?,?,?,?,'','',?,'web')", (pid, name, g[0], gid, sk))
        return {"product_id": pid}, pid
    if op == "add_line":
        pid = body.get("product_id")
        if not isinstance(pid, str) or not conn.execute("select 1 from products where product_id=?", (pid,)).fetchone():
            raise BadRequest("その品番はありません")
        _need_item(conn, body.get("item_code"))
        qty = _qty(body.get("qty"))
        unit = _str(body.get("unit"), "単位", 1, 20)
        n = _line_count(conn, pid)
        pos = n + 1
        if body.get("position") is not None:
            pos = _int(body["position"], "位置")
            if not (1 <= pos <= n + 1):
                raise BadRequest(f"位置は 1〜{n + 1} で入力してください")
        cur = conn.execute("insert into bom_lines(product_id,seq,item_code,qty,unit,origin) values(?,?,?,?,?,'web')", (pid, n + 1, body["item_code"], qty, unit))
        if pos != n + 1:
            _reorder(conn, pid, cur.lastrowid, pos)
        return {"line_id": cur.lastrowid}, str(cur.lastrowid)
    if op in ("update_line", "move_line", "delete_line"):
        lid = body.get("line_id")
        r = conn.execute("select product_id, item_code, qty, unit from bom_lines where line_id=?", (lid,)).fetchone() if isinstance(lid, int) and not isinstance(lid, bool) else None
        if not r:
            raise BadRequest("その BOM の行はありません")
        pid = r[0]
        if op == "update_line":
            code = body["item_code"] if "item_code" in body else r[1]
            _need_item(conn, code)
            qty = _qty(body["qty"]) if "qty" in body else r[2]
            unit = _str(body["unit"], "単位", 1, 20) if "unit" in body else r[3]
            conn.execute("update bom_lines set item_code=?, qty=?, unit=? where line_id=?", (code, qty, unit, lid))
        elif op == "move_line":
            pos = _int(body.get("position"), "移動先")
            n = _line_count(conn, pid)
            if not (1 <= pos <= n):
                raise BadRequest(f"移動先は 1〜{n} で入力してください")
            _reorder(conn, pid, lid, pos)
        else:
            conn.execute("delete from bom_lines where line_id=?", (lid,))
            _renumber(conn, pid)
        return {"line_id": lid}, str(lid)
    raise BadRequest("知らない操作です")
