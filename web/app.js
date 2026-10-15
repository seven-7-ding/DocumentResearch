'use strict';
const month = document.getElementById('month');
const query = document.getElementById('query');
const reports = document.getElementById('reports');
const status = document.getElementById('status');
let rows = [], request = 0;
async function json(path) {
  const response = await fetch(path, {cache: 'no-cache'});
  if (!response.ok) throw new Error('读取失败 (' + response.status + ')');
  return response.json();
}
function render() {
  reports.replaceChildren();
  const shown = rows.filter(row => (row.date + ' ' + row.title).toLowerCase().includes(query.value.toLowerCase()));
  document.getElementById('count').textContent = shown.length + ' 份日报';
  status.textContent = shown.length ? '' : '本月没有匹配的日报。';
  for (const row of shown) {
    const link = document.createElement('a'); link.className = 'card'; link.href = row.url;
    const date = document.createElement('span'); date.className = 'date'; date.textContent = row.date;
    const title = document.createElement('h2'); title.textContent = row.title;
    const read = document.createElement('span'); read.className = 'read'; read.textContent = '打开阅读档案 ↗';
    if (row.missing_images) read.textContent += ' · 部分历史图片已缺失';
    link.append(date, title, read); reports.append(link);
  }
}
async function load() {
  const id = ++request; rows = []; reports.replaceChildren();
  document.getElementById('count').textContent = ''; status.textContent = '正在加载…';
  try {
    const result = await json('catalog/' + month.value + '.json');
    if (id !== request) return;
    rows = result; history.replaceState(null, '', '#month=' + month.value); render();
  } catch (error) { if (id === request) status.textContent = error.message + '，请刷新重试。'; }
}
query.addEventListener('input', render); month.addEventListener('change', load);
(async () => {
  try {
    const months = await json('catalog/months.json');
    for (const value of months) { const option = document.createElement('option'); option.value = value; option.textContent = value; month.append(option); }
    const selected = new URLSearchParams(location.hash.slice(1)).get('month');
    if (months.includes(selected)) month.value = selected;
    if (months.length) await load(); else status.textContent = '尚未发布日报。';
  } catch (error) { status.textContent = error.message + '，请刷新重试。'; }
})();
