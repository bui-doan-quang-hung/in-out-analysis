const content = document.querySelector('.content');
content.replaceChildren();
const heading = document.createElement('div'); heading.className = 'heading';
heading.innerHTML = '<div><h1>Giám sát ra vào</h1><p>Theo dõi camera tại cổng cơ quan</p></div><div class="date-chip"></div>';
const aiControls = document.createElement('div'); aiControls.className = 'ai-controls';
const aiStatus = document.createElement('span'); aiStatus.className = 'ai-status'; aiStatus.textContent = 'Đang kiểm tra AI…';
const aiButton = document.createElement('button'); aiButton.className = 'ai-button'; aiButton.disabled = true;
const restartButton = document.createElement('button'); restartButton.className = 'ai-button'; restartButton.textContent = 'Kh\u1edfi \u0111\u1ed9ng l\u1ea1i AI'; restartButton.disabled = true;
aiControls.append(aiStatus, aiButton, restartButton); heading.insertBefore(aiControls, heading.querySelector('.date-chip'));
let aiState = null;
async function refreshAI() {
  try {
    aiState = await json('/api/ai');
    aiStatus.textContent = aiState.error ? `L\u1ed7i c\u1ea5u h\u00ecnh: ${aiState.error}` : aiState.restarting ? '\u0110ang kh\u1edfi \u0111\u1ed9ng l\u1ea1i AI\u2026' : !aiState.worker_online ? 'AI chưa kết nối' : aiState.enabled ? 'AI đang bật' : 'AI đã tắt';
    aiStatus.classList.toggle('online', aiState.worker_online && aiState.enabled);
    aiButton.textContent = aiState.enabled ? 'Tắt AI' : 'Bật AI';
    aiButton.disabled = false; restartButton.disabled = !aiState.worker_online || aiState.restarting;
  } catch { aiStatus.textContent = 'Không kết nối được AI'; aiButton.disabled = true; restartButton.disabled = true; }
}
aiButton.onclick = async () => {
  if (!aiState) return;
  aiButton.disabled = true;
  try { await json('/api/ai', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:!aiState.enabled})}); await refreshAI(); }
  catch (error) { aiStatus.textContent = error.message; aiButton.disabled = false; }
};
restartButton.onclick = async () => {
  restartButton.disabled = true;
  try { await json('/api/ai/restart', {method:'POST'}); await refreshAI(); }
  catch (error) { aiStatus.textContent = error.message; restartButton.disabled = false; }
};
refreshAI(); setInterval(refreshAI, 3000);
heading.querySelector('.date-chip').textContent = new Intl.DateTimeFormat('vi-VN', {dateStyle:'full'}).format(new Date());
const stats = document.createElement('section'); stats.className = 'stats';
for (const [label, value, note] of [['Xe trong cơ quan','—','Chưa có dữ liệu nhận diện'],['Lượt vào hôm nay','—','Chưa có dữ liệu nhận diện'],['Lượt ra hôm nay','—','Chưa có dữ liệu nhận diện'],['Camera kết nối','—','Đang kiểm tra']]) {
  const card = document.createElement('div'); card.className = 'stat';
  const top = document.createElement('div'); top.className = 'stat-top'; top.textContent = label;
  const number = document.createElement('div'); number.className = 'stat-value'; number.textContent = value;
  const detail = document.createElement('div'); detail.className = 'stat-note'; detail.textContent = note;
  card.append(top, number, detail); stats.append(card);
}
const grid = document.createElement('section'); grid.className = 'camera-grid';
const events = document.createElement('section'); events.className = 'events-card';
events.innerHTML = '<div class="events-head"><div><h2>Sự kiện xe gần đây</h2><p>Biển số được phát hiện trong ROI (tối đa 100 sự kiện gần nhất)</p></div><div class="filters"><button class="filter active" data-direction="all">Tất cả</button><button class="filter" data-direction="in">Xe vào</button><button class="filter" data-direction="out">Xe ra</button></div></div><div class="table-wrap"><table><thead><tr><th>Ảnh</th><th>Biển số</th><th>Hướng</th><th>Thời gian</th><th>Camera</th><th>Độ tin cậy phát hiện</th><th>Độ tin cậy OCR</th></tr></thead><tbody></tbody></table></div>';
content.append(heading, stats, grid, events);
let eventData = [], filterDirection = 'all';
function renderEvents() {
  const tbody = events.querySelector('tbody'); tbody.replaceChildren();
  const list = eventData.filter(event => filterDirection === 'all' || event.direction === filterDirection);
  if (!list.length) { const cell = tbody.insertRow().insertCell(); cell.colSpan = 7; cell.textContent = 'Chưa có sự kiện phù hợp.'; return; }
  for (const event of list) {
    const row = tbody.insertRow(), imageCell = row.insertCell(), image = document.createElement('img');
    image.src = `/api/events/${event.id}/image?v=${event.ocr_confidence ?? 'initial'}`; image.alt = 'Ảnh biển số'; image.style.cssText = 'max-width:100px;max-height:50px'; imageCell.append(image);
    if (event.has_full_image) { const link = document.createElement('a'); link.href = `/api/events/${event.id}/full-image?v=${event.ocr_confidence ?? 'initial'}`; link.target = '_blank'; link.rel = 'noopener'; link.textContent = '\u0058em \u1ea3nh full'; link.style.cssText = 'display:block;margin-top:4px;color:#416dda'; imageCell.append(link); }
    for (const value of [event.plate, event.direction === 'in' ? 'Xe vào' : 'Xe ra', new Date(event.created_at).toLocaleString('vi-VN'), event.camera_name, `${Math.round(event.confidence*100)}%`, event.ocr_confidence == null ? '—' : `${Math.round(event.ocr_confidence*100)}%`]) row.insertCell().textContent = value;
  }
}
events.querySelectorAll('[data-direction]').forEach(button => button.onclick = () => { filterDirection = button.dataset.direction; events.querySelectorAll('[data-direction]').forEach(item => item.classList.toggle('active', item === button)); renderEvents(); });
async function refreshEvents() {
  try {
    const [items, totals] = await Promise.all([json('/api/events'), json('/api/event-stats')]); eventData = items; renderEvents();
    for (const [index, value] of [[1, totals.in], [2, totals.out]]) { stats.children[index].querySelector('.stat-value').textContent = value; stats.children[index].querySelector('.stat-note').textContent = 'Sự kiện ghi nhận hôm nay'; }
  } catch { events.querySelector('tbody').textContent = 'Không tải được sự kiện.'; }
}
refreshEvents(); setInterval(refreshEvents, 10000);
const states = new Map();
function updateCount() {
  const values = [...states.values()];
  stats.lastElementChild.querySelector('.stat-value').textContent = `${values.filter(x => x === true).length} / ${values.length}`;
  stats.lastElementChild.querySelector('.stat-note').textContent = values.includes(null) ? 'Đang kiểm tra kết nối' : 'Camera đang kết nối / đang sử dụng';
}
async function json(url, options) {
  const response = await fetch(url, options); const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Không thể kết nối'); return data;
}
function addCamera(camera) {
  states.set(camera.id, null); updateCount();
  const card = document.createElement('article'); card.className = 'camera-card';
  const head = document.createElement('div'); head.className = 'card-head';
  const title = document.createElement('div'); title.className = 'cam-title';
  const text = document.createElement('div'), name = document.createElement('strong'), info = document.createElement('small');
  name.textContent = camera.name; info.textContent = `${camera.code} · ${camera.direction === 'in' ? 'Xe vào' : 'Xe ra'}`;
  text.append(name, info); title.append(text);
  const badge = document.createElement('span'); badge.className = 'live'; badge.textContent = 'ĐANG KẾT NỐI'; head.append(title, badge);
  const view = document.createElement('div'); view.style.cssText = 'background:#17212b;min-height:215px;display:flex;align-items:center;justify-content:center;overflow:hidden';
  const stage = document.createElement('div'); stage.style.cssText = 'position:relative;line-height:0;max-width:100%';
  const image = document.createElement('img'); image.alt = `Video camera ${camera.name}`; image.style.cssText = 'display:block;width:100%;height:auto;max-height:440px';
  const region = document.createElement('div'); region.style.cssText = 'position:absolute;display:none;border:2px dashed #60dfb0;pointer-events:none';
  stage.append(image, region); view.append(stage);
  const footer = document.createElement('div'); footer.className = 'cam-footer';
  const status = document.createElement('span'); status.textContent = 'Đang kiểm tra kết nối…';
  const controls = document.createElement('div'); controls.className = 'cam-controls';
  const full = document.createElement('button'); full.className = 'small-btn'; full.textContent = 'Toàn màn hình'; full.onclick = () => { if (stage.requestFullscreen) stage.requestFullscreen(); };
  const config = document.createElement('a'); config.className = 'small-btn'; config.href = `roi.html?camera=${camera.id}`; config.textContent = 'Cấu hình ROI';
  controls.append(full, config); footer.append(status, controls);
  card.append(head, view, footer); grid.append(card);
  json(`/api/cameras/${camera.id}/roi`).then(roi => { if ('x' in roi) { Object.assign(region.style, {display:'block',left:`${roi.x*100}%`,top:`${roi.y*100}%`,width:`${roi.width*100}%`,height:`${roi.height*100}%`}); } }).catch(() => {});
  let online = null, active = false, annotated = false, objectUrl = null;
  async function refreshAnnotated() {
    try {
      const response = await fetch(`/api/cameras/${camera.id}/annotated`, {cache:'no-store'});
      if (!response.ok) throw new Error('No frame');
      const blob = await response.blob(), next = URL.createObjectURL(blob);
      image.src = next; if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = next; annotated = true; active = true;
    } catch {
      if (annotated) { annotated = false; active = false; }
      if (online && !active) { active = true; image.src = `/api/cameras/${camera.id}/stream?t=${Date.now()}`; }
    }
  }
  async function pollAnnotated() { await refreshAnnotated(); setTimeout(pollAnnotated, 100); }
  pollAnnotated();
  async function check() {
    try {
      const result = await json(`/api/cameras/${camera.id}/check`, {method:'POST'}); online = result.connected;
    } catch { online = false; }
    states.set(camera.id, online); updateCount();
    badge.textContent = online ? 'TRỰC TIẾP' : 'MẤT KẾT NỐI'; status.textContent = online ? 'Camera đã kết nối' : 'Không kết nối được camera';
    if (online && !active) { active = true; image.src = `/api/cameras/${camera.id}/stream?t=${Date.now()}`; }
    if (!online && active) { active = false; image.removeAttribute('src'); }
  }
  image.onerror = () => { active = false; states.set(camera.id, false); updateCount(); badge.textContent = 'MẤT KẾT NỐI'; status.textContent = 'Không tải được video; đang thử kết nối lại.'; };
  check(); setInterval(check, 30000);
}
json('/api/cameras').then(cameras => {
  const enabled = cameras.filter(c => c.enabled);
  if (!enabled.length) { const empty = document.createElement('p'); empty.textContent = 'Chưa có camera đang sử dụng. Hãy thêm hoặc bật camera trong trang Quản lý camera.'; grid.append(empty); updateCount(); }
  enabled.forEach(addCamera);
}).catch(error => { grid.textContent = `Không tải được danh sách camera: ${error.message}`; stats.lastElementChild.querySelector('.stat-note').textContent = 'Không thể kiểm tra'; });
