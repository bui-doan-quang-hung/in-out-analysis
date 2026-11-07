import json, os, sqlite3, subprocess, re, math, datetime, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

DB = os.environ.get('DB_PATH', '/data/gateview.db')
annotated_frames = {}
ai_heartbeat = None
ai_revision = 0
ai_applied_revision = 0
ai_error = None
os.makedirs(os.path.dirname(DB), exist_ok=True)
def db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn
with db() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT OR IGNORE INTO settings VALUES ('ai_enabled', '1')")
    conn.execute('CREATE TABLE IF NOT EXISTS cameras (id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL, rtsp TEXT NOT NULL, direction TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)')
    conn.execute('CREATE TABLE IF NOT EXISTS camera_roi (camera_id INTEGER PRIMARY KEY, x REAL NOT NULL, y REAL NOT NULL, width REAL NOT NULL, height REAL NOT NULL, FOREIGN KEY(camera_id) REFERENCES cameras(id))')
    conn.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL, camera_name TEXT NOT NULL, direction TEXT NOT NULL, plate TEXT NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL, image BLOB)')
    if 'full_image' not in {row['name'] for row in conn.execute('PRAGMA table_info(events)')}: conn.execute('ALTER TABLE events ADD COLUMN full_image BLOB')
    if 'event_key' not in {row['name'] for row in conn.execute('PRAGMA table_info(events)')}: conn.execute('ALTER TABLE events ADD COLUMN event_key TEXT')
    if 'ocr_confidence' not in {row['name'] for row in conn.execute('PRAGMA table_info(events)')}: conn.execute('ALTER TABLE events ADD COLUMN ocr_confidence REAL')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS events_event_key ON events(event_key) WHERE event_key IS NOT NULL')

def ai_enabled():
    with db() as conn: return conn.execute("SELECT value FROM settings WHERE key='ai_enabled'").fetchone()[0] == '1'

def public(row):
    return {k: row[k] for k in ('id', 'name', 'code', 'rtsp', 'direction', 'enabled')}

def statistics(query):
    params = parse_qs(query)
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date()
    start = datetime.date.fromisoformat(params.get('start', [(today - datetime.timedelta(days=29)).isoformat()])[0])
    end = datetime.date.fromisoformat(params.get('end', [today.isoformat()])[0])
    if end < start or (end - start).days > 3659: raise ValueError('Invalid date range')
    direction = params.get('direction', ['all'])[0]
    if direction not in ('all', 'in', 'out'): raise ValueError('Invalid direction')
    camera = params.get('camera', ['all'])[0]
    if camera != 'all' and (not camera.isdigit() or int(camera) < 1): raise ValueError('Invalid camera')
    where = ["date(created_at, '+7 hours') >= ?", "date(created_at, '+7 hours') <= ?"]
    values = [start.isoformat(), end.isoformat()]
    if direction != 'all': where.append('direction = ?'); values.append(direction)
    if camera != 'all': where.append('camera_id = ?'); values.append(int(camera))
    where = ' AND '.join(where)
    with db() as conn:
        daily = conn.execute("SELECT date(created_at, '+7 hours') AS day, direction, count(*) AS total FROM events WHERE " + where + ' GROUP BY day, direction', values).fetchall()
        hourly = conn.execute("SELECT CAST(strftime('%H', created_at, '+7 hours') AS INTEGER) AS hour, count(*) AS total FROM events WHERE " + where + ' GROUP BY hour', values).fetchall()
        cameras = conn.execute('SELECT camera_id, camera_name, direction, count(*) AS total FROM events WHERE ' + where + ' GROUP BY camera_id, camera_name, direction ORDER BY total DESC', values).fetchall()
        summary = conn.execute('SELECT count(*) AS total, count(DISTINCT plate) AS unique_plates, avg(confidence) AS detection, avg(ocr_confidence) AS ocr, count(ocr_confidence) AS ocr_count FROM events WHERE ' + where, values).fetchone()
        quality = conn.execute('SELECT sum(CASE WHEN confidence < 0.5 THEN 1 ELSE 0 END) AS detection_low, sum(CASE WHEN ocr_confidence < 0.8 THEN 1 ELSE 0 END) AS ocr_low FROM events WHERE ' + where, values).fetchone()
    counts = {(row['day'], row['direction']): row['total'] for row in daily}
    days = []
    for i in range((end - start).days + 1):
        day = start + datetime.timedelta(days=i); key = day.isoformat()
        days.append({'date': key, 'in': counts.get((key, 'in'), 0), 'out': counts.get((key, 'out'), 0)})
    totals = {key: sum(d[key] for d in days) for key in ('in', 'out')}
    week_count = ((end - datetime.timedelta(days=end.weekday())) - (start - datetime.timedelta(days=start.weekday()))).days // 7 + 1
    month_count = (end.year - start.year) * 12 + end.month - start.month + 1
    weekdays = [0] * 7
    for item in days: weekdays[datetime.date.fromisoformat(item['date']).weekday()] += item['in'] + item['out']
    hours = [0] * 24
    for row in hourly: hours[row['hour']] = row['total']
    return {'start': start.isoformat(), 'end': end.isoformat(), 'totals': totals, 'days': days, 'hours': hours, 'weekdays': weekdays, 'cameras': [dict(row) for row in cameras], 'unique_plates': summary['unique_plates'], 'average_detection': summary['detection'], 'average_ocr': summary['ocr'], 'ocr_count': summary['ocr_count'], 'detection_low': quality['detection_low'] or 0, 'ocr_low': quality['ocr_low'] or 0, 'periods': {'days': len(days), 'weeks': week_count, 'months': month_count}}

