"use strict";
// IZ-002 画面（規則 F）。素の JavaScript。API: /api/meta /api/canvas.svg /api/product /api/group /api/items /api/edit
const KIND = {
  scope: "対象範囲", template_match: "お手本との照合", new_g: "新しい G", unentered: "工程未入力",
  no_nippo_code: "日報コードなし", check_products: "要確認の品番", judge: "IZ-001 の判定",
  template_diff: "お手本と違う", map_check: "日報Map 要確認",
};
const CONFLICT_TEXT = "他の人が先に保存しました。読み込み直してからやり直してください";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = { version: null, items: [], sel: null, busy: false, groups: [], view: { x: 0, y: 0, k: 1 } };

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "読み込めませんでした（" + r.status + "）");
  return j;
}

function msg(text, cls) {
  const m = $("msg");
  m.textContent = text || "";
  m.className = cls || "";
}

function noteHtml(n, extra) {
  return `<div class="note ${extra || ""}"><b>${esc(KIND[n.kind] || n.kind)}</b> ${esc(n.text)}</div>`;
}

function setBusy(b) {
  state.busy = b;
  document.querySelectorAll("button, input, select").forEach((e) => { if (e.id !== "reload") e.disabled = b; });
}

// ---------------------------------------------------------------- 編集（操作 1 つごとにすぐ保存）
async function edit(op, fields) {
  if (state.busy) return false;
  setBusy(true);
  msg("保存しています…");
  try {
    const r = await fetch("/api/edit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ op, base_version: state.version, ...fields }) });
    const j = await r.json().catch(() => ({}));
    if (r.status === 409) {
      msg(CONFLICT_TEXT, "err");  // 自動で送り直さない。「読み込み直す」を押してもらう
      return false;
    }
    if (!r.ok || !j.ok) {
      msg(j.error || "保存できませんでした（" + r.status + "）", "err");
      return false;
    }
    state.version = j.version;
    msg("保存しました", "ok");
    await refresh(true);
    return j;
  } catch (e) {
    msg("保存できませんでした: " + e.message, "err");
    return false;
  } finally {
    setBusy(false);
  }
}

// ---------------------------------------------------------------- 読み込み
async function loadMeta() {
  const m = await getJSON("/api/meta");
  state.version = m.version;
  const c = m.counts;
  $("counts").textContent = `グループ ${c.groups}・品番 ${c.products}（IZ-001 ${c.products_iz001}・画面で追加 ${c.products_web}）・アイテム（部品）${c.items}・BOM の行 ${c.bom_lines}`;
  $("global-notes").innerHTML = m.global_notes.map((n) => noteHtml(n)).join("");
}

async function loadItems() {
  state.items = (await getJSON("/api/items")).items;
}

async function loadCanvas() {
  const r = await fetch("/api/canvas.svg", { cache: "no-store" });
  if (!r.ok) throw new Error("キャンバスを読み込めませんでした");
  $("canvas").innerHTML = await r.text();
  state.groups = [...document.querySelectorAll("#canvas g.group")].map((g) => g.dataset.groupId);
  const sel = $("group-select");
  const keep = sel.value;
  sel.innerHTML = state.groups.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join("");
  if (state.groups.includes(keep)) sel.value = keep;
}

async function refresh(keepView) {
  const v = { ...state.view };
  await Promise.all([loadMeta(), loadItems(), loadCanvas()]);
  if (keepView) { state.view = v; applyView(); } else fit();
  if (state.sel) await openPanel(state.sel.kind, state.sel.id);
}

// ---------------------------------------------------------------- キャンバス（ドラッグで動かし、ホイールで拡大・縮小）
function applyView() {
  const { x, y, k } = state.view;
  $("canvas").style.transform = `translate(${x}px, ${y}px) scale(${k})`;
}

function fit() {
  const svg = document.querySelector("#canvas svg");
  const w = $("canvas-wrap");
  if (!svg) return;
  const vb = svg.viewBox.baseVal;
  const k = Math.min(w.clientWidth / vb.width, w.clientHeight / vb.height, 1);
  state.view = { x: 8, y: 8, k: k > 0 ? k : 1 };
  applyView();
}

(function initPan() {
  const w = $("canvas-wrap");
  let drag = null;
  w.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, vx: state.view.x, vy: state.view.y, moved: false }; w.setPointerCapture(e.pointerId); });
  w.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; w.classList.add("drag"); }
    if (drag.moved) { state.view.x = drag.vx + dx; state.view.y = drag.vy + dy; applyView(); }
  });
  w.addEventListener("pointerup", (e) => {
    const d = drag;
    drag = null;
    w.classList.remove("drag");
    if (d && !d.moved) {
      const t = document.elementFromPoint(e.clientX, e.clientY);
      const p = t && t.closest && t.closest("g.product");
      const g = t && t.closest && t.closest("g.group");
      if (p) openPanel("product", p.dataset.productId);
      else if (g) openPanel("group", g.dataset.groupId);
    }
  });
  w.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = w.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const k = Math.min(4, Math.max(0.05, state.view.k * f));
    const s = k / state.view.k;
    state.view.x = px - (px - state.view.x) * s;
    state.view.y = py - (py - state.view.y) * s;
    state.view.k = k;
    applyView();
  }, { passive: false });
})();

