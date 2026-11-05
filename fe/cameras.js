const $ = id => document.getElementById(id);
let cameras = [], editing = null;
const statuses = new Map();
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
  if (!list.length) { const tr = tbody.insertRow(); const cell = tr.insertCell(); cell.colSpan = 5; cell.textContent = 'Không có camera phù hợp.'; return; }
  for (const camera of list) {
    const row = tbody.insertRow();
    for (const text of [`${camera.name} (${camera.code})`, camera.direction === 'in' ? 'Xe vào' : 'Xe ra', camera.enabled ? 'Đang sử dụng' : 'Ngừng sử dụng', statuses.get(camera.id) || 'Chưa kiểm tra']) row.insertCell().textContent = text;
    const actions = row.insertCell();
    const check = document.createElement('button'); check.className = 'small-btn'; check.textContent = 'Kiểm tra'; check.onclick = async () => {
      check.disabled = true; statuses.set(camera.id, 'Đang kiểm tra…'); render();
      try { const result = await request(`/api/cameras/${camera.id}/check`, {method:'POST'}); statuses.set(camera.id, result.connected ? `Kết nối thành công${result.video.width ? ` · ${result.video.width} × ${result.video.height}` : ''}` : 'Không kết nối được'); }
      catch (error) { statuses.set(camera.id, error.message); } render();
    };
    const edit = document.createElement('button'); edit.className = 'small-btn'; edit.textContent = 'Sửa'; edit.onclick = () => { editing = camera.id; $('name').value = camera.name; $('code').value = camera.code; $('direction').value = camera.direction; $('enabled').checked = !!camera.enabled; $('rtsp').value = ''; $('rtsp').required = false; $('form-title').textContent = 'Sửa camera'; $('message').textContent = ''; $('editor').scrollIntoView({behavior:'smooth'}); };
    const roiLink = document.createElement('a'); roiLink.className = 'small-btn'; roiLink.href = `roi.html?camera=${camera.id}`; roiLink.textContent = 'ROI'; actions.append(check, ' ', edit, ' ', roiLink);
  }
}
async function load() { cameras = await request('/api/cameras'); render(); }
$('camera-form').onsubmit = async event => {
  event.preventDefault(); $('message').textContent = 'Đang lưu…';
  try { await request(editing ? `/api/cameras/${editing}` : '/api/cameras', {method: editing ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:$('name').value, code:$('code').value, rtsp:$('rtsp').value, direction:$('direction').value, enabled:$('enabled').checked})}); reset(); await load(); $('message').textContent = 'Đã lưu camera.'; }
  catch (error) { $('message').textContent = error.message; }
};
$('search').oninput = render; $('cancel').onclick = reset; $('add-camera').onclick = () => { reset(); $('editor').scrollIntoView({behavior:'smooth'}); $('name').focus(); };
reset(); load().catch(error => $('message').textContent = error.message);