def visit_report(query):
    params = parse_qs(query)
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date()
    start = datetime.date.fromisoformat(params.get('start', [(today - datetime.timedelta(days=29)).isoformat()])[0])
    end = datetime.date.fromisoformat(params.get('end', [today.isoformat()])[0])
    if end < start or (end - start).days > 3659: raise ValueError('Invalid date range')
    plate = re.sub(r'[^A-Z0-9]', '', params.get('plate', [''])[0].upper())
    mode = params.get('plate_mode', ['partial'])[0]
    time_field = params.get('time_field', ['anchor'])[0]
    side = params.get('confidence_side', ['either'])[0]
    image = params.get('image', ['all'])[0]
    if mode not in ('partial', 'exact') or time_field not in ('anchor', 'entry', 'exit', 'either') or side not in ('entry', 'exit', 'either') or image not in ('all', 'yes', 'no'): raise ValueError('Invalid filter')
    def numeric(name, maximum=None, integer=False):
        value = params.get(name, [''])[0]
        if not value: return None
        result = int(value) if integer else float(value)
        if not math.isfinite(result) or result < 0 or (maximum is not None and result > maximum): raise ValueError('Invalid number')
        return result
    limits = {name: numeric(name, 100 if 'confidence' in name else None, 'count' in name or name == 'event_id') for name in ('duration_min', 'duration_max', 'detection_confidence_min', 'detection_confidence_max', 'ocr_confidence_min', 'ocr_confidence_max', 'entry_count_min', 'entry_count_max', 'exit_count_min', 'exit_count_max', 'event_id')}
    for prefix in ('duration', 'detection_confidence', 'ocr_confidence', 'entry_count', 'exit_count'):
        low, high = limits[prefix+'_min'], limits[prefix+'_max']
        if low is not None and high is not None and low > high: raise ValueError('Invalid range')
    clock_start = datetime.time.fromisoformat(params['time_start'][0]) if params.get('time_start') else None
    clock_end = datetime.time.fromisoformat(params['time_end'][0]) if params.get('time_end') else None
    if clock_start and clock_end and clock_start > clock_end: raise ValueError('Invalid time range')
    camera = params.get('camera', ['all'])[0]
    status = params.get('status', ['all'])[0]
    if camera != 'all' and (not camera.isdigit() or int(camera) < 1): raise ValueError('Invalid camera')
    if status not in ('all', 'complete', 'open', 'missing_in', 'review'): raise ValueError('Invalid status')
    with db() as conn:
        rows = conn.execute('SELECT id,camera_id,camera_name,direction,plate,created_at,confidence,ocr_confidence,(full_image IS NOT NULL) AS has_full_image FROM events ORDER BY plate, julianday(created_at), id').fetchall()
    groups = {}
    for row in rows:
        normalized = re.sub(r'[^A-Z0-9]', '', row['plate'].upper())
        if plate and ((mode == 'exact' and normalized != plate) or (mode == 'partial' and plate not in normalized)): continue
        groups.setdefault(row['plate'], []).append(dict(row))
    visits = []
    for plate_number, events in groups.items():
        pending = []
        for event in events:
            if event['direction'] == 'in': pending.append(event); continue
            if len(pending) == 1:
                entry = pending.pop()
                elapsed = (datetime.datetime.fromisoformat(event['created_at']) - datetime.datetime.fromisoformat(entry['created_at'])).total_seconds()
                visits.append({'plate': plate_number, 'entry': entry, 'exit': event, 'status': 'complete', 'duration_seconds': max(0, int(elapsed))})
            elif pending:
                for entry in pending: visits.append({'plate': plate_number, 'entry': entry, 'exit': None, 'status': 'review', 'duration_seconds': None})
                pending = []
                visits.append({'plate': plate_number, 'entry': None, 'exit': event, 'status': 'review', 'duration_seconds': None})
            else:
                if visits and visits[-1]['plate'] == plate_number and visits[-1]['exit'] is not None:
                    visits[-1]['status'] = 'review'; visits[-1]['duration_seconds'] = None
                    visits.append({'plate': plate_number, 'entry': None, 'exit': event, 'status': 'review', 'duration_seconds': None})
                else: visits.append({'plate': plate_number, 'entry': None, 'exit': event, 'status': 'missing_in', 'duration_seconds': None})
        for entry in pending: visits.append({'plate': plate_number, 'entry': entry, 'exit': None, 'status': 'open' if len(pending) == 1 else 'review', 'duration_seconds': None})
    tz = datetime.timezone(datetime.timedelta(hours=7))
    def selected(event):
        timestamp = datetime.datetime.fromisoformat(event['created_at']).astimezone(tz)
        return start <= timestamp.date() <= end and (clock_start is None or timestamp.time().replace(tzinfo=None) >= clock_start) and (clock_end is None or timestamp.time().replace(tzinfo=None) <= clock_end)
    def camera_value(name):
        value = params.get(name, ['all'])[0]
        if value != 'all' and (not value.isdigit() or int(value) < 1): raise ValueError('Invalid camera')
        return value
    entry_camera, exit_camera = camera_value('entry_camera'), camera_value('exit_camera')
    filtered = []
    for visit in visits:
        anchor = visit['entry'] or visit['exit']
        time_events = {'anchor': [anchor], 'entry': [visit['entry']], 'exit': [visit['exit']], 'either': [visit['entry'], visit['exit']]}[time_field]
        if not any(event and selected(event) for event in time_events) or (status != 'all' and visit['status'] != status): continue
        if camera != 'all' and not any(event and event['camera_id'] == int(camera) for event in (visit['entry'], visit['exit'])): continue
        if entry_camera != 'all' and (not visit['entry'] or visit['entry']['camera_id'] != int(entry_camera)): continue
        if exit_camera != 'all' and (not visit['exit'] or visit['exit']['camera_id'] != int(exit_camera)): continue
        seconds = visit['duration_seconds']
        if (limits['duration_min'] is not None or limits['duration_max'] is not None) and (seconds is None or (limits['duration_min'] is not None and seconds < limits['duration_min']*60) or (limits['duration_max'] is not None and seconds > limits['duration_max']*60)): continue
        events = [event for event in (visit['entry'], visit['exit']) if event]
        if limits['event_id'] is not None and not any(event['id'] == limits['event_id'] for event in events): continue
        if image != 'all' and not any(bool(event['has_full_image']) == (image == 'yes') for event in events): continue
        check_events = events if side == 'either' else [visit[side]] if visit[side] else []
        def confidence_matches(event):
            for key, field in [('detection_confidence','confidence'), ('ocr_confidence','ocr_confidence')]:
                low, high, value = limits[key+'_min'], limits[key+'_max'], event[field]
                if (low is not None or high is not None) and (value is None or (low is not None and value*100 < low) or (high is not None and value*100 > high)): return False
            return True
        if any(limits[k] is not None for k in ('detection_confidence_min','detection_confidence_max','ocr_confidence_min','ocr_confidence_max')) and not any(confidence_matches(event) for event in check_events): continue
        filtered.append(visit)
    filtered.sort(key=lambda v: (v['entry'] or v['exit'])['created_at'], reverse=True)
    summaries = {}
    for visit in filtered:
        item = summaries.setdefault(visit['plate'], {'plate': visit['plate'], 'entries': 0, 'exits': 0, 'complete': 0, 'duration_seconds': 0, 'open': 0, 'review': 0})
        item['entries'] += int(visit['entry'] is not None)
        item['exits'] += int(visit['exit'] is not None)
        item['complete'] += int(visit['status'] == 'complete')
        item['duration_seconds'] += visit['duration_seconds'] or 0
        item['open'] += int(visit['status'] == 'open')
        item['review'] += int(visit['status'] in ('review', 'missing_in'))
    allowed = {plate for plate, item in summaries.items() if all((limits[field+'_min'] is None or item[key] >= limits[field+'_min']) and (limits[field+'_max'] is None or item[key] <= limits[field+'_max']) for field,key in [('entry_count','entries'),('exit_count','exits')])}
    return {'visits': [v for v in filtered if v['plate'] in allowed], 'summary': sorted((v for k,v in summaries.items() if k in allowed), key=lambda x: x['plate'])}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    def reply(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length > 2097152: raise ValueError('Dữ liệu quá lớn')
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict): raise ValueError('Dữ liệu không hợp lệ')
        return value
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/visits':
            try: return self.reply(200, visit_report(urlsplit(self.path).query))
            except (ValueError, OverflowError): return self.reply(400, {'error': 'Khoảng thời gian hoặc bộ lọc không hợp lệ (tối đa 10 năm).'})
        if path == '/api/statistics':
            try: return self.reply(200, statistics(urlsplit(self.path).query))
            except (ValueError, OverflowError): return self.reply(400, {'error': 'Khoảng thời gian hoặc bộ lọc không hợp lệ (tối đa 10 năm).'})
        if path == '/api/ai':
            online = ai_heartbeat is not None and (datetime.datetime.now(datetime.timezone.utc) - ai_heartbeat).total_seconds() < 15
            return self.reply(200, {'enabled': ai_enabled(), 'worker_online': online, 'restarting': online and ai_revision != ai_applied_revision and not ai_error, 'error': ai_error})
        match = re.fullmatch(r'/api/cameras/(\d+)/annotated', path)
        if match:
            item = annotated_frames.get(int(match.group(1)))
            if not item or (datetime.datetime.now(datetime.timezone.utc) - item[0]).total_seconds() > 30: return self.reply(404, {'error': 'Chưa có khung hình nhận diện'})
            image = item[1]; self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(image))); self.end_headers(); self.wfile.write(image); return
        if path == '/api/event-stats':
            with db() as conn:
                rows = conn.execute("SELECT direction, count(*) AS total FROM events WHERE date(created_at, '+7 hours') = date('now', '+7 hours') GROUP BY direction").fetchall()
            totals = {row['direction']: row['total'] for row in rows}
            return self.reply(200, {'in': totals.get('in', 0), 'out': totals.get('out', 0)})
        if path == '/api/events':
            with db() as conn:
                rows = conn.execute('SELECT id,camera_id,camera_name,direction,plate,confidence,ocr_confidence,created_at, (full_image IS NOT NULL) AS has_full_image FROM events ORDER BY id DESC LIMIT 100').fetchall()
            return self.reply(200, [dict(row) for row in rows])
        match = re.fullmatch(r'/api/events/(\d+)/(image|full-image)', path)
        if match:
            with db() as conn: row = conn.execute('SELECT image, full_image FROM events WHERE id=?', (match.group(1),)).fetchone()
            image = row['full_image' if match.group(2) == 'full-image' else 'image'] if row else None
            if not image: return self.reply(404, {'error': 'Không tìm thấy ảnh'})
            self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.send_header('Content-Length', str(len(image))); self.end_headers(); self.wfile.write(image); return
        if path == '/api/cameras':
            with db() as conn: rows = conn.execute('SELECT * FROM cameras ORDER BY id').fetchall()
            return self.reply(200, [public(r) for r in rows])
        match = re.fullmatch(r'/api/cameras/(\d+)/(roi|snapshot|stream)', path)
        if match:
            with db() as conn:
                camera = conn.execute('SELECT * FROM cameras WHERE id=?', (match.group(1),)).fetchone()
                roi = conn.execute('SELECT x,y,width,height FROM camera_roi WHERE camera_id=?', (match.group(1),)).fetchone()
            if not camera: return self.reply(404, {'error': 'Không tìm thấy camera'})
            if match.group(2) == 'roi': return self.reply(200, dict(roi) if roi else {})
            if not camera['enabled']: return self.reply(409, {'error': 'Camera đã ngừng sử dụng'})
            if match.group(2) == 'stream':
                process = subprocess.Popen(['ffmpeg', '-nostdin', '-loglevel', 'error', '-rtsp_transport', 'tcp', '-i', camera['rtsp'], '-an', '-vf', 'fps=5,scale=960:-2', '-q:v', '5', '-f', 'mpjpeg', '-boundary_tag', 'frame', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                try:
                    self.send_response(200); self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame'); self.send_header('Cache-Control', 'no-store'); self.end_headers()
                    while True:
                        chunk = process.stdout.read1(65536)
                        if not chunk: break
                        self.wfile.write(chunk); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError): pass
                finally:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
                    process.stdout.close()
                return
            try:
                result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-rtsp_transport', 'tcp', '-i', camera['rtsp'], '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'], capture_output=True, timeout=12)
                if result.returncode or not result.stdout: return self.reply(502, {'error': 'Không lấy được ảnh camera'})
                self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(result.stdout))); self.end_headers(); self.wfile.write(result.stdout); return
            except subprocess.TimeoutExpired: return self.reply(504, {'error': 'Camera không phản hồi'})
        self.reply(404, {'error': 'Không tìm thấy'})
    def do_POST(self):
        global ai_heartbeat, ai_revision, ai_applied_revision, ai_error
        if self.path == '/api/ai/restart':
            if ai_heartbeat is None or (datetime.datetime.now(datetime.timezone.utc) - ai_heartbeat).total_seconds() >= 15:
                return self.reply(409, {'error': 'AI worker is not connected'})
            ai_revision += 1; ai_error = None; annotated_frames.clear()
            return self.reply(202, {'revision': ai_revision})
        if self.path == '/api/ai/heartbeat':
            body = self.body()
            ai_heartbeat = datetime.datetime.now(datetime.timezone.utc)
            ai_applied_revision = body.get('revision', 0)
            ai_error = body.get('error') if ai_applied_revision != ai_revision else None
            return self.reply(200, {'enabled': ai_enabled(), 'revision': ai_revision})
        if (self.path == '/api/events' or re.fullmatch(r'/api/cameras/\d+/annotated', self.path)) and not ai_enabled():
            return self.reply(409, {'error': 'AI đã tắt'})
        match = re.fullmatch(r'/api/cameras/(\d+)/annotated', self.path)
        if match:
            try:
                image = base64.b64decode(self.body()['image'], validate=True)
                if not image.startswith(b'\xff\xd8') or len(image) > 750000: raise ValueError()
                annotated_frames[int(match.group(1))] = (datetime.datetime.now(datetime.timezone.utc), image)
                return self.reply(200, {'ok': True})
            except (ValueError, TypeError, KeyError): return self.reply(400, {'error': 'Ảnh không hợp lệ'})
        if self.path != '/api/events': return self.write_camera(False)
        try:
            body = self.body(); camera_id = int(body['camera_id']); plate = re.sub(r'[^A-Z0-9]', '', str(body['plate']).upper()); confidence = float(body['confidence']); event_key = body.get('event_key'); ocr_confidence = float(body['ocr_confidence']) if body.get('ocr_confidence') is not None else None
            if not 5 <= len(plate) <= 12 or not math.isfinite(confidence) or not 0 <= confidence <= 1: raise ValueError('Dữ liệu nhận diện không hợp lệ')
            if ocr_confidence is not None and (not math.isfinite(ocr_confidence) or not 0 <= ocr_confidence <= 1): raise ValueError('Độ tin cậy OCR không hợp lệ')
            if event_key is not None and (not isinstance(event_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', event_key)): raise ValueError('Mã sự kiện không hợp lệ')
            image = base64.b64decode(body.get('image', ''), validate=True)
            full_image = base64.b64decode(body['full_image'], validate=True) if body.get('full_image') else None
            if full_image and (not full_image.startswith(b'\xff\xd8') or len(full_image) > 1200000): raise ValueError('Invalid full image')
            now = datetime.datetime.now(datetime.timezone.utc); cutoff = (now - datetime.timedelta(minutes=5)).isoformat()
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                camera = conn.execute('SELECT * FROM cameras WHERE id=? AND enabled=1', (camera_id,)).fetchone()
                if not camera: return self.reply(404, {'error': 'Không tìm thấy camera đang sử dụng'})
                existing = conn.execute('SELECT id,camera_id,ocr_confidence FROM events WHERE event_key=?', (event_key,)).fetchone() if event_key else None
                if existing:
                    if existing['camera_id'] != camera_id: return self.reply(409, {'error':'Mã sự kiện thuộc camera khác'})
                    if ocr_confidence is not None and (existing['ocr_confidence'] is None or ocr_confidence > existing['ocr_confidence']):
                        if conn.execute('SELECT id FROM events WHERE plate=? AND created_at>=? AND id<>? LIMIT 1', (plate, cutoff, existing['id'])).fetchone(): return self.reply(200, {'id': existing['id'], 'duplicate': True, 'reason':'plate_recent_update'})
                        conn.execute('UPDATE events SET plate=?,confidence=?,ocr_confidence=?,image=?,full_image=COALESCE(?,full_image) WHERE id=?', (plate, confidence, ocr_confidence, image, full_image, existing['id']))
                        return self.reply(200, {'id': existing['id'], 'updated': True})
                    return self.reply(200, {'id': existing['id'], 'duplicate': True})
                if conn.execute('SELECT id FROM events WHERE plate=? AND created_at>=? LIMIT 1', (plate, cutoff)).fetchone(): return self.reply(200, {'duplicate': True, 'reason': 'plate_recent'})
                event_id = conn.execute('INSERT INTO events (camera_id,camera_name,direction,plate,confidence,created_at,image,event_key,ocr_confidence,full_image) VALUES (?,?,?,?,?,?,?,?,?,?)', (camera_id,camera['name'],camera['direction'],plate,confidence,now.isoformat(),image,event_key,ocr_confidence,full_image)).lastrowid
            return self.reply(201, {'id': event_id})
        except (ValueError, TypeError, KeyError): return self.reply(400, {'error': 'Dữ liệu nhận diện không hợp lệ'})
    def do_PUT(self):
        if self.path == '/api/ai':
            try:
                enabled = self.body()['enabled']
                if not isinstance(enabled, bool): raise ValueError()
                with db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='ai_enabled'", ('1' if enabled else '0',))
                if not enabled: annotated_frames.clear()
                return self.reply(200, {'enabled': enabled})
            except (KeyError, ValueError, TypeError): return self.reply(400, {'error': 'Trạng thái AI không hợp lệ'})
        match = re.fullmatch(r'/api/cameras/(\d+)/roi', self.path)
        if not match: return self.write_camera(True)
        try:
            body = self.body()
            values = [float(body[k]) for k in ('x', 'y', 'width', 'height')]
            x, y, width, height = values
            if not all(math.isfinite(v) for v in values) or x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1.000001 or y + height > 1.000001: raise ValueError('Vùng ROI không hợp lệ')
            with db() as conn:
                if not conn.execute('SELECT id FROM cameras WHERE id=?', (match.group(1),)).fetchone(): return self.reply(404, {'error': 'Không tìm thấy camera'})
                conn.execute('INSERT INTO camera_roi VALUES (?, ?, ?, ?, ?) ON CONFLICT(camera_id) DO UPDATE SET x=excluded.x,y=excluded.y,width=excluded.width,height=excluded.height', (match.group(1), *values))
            return self.reply(200, dict(zip(('x', 'y', 'width', 'height'), values)))
        except (ValueError, TypeError, KeyError): return self.reply(400, {'error': 'Vùng ROI không hợp lệ'})
    def write_camera(self, update):
        match = re.fullmatch(r'/api/cameras/(\d+)(/check)?', self.path)
        if match and match.group(2) and not update:
            with db() as conn: row = conn.execute('SELECT * FROM cameras WHERE id=?', (match.group(1),)).fetchone()
            if not row: return self.reply(404, {'error': 'Không tìm thấy camera'})
            if not row['enabled']: return self.reply(409, {'error': 'Camera đã ngừng sử dụng'})
            try:
                result = subprocess.run(['ffprobe', '-v', 'error', '-rtsp_transport', 'tcp', '-show_entries', 'stream=codec_type,width,height', '-of', 'json', row['rtsp']], capture_output=True, timeout=12)
                streams = json.loads(result.stdout or b'{}').get('streams', [])
                video = next((s for s in streams if s.get('codec_type') == 'video'), None)
                return self.reply(200, {'connected': result.returncode == 0 and video is not None, 'video': video})
            except (subprocess.TimeoutExpired, ValueError): return self.reply(200, {'connected': False, 'video': None})
        if (update and (not match or match.group(2))) or (not update and self.path != '/api/cameras'): return self.reply(404, {'error': 'Không tìm thấy'})
        try:
            body = self.body(); name = str(body.get('name', '')).strip(); code = str(body.get('code', '')).strip(); direction = body.get('direction'); rtsp = str(body.get('rtsp', '')).strip()
            if not name or not code or direction not in ('in', 'out'): raise ValueError('Tên, mã và hướng camera là bắt buộc')
            if len(name) > 120 or len(code) > 80: raise ValueError('Tên hoặc mã camera quá dài')
            with db() as conn:
                old = conn.execute('SELECT * FROM cameras WHERE id=?', (match.group(1),)).fetchone() if update else None
                if update and not old: return self.reply(404, {'error': 'Không tìm thấy camera'})
                if not rtsp and old: rtsp = old['rtsp']
                url = urlsplit(rtsp)
                if url.scheme not in ('rtsp', 'rtsps') or not url.hostname: raise ValueError('Địa chỉ RTSP không hợp lệ')
                if update:
                    conn.execute('UPDATE cameras SET name=?, code=?, direction=?, rtsp=?, enabled=? WHERE id=?', (name, code, direction, rtsp, int(bool(body.get('enabled', True))), match.group(1))); camera_id = match.group(1)
                else:
                    camera_id = conn.execute('INSERT INTO cameras (name, code, direction, rtsp, enabled) VALUES (?, ?, ?, ?, ?)', (name, code, direction, rtsp, int(bool(body.get('enabled', True))))).lastrowid
                row = conn.execute('SELECT * FROM cameras WHERE id=?', (camera_id,)).fetchone()
            self.reply(200 if update else 201, public(row))
        except (ValueError, TypeError, json.JSONDecodeError) as e: self.reply(400, {'error': str(e)})
        except sqlite3.IntegrityError: self.reply(409, {'error': 'Mã camera đã tồn tại'})

ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
