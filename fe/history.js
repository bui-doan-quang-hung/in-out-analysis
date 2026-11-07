const content = document.querySelector('.content');
content.innerHTML = `
  <div class="heading"><div><h1>Lịch sử ra / vào</h1><p>Tra cứu lượt lưu trú theo biển số và xuất báo cáo</p></div><button id="export" class="btn primary" type="button">⇩ &nbsp;Xuất báo cáo CSV</button></div>
  <form id="filters" class="filter-card filters"><div class="filter-grid">
    <div class="field"><label for="plate">Tìm kiếm biển số</label><input id="plate" class="input" placeholder="Nhập biển số xe..."></div>
    <div class="field"><label for="start">Từ ngày</label><input id="start" class="input" type="date" required></div>
    <div class="field"><label for="end">Đến ngày</label><input id="end" class="input" type="date" required></div>
    <div class="field"><label for="status">Trạng thái</label><select id="status" class="select"><option value="all">Tất cả trạng thái</option><option value="complete">Đã ra</option><option value="open">Chưa ghi nhận ra</option><option value="missing_in">Thiếu lượt vào</option><option value="review">Cần kiểm tra</option></select></div>
    <div class="field"><label for="camera">Camera</label><select id="camera" class="select"><option value="all">Tất cả camera</option></select></div>
    <div class="filter-actions"><button class="btn primary" type="submit">Tìm kiếm</button><button class="btn" id="reset" type="button">Đặt lại</button></div>
  </div><div class="quick-ranges"><span>Khoảng nhanh:</span><button type="button" data-range="today">Hôm nay</button><button type="button" data-range="7">7 ngày</button><button type="button" data-range="30">30 ngày</button><button type="button" data-range="month">Tháng này</button><button type="button" data-range="previous">Tháng trước</button></div>
  <details class="advanced"><summary>Tìm kiếm nâng cao</summary><div class="advanced-grid">
    <label>Kiểu tìm biển số<select id="plate_mode"><option value="partial">Chứa nội dung</option><option value="exact">Chính xác</option></select></label>
    <label>Thời điểm lọc<select id="time_field"><option value="anchor">Ngày vào; thiếu vào dùng ngày ra</option><option value="entry">Thời gian vào</option><option value="exit">Thời gian ra</option><option value="either">Vào hoặc ra</option></select></label>
    <label>Giờ từ<input id="time_start" type="time"></label><label>Giờ đến<input id="time_end" type="time"></label>
    <label>Camera vào<select id="entry_camera"><option value="all">Tất cả</option></select></label><label>Camera ra<select id="exit_camera"><option value="all">Tất cả</option></select></label>
    <label>Lưu trú từ (phút)<input id="duration_min" type="number" min="0" step="any"></label><label>Lưu trú đến (phút)<input id="duration_max" type="number" min="0" step="any"></label>
    <label>Độ tin cậy áp dụng<select id="confidence_side"><option value="either">Một sự kiện vào hoặc ra</option><option value="entry">Sự kiện vào</option><option value="exit">Sự kiện ra</option></select></label>
    <label>Phát hiện từ (%)<input id="detection_confidence_min" type="number" min="0" max="100" step="any"></label><label>Phát hiện đến (%)<input id="detection_confidence_max" type="number" min="0" max="100" step="any"></label>
    <label>OCR từ (%)<input id="ocr_confidence_min" type="number" min="0" max="100" step="any"></label><label>OCR đến (%)<input id="ocr_confidence_max" type="number" min="0" max="100" step="any"></label>
    <label>Số lượt vào từ<input id="entry_count_min" type="number" min="0" step="1"></label><label>Số lượt vào đến<input id="entry_count_max" type="number" min="0" step="1"></label><label>Số lượt ra từ<input id="exit_count_min" type="number" min="0" step="1"></label><label>Số lượt ra đến<input id="exit_count_max" type="number" min="0" step="1"></label>
    <label>Ảnh toàn khung hình<select id="image"><option value="all">Tất cả</option><option value="yes">Có ảnh ở ít nhất một sự kiện</option><option value="no">Thiếu ảnh ở ít nhất một sự kiện</option></select></label><label>Mã sự kiện<input id="event_id" type="number" min="1" step="1"></label>
  </div><p class="advanced-note">Khoảng giờ cùng ngày; các ngưỡng độ tin cậy phải cùng đúng trên một sự kiện. Số lượt tính sau các bộ lọc lượt khác.</p></details></form>
  <div id="filter-chips" class="filter-chips" aria-label="Bộ lọc đang áp dụng"></div>
  <p id="message" role="status" style="font-size:12px;color:#788397;margin:0 0 12px"></p>
  <section class="summary" id="summary"></section>
  <section class="table-card" style="margin-bottom:16px"><div class="table-title"><div><h2>Tổng hợp theo biển số</h2><p>Chọn “Xem chi tiết” để xem các lượt ra vào và ảnh của xe.</p></div><div class="tools"><label for="summary-sort" style="font-size:12px;color:#788397">Sắp xếp</label><select id="summary-sort" class="select" style="width:auto"><option value="plate">Biển số A–Z</option><option value="entries">Lượt vào nhiều nhất</option><option value="exits">Lượt ra nhiều nhất</option><option value="duration">Thời gian lưu trú nhiều nhất</option><option value="review">Cần kiểm tra nhiều nhất</option></select></div></div><div class="table-wrap"><table><thead><tr><th>Biển số</th><th>Lượt vào</th><th>Lượt ra</th><th>Hoàn chỉnh</th><th>Tổng thời gian</th><th>Trung bình</th><th>Chưa ghi nhận ra</th><th>Cần kiểm tra</th><th>Thông tin xe</th></tr></thead><tbody id="summary-rows"></tbody></table></div><div class="pagination"><span id="summary-page-info"></span><nav class="pages" id="summary-pages" aria-label="Phân trang bảng tổng hợp"></nav></div></section>
  <section class="table-card"><div class="table-title"><div><h2>Chi tiết lượt lưu trú</h2><p>Chọn theo ngày vào; lượt thiếu vào chọn theo ngày ra. Thời gian sử dụng múi giờ Việt Nam.</p></div></div><div class="table-wrap"><table><thead><tr><th>Biển số</th><th>Thời gian vào</th><th>Camera vào</th><th>Thời gian ra</th><th>Camera ra</th><th>Thời gian lưu trú</th><th>Trạng thái</th><th>Ảnh sự kiện</th></tr></thead><tbody id="visit-rows"></tbody></table></div><div class="pagination"><span id="page-info"></span><nav class="pages" id="visit-pages" aria-label="Phân trang bảng chi tiết"></nav></div></section>
  <p style="font-size:12px;color:#8993a4;line-height:1.6">Ghép chính xác theo biển số và thứ tự sự kiện. Lượt thiếu hoặc liên tiếp cùng hướng cần kiểm tra ảnh; OCR sai hoặc sự kiện ghi trùng có thể ảnh hưởng kết quả. Bộ lọc camera chọn lượt có camera ở một trong hai đầu; bộ lọc trạng thái áp dụng cho cả bảng và xuất file.</p>
  <dialog id="vehicle-dialog" class="vehicle-dialog" aria-labelledby="vehicle-title"><div class="dialog-header"><div><h2 id="vehicle-title"></h2><p>Thông tin và ảnh theo bộ lọc đang áp dụng</p></div><button id="close-vehicle" type="button" class="dialog-close" aria-label="Đóng">×</button></div><div id="vehicle-body" class="dialog-body"></div></dialog>`;
