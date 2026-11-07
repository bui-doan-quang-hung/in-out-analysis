const $ = id => document.getElementById(id);
const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Bangkok', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
const dateFrom = value => new Date(`${value}T00:00:00Z`);
const iso = date => date.toISOString().slice(0, 10);
const addDays = (value, n) => { const date = dateFrom(value); date.setUTCDate(date.getUTCDate() + n); return iso(date); };
const number = n => new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 1}).format(n);
let data = null, grain = 'day';

function setRange(range) {
  let start = today, end = today;
  if (range === '7' || range === '30') start = addDays(today, 1 - Number(range));
  if (range === 'month') start = today.slice(0, 8) + '01';
  if (range === 'previous') { end = addDays(today.slice(0, 8) + '01', -1); start = end.slice(0, 8) + '01'; }
  $('start').value = start; $('end').value = end;
  document.querySelectorAll('[data-range]').forEach(button => button.classList.toggle('selected', button.dataset.range === range));
}
setRange('30');
document.querySelectorAll('[data-range]').forEach(button => button.onclick = () => { setRange(button.dataset.range); load(); });
['start', 'end'].forEach(id => $(id).addEventListener('change', () => document.querySelectorAll('[data-range]').forEach(button => button.classList.remove('selected'))));
$('filters').addEventListener('submit', event => { event.preventDefault(); load(); });
document.querySelectorAll('[data-grain]').forEach(button => button.onclick = () => { grain = button.dataset.grain; document.querySelectorAll('[data-grain]').forEach(b => b.classList.toggle('selected', b === button)); if (data) renderTrend(); });

