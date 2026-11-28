"use strict"
// IZ-002 画面。bom-standalone（v0 製）を元に、実 API（/api/tree・/api/product・/api/items・/api/edit）につないだもの。
// 保存は操作 1 つごとにすぐ /api/edit へ。base_version を付け、409 は自動で送り直さない。
const state = { mode: 'product', group: null, data: null, version: null, selected: null, detail: null, tab: 'bom', zoom: 1, offset: { x: 0, y: 0 }, collapsed: new Set(), editing: null, busy: false }
const $ = (selector, root = document) => root.querySelector(selector)
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)]
const labels = { scope: '対象範囲', template_match: 'お手本との照合', new_g: '新しい G', unentered: '工程未入力', no_nippo_code: '日報コードなし', check_products: '要確認の品番', judge: 'IZ-001 の判定', template_diff: 'お手本と違う', map_check: '日報Map 要確認' }
const CONFLICT = '他の人が先に保存しました。読み込み直してからやり直してください'
const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character])
const judgeClass = judge => judge === '要確認' ? 'red' : judge === '類推' ? 'orange' : judge === '一致' ? 'green' : 'gray'
const judgeText = judge => judge || '新規（判定なし）'
const groupOf = id => state.data.groups.find(group => group.products.some(product => product.product_id === id))

async function getJSON(url) {
  const response = await fetch(url, { cache: 'no-store' })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error || `読み込めませんでした（${response.status}）`)
  return body
}
function showToast(text, error = false) {
  const toast = $('#toast')
  toast.textContent = text
  toast.classList.toggle('error', error)
  toast.classList.add('show')
  clearTimeout(showToast.timer)
  showToast.timer = setTimeout(() => toast.classList.remove('show'), error ? 7000 : 2400)
}
function setBusy(value) { state.busy = value; document.body.classList.toggle('busy', value) }

// ---------------------------------------------------------------- 読み込み
async function loadData() {
  const [tree, items] = await Promise.all([getJSON('/api/tree'), getJSON('/api/items')])
  state.data = { ...tree, items: items.items }
  state.version = tree.version
  $('#conflict').hidden = true
  $('#conflict b').textContent = CONFLICT
  if (!state.selected || !groupOf(state.selected)) {
    const first = tree.groups.find(group => group.products.length)
    state.selected = first ? first.products[0].product_id : null
  }
  await loadDetail()
  render()
}
async function loadDetail() {
  state.detail = state.selected ? await getJSON('/api/product?id=' + encodeURIComponent(state.selected)).catch(() => null) : null
  if (state.detail) state.version = state.detail.version
}
async function selectProduct(id) {
  state.mode = 'product'
  state.selected = id
  state.detail = null
  renderCanvas()
  renderInspector()
  await loadDetail()
  renderInspector()
}

async function selectGroup(id) {
  state.mode = 'group'
  state.gtab = 'routing'
  state.group = null
  state.groupId = id
  renderCanvas()
  try { state.group = await getJSON('/api/group?id=' + encodeURIComponent(id)); state.version = state.group.version } catch (error) { showToast(error.message, true) }
  renderInspector()
}
// 画面に戻ってきたとき、版が変わっていれば知らせる（保存の衝突を減らす。自動では読み込み直さない）
async function checkStale() {
  if (!state.version || state.busy) return
  try {
    const meta = await getJSON('/api/meta')
    if (meta.version !== state.version) { $('#conflict').hidden = false; $('#conflict b').textContent = '他の人が更新しました。読み込み直してから操作してください' }
  } catch (error) { /* 次の操作のときに分かる */ }
}
window.addEventListener('focus', checkStale)