const $ = id => document.getElementById(id);
const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const date = new Date(`${today}T00:00:00Z`); date.setUTCDate(date.getUTCDate()-29);
const defaultStart = date.toISOString().slice(0,10);
const labels = {complete:'Đã ra',open:'Chưa ghi nhận ra',missing_in:'Thiếu lượt vào',review:'Cần kiểm tra'};
let report = null, page = 0, summaryPage = 0;
const pageSize = 30;
const filterIds=['plate','start','end','status','camera','plate_mode','time_field','time_start','time_end','entry_camera','exit_camera','duration_min','duration_max','confidence_side','detection_confidence_min','detection_confidence_max','ocr_confidence_min','ocr_confidence_max','entry_count_min','entry_count_max','exit_count_min','exit_count_max','image','event_id'];
const defaults={plate:'',start:defaultStart,end:today,status:'all',camera:'all',plate_mode:'partial',time_field:'anchor',time_start:'',time_end:'',entry_camera:'all',exit_camera:'all',duration_min:'',duration_max:'',confidence_side:'either',detection_confidence_min:'',detection_confidence_max:'',ocr_confidence_min:'',ocr_confidence_max:'',entry_count_min:'',entry_count_max:'',exit_count_min:'',exit_count_max:'',image:'all',event_id:''};
function reset() { for(const id of filterIds) $(id).value=defaults[id]; }
reset();
let appliedFilters=null, searchTimer=null, requestVersion=0;
const fromUrl=new URLSearchParams(location.search); for(const id of filterIds) if(fromUrl.has(id)) $(id).value=fromUrl.get(id);
const shiftDay=(value,n)=>{const d=new Date(`${value}T00:00:00Z`);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
document.querySelectorAll('[data-range]').forEach(button=>button.onclick=()=>{const range=button.dataset.range; let start=today,end=today; if(range==='7'||range==='30') start=shiftDay(today,1-Number(range)); if(range==='month') start=today.slice(0,8)+'01'; if(range==='previous'){end=shiftDay(today.slice(0,8)+'01',-1);start=end.slice(0,8)+'01';} $('start').value=start;$('end').value=end;load();});
function element(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
function formatTime(value) { return value ? new Intl.DateTimeFormat('vi-VN', {timeZone:'Asia/Bangkok',dateStyle:'short',timeStyle:'medium'}).format(new Date(value)) : '—'; }
function duration(value) { if (value == null) return '—'; const seconds = Math.floor(value), days = Math.floor(seconds/86400), hours = Math.floor(seconds%86400/3600), minutes = Math.floor(seconds%3600/60); return `${days ? days+' ngày ' : ''}${hours} giờ ${minutes} phút`; }
function emptyRow(target, columns, message) { const row = target.insertRow(), cell = row.insertCell(); cell.colSpan=columns; cell.textContent=message; }
function render() {
  const totals = report.summary.reduce((a,x) => ({entries:a.entries+x.entries, exits:a.exits+x.exits, complete:a.complete+x.complete, open:a.open+x.open}), {entries:0,exits:0,complete:0,open:0});
  $('summary').replaceChildren();
  for (const [label,value] of [['Lượt vào',totals.entries],['Lượt ra',totals.exits],['Lượt hoàn chỉnh',totals.complete],['Chưa ghi nhận ra',totals.open]]) { const card=element('div',''); card.className='summary-card'; const box=element('div',''); box.append(element('span',label),element('b',String(value))); card.append(box); $('summary').append(card); }
  renderSummaryPage();
  renderPage();
}
function renderSummaryPage() {
  const tbody=$('summary-rows'); tbody.replaceChildren();
  const sort=$('summary-sort').value, key=sort==='duration'?'duration_seconds':sort;
  const items=[...report.summary].sort((a,b)=>sort==='plate' ? a.plate.localeCompare(b.plate) : b[key]-a[key] || a.plate.localeCompare(b.plate));
  for (const item of items.slice(summaryPage*pageSize,(summaryPage+1)*pageSize)) { const row=tbody.insertRow(); const button=element('button',item.plate); button.type='button'; button.className='plate-detail'; button.setAttribute('aria-label',`Xem chi tiết biển số ${item.plate}`); button.onclick=()=>showVehicle(item.plate); row.insertCell().append(button); for (const value of [item.entries,item.exits,item.complete,duration(item.duration_seconds),duration(item.complete ? item.duration_seconds/item.complete : null),item.open,item.review]) row.insertCell().textContent=value; const details=element('button','Xem chi tiết →'); details.type='button'; details.className='view-details'; details.setAttribute('aria-label',`Xem chi tiết và ảnh xe ${item.plate}`); details.onclick=()=>showVehicle(item.plate); row.insertCell().append(details); }
  if (!items.length) emptyRow(tbody,9,'Không có dữ liệu phù hợp.');
  $('summary-page-info').textContent=items.length ? `Hiển thị ${summaryPage*pageSize+1}–${Math.min((summaryPage+1)*pageSize,items.length)} / ${items.length} biển số` : 'Không có biển số';
  renderPagination($('summary-pages'),summaryPage,items.length,next=>{summaryPage=next;renderSummaryPage();});
}
$('summary-sort').onchange=()=>{summaryPage=0;if(report)renderSummaryPage();};
function renderPagination(container,current,total,onChange) {
  container.replaceChildren(); const count=Math.ceil(total/pageSize);
  if (count<=1) return;
  const button=(text,target,label,disabled=false,active=false)=>{
    const item=element('button',text); item.type='button'; item.className=`page${active?' on':''}`; item.disabled=disabled; item.setAttribute('aria-label',label);
    if(active) item.setAttribute('aria-current','page'); item.onclick=()=>onChange(target); container.append(item);
  };
  button('‹',current-1,'Trang trước',current===0);
  const pages=new Set([0,count-1,current-1,current,current+1]); let last=-1;
  for(const index of [...pages].filter(n=>n>=0&&n<count).sort((a,b)=>a-b)) {
    if(index-last>1) { const gap=element('span','…'); gap.className='page-gap'; gap.setAttribute('aria-hidden','true'); container.append(gap); }
    button(String(index+1),index,`Trang ${index+1}`,false,index===current); last=index;
  }
  button('›',current+1,'Trang sau',current===count-1);
}
function renderPage() {
  const tbody=$('visit-rows'); tbody.replaceChildren();
  const visits=report.visits.slice(page*pageSize,(page+1)*pageSize);
  for (const item of visits) {
    const row=tbody.insertRow();
    const button=element('button',item.plate); button.type='button'; button.className='plate-detail'; button.setAttribute('aria-label',`Xem chi tiết biển số ${item.plate}`); button.onclick=()=>showVehicle(item.plate); row.insertCell().append(button);
    for (const value of [formatTime(item.entry?.created_at),item.entry?.camera_name || '—',formatTime(item.exit?.created_at),item.exit?.camera_name || '—',duration(item.duration_seconds),labels[item.status]]) row.insertCell().textContent=value;
    const cell=row.insertCell();
    for (const [name,event] of [['vào',item.entry],['ra',item.exit]]) if (event) { const link=element('a',`Xem ảnh ${name} ↗`); link.href=`/api/events/${event.id}/${event.has_full_image ? 'full-image' : 'image'}`; link.target='_blank'; link.rel='noopener'; link.className='event-image-link'; link.setAttribute('aria-label',`Xem ảnh sự kiện xe ${name}, biển số ${item.plate}`); cell.append(link); }
  }
  if (!visits.length) emptyRow(tbody,8,'Không có lượt phù hợp.');
  $('page-info').textContent=report.visits.length ? `Hiển thị ${page*pageSize+1}–${Math.min((page+1)*pageSize,report.visits.length)} / ${report.visits.length} lượt` : 'Không có lượt';
  renderPagination($('visit-pages'),page,report.visits.length,next=>{page=next;renderPage();});
}
function showVehicle(plate) {
  const summary=report.summary.find(item=>item.plate===plate), visits=report.visits.filter(item=>item.plate===plate), body=$('vehicle-body');
  if (!summary) return;
  $('vehicle-title').textContent=`Biển số ${plate}`; body.replaceChildren();
  const stats=element('div',''); stats.className='vehicle-stats';
  for (const [name,value] of [['Lượt vào',summary.entries],['Lượt ra',summary.exits],['Lượt hoàn chỉnh',summary.complete],['Tổng thời gian',summary.complete ? duration(summary.duration_seconds) : '—']]) { const card=element('div',''); card.append(element('span',name),element('strong',String(value))); stats.append(card); }
  body.append(stats);
  for (const visit of visits) {
    const card=element('section',''); card.className='visit-detail';
    const header=element('div',''); header.className='visit-detail-head'; header.append(element('strong',labels[visit.status]),element('span',`Thời gian lưu trú: ${duration(visit.duration_seconds)}`)); card.append(header);
    const sides=element('div',''); sides.className='visit-sides';
    for (const [name,event] of [['Xe vào',visit.entry],['Xe ra',visit.exit]]) {
      const side=element('div',''); side.className='visit-side'; side.append(element('h3',name));
      if (!event) { side.append(element('p','Chưa có sự kiện.')); sides.append(side); continue; }
      side.append(element('p',`${formatTime(event.created_at)} · ${event.camera_name}`));
      const images=element('div',''); images.className='event-images';
      for (const [label,type,available] of [['Ảnh biển số','image',true],['Ảnh toàn khung hình','full-image',event.has_full_image]]) {
        const figure=element('figure',''); const caption=element('figcaption',label); figure.append(caption);
        if (available) { const link=element('a',''); link.href=`/api/events/${event.id}/${type}`; link.target='_blank'; link.rel='noopener'; const img=document.createElement('img'); img.src=link.href; img.alt=`${label} · ${name} · ${plate}`; img.loading='lazy'; img.onerror=()=>{link.replaceChildren(element('span','Không có ảnh'));}; link.append(img); figure.append(link); }
        else figure.append(element('span','Không có ảnh toàn khung hình'));
        images.append(figure);
      }
      side.append(images); sides.append(side);
    }
    card.append(sides); body.append(card);
  }
  $('vehicle-dialog').showModal();
}
$('close-vehicle').onclick=()=>$('vehicle-dialog').close();
$('vehicle-dialog').addEventListener('click',event=>{if(event.target===$('vehicle-dialog')) $('vehicle-dialog').close();});
async function load() {
  clearTimeout(searchTimer);
  const version=++requestVersion;
  $('message').textContent='Đang tải dữ liệu…'; $('export').disabled=true;
  const params=new URLSearchParams(); for(const id of filterIds) if($(id).value) params.set(id,$(id).value);
  try { const response=await fetch(`/api/visits?${params}`); const data=await response.json(); if(version!==requestVersion) return; if(!response.ok) throw new Error(data.error || 'Không tải được báo cáo'); report=data; appliedFilters=new URLSearchParams(params); history.replaceState(null,'',`${location.pathname}?${params}`); page=0; summaryPage=0; render(); renderChips(); $('export').disabled=false; $('message').textContent=`Tìm thấy ${data.visits.length} lượt · ${data.summary.length} biển số. Dữ liệu được ghép trước khi lọc.`; }
  catch(error) { if(version!==requestVersion) return; report=null; $('summary').replaceChildren(); $('summary-rows').replaceChildren(); $('visit-rows').replaceChildren(); $('page-info').textContent=''; $('summary-page-info').textContent=''; $('summary-pages').replaceChildren(); $('visit-pages').replaceChildren(); $('message').textContent=error.message; }
}
$('filters').onsubmit=event=>{event.preventDefault();load();}; $('reset').onclick=()=>{reset();load();};
$('plate').addEventListener('input',()=>{ clearTimeout(searchTimer); requestVersion++; $('export').disabled=true; $('message').textContent='Đang chờ tìm kiếm…'; searchTimer=setTimeout(load,350); });
function renderChips(){ const chips=$('filter-chips');chips.replaceChildren(); for(const id of filterIds){const value=appliedFilters.get(id);if(!value||value===defaults[id])continue;const label=document.querySelector(`label[for="${id}"]`) || $(id).closest('label');const name=label ? label.childNodes[0].textContent.trim() : id;const selected=$(id).tagName==='SELECT' ? $(id).selectedOptions[0]?.textContent : value;const chip=element('button',`${name}: ${selected} ×`);chip.type='button';chip.className='filter-chip';chip.onclick=()=>{$(id).value=defaults[id];load();};chips.append(chip);} }
function csvCell(value) { let text=String(value ?? ''); if (/^[\s]*[=+\-@\t\r]/.test(text)) text="'"+text; return `"${text.replaceAll('"','""')}"`; }
$('export').onclick=()=>{
  if(!report) return;
  const rows=[['BÁO CÁO GATEVIEW'],['Thời điểm xuất',formatTime(new Date().toISOString())],['Bộ lọc',appliedFilters.toString()],[],['TỔNG HỢP THEO BIỂN SỐ'],['Biển số','Lượt vào','Lượt ra','Hoàn chỉnh','Tổng thời gian','Trung bình','Chưa ghi nhận ra','Cần kiểm tra']];
  for(const s of report.summary) rows.push([s.plate,s.entries,s.exits,s.complete,duration(s.duration_seconds),duration(s.complete ? s.duration_seconds/s.complete : null),s.open,s.review]);
  rows.push([],['CHI TIẾT LƯỢT LƯU TRÚ'],['Biển số','Thời gian vào','Camera vào','Thời gian ra','Camera ra','Thời gian lưu trú','Trạng thái','Mã sự kiện vào','Mã sự kiện ra']);
  for(const v of report.visits) rows.push([v.plate,formatTime(v.entry?.created_at),v.entry?.camera_name,formatTime(v.exit?.created_at),v.exit?.camera_name,duration(v.duration_seconds),labels[v.status],v.entry?.id,v.exit?.id]);
  const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n'); const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})); const link=document.createElement('a'); link.href=url; link.download=`gateview-luot-xe-${appliedFilters.get('start')}-${appliedFilters.get('end')}.csv`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
};
fetch('/api/cameras').then(r=>r.json()).then(cameras=>{for(const id of ['camera','entry_camera','exit_camera']){for(const c of cameras){const option=element('option',`${c.name} (${c.code})`);option.value=c.id;$(id).append(option);}if(fromUrl.has(id)) $(id).value=fromUrl.get(id);}}).catch(()=>{}).finally(load);