// ---------------------------------------------------------------- パネル
async function openPanel(kind, id) {
  state.sel = { kind, id };
  try {
    if (kind === "group") {
      const j = await getJSON("/api/group?id=" + encodeURIComponent(id));
      const g = j.group;
      $("panel").innerHTML =
        `<h3>グループ ${esc(g.group_id)}</h3>` +
        j.notes.map((n) => noteHtml(n)).join("") +
        `<p>ファミリー: ${esc(g.family)}<br>前工程G: ${esc(g.front_g)}（${esc(g.front_section)}）${esc(g.front_feature)}<br>後工程G: ${esc(g.back_g)}（${esc(g.back_section)}）</p>` +
        `<div class="flow">${esc(g.group_flow)}</div>` +
        `<h4>品番（${j.products.length}）</h4><table><tr><th>品番 ID</th><th>製品名</th><th>判定</th></tr>` +
        j.products.map((p) => `<tr><td><a href="#" data-pid="${esc(p.product_id)}">${esc(p.product_id)}</a></td><td>${esc(p.product_name)}</td><td>${esc(p.judge)}</td></tr>`).join("") + "</table>";
      $("panel").querySelectorAll("a[data-pid]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); openPanel("product", a.dataset.pid); }));
    } else {
      const j = await getJSON("/api/product?id=" + encodeURIComponent(id));
      renderProduct(j);
    }
  } catch (e) {
    $("panel").innerHTML = `<p class="note">${esc(e.message)}</p>`;
  }
}

function renderProduct(j) {
  const p = j.product;
  const itemOpts = (sel) => state.items.map((i) => `<option value="${esc(i.item_code)}" ${i.item_code === sel ? "selected" : ""}>${esc(i.item_type)} / ${esc(i.item_code)} ${esc(i.name)}</option>`).join("");
  const route = j.routing.map((r) =>
    `<tr><td class="num">${r.seq}</td><td>${esc(r.name)}</td><td>${esc(r.process_code)}</td></tr>` +
    r.notes.map((n) => `<tr><td></td><td colspan="2">${noteHtml(n, "row-note")}</td></tr>`).join("")).join("");
  const bom = j.bom.map((l, i) =>
    `<tr data-line="${l.line_id}"><td class="num">${l.seq}</td><td>${esc(l.item_type)} / ${esc(l.item_code)} ${esc(l.name)}</td><td class="num">${esc(l.qty)}</td><td>${esc(l.unit)}</td>` +
    `<td><button data-act="up" ${i === 0 ? "disabled" : ""}>上へ</button> <button data-act="down" ${i === j.bom.length - 1 ? "disabled" : ""}>下へ</button> <button data-act="edit">変更</button> <button data-act="del">削除</button></td></tr>`).join("");
  $("panel").innerHTML =
    `<h3>品番 ${esc(p.product_id)}</h3><div><b>${esc(p.product_name)}</b>（${esc(p.family)} / ${esc(p.group_id)}）判定: ${esc(p.judge) || "-"}</div>` +
    j.notes.map((n) => noteHtml(n)).join("") +
    j.group_notes.map((n) => noteHtml(n)).join("") +
    `<h4>工程（Routing）— 見るだけ</h4>` +
    (j.routing.length ? `<table><tr><th>順</th><th>工程</th><th>コード</th></tr>${route}</table>` : `<p class="muted">工程はありません。</p>`) +
    `<h4>BOM（部品）</h4>` +
    (j.bom.length ? `<table id="bom"><tr><th>順</th><th>部品</th><th>数量</th><th>単位</th><th></th></tr>${bom}</table>` : `<p class="muted">部品はまだありません。</p>`) +
    `<form id="f-line" class="inline"><b>部品の行を追加</b><select name="item_code">${itemOpts("")}</select>` +
    `<input name="qty" type="number" step="any" min="0" placeholder="数量" required size="6" style="width:6em">` +
    `<input name="unit" placeholder="単位" maxlength="20" required size="6" style="width:5em">` +
    `<input name="position" type="number" min="1" placeholder="位置（空=末尾）" style="width:9em"><button type="submit">追加</button></form>` +
    (state.items.length ? "" : `<p class="muted">先に上の「新規アイテム（部品）」で部品を追加してください。</p>`);
  const pid = p.product_id;
  $("f-line").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = { product_id: pid, item_code: f.get("item_code"), qty: Number(f.get("qty")), unit: f.get("unit") };
    if (f.get("position")) body.position = Number(f.get("position"));
    await edit("add_line", body);
  });
  document.querySelectorAll("#bom button[data-act]").forEach((b) => b.addEventListener("click", () => {
    const tr = b.closest("tr");
    const line = j.bom.find((l) => String(l.line_id) === tr.dataset.line);
    const act = b.dataset.act;
    if (act === "up") edit("move_line", { line_id: line.line_id, position: line.seq - 1 });
    else if (act === "down") edit("move_line", { line_id: line.line_id, position: line.seq + 1 });
    else if (act === "del") { if (confirm("この行を消しますか？")) edit("delete_line", { line_id: line.line_id }); }
    else editRow(tr, line, itemOpts);
  }));
}

