const state = { index: null, daily: new Map(), date: null, strategy: null, search: '', sort: null };
const labels = {
  '序號':'序號','代碼':'代碼','商品':'商品','成交':'成交','漲幅%':'漲幅%','總量':'總量',
  '歐奈爾RS評分(1-99)':'RS評分','5日籌碼集中度(%)':'主5','10日籌碼集中度(%)':'主10','20日籌碼集中度(%)':'主20',
  '5日主力集中度%':'主5','10日主力集中度%':'主10','20日主力集中度%':'主20',
  '月線斜率(%)':'月斜%','布林通道位階':'布林位階','處置股(1=是)':'處置股','20日乖離率(%)':'乖離率',
  '距最高收盤跌幅(%)':'距離高點%','產業':'產業','細產業':'細產業','所有細產業':'所有細產業','產業地位':'產業地位'
};
const baseColumns = ['序號','代碼','商品','成交','漲幅%','總量'];
const tradingViewColumn = 'TradingView';
const orderedColumnGroups = [
  ['歐奈爾RS評分(1-99)'], ['5日籌碼集中度(%)','5日主力集中度%'],
  ['10日籌碼集中度(%)','10日主力集中度%'], ['20日籌碼集中度(%)','20日主力集中度%'],
  ['月線斜率(%)','月線斜率%'], ['布林通道位階'], [tradingViewColumn], ['處置股(1=是)'],
  ['20日乖離率(%)'], ['距最高收盤跌幅(%)'], ['近5日漲幅(%)'],
  ['近10日漲幅(%)'], ['近20日漲幅(%)'],
];
const industryColumns = ['產業','細產業','所有細產業','產業地位'];
const concentration = new Set(['5日籌碼集中度(%)','10日籌碼集中度(%)','20日籌碼集中度(%)','5日主力集中度%','10日主力集中度%','20日主力集中度%']);
const hiddenColumns = new Set(['1日籌碼集中度(%)','1日主力集中度%','60日籌碼集中度(%)','60日主力集中度%']);
const integerColumns = new Set(['序號','總量','歐奈爾RS評分(1-99)','布林通道位階','處置股(1=是)', ...concentration, '60日籌碼集中度(%)','60日主力集中度%']);
const qs = selector => document.querySelector(selector);

function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char])); }
function formatUpdatedAt(value, fallbackDate) {
  const parsed = value ? new Date(value) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) {
    return `<span class="update-date">資料日期 ${escapeHtml(fallbackDate)}</span><span class="update-time">尚無更新時間</span>`;
  }
  const parts = new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(parsed).reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
  return `<span class="update-date">資料日期 ${parts.year}-${parts.month}-${parts.day}</span><span class="update-time">${parts.hour}:${parts.minute}:${parts.second}</span>`;
}
function toRows(payload) { return payload.rows.map(values => Object.fromEntries(payload.columns.map((column, index) => [column, values[index]]))); }
function number(value) { if (value === null || value === undefined || value === '') return null; const parsed = Number(value); return Number.isFinite(parsed) ? parsed : null; }
function displayValue(column, value) { const numeric = number(value); if (numeric === null) return value ?? ''; if (integerColumns.has(column)) return numeric.toFixed(0); if (column === '實際量增倍數') return numeric.toFixed(1); return numeric.toFixed(2); }
function visibleColumns(payload, rows) {
  const available = new Set([...payload.columns, tradingViewColumn]); const selected = baseColumns.filter(column => available.has(column));
  orderedColumnGroups.forEach(group => { const column = group.find(item => available.has(item) && (item === tradingViewColumn || rows.some(row => row[item] !== null && row[item] !== undefined && row[item] !== ''))); if (column) selected.push(column); });
  const aliasColumns = new Set(orderedColumnGroups.flat());
  const excluded = new Set(['資料日期','來源檔案','來源標題','來源順位','匯入時間', ...industryColumns, ...aliasColumns, ...hiddenColumns]);
  const extras = payload.columns.filter(column => !selected.includes(column) && !excluded.has(column) && rows.some(row => row[column] !== null && row[column] !== undefined && row[column] !== ''));
  return [...selected, ...extras, ...industryColumns.filter(column => available.has(column) && rows.some(row => row[column] !== null && row[column] !== undefined && row[column] !== ''))];
}
function activeDay() { return state.index.dates.find(item => item.date === state.date); }
function payloadFor(id) { return state.daily.get(id); }
function overlapCodes() { const rs = payloadFor('rs-weighted'); const main = payloadFor('main-buy-up'); if (!rs || !main) return new Set(); const rsCodes = new Set(toRows(rs).filter(row => number(row['歐奈爾RS評分(1-99)']) > 85).map(row => String(row['代碼']))); return new Set(toRows(main).map(row => String(row['代碼'])).filter(code => rsCodes.has(code))); }
function matchRow(row, query) { if (!query) return true; const term = query.toLowerCase(); return `${row['代碼'] ?? ''} ${row['商品'] ?? ''}`.toLowerCase().includes(term); }
function tradingViewMarket(row) {
  const marketDescription = `${row['市場'] ?? ''} ${row['交易所'] ?? ''} ${row['產業'] ?? ''}`;
  return /上櫃|興櫃|TPEX|OTC/i.test(marketDescription) ? 'TPEX' : 'TWSE';
}

