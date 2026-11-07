const $ = id => document.getElementById(id);
let cameras = [], editing = null;
const statuses = new Map();
const checking = new Set();
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Không thể kết nối máy chủ');
  return data;
}
function reset() { editing = null; $('camera-form').reset(); $('enabled').checked = true; $('rtsp').required = true; $('form-title').textContent = 'Thêm camera'; $('message').textContent = ''; }
function render() {
  const tbody = $('camera-list'); tbody.replaceChildren();
  const query = $('search').value.trim().toLocaleLowerCase('vi');
  const list = cameras.filter(c => `${c.name} ${c.code}`.toLocaleLowerCase('vi').includes(query));
  if (!list.length) { const tr = tbody.insertRow(); const cell = tr.insertCell(); cell.colSpan = 6; cell.textContent = cameras.length ? 'Không tìm thấy camera phù hợp.' : 'Chưa có camera. Hãy thêm camera bên dưới.'; return; }
  for (const camera of list) {
    const row = tbody.insertRow();
    for (const text of [`${camera.name} (${camera.code})`, camera.rtsp, camera.direction === 'in' ? 'Xe vào' : 'Xe ra', camera.enabled ? 'Đang sử dụng' : 'Ngừng sử dụng', statuses.get(camera.id) || 'Chưa kiểm tra']) row.insertCell().textContent = text;
    const actions = row.insertCell();
    const check = document.createElement('button'); check.className = 'small-btn'; check.textContent = 'Kiểm tra'; check.disabled = !camera.enabled || checking.has(camera.id); check.onclick = async () => {
      checking.add(camera.id); statuses.set(camera.id, 'Đang kiểm tra…'); render();
      try { const result = await request(`/api/cameras/${camera.id}/check`, {method:'POST'}); statuses.set(camera.id, result.connected ? `Kết nối thành công${result.video.width ? ` · ${result.video.width} × ${result.video.height}` : ''}` : 'Không kết nối được'); }
      catch (error) { statuses.set(camera.id, error.message); } finally { checking.delete(camera.id); render(); }
    };
    const edit = document.createElement('button'); edit.className = 'small-btn'; edit.textContent = 'Sửa'; edit.onclick = () => { editing = camera.id; $('name').value = camera.name; $('code').value = camera.code; $('direction').value = camera.direction; $('enabled').checked = !!camera.enabled; $('rtsp').value = camera.rtsp; $('rtsp').required = false; $('form-title').textContent = 'Sửa camera'; $('message').textContent = ''; $('editor').scrollIntoView({behavior:'smooth'}); };
    const view = document.createElement('button'); view.className = 'small-btn'; view.textContent = 'Xem ảnh'; view.disabled = !camera.enabled; view.onclick = () => preview(camera);
    const roiLink = document.createElement('a'); roiLink.className = 'small-btn'; roiLink.href = `roi.html?camera=${camera.id}`; roiLink.textContent = 'ROI'; actions.append(check, ' ', view, ' ', edit, ' ', roiLink);
  }
}
async function load() { cameras = await request('/api/cameras'); render(); }
function preview(camera) {
  const dialog = document.createElement('dialog'), title = document.createElement('h2'), status = document.createElement('p'), img = document.createElement('img'), close = document.createElement('button');
  title.textContent = `Ảnh camera: ${camera.name}`; status.textContent = 'Đang tải ảnh camera…'; img.alt = 'Ảnh chụp từ camera'; img.style.cssText = 'display:none;max-width:100%;max-height:65vh'; close.className = 'btn'; close.textContent = 'Đóng'; close.onclick = () => dialog.close();
  dialog.append(title, status, img, close); document.body.append(dialog); dialog.addEventListener('close', () => { if (img.src.startsWith('blob:')) URL.revokeObjectURL(img.src); dialog.remove(); }); dialog.showModal();
  fetch(`/api/cameras/${camera.id}/snapshot`).then(async response => { if (!response.ok) throw new Error((await response.json()).error || 'Không tải được ảnh camera'); return response.blob(); }).then(blob => { if (!dialog.open) return; img.src = URL.createObjectURL(blob); img.style.display = 'block'; status.textContent = ''; }).catch(error => { if (dialog.open) status.textContent = error.message; });
}
$('camera-form').onsubmit = async event => {
  event.preventDefault(); const name = $('name').value.trim(), code = $('code').value.trim(), rtsp = $('rtsp').value.trim();
  if (!name || !code) { $('message').textContent = 'Vui lòng nhập tên và mã camera.'; return; }
  if (rtsp) { try { const url = new URL(rtsp); if (!['rtsp:', 'rtsps:'].includes(url.protocol) || !url.hostname) throw new Error(); } catch { $('message').textContent = 'Địa chỉ RTSP không hợp lệ.'; $('rtsp').focus(); return; } }
  const submit = $('camera-form').querySelector('[type=submit]'); submit.disabled = true; $('message').textContent = 'Đang lưu…';
  try { await request(editing ? `/api/cameras/${editing}` : '/api/cameras', {method: editing ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, code, rtsp, direction:$('direction').value, enabled:$('enabled').checked})}); if (editing) statuses.delete(editing); reset(); await load(); $('message').textContent = 'Đã lưu camera.'; }
  catch (error) { $('message').textContent = error.message; }
  finally { submit.disabled = false; }
};
$('search').oninput = render; $('cancel').onclick = reset; $('add-camera').onclick = () => { reset(); $('editor').scrollIntoView({behavior:'smooth'}); $('name').focus(); };
reset(); load().catch(error => $('message').textContent = error.message);
