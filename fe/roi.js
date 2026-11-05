const select = document.querySelector('#camera-select'), img = document.querySelector('#camera-image'), stage = document.querySelector('#roi-stage'), box = document.querySelector('#roi-box'), message = document.querySelector('#roi-message'), status = document.querySelector('#preview-message'), save = document.querySelector('#save-roi');
let roi = null, start = null, current = '', imageUrl = null, generation = 0;
async function json(url, options) { const r = await fetch(url, options); const data = await r.json(); if (!r.ok) throw new Error(data.error || 'Không thể kết nối'); return data; }
function draw() { if (!roi) { box.style.display='none'; return; } box.style.display='block'; Object.assign(box.style, {left:`${roi.x*100}%`, top:`${roi.y*100}%`, width:`${roi.width*100}%`, height:`${roi.height*100}%`}); }
async function refresh() {
  const id = current, token = ++generation; if (!id) return;
  status.textContent='Đang tải ảnh camera…';
  try {
    const response=await fetch(`/api/cameras/${id}/snapshot`); if (!response.ok) { const error=await response.json(); throw new Error(error.error); }
    const blob=await response.blob(); if (token !== generation) return;
    const nextUrl=URL.createObjectURL(blob); img.onload=()=>{ if(token!==generation){ URL.revokeObjectURL(nextUrl); return; } if(imageUrl) URL.revokeObjectURL(imageUrl); imageUrl=nextUrl; stage.style.display='block'; status.textContent='Ảnh chụp từ camera. Bấm “Làm mới ảnh” để cập nhật.'; draw(); }; img.src=nextUrl;
  } catch(error) { if(token===generation) { stage.style.display='none'; status.textContent=error.message || 'Không tải được ảnh.'; } }
}
async function choose() {
  current=select.value; generation++; roi=null; draw(); stage.style.display='none'; save.disabled=true; message.textContent='';
  if (!current) { status.textContent='Chưa có camera. Hãy thêm camera trong trang Quản lý camera.'; return; }
  const id=current;
  try { const value=await json(`/api/cameras/${id}/roi`); if(id!==current)return; if('x' in value) roi=value; draw(); await refresh(); }
  catch(error) { status.textContent=error.message; }
}
function point(e) { const r=stage.getBoundingClientRect(); return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)), y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}; }
stage.onpointerdown=e=>{ start=point(e); stage.setPointerCapture(e.pointerId); };
stage.onpointermove=e=>{ if(!start)return; const p=point(e); roi={x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),width:Math.abs(start.x-p.x),height:Math.abs(start.y-p.y)}; draw(); };
stage.onpointerup=()=>{ start=null; save.disabled=!roi || roi.width<0.01 || roi.height<0.01; };
stage.onpointercancel=()=>{ start=null; save.disabled=true; };
save.onclick=async()=>{ try { await json(`/api/cameras/${current}/roi`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(roi)}); message.textContent='Đã lưu ROI.'; save.disabled=true; } catch(e){ message.textContent=e.message; } };
select.onchange=choose; document.querySelector('#refresh-image').onclick=refresh;
json('/api/cameras').then(cameras=>{ select.replaceChildren(); cameras.forEach(c=>{ const option=document.createElement('option'); option.value=c.id; option.textContent=`${c.name} · ${c.code}`; select.append(option); }); const requested=new URLSearchParams(location.search).get('camera'); if(cameras.some(c=>String(c.id)===requested))select.value=requested; choose(); }).catch(e=>status.textContent=e.message);