async function load() {
  $('message').textContent = 'Đang tải dữ liệu…'; $('message').classList.remove('error');
  const params = new URLSearchParams({start:$('start').value, end:$('end').value, camera:$('camera').value, direction:$('direction').value});
  try {
    const response = await fetch(`/api/statistics?${params}`); const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Không tải được thống kê');
    data = result; render(); $('message').textContent = `Từ ${result.start.split('-').reverse().join('/')} đến ${result.end.split('-').reverse().join('/')} · múi giờ Việt Nam`;
  } catch (error) { data = null; $('message').textContent = error.message; $('message').classList.add('error'); for (const id of ['summary','averages','trend','hours','weekdays','camera-rows','quality']) $(id).replaceChildren(); }
}
function node(tag, text, className) { const el = document.createElement(tag); if (text != null) el.textContent = text; if (className) el.className = className; return el; }
function render() {
  const total = data.totals.in + data.totals.out;
  $('summary').replaceChildren();
  for (const [label, value, note] of [['Lượt xe vào', data.totals.in, 'Sự kiện ghi nhận'], ['Lượt xe ra', data.totals.out, 'Sự kiện ghi nhận'], ['Tổng lượt ghi nhận', total, 'Theo bộ lọc đã chọn'], ['Biển số khác nhau', data.unique_plates, 'Trong khoảng thời gian chọn']]) {
    const card = node('div', null, 'card'); card.append(node('span', label), node('strong', number(value)), node('small', note)); $('summary').append(card);
  }
  $('averages').replaceChildren();
  for (const [label, count] of [['Mỗi ngày',data.periods.days], ['Mỗi tuần',data.periods.weeks], ['Mỗi tháng',data.periods.months]]) {
    const item = node('div', null, 'average'); item.append(node('span', label), node('strong', `${number(data.totals.in/count)} / ${number(data.totals.out/count)}`), node('small', ` lượt · ${count} kỳ`)); $('averages').append(item);
  }
  renderTrend();
  drawChart($('hours'), data.hours.map((v,i) => ({label: `${String(i).padStart(2,'0')}h`, values:[v]})), ['#4778f5']);
  drawChart($('weekdays'), data.weekdays.map((v,i) => ({label:['T2','T3','T4','T5','T6','T7','CN'][i], values:[v]})), ['#4778f5']);
  $('camera-rows').replaceChildren();
  for (const item of data.cameras) { const row = node('tr'); [item.camera_name, item.direction === 'in' ? 'Xe vào' : 'Xe ra', number(item.total)].forEach(v => row.append(node('td',v))); $('camera-rows').append(row); }
  if (!data.cameras.length) { const row = node('tr'), cell = node('td','Không có sự kiện trong khoảng đã chọn.'); cell.colSpan = 3; row.append(cell); $('camera-rows').append(row); }
  $('quality').replaceChildren();
  const pct = value => value == null ? '—' : `${number(value * 100)}%`;
  for (const [value,label] of [[pct(data.average_detection),'Độ tin cậy phát hiện trung bình'],[pct(data.average_ocr),`Độ tin cậy OCR trung bình · ${number(data.ocr_count)} lượt có dữ liệu`],[number(data.detection_low),'Lượt có độ tin cậy phát hiện dưới 50%'],[number(data.ocr_low),'Lượt có độ tin cậy OCR dưới 80%']]) { const item=node('div'); item.append(node('strong',value),node('span',label)); $('quality').append(item); }
}
function renderTrend() {
  const groups = new Map();
  for (const day of data.days) {
    let key = day.date;
    if (grain === 'week') { const d = dateFrom(day.date); key = addDays(day.date, -((d.getUTCDay()+6)%7)); }
    if (grain === 'month') key = day.date.slice(0,7);
    if (!groups.has(key)) groups.set(key, {label:key, values:[0,0]});
    const group = groups.get(key); group.values[0] += day.in; group.values[1] += day.out;
  }
  drawChart($('trend'), [...groups.values()], ['#4778f5','#20af8a']);
}
function drawChart(container, items, colors) {
  const ns = 'http://www.w3.org/2000/svg', width = Math.max(620, items.length * (colors.length === 2 ? 32 : 24)), height = 220, left = 40, bottom = 180, top = 15, plotWidth = width-left-12;
  const svg = document.createElementNS(ns,'svg'); svg.setAttribute('viewBox',`0 0 ${width} ${height}`); svg.style.minWidth = `${width}px`;
  const add = (type, attrs, text) => { const el = document.createElementNS(ns,type); for (const [k,v] of Object.entries(attrs)) el.setAttribute(k,v); if (text != null) el.textContent = text; svg.append(el); return el; };
  const max = Math.max(1,...items.flatMap(item => item.values)), step = plotWidth / Math.max(items.length,1);
  for (let i=0; i<=4; i++) { const y=bottom-(bottom-top)*i/4; add('line',{x1:left,y1:y,x2:width-12,y2:y,stroke:'#edf0f5'}); add('text',{x:left-7,y:y+4,'text-anchor':'end'},number(max*i/4)); }
  items.forEach((item,i) => {
    const groupWidth = Math.min(step*.7, 32), barWidth=groupWidth/colors.length, x=left+i*step+(step-groupWidth)/2;
    item.values.forEach((value,j) => { const barHeight=(bottom-top)*value/max; const rect=add('rect',{x:x+j*barWidth,y:bottom-barHeight,width:Math.max(1,barWidth-1),height:barHeight,fill:colors[j],rx:2}); const title=document.createElementNS(ns,'title'); title.textContent=`${item.label}: ${value}`; rect.append(title); });
    const stride = Math.max(1,Math.ceil(items.length/12));
    if (i % stride === 0 || i === items.length-1) add('text',{x:left+i*step+step/2,y:bottom+20,'text-anchor':'middle'},item.label.length===10 ? item.label.slice(5).split('-').reverse().join('/') : item.label);
  });
  container.replaceChildren(svg);
}
fetch('/api/cameras').then(r => r.json()).then(cameras => { for (const camera of cameras) { const option=node('option',`${camera.name} (${camera.code})`); option.value=camera.id; $('camera').append(option); } }).catch(() => {});
load();
