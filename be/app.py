import json, os, sqlite3, subprocess, re, math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DB = os.environ.get('DB_PATH', '/data/gateview.db')
os.makedirs(os.path.dirname(DB), exist_ok=True)
def db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn
with db() as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS cameras (id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL, rtsp TEXT NOT NULL, direction TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)')
    conn.execute('CREATE TABLE IF NOT EXISTS camera_roi (camera_id INTEGER PRIMARY KEY, x REAL NOT NULL, y REAL NOT NULL, width REAL NOT NULL, height REAL NOT NULL, FOREIGN KEY(camera_id) REFERENCES cameras(id))')

def public(row):
    return {k: row[k] for k in ('id', 'name', 'code', 'direction', 'enabled')}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    def reply(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length > 16384: raise ValueError('Dữ liệu quá lớn')
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict): raise ValueError('Dữ liệu không hợp lệ')
        return value
    def do_GET(self):
        if self.path == '/api/cameras':
            with db() as conn: rows = conn.execute('SELECT * FROM cameras ORDER BY id').fetchall()
            return self.reply(200, [public(r) for r in rows])
        match = re.fullmatch(r'/api/cameras/(\d+)/(roi|snapshot)', self.path)
        if match:
            with db() as conn:
                camera = conn.execute('SELECT * FROM cameras WHERE id=?', (match.group(1),)).fetchone()
                roi = conn.execute('SELECT x,y,width,height FROM camera_roi WHERE camera_id=?', (match.group(1),)).fetchone()
            if not camera: return self.reply(404, {'error': 'Không tìm thấy camera'})
            if match.group(2) == 'roi': return self.reply(200, dict(roi) if roi else {})
            if not camera['enabled']: return self.reply(409, {'error': 'Camera đã ngừng sử dụng'})
            try:
                result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-rtsp_transport', 'tcp', '-i', camera['rtsp'], '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'], capture_output=True, timeout=12)
                if result.returncode or not result.stdout: return self.reply(502, {'error': 'Không lấy được ảnh camera'})
                self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(result.stdout))); self.end_headers(); self.wfile.write(result.stdout); return
            except subprocess.TimeoutExpired: return self.reply(504, {'error': 'Camera không phản hồi'})
        self.reply(404, {'error': 'Không tìm thấy'})
    def do_POST(self): self.write_camera(False)
    def do_PUT(self):
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