function editRow(tr, line, itemOpts) {
  tr.innerHTML = `<td class="num">${line.seq}</td><td><select>${itemOpts(line.item_code)}</select></td>` +
    `<td><input type="number" step="any" min="0" value="${esc(line.qty)}" style="width:6em"></td><td><input value="${esc(line.unit)}" maxlength="20" style="width:5em"></td>` +
    `<td><button data-act="save">保存</button> <button data-act="cancel">取消</button></td>`;
  tr.querySelector('[data-act="cancel"]').addEventListener("click", () => openPanel("product", state.sel.id));
  tr.querySelector('[data-act="save"]').addEventListener("click", () => {
    const [sel, qty, unit] = [tr.querySelector("select"), tr.querySelectorAll("input")[0], tr.querySelectorAll("input")[1]];
    edit("update_line", { line_id: line.line_id, item_code: sel.value, qty: Number(qty.value), unit: unit.value });
  });
}

// ---------------------------------------------------------------- 上の帯の操作
$("f-product").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const r = await edit("add_product", { product_name: f.get("product_name"), group_id: f.get("group_id") });
  if (r) { e.target.reset(); openPanel("product", r.product_id); }
});
$("f-item").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const r = await edit("add_item", { item_type: f.get("item_type"), code: f.get("code"), name: f.get("name") });
  if (r) e.target.reset();
});
$("reload").addEventListener("click", async () => { msg(""); try { await refresh(true); } catch (e) { msg(e.message, "err"); } });

refresh(false).catch((e) => msg(e.message, "err"));