// ---------------------------------------------------------------- 保存（操作 1 つごと）
async function edit(op, fields) {
  if (state.busy) return null
  setBusy(true)
  try {
    const response = await fetch('/api/edit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op, base_version: state.version, ...fields }) })
    const body = await response.json().catch(() => ({}))
    if (response.status === 409) { $('#conflict').hidden = false; showToast(CONFLICT, true); return null }
    if (!response.ok || !body.ok) { showToast(body.error || `保存できませんでした（${response.status}）`, true); return null }
    state.version = body.version
    return body
  } catch (error) {
    showToast('保存できませんでした: ' + error.message, true)
    return null
  } finally {
    setBusy(false)
  }
}
async function afterEdit(message) {
  try { await loadData(); showToast(message) } catch (error) { showToast(error.message, true) }
}

// ---------------------------------------------------------------- 描画
function renderNotes(notes, extra = '') { return notes.map(note => `<article class="note-card ${extra}"><b>${esc(labels[note.kind] || '確認事項')}</b><p>${esc(note.text)}</p></article>`).join('') }
function renderCanvas() {
  const query = $('#search').value.trim().toLowerCase()
  const match = (group, product) => `${group.group_id} ${group.family} ${product.product_id} ${product.product_name}`.toLowerCase().includes(query)
  $('#families').innerHTML = state.data.families.map(family => {
    const groups = state.data.groups.filter(group => group.family === family)
      .map(group => ({ ...group, shown: group.products.filter(product => !query || match(group, product)) }))
      .filter(group => !query || group.shown.length || `${group.group_id} ${family}`.toLowerCase().includes(query))
    return `<section class="family-column"><header class="family-heading"><i class="family-color"></i><span class="family-name"><b>${esc(family)}</b><small>${groups.length} グループ</small></span></header><div class="group-stack">${groups.map(group => {
      const folded = state.collapsed.has(group.group_id)
      const mark = group.notes.length ? `<span class="note-mark">! ${group.notes.length}</span>` : ''
      return `<article class="group-card ${group.group_id === (state.mode === 'group' ? state.groupId : groupOf(state.selected)?.group_id) ? 'selected' : ''}"><div class="group-head"><button class="group-main" data-group="${esc(group.group_id)}"><span class="group-icon">▧</span><span class="group-name"><b>${esc(group.group_id)}</b><small>${esc(group.front_g)} → ${esc(group.back_g)}</small></span>${mark}<span class="group-count">${group.products.length}</span></button><button class="collapse" data-collapse="${esc(group.group_id)}" aria-label="グループを畳む">${folded ? '›' : '⌄'}</button></div>${folded ? '' : `<div class="flow"><small>工程の流れ</small><b title="${esc(group.group_flow)}">${esc(group.group_flow)}</b></div><div class="product-list">${group.shown.map(product => {
        const style = product.judge === '要確認' ? 'judge-check' : product.judge === '類推' ? 'judge-infer' : ''
        const notes = product.notes_n
        return `<button class="product-row ${state.selected === product.product_id ? 'active' : ''} ${style}" data-product="${esc(product.product_id)}"><span class="tree-line"></span><span class="product-node">◇</span><span class="product-title"><b>${esc(product.product_name)}</b><small>品番 ${esc(product.product_id)}</small></span><span class="judge ${judgeClass(product.judge)}">${esc(judgeText(product.judge))}</span><span class="counts">工 ${product.routing_n} · 部 ${product.bom_n}</span>${notes ? `<span class="note-mark">! ${notes}</span>` : ''}</button>`
      }).join('')}</div>`}</article>`
    }).join('')}<button class="add-product" data-add-product="${esc(groups[0]?.group_id || '')}" ${groups.length ? '' : 'disabled'}>＋ 品番を追加</button></div></section>`
  }).join('')
  $('#family-total').textContent = `${state.data.families.length} ファミリー`
}
function renderGroupPanel() {
  const g = state.group
  $('.tabs').hidden = true
  $('#product-group').textContent = g ? `${g.group.family} ・ グループ` : ''
  $('#product-name').textContent = g ? g.group.group_id : '読み込み中…'
  $('#product-id').textContent = g ? `前工程G ${g.group.front_g}（${g.group.front_section}） / 後工程G ${g.group.back_g}（${g.group.back_section}）` : ''
  $('#product-origin').textContent = ''
  const badge = $('#product-judge'); badge.textContent = g ? `${g.products.length} 品番` : ''; badge.className = 'badge gray'
  $('#note-total').textContent = g ? g.notes.length : 0
  $('#notes-list').innerHTML = !g ? '' : g.notes.length ? renderNotes(g.notes) : '<div class="no-notes">✓ 確認が必要な注記はありません</div>'
  if (!g) { $('#detail').innerHTML = ''; return }
  const tab = state.gtab || 'routing'
  const steps = g.group.group_flow.split('→').filter(Boolean)
  const body = tab === 'routing'
    ? `<div class="detail-heading"><div><b>グループの工程順（Routing）</b><small>前工程G ${esc(g.group.front_g)}：${esc(g.group.front_feature)} ／ 後工程G ${esc(g.group.back_g)}</small></div></div><div class="route-chips">${steps.map((step, i) => `<span class="chip"><i>${String(i + 1).padStart(2, '0')}</i>${esc(step)}</span>`).join('<span class="arrow">→</span>')}</div>`
    : `<div class="detail-heading"><div><b>対象品番（${g.products.length}）</b><small>このグループに入っている品番。押すと品番の詳細へ</small></div></div><div class="table"><div class="table-head" style="grid-template-columns:70px minmax(0,1fr) 64px"><span>品番 ID</span><span>製品名</span><span>判定</span></div>${g.products.map(p => `<button class="product-row" data-pid="${esc(p.product_id)}" style="min-height:30px"><span class="product-title" style="flex:0 0 70px"><small>${esc(p.product_id)}</small></span><span class="product-title"><b>${esc(p.product_name)}</b></span><span class="judge ${judgeClass(p.judge)}">${esc(judgeText(p.judge))}</span></button>`).join('')}</div>`
  $('#detail').innerHTML = `<nav class="tabs" style="padding:0 14px"><button data-gtab="routing" class="${tab === 'routing' ? 'active' : ''}">↗ Routing（工程順） <span>${steps.length}</span></button><button data-gtab="products" class="${tab === 'products' ? 'active' : ''}">◇ 対象品番 <span>${g.products.length}</span></button></nav>${body}`
}
function renderInspector() {
  if (state.mode === 'group') return renderGroupPanel()
  $('.tabs').hidden = false
  const detail = state.detail
  const product = detail?.product
  $('#product-group').textContent = product ? `${product.family} / ${product.group_id}` : ''
  $('#product-name').textContent = product ? product.product_name : (state.selected ? '読み込み中…' : '品番を選択してください')
  $('#product-id').textContent = product ? `ID: ${product.product_id}` : ''
  $('#product-origin').textContent = product ? (product.origin === 'web' ? '画面で追加' : 'IZ-001') : ''
  const badge = $('#product-judge')
  badge.textContent = product ? judgeText(product.judge) : ''
  badge.className = `badge ${product ? judgeClass(product.judge) : 'gray'}`
  const notes = detail ? [...detail.notes, ...detail.group_notes] : []
  $('#note-total').textContent = notes.length
  $('#notes-list').innerHTML = !detail ? '' : notes.length ? renderNotes(notes) : '<div class="no-notes">✓ 確認が必要な注記はありません</div>'
  $('#bom-count').textContent = detail ? detail.bom.length : 0
  $('#routing-count').textContent = detail ? detail.routing.length : 0
  $$('.tabs button').forEach(button => button.classList.toggle('active', button.dataset.tab === state.tab))
  if (!detail) { $('#detail').innerHTML = ''; return }
  if (state.tab === 'bom') {
    const bom = detail.bom
    $('#detail').innerHTML = `<div class="detail-heading"><div><b>部品構成</b><small>使用する部品と数量を管理します</small></div><button class="button green" id="add-line-top">＋ 部品を追加</button></div>${bom.length ? `<div class="table"><div class="table-head"><span>順</span><span>部品</span><span>数量</span><span></span></div>${bom.map((line, index) => `<div class="bom-row"><span class="seq">${String(index + 1).padStart(2, '0')}</span><span class="part"><b>${esc(line.name)}</b><small>${esc(line.item_code)} · ${esc(line.item_type)}</small></span><span class="quantity">${esc(line.qty)} <small>${esc(line.unit)}</small></span><span class="row-buttons"><button data-move="${line.line_id}" data-direction="-1" ${index === 0 ? 'disabled' : ''} aria-label="上へ">↑</button><button data-move="${line.line_id}" data-direction="1" ${index === bom.length - 1 ? 'disabled' : ''} aria-label="下へ">↓</button><button data-edit="${line.line_id}" aria-label="編集">✎</button><button class="delete" data-delete="${line.line_id}" aria-label="削除">−</button></span></div>`).join('')}</div><button class="add-line" id="add-line-bottom">＋ 部品の行を追加</button>` : `<div class="empty"><b>部品はまだありません</b>この品番で使う部品を追加できます。${state.data.items.length ? '' : '<br>先に右下の「＋ 新規アイテム」で部品を登録してください。'}<br><br><button id="add-line-empty">＋ 最初の部品を追加</button></div>`}`
  } else {
    $('#detail').innerHTML = `<div class="detail-heading"><div><b>工程の流れ</b><small>製品を作る順番・閲覧のみ</small></div></div>${detail.routing.length ? detail.routing.map(step => `<article class="routing-row"><span class="routing-seq">${String(step.seq).padStart(2, '0')}</span><div><b>${esc(step.name)}</b><small>${esc(step.process_code)}</small>${step.notes.map(note => `<p class="routing-note">⚠ ${esc(note.text)}</p>`).join('')}</div></article>`).join('') : '<div class="empty"><b>工程情報はありません</b></div>'}`
  }
}
function render() {
  renderCanvas()
  renderInspector()
  const counts = state.data.counts
  $('#group-total').textContent = counts.groups.toLocaleString('ja-JP')
  $('#product-total').textContent = counts.products.toLocaleString('ja-JP')
  $('#product-web').textContent = counts.products_web ? `（画面で追加 ${counts.products_web}）` : ''
  $('#item-total').textContent = counts.items.toLocaleString('ja-JP')
  $('#line-total').textContent = counts.bom_lines.toLocaleString('ja-JP')
  $('#global-notes').innerHTML = state.data.global_notes.map(note => `<p><b>${esc(labels[note.kind] || '確認事項')}</b> ${esc(note.text)}</p>`).join('')
}

// ---------------------------------------------------------------- ダイアログ（追加・変更）
function openDialog(type, options = {}) {
  if (type === 'line' && (state.mode !== 'product' || !state.detail)) return showToast('先に品番を選んでください。', true)
  if (type === 'line' && !state.data.items.length) return showToast('部品（アイテム）がまだありません。先に「＋ 新規アイテム」で登録してください。', true)
  state.editing = options.lineId || null
  const dialog = $('#editor'); const fields = $('#dialog-fields')
  $('#dialog-title').textContent = type === 'item' ? '新規アイテム（部品）' : type === 'product' ? '新規品番' : state.editing ? 'BOM の行を変更' : 'BOM に部品を追加'
  $('#dialog-subtitle').textContent = type === 'item' ? '部品の基本情報を登録します（登録した部品は消せません）' : type === 'product' ? '商品グループに品番を追加します（工程と BOM は空で作られます）' : '部品・数量・単位を指定します'
  if (type === 'item') fields.innerHTML = '<label>種別（材料・消耗品など）<input name="item_type" maxlength="20" required value="材料"></label><label>コード<input name="code" maxlength="40" required placeholder="例：MAT-001"></label><label>名前<input name="name" maxlength="100" required placeholder="部品名を入力"></label>'
  if (type === 'product') fields.innerHTML = `<label>商品グループ<select name="group_id">${state.data.groups.map(group => `<option value="${esc(group.group_id)}" ${group.group_id === options.groupId ? 'selected' : ''}>${esc(group.group_id)} · ${esc(group.family)}</option>`).join('')}</select></label><label>製品名<input name="product_name" maxlength="100" required placeholder="製品名を入力"></label>`
  if (type === 'line') {
    const existing = state.detail.bom.find(line => line.line_id === options.lineId)
    const position = existing ? '' : `<label>位置（空 = 末尾）<input name="position" type="number" min="1" step="1" max="${state.detail.bom.length + 1}" placeholder="1〜${state.detail.bom.length + 1}"></label>`
    fields.innerHTML = `<label>部品<select name="item_code" required>${state.data.items.map(item => `<option value="${esc(item.item_code)}" ${item.item_code === existing?.item_code ? 'selected' : ''}>${esc(item.item_code)} · ${esc(item.name)}（${esc(item.item_type)}）</option>`).join('')}</select></label><div class="pair"><label>数量<input name="qty" type="number" step="any" min="0.0001" required value="${existing?.qty ?? 1}"></label><label>単位<input name="unit" maxlength="20" required value="${esc(existing?.unit || '個')}"></label></div>${position}`
  }
  $('#dialog-save').dataset.type = type
  dialog.showModal()
}
$('#editor-form').addEventListener('submit', async event => {
  if (event.submitter?.value !== 'save') return
  event.preventDefault()
  const form = new FormData(event.currentTarget); const type = $('#dialog-save').dataset.type
  if (type === 'item') {
    const result = await edit('add_item', { item_type: String(form.get('item_type')), code: String(form.get('code')), name: String(form.get('name')) })
    if (!result) return
    $('#editor').close()
    await afterEdit('アイテムを追加しました。')
    if (state.detail) openDialog('line')   // 続けて BOM の行を足せる
    return
  }
  if (type === 'product') {
    const result = await edit('add_product', { product_name: String(form.get('product_name')), group_id: String(form.get('group_id')) })
    if (!result) return
    $('#editor').close()
    state.mode = 'product'
    state.selected = result.product_id
    state.tab = 'bom'
    await afterEdit('品番を追加しました。続けて部品の行を足せます。')
    if (state.data.items.length) openDialog('line')
    return
  }
  const fields = { item_code: String(form.get('item_code')), qty: Number(form.get('qty')), unit: String(form.get('unit')) }
  let result
  if (state.editing) result = await edit('update_line', { line_id: state.editing, ...fields })
  else {
    const body = { product_id: state.selected, ...fields }
    if (form.get('position')) body.position = Number(form.get('position'))
    result = await edit('add_line', body)
  }
  if (!result) return
  $('#editor').close()
  await afterEdit(state.editing ? 'BOM の行を変更しました。' : 'BOM に部品を追加しました。')
})
async function moveLine(id, direction) {
  const index = state.detail.bom.findIndex(line => line.line_id === id)
  if (index < 0 || !(await edit('move_line', { line_id: id, position: index + 1 + direction }))) return
  await afterEdit('順番を変えました。')
}
async function deleteLine(id) {
  const line = state.detail.bom.find(item => item.line_id === id)
  if (!line || !confirm(`「${line.name}」をBOMから削除しますか？`)) return
  if (await edit('delete_line', { line_id: id })) await afterEdit('BOM の行を削除しました。')
}

// ---------------------------------------------------------------- 操作（イベントは一括で受ける）
$('#families').addEventListener('click', event => {
  const product = event.target.closest('[data-product]')
  const group = event.target.closest('[data-group]')
  const fold = event.target.closest('[data-collapse]')
  const add = event.target.closest('[data-add-product]')
  if (fold) { const id = fold.dataset.collapse; state.collapsed.has(id) ? state.collapsed.delete(id) : state.collapsed.add(id); renderCanvas() }
  else if (add) openDialog('product', { groupId: add.dataset.addProduct })
  else if (product) selectProduct(product.dataset.product)
  else if (group) selectGroup(group.dataset.group)
})
$('#detail').addEventListener('click', event => {
  const button = event.target.closest('button')
  if (!button) return
  if (button.dataset.pid) selectProduct(button.dataset.pid)
  else if (button.dataset.gtab) { state.gtab = button.dataset.gtab; renderInspector() }
  else if (button.id.startsWith('add-line')) openDialog('line')
  else if (button.dataset.move) moveLine(Number(button.dataset.move), Number(button.dataset.direction))
  else if (button.dataset.edit) openDialog('line', { lineId: Number(button.dataset.edit) })
  else if (button.dataset.delete) deleteLine(Number(button.dataset.delete))
})
$$('.tabs button').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.tab; renderInspector() }))
$('#search').addEventListener('input', renderCanvas)
const reload = () => loadData().then(() => showToast('読み込み直しました。')).catch(error => showToast(error.message, true))
$('#reload').addEventListener('click', reload)
$('#reload-bottom').addEventListener('click', reload)
$('#conflict-reload').addEventListener('click', reload)
$('#toggle-all').addEventListener('click', event => { if (state.collapsed.size) state.collapsed.clear(); else state.data.groups.forEach(group => state.collapsed.add(group.group_id)); event.currentTarget.textContent = state.collapsed.size ? 'すべて展開' : 'すべて畳む'; renderCanvas() })
$('#new-item').addEventListener('click', () => openDialog('item'))
$('#new-product').addEventListener('click', () => openDialog('product', { groupId: state.mode === 'group' ? state.groupId : state.detail?.product.group_id }))

