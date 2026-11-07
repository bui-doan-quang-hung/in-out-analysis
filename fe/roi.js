const select = document.querySelector('#camera-select'), img = document.querySelector('#camera-image'), stage = document.querySelector('#roi-stage'), box = document.querySelector('#roi-box'), handle = document.querySelector('#roi-handle'), message = document.querySelector('#roi-message'), status = document.querySelector('#preview-message'), save = document.querySelector('#save-roi'), reset = document.querySelector('#reset-roi');
let roi = null, saved = null, gesture = null, current = '', imageUrl = null, generation = 0, saving = false;
const drawButton = document.querySelector('#draw-roi'); let drawing = false;
const copy = value => value ? {...value} : null;
async function json(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Không thể kết nối'); return data; }
function draw() {
  box.style.display = roi ? 'block' : 'none';
  if (roi) Object.assign(box.style, {left:`${roi.x*100}%`, top:`${roi.y*100}%`, width:`${roi.width*100}%`, height:`${roi.height*100}%`});
  const changed = JSON.stringify(roi) !== JSON.stringify(saved);
  save.disabled = saving || !roi || roi.width < .01 || roi.height < .01;
  reset.disabled = saving || !changed;
}
async function refresh() {
  const id = current, token = ++generation; if (!id) return;
  status.textContent = 'Đang tải ảnh camera…';
  try {
    const response = await fetch(`/api/cameras/${id}/snapshot`, {cache:'no-store'});
    if (!response.ok) { const error = await response.json(); throw new Error(error.error); }
    const blob = await response.blob(); if (token !== generation) return;
    const next = URL.createObjectURL(blob);
    img.onload = () => { if (token !== generation) { URL.revokeObjectURL(next); return; } if (imageUrl) URL.revokeObjectURL(imageUrl); imageUrl = next; stage.style.display = 'block'; drawButton.disabled = false; status.textContent = 'Nhấn giữ chuột và kéo trên ảnh để vẽ. Với ROI đã có, kéo khung để di chuyển hoặc bấm Vẽ ROI mới.'; draw(); };
    img.onerror = () => { URL.revokeObjectURL(next); if (token === generation) { stage.style.display = 'none'; status.textContent = 'Không thể hiển thị ảnh camera.'; } };
    img.src = next;
  } catch (error) { if (token === generation) { stage.style.display = 'none'; status.textContent = error.message || 'Không tải được ảnh.'; } }
}
async function choose() {
  current = select.value; generation++; roi = saved = null; gesture = null; drawing = false; drawButton.disabled = true; drawButton.textContent = 'Vẽ ROI mới'; draw(); stage.style.display = 'none'; message.textContent = '';
  if (!current) { status.textContent = 'Chưa có camera. Hãy thêm camera trong trang Quản lý camera.'; return; }
  const id = current;
  try { const value = await json(`/api/cameras/${id}/roi`); if (id !== current) return; saved = 'x' in value ? value : null; roi = copy(saved); draw(); await refresh(); }
  catch (error) { if (id === current) status.textContent = error.message; }
}
function point(event) { const r = stage.getBoundingClientRect(); return {x:Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)), y:Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))}; }
stage.onpointerdown = event => {
  if (event.button !== 0 || saving) return;
  const start = point(event), original = copy(roi);
  gesture = {start, original, mode:drawing ? 'draw' : (event.target === handle ? 'resize' : (event.target === box && roi ? 'move' : 'draw'))};
  stage.setPointerCapture(event.pointerId); event.preventDefault();
};
stage.onpointermove = event => {
  if (!gesture) return;
  const p = point(event), {start, original, mode} = gesture;
  if (mode === 'draw') roi = {x:Math.min(start.x,p.x), y:Math.min(start.y,p.y), width:Math.abs(start.x-p.x), height:Math.abs(start.y-p.y)};
  else if (mode === 'move') roi = {...original, x:Math.max(0,Math.min(1-original.width, original.x+p.x-start.x)), y:Math.max(0,Math.min(1-original.height, original.y+p.y-start.y))};
  else roi = {...original, width:Math.max(.01, Math.min(1-original.x, original.width+p.x-start.x)), height:Math.max(.01, Math.min(1-original.y, original.height+p.y-start.y))};
  message.textContent = 'ROI chưa được lưu.'; draw();
};
stage.onpointerup = () => { if (!gesture) return; if (!roi || roi.width < .01 || roi.height < .01) { roi = gesture.original; message.textContent = 'Vùng quá nhỏ; hãy kéo để vẽ lại.'; } else if (gesture.mode === 'draw') { drawing = false; drawButton.textContent = 'Vẽ ROI mới'; } gesture = null; draw(); };
stage.onpointercancel = () => { if (gesture) roi = gesture.original; gesture = null; draw(); };
reset.onclick = () => { roi = copy(saved); drawing = false; drawButton.textContent = 'Vẽ ROI mới'; message.textContent = 'Đã hoàn tác thay đổi.'; draw(); };
drawButton.onclick = () => { drawing = true; drawButton.textContent = 'Đang vẽ ROI'; message.textContent = 'Nhấn giữ chuột và kéo trên ảnh để vẽ vùng mới.'; stage.scrollIntoView({behavior:'smooth',block:'center'}); };
save.onclick = async () => {
  const id = current, value = copy(roi); if (!id || !value || saving) return;
  saving = true; draw(); message.textContent = 'Đang lưu ROI…';
  try { await json(`/api/cameras/${id}/roi`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}); if (id === current) { saved = value; message.textContent = `Đã lưu ROI cho camera ${select.selectedOptions[0].textContent}.`; } }
  catch (error) { if (id === current) message.textContent = error.message; }
  finally { saving = false; draw(); }
};
select.onchange = choose; document.querySelector('#refresh-image').onclick = refresh;
json('/api/cameras').then(cameras => {
  select.replaceChildren();
  cameras.forEach(camera => { const option = document.createElement('option'); option.value = camera.id; option.textContent = `${camera.name} · ${camera.code}${camera.enabled ? '' : ' · Đã tắt'}`; select.append(option); });
  const requested = new URLSearchParams(location.search).get('camera'); if (cameras.some(camera => String(camera.id) === requested)) select.value = requested;
  choose();
}).catch(error => status.textContent = error.message);