async function loadIndex() {
  const response = await fetch('data/index.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('找不到 data/index.json，請先執行匯出程式。');
  state.index = await response.json(); state.date = state.index.latest_date; populateDates(); await loadDate();
}
function populateDates() {
  const input = qs('#date-select'); const feedback = qs('#date-feedback');
  const orderedDates = [...new Set(state.index.dates.map(item => item.date))].sort();
  const availableDates = new Set(orderedDates);
  input.min = orderedDates[0]; input.max = orderedDates.at(-1); input.value = state.date;
  input.addEventListener('change', async event => {
    const nextDate = event.target.value;
    if (!availableDates.has(nextDate)) {
      feedback.textContent = `${nextDate || '所選日期'}無資料，請選擇其他日期。`;
      feedback.classList.remove('is-hidden'); input.setAttribute('aria-invalid', 'true');
      renderUnavailableDate(nextDate);
      return;
    }
    feedback.textContent = ''; feedback.classList.add('is-hidden'); input.removeAttribute('aria-invalid');
    state.date = nextDate; state.search = ''; qs('#stock-search').value = ''; await loadDate();
  });
}
function renderUnavailableDate(date) {
  state.date = date; state.strategy = null; state.search = ''; state.daily.clear();
  qs('#stock-search').value = ''; qs('#market-mood-section').classList.remove('is-hidden');
  qs('#last-updated').innerHTML = `<span class="update-date">資料日期 ${escapeHtml(date)}</span><span class="update-time">無資料</span>`;
  qs('#market-mood').innerHTML = '<p class="empty">所選日期無市場氣氛趨勢資料。</p>';
  qs('#strategy-tabs').innerHTML = '';
  qs('#strategy-content').innerHTML = '<p class="empty">所選日期無選股清單資料。</p>';
  refreshCandidates();
}
async function loadDate() {
  const day = activeDay(); if (!day) return; state.daily.clear();
  await Promise.all(day.strategies.map(async strategy => { const response = await fetch(`data/${strategy.file}`, { cache: 'no-store' }); if (!response.ok) throw new Error(`無法讀取 ${strategy.label} 資料。`); state.daily.set(strategy.id, await response.json()); }));
  state.strategy = day.strategies.some(item => item.id === state.strategy) ? state.strategy : day.strategies[0]?.id;
  const updates = [...state.daily.values()].map(item => item.updated_at).filter(Boolean).sort();
  qs('#last-updated').innerHTML = formatUpdatedAt(updates.at(-1), day.date);
  renderMood(); renderStrategies(); refreshCandidates();
}
function renderMood() {
  const root = qs('#market-mood'); const file = state.index.market_strength_file;
  if (!file) { root.innerHTML = '<p class="empty">尚無市場氣氛歷史資料。</p>'; return; }

  fetch(`data/${file}`, { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error();
      return response.json();
    })
    .then(payload => {
      const fields = ['RS 80以上', 'RS 90以上', '主力買向上家數'];
      const allHistory = toRows(payload)
        .filter(row => (!row['策略'] || row['策略'] === 'RS加權') && row['日期'] <= state.date)
        .filter(row => fields.some(field => number(row[field]) !== null))
        .sort((left, right) => String(left['日期']).localeCompare(String(right['日期'])));
      // Ignore old placeholder rows that were created before daily statistics existed.
      const firstReported = allHistory.findIndex(row => fields.some(field => (number(row[field]) ?? 0) > 0));
      const history = firstReported >= 0 ? allHistory.slice(firstReported) : allHistory;
      const selected = history.find(row => row['日期'] === state.date) || history.at(-1);

      if (!selected) throw new Error();

      const cards = fields.map(field => `<article class="mood-card"><span>${field}</span><strong>${escapeHtml(selected[field] ?? '--')}</strong><small>${escapeHtml(selected['日期'])}</small></article>`).join('');
      const recentHistory = history.slice(-90);
      root.innerHTML = `${cards}<article class="mood-chart-card"><div class="mood-chart-title"><strong>市場氣氛走勢</strong><span>最近 ${recentHistory.length} 個交易日，截至 ${escapeHtml(selected['日期'])}</span></div>${renderMoodChart(recentHistory, fields)}${renderMoodHistoryTable(history)}</article>`;
      bindMoodTooltip(root);
    })
    .catch(() => { root.innerHTML = '<p class="empty">市場氣氛資料尚未匯出。</p>'; });
}

function renderMoodChart(history, fields) {
  const chartRows = history.filter(row => fields.some(field => number(row[field]) !== null));
  if (chartRows.length < 2) return '<p class="empty">累積至少兩個交易日後會顯示趨勢圖。</p>';

  const values = chartRows.flatMap(row => fields.map(field => number(row[field])).filter(value => value !== null));
  const low = Math.min(...values, 0); const high = Math.max(...values, 1); const range = high - low || 1;
  const width = 820; const height = 280; const padding = { top: 22, right: 24, bottom: 72, left: 34 };
  const x = index => padding.left + (index * (width - padding.left - padding.right)) / (chartRows.length - 1);
  const y = value => height - padding.bottom - ((value - low) / range) * (height - padding.top - padding.bottom);
  const colors = ['#147a98', '#9b6b08', '#d34e58'];
  const grid = [0, .5, 1].map(ratio => { const value = low + range * ratio; const lineY = y(value); return `<line x1="${padding.left}" x2="${width - padding.right}" y1="${lineY}" y2="${lineY}" class="chart-grid"/><text x="${padding.left - 7}" y="${lineY + 4}" class="chart-axis">${value.toFixed(0)}</text>`; }).join('');
  const series = fields.map((field, fieldIndex) => {
    const points = chartRows.map((row, index) => `${x(index)},${y(number(row[field]) ?? 0)}`).join(' ');
    return `<polyline points="${points}" fill="none" stroke="${colors[fieldIndex]}" class="chart-line"/>`;
  }).join('');
  const labelStep = Math.max(1, Math.ceil(chartRows.length / 6));
  const datePoints = chartRows.map((row, index) => {
    const values = fields.map(field => `${field}: ${row[field] ?? '--'}`).join('\n');
    const points = fields.map((field, fieldIndex) => {
      const value = number(row[field]);
      return value === null ? '' : `<circle cx="${x(index)}" cy="${y(value)}" r="4.5" fill="${colors[fieldIndex]}"/>`;
    }).join('');
    const hitWidth = Math.max(20, (width - padding.left - padding.right) / chartRows.length);
    const label = index % labelStep === 0 || index === chartRows.length - 1
      ? `<text x="${x(index)}" y="${height - 10}" text-anchor="end" transform="rotate(-42 ${x(index)} ${height - 10})" class="chart-axis" font-size="11">${escapeHtml(row['日期'])}</text>`
      : '';
    return `<g class="chart-hit" data-tooltip="${escapeHtml(`${row['日期']}\n${values}`)}"><rect x="${x(index) - hitWidth / 2}" y="${padding.top}" width="${hitWidth}" height="${height - padding.top - padding.bottom}" fill="transparent"></rect>${points}${label}</g>`;
  }).join('');
  const legend = fields.map((field, index) => `<span><i style="background:${colors[index]}"></i>${field}</span>`).join('');
  return `<div class="chart-legend">${legend}</div><div class="mood-chart-wrap"><svg class="mood-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="市場氣氛趨勢圖，移到日期點位可查看家數">${grid}${series}${datePoints}</svg><div class="mood-tooltip is-hidden"></div></div>`;
}

function bindMoodTooltip(root) {
  const wrap = root.querySelector('.mood-chart-wrap'); const tooltip = root.querySelector('.mood-tooltip');
  if (!wrap || !tooltip) return;
  root.querySelectorAll('.chart-hit').forEach(hit => {
    const show = event => {
      tooltip.textContent = hit.dataset.tooltip || '';
      tooltip.classList.remove('is-hidden');
      const bounds = wrap.getBoundingClientRect();
      const left = Math.min(Math.max(8, event.clientX - bounds.left + 12), bounds.width - tooltip.offsetWidth - 8);
      const top = Math.max(8, event.clientY - bounds.top - tooltip.offsetHeight - 12);
      tooltip.style.left = `${left}px`; tooltip.style.top = `${top}px`;
    };
    hit.addEventListener('mouseenter', show); hit.addEventListener('mousemove', show);
    hit.addEventListener('mouseleave', () => tooltip.classList.add('is-hidden'));
  });
}

function renderMoodHistoryTable(history) {
  const columns = ['日期', 'RS 80以上', 'RS 85以上', 'RS 90以上', 'RS 95以上', '主力買向上家數'];
  const header = columns.map(column => `<th>${escapeHtml(column)}</th>`).join('');
  const body = [...history].reverse().map(row => `<tr>${columns.map(column => `<td>${escapeHtml(row[column] ?? '--')}</td>`).join('')}</tr>`).join('');
  return `<details class="mood-details"><summary>查看每日統計</summary><div class="mood-history-shell"><table class="mood-history-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div></details>`;
}
function renderStrategies() {
  const day = activeDay(); const tabs = qs('#strategy-tabs'); tabs.innerHTML = day.strategies.map(strategy => `<button class="strategy-tab ${strategy.id === state.strategy ? 'is-active' : ''}" data-strategy="${strategy.id}">${escapeHtml(strategy.label)}</button>`).join(''); tabs.querySelectorAll('button').forEach(button => button.addEventListener('click', () => { state.strategy = button.dataset.strategy; state.sort = null; renderStrategies(); })); renderStrategyContent();
}
function sortRows(rows, strategyId) {
  const slopeColumn = ['月線斜率(%)', '月線斜率%'].find(column => rows.some(row => column in row));
  const defaultSort = strategyId === 'rs-weighted' ? ['歐奈爾RS評分(1-99)', -1] : strategyId === 'main-buy-up' && slopeColumn ? [slopeColumn, -1] : strategyId === 'deviation-rebound' ? ['20日乖離率(%)', 1] : null;
  const [column, direction] = state.sort || defaultSort || [];
  if (!column) return [...rows];
  return [...rows].sort((a,b) => { const av = number(a[column]); const bv = number(b[column]); if (av === null && bv === null) return 0; if (av === null) return 1; if (bv === null) return -1; return (av - bv) * direction; });
}
function renderStrategyContent() {
  qs('#market-mood-section').classList.toggle('is-hidden', Boolean(state.search));
  const root = qs('#strategy-content'); const payload = payloadFor(state.strategy); if (!payload) { root.innerHTML = '<p class="empty">此策略沒有資料。</p>'; return; }
  const strategy = payload.strategy; let rows = toRows(payload).filter(row => matchRow(row, state.search)); rows = sortRows(rows, strategy.id); const columns = visibleColumns(payload, rows); const overlaps = overlapCodes();
  const note = strategy.id === 'deviation-rebound' ? '<details class="strategy-note"><summary>搶反彈經驗</summary><ol><li>按照負乖離排序。</li><li>將資金分成 10 等份。</li><li>當天晚上出現小於地板或接近地板個股時，列入自選。</li><li>第二天殺低爆量時搶反彈，買黑不買紅。</li><li>第三天開高上漲無力時獲利了結。</li><li>若第三天殺低爆量，第二份資金再搶一次。</li></ol></details>' : strategy.id === 'disposition' ? '<p class="strategy-note">月線斜率大於 1、布林位階小於 4，搭配距高點回檔幅度與盤勢經驗，尋找做多機會。</p>' : '';
  const header = columns.map(column => column === tradingViewColumn ? `<th>${tradingViewColumn}</th>` : `<th><button data-sort="${escapeHtml(column)}">${escapeHtml(labels[column] || column)}${state.sort?.[0] === column ? (state.sort[1] === 1 ? ' ↑' : ' ↓') : ''}</button></th>`).join('');
  const body = rows.map(row => `<tr>${columns.map(column => { const raw = row[column]; const isOverlap = overlaps.has(String(row['代碼'])); if (column === tradingViewColumn) { const code = encodeURIComponent(String(row['代碼'] ?? '')); const market = tradingViewMarket(row); return `<td><a class="trading-view-link" target="_blank" rel="noopener" href="https://tw.tradingview.com/chart/?symbol=${market}%3A${code}" aria-label="在 TradingView 開啟 ${escapeHtml(row['代碼'])} ${escapeHtml(row['商品'])} 線圖">開啟線圖</a></td>`; } if (column === '商品') { const code = escapeHtml(row['代碼']); return `<td><a class="${isOverlap ? 'overlap' : ''}" target="_blank" rel="noopener" href="https://fubon-ebrokerdj.fbs.com.tw/z/zc/zco/zco_${code}.djhtm">${isOverlap ? '◆ ' : ''}${escapeHtml(raw)}</a></td>`; } if (column === '代碼') return `<td class="${isOverlap ? 'overlap' : ''}">${isOverlap ? '◆ ' : ''}${escapeHtml(raw)}</td>`; const numeric = number(raw); const className = (concentration.has(column) || column === '漲幅%') && numeric !== null ? (numeric > 0 ? 'positive' : numeric < 0 ? 'negative' : '') : ''; return `<td class="${className}">${escapeHtml(displayValue(column, raw))}</td>`; }).join('')}</tr>`).join('');
  root.innerHTML = `${note}<div class="section-heading list-heading"><span>${escapeHtml(strategy.label)} 選股清單</span></div><div class="table-shell selection-table"><table class="stock-table"><thead><tr>${header}</tr></thead><tbody>${body || `<tr><td colspan="${columns.length}">沒有符合搜尋條件的股票。</td></tr>`}</tbody></table></div><a class="download-link" href="data/${activeDay().strategies.find(item => item.id === strategy.id).file}" download>下載 ${escapeHtml(strategy.label)} JSON</a>${['rs-weighted','main-buy-up'].includes(strategy.id) ? renderGroups(strategy.id, strategy.label, overlaps) : ''}`;
  root.querySelectorAll('[data-sort]').forEach(button => button.addEventListener('click', () => { const column = button.dataset.sort; state.sort = state.sort?.[0] === column ? [column, state.sort[1] * -1] : [column, 1]; renderStrategyContent(); }));
}
function renderGroups(strategyId, label, overlaps) { const groups = new Map(); toRows(payloadFor(strategyId)).forEach(row => { const key = row['細產業'] || row['產業'] || '未分類'; const code = String(row['代碼']); if (!groups.has(key)) groups.set(key, new Map()); groups.get(key).set(code, row); }); const ranked = [...groups.entries()].map(([name, stocks]) => { const list = [...stocks.values()]; const rs = list.map(row => number(row['歐奈爾RS評分(1-99)'])).filter(value => value !== null); const change = list.map(row => number(row['漲幅%'])).filter(value => value !== null); return { name, list, rs90:rs.filter(value => value >= 90).length, avgRs:rs.length ? rs.reduce((a,b)=>a+b,0)/rs.length : null, avgChange:change.length ? change.reduce((a,b)=>a+b,0)/change.length : null }; }).sort((a,b) => (b.rs90-a.rs90) || ((b.avgRs ?? -Infinity)-(a.avgRs ?? -Infinity)) || ((b.avgChange ?? -Infinity)-(a.avgChange ?? -Infinity))).slice(0,15); const items = state.search ? ranked.map(item => ({ ...item, list: item.list.filter(row => matchRow(row, state.search)) })).filter(item => item.list.length) : ranked; const body = items.map(item => `<tr><td>${escapeHtml(item.name)}</td><td>${item.list.length}</td><td>${item.list.map(row => `<span class="${overlaps.has(String(row['代碼'])) ? 'overlap' : ''}">${overlaps.has(String(row['代碼'])) ? '◆ ' : ''}${escapeHtml(row['代碼'])} ${escapeHtml(row['商品'])}</span>`).join('、')}</td><td>${item.avgRs?.toFixed(1) ?? ''}</td><td>${item.rs90}</td><td>${item.avgChange?.toFixed(2) ?? ''}</td></tr>`).join(''); return `<div class="group-wrap"><div class="section-heading"><span>${escapeHtml(label)}｜${state.date} 強勢族群</span></div><div class="table-shell"><table class="group-table"><thead><tr><th>族群</th><th>股票數</th><th>股票清單</th><th>平均 RS</th><th>RS 90以上</th><th>平均漲幅%</th></tr></thead><tbody>${body || '<tr><td colspan="6">此股票不在今日強勢族群名單。</td></tr>'}</tbody></table></div></div>`; }
function refreshCandidates() { const input = qs('#stock-search'); const list = qs('#search-candidates'); const query = input.value.trim().toLowerCase(); if (!query) { list.classList.add('is-hidden'); list.innerHTML = ''; return; } const unique = new Map(); state.daily.forEach(payload => toRows(payload).forEach(row => { const code = String(row['代碼'] ?? ''); const name = String(row['商品'] ?? ''); if (`${code} ${name}`.toLowerCase().includes(query) && !unique.has(code)) unique.set(code, name); })); list.innerHTML = [...unique].map(([code,name]) => `<button type="button" class="candidate-option" data-code="${escapeHtml(code)}"><strong>${escapeHtml(code)}</strong><span>${escapeHtml(name)}</span></button>`).join(''); list.querySelectorAll('.candidate-option').forEach(button => button.addEventListener('click', () => { qs('#stock-search').value = button.dataset.code; state.search = button.dataset.code; list.classList.add('is-hidden'); renderStrategyContent(); })); list.classList.toggle('is-hidden', unique.size === 0); }
function applySearch() { state.search = qs('#stock-search').value.trim(); qs('#search-candidates').classList.add('is-hidden'); renderStrategyContent(); }
function clearSearch() { state.search = ''; qs('#stock-search').value = ''; refreshCandidates(); renderStrategyContent(); }
function configureTrailingStop() { const buy = qs('#buy-price'), high = qs('#high-price'), percent = qs('#retracement-number'), range = qs('#retracement-range'), submit = qs('#calculate-trailing'); const result = qs('#trailing-results'), message = qs('#trailing-message'); const updateStep = input => { const value = Number(input.value); input.step = value < 10 ? .01 : value < 50 ? .05 : value < 100 ? .1 : value < 500 ? .5 : value < 1000 ? 1 : 5; }; const calculate = () => { updateStep(buy); updateStep(high); const cost=Number(buy.value), top=Number(high.value), ratio=Math.max(0,Math.min(100,Number(percent.value)||0))/100; if (!cost || !top) { result.classList.add('is-hidden'); message.textContent='請先輸入買入股價與目前最高點。'; return; } if (top <= cost) { result.classList.add('is-hidden'); message.textContent='目前最高價尚未超過買入價，尚無獲利可計算停利。'; return; } const max=top-cost, giveBack=max*ratio, stop=top-giveBack; qs('#stop-price').textContent=stop.toFixed(2); qs('#max-profit').textContent=max.toFixed(2); qs('#retracement-amount').textContent=giveBack.toFixed(2); qs('#final-profit').textContent=(stop-cost).toFixed(2); message.textContent=`目前設定：最多容許回吐最高帳面獲利的 ${Math.round(ratio*100)}%。`; result.classList.remove('is-hidden'); }; percent.addEventListener('input', () => { percent.value=Math.max(0,Math.min(100,percent.value)); range.value=percent.value; }); range.addEventListener('input', () => { percent.value=range.value; }); submit.addEventListener('click', calculate); [buy,high,percent].forEach(input => input.addEventListener('keydown', event => { if (event.key === 'Enter') calculate(); })); }
function configureNavigation() { document.querySelectorAll('.nav-button').forEach(button => button.addEventListener('click', () => { const page=button.dataset.page; document.querySelectorAll('.nav-button').forEach(item => item.classList.toggle('is-active', item === button)); document.querySelectorAll('.page').forEach(item => item.classList.toggle('is-active', item.id === `${page}-page`)); })); }
async function init() { configureNavigation(); configureTrailingStop(); qs('#stock-search').addEventListener('input', refreshCandidates); qs('#stock-search').addEventListener('keydown', event => { if (event.key === 'Enter') applySearch(); }); qs('#search-apply').addEventListener('click', applySearch); qs('#search-clear').addEventListener('click', clearSearch); try { await loadIndex(); } catch (error) { qs('#load-error').textContent = `${error.message} 請用本機網站伺服器或 GitHub Pages 開啟，不要直接雙擊 index.html。`; qs('#load-error').classList.remove('is-hidden'); } }
init();