// ---------------------------------------------------------------- キャンバスの移動・拡大縮小
function setZoom(value) { state.zoom = Math.min(1.35, Math.max(.35, value)); $('#families').style.transform = `translate(${state.offset.x}px,${state.offset.y}px) scale(${state.zoom})`; $('#families').style.transformOrigin = 'top left'; $('#zoom-level').textContent = `${Math.round(state.zoom * 100)}%` }
$('#zoom-in').addEventListener('click', () => setZoom(state.zoom + .1)); $('#zoom-out').addEventListener('click', () => setZoom(state.zoom - .1)); $('#zoom-reset').addEventListener('click', () => { state.offset = { x: 0, y: 0 }; setZoom(1) })
$('#canvas-viewport').addEventListener('wheel', event => { event.preventDefault(); setZoom(state.zoom + (event.deltaY < 0 ? .05 : -.05)) }, { passive: false })
$('#canvas-viewport').addEventListener('mousedown', event => {
  if (event.target.closest('button,input')) return
  const startX = event.clientX - state.offset.x; const startY = event.clientY - state.offset.y
  const move = current => { state.offset = { x: current.clientX - startX, y: current.clientY - startY }; setZoom(state.zoom) }
  const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
  window.addEventListener('mousemove', move); window.addEventListener('mouseup', up)
})

loadData().catch(error => { console.error(error); showToast(error.message, true) })
