"""Read each RTSP stream independently and process its latest frame on CUDA."""
import base64, json, logging, threading, time, urllib.request, uuid, re
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
import cv2
import torch
import numpy as np
from fast_alpr import ALPR
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import YAML, ROOT

BASE = 'http://127.0.0.1:8080'
MODEL = Path(__file__).resolve().parent.parent / 'model' / 'best_640x640.pt'
CONFIG_PATH = Path(__file__).resolve().parent.parent / 'tracking.json'
def load_settings():
    with CONFIG_PATH.open(encoding='utf-8') as config_file:
        settings = json.load(config_file)
    confidence = settings['detection_confidence']
    tracker = settings['tracker']
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError('detection_confidence must be between 0 and 1')
    for key in ('track_high_thresh', 'track_low_thresh', 'new_track_thresh', 'match_thresh'):
        value = tracker[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1: raise ValueError(key + ' must be between 0 and 1')
    if not isinstance(tracker['track_buffer'], int) or isinstance(tracker['track_buffer'], bool) or tracker['track_buffer'] < 1: raise ValueError('track_buffer must be a positive integer')
    if not isinstance(tracker['fuse_score'], bool): raise ValueError('fuse_score must be a boolean')
    return settings

SETTINGS = load_settings()
DETECTION_CONFIDENCE = SETTINGS['detection_confidence']
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(threadName)s %(message)s')

def request(path, data=None):
    raw = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=raw, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response: return response.read()

def host_url(url):
    parts = urlsplit(url)
    if parts.hostname != 'host.docker.internal': return url
    return urlunsplit((parts.scheme, parts.netloc.replace('host.docker.internal', '127.0.0.1'), parts.path, parts.query, parts.fragment))

class CameraWorker:
    def __init__(self, camera, detector, detector_lock):
        self.camera = camera
        self.detector = detector
        self.detector_lock = detector_lock
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.frame = None
        self.sequence = 0
        self.connection = 0
        self.reader = threading.Thread(target=self.read, name=f'reader-{camera["id"]}', daemon=True)
        self.processor = threading.Thread(target=self.process, name=f'camera-{camera["id"]}', daemon=True)
        self.reader.start(); self.processor.start()

    def read(self):
        url = host_url(self.camera['rtsp'])
        while not self.stop.is_set():
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            if not cap.isOpened():
                logging.warning('Cannot open camera'); cap.release(); self.stop.wait(3); continue
            logging.info('Stream connected')
            with self.lock: self.connection += 1
            while not self.stop.is_set():
                ok, frame = cap.read()
                if not ok: break
                with self.lock: self.frame = frame; self.sequence += 1
            cap.release()
            with self.lock: self.frame = None
            if not self.stop.is_set(): logging.warning('Stream disconnected'); self.stop.wait(2)

    def process(self):
        ocr = ALPR(detector_model='yolo-v9-t-384-license-plate-end2end', detector_providers=['CPUExecutionProvider'], ocr_model='cct-s-v2-global-model', ocr_device='cuda', ocr_providers=['CUDAExecutionProvider','CPUExecutionProvider']).ocr
        logging.info('OCR providers: %s', ocr.ocr_model.model.get_providers())
        logging.info('Using CUDA model %s', MODEL)
        last = -1; roi = {}; roi_time = 0; metrics_start = time.monotonic(); frames = 0; detect_time = 0; ocr_time = 0
        tracker_config = YAML.load(ROOT / 'cfg/trackers/bytetrack.yaml')
        tracker_config.update(SETTINGS['tracker'])
        config = SimpleNamespace(**tracker_config)
        tracker = BYTETracker(config); tracks = {}; session = uuid.uuid4().hex; connection = 0
        while not self.stop.is_set():
            with self.lock:
                seq = self.sequence
                current_connection = self.connection
                frame = self.frame.copy() if self.frame is not None and seq != last else None
            if frame is None: self.stop.wait(.05); continue
            last = seq
            try:
                if connection != current_connection:
                    tracker = BYTETracker(config); tracks = {}; session = uuid.uuid4().hex; connection = current_connection
                if time.monotonic() - roi_time >= 10:
                    roi = json.loads(request('/api/cameras/%s/roi' % self.camera['id'])); roi_time = time.monotonic()
                h, w = frame.shape[:2]; annotated = frame.copy()
                start = time.monotonic()
                with self.detector_lock:
                    boxes = self.detector.predict(frame, imgsz=640, conf=DETECTION_CONFIDENCE, classes=[0], device=0, verbose=False)[0].boxes.cpu().numpy()
                detect_time += time.monotonic() - start
                now = time.monotonic(); tracks = {key:value for key,value in tracks.items() if now-value['seen'] < 120}
                for tracked in tracker.update(boxes, frame):
                    x1, y1, x2, y2 = map(int, tracked[:4]); track_id = int(tracked[4]); score = float(tracked[5])
                    state = tracks.setdefault(track_id, {'seen':now,'label':'Plate','ocr_at':0,'best_ocr':-1,'pending':None,'suppressed':False,'trail':deque(maxlen=45)})
                    state['seen'] = now
                    crop = frame[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
                    if not crop.size: continue
                    x, y = (x1+x2)/(2*w), (y1+y2)/(2*h)
                    inside = all(k in roi for k in ('x','y','width','height')) and roi['x'] <= x <= roi['x']+roi['width'] and roi['y'] <= y <= roi['y']+roi['height']
                    if (inside or state['label'] == 'Plate') and now-state['ocr_at'] >= 1:
                        started = time.monotonic(); text = ocr.predict(crop); ocr_time += time.monotonic()-started
                        state['ocr_at'] = now
                        if text and text.text:
                            clean = re.sub(r'[^A-Z0-9]', '', text.text.upper())
                            scores = list(text.confidence) if text.confidence is not None else []
                            valid_scores = scores[:len(clean)]
                            quality = float(np.mean(valid_scores)) if valid_scores else None
                            if 5 <= len(clean) <= 12 and quality is not None and np.isfinite(quality) and 0 <= quality <= 1:
                                if state['label'] == 'Plate': state['label'] = clean
                                if inside and not state['suppressed'] and quality > state['best_ocr']:
                                    ok, jpeg = cv2.imencode('.jpg', crop)
                                    if ok:
                                        state['label'] = clean; state['best_ocr'] = quality
                                        full_scale = min(1.0, 1280 / w)
                                        full_frame = cv2.resize(frame, None, fx=full_scale, fy=full_scale, interpolation=cv2.INTER_AREA) if full_scale < 1 else frame
                                        full_ok, full_jpeg = cv2.imencode('.jpg', full_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                                        state['pending'] = {'camera_id':self.camera['id'], 'plate':clean, 'confidence':score, 'ocr_confidence':quality, 'image':base64.b64encode(jpeg).decode(), 'full_image':base64.b64encode(full_jpeg).decode() if full_ok else None, 'event_key':f'{session}_{self.camera["id"]}_{track_id}'}
                    label = state['label']
                    center = ((x1+x2)//2, (y1+y2)//2)
                    state['trail'].append((now, center))
                    while state['trail'] and now-state['trail'][0][0] > 5: state['trail'].popleft()
                    points = np.array([position for _, position in state['trail']], dtype=np.int32)
                    if len(points) > 1: cv2.polylines(annotated, [points], False, (255,185,40), 3, cv2.LINE_AA)
                    cv2.circle(annotated, center, 4, (255,185,40), -1, cv2.LINE_AA)
                    cv2.rectangle(annotated, (x1,y1), (x2,y2), (0,220,80), 3)
                    cv2.putText(annotated, f'ID {track_id} {label} {score:.2f}', (max(0,x1),max(25,y1-8)), cv2.FONT_HERSHEY_SIMPLEX, .8, (0,220,80), 2, cv2.LINE_AA)
                    if inside and state['pending']:
                        result = json.loads(request('/api/events', state['pending']))
                        if result.get('reason') == 'plate_recent': state['suppressed'] = True
                        state['pending'] = None
                scale = min(1.0, 960 / w)
                if scale < 1: annotated = cv2.resize(annotated, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                ok, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok: request('/api/cameras/%s/annotated' % self.camera['id'], {'image':base64.b64encode(jpeg).decode()})
                frames += 1
                elapsed = time.monotonic() - metrics_start
                if elapsed >= 15:
                    logging.info('fps=%.2f detection_wait_ms=%.0f ocr_ms_per_frame=%.0f', frames/elapsed, 1000*detect_time/frames, 1000*ocr_time/frames)
                    metrics_start = time.monotonic(); frames = 0; detect_time = 0; ocr_time = 0
            except Exception: logging.exception('Error processing camera'); self.stop.wait(2)

def run():
    global SETTINGS, DETECTION_CONFIDENCE
    if not torch.cuda.is_available(): raise RuntimeError('CUDA is unavailable; install CUDA-enabled PyTorch and verify the NVIDIA driver')
    logging.info('CUDA device: %s', torch.cuda.get_device_name(0))
    detector = YOLO(str(MODEL)); detector_lock = threading.Lock()
    workers = {}
    revision = 0; reload_error = None; failed_revision = None
    try:
        while True:
            try:
                status = json.loads(request('/api/ai/heartbeat', {'revision': revision, 'error': reload_error}))
                enabled = status['enabled']
                if status['revision'] != revision and status['revision'] != failed_revision:
                    try:
                        new_settings = load_settings()
                        for worker in workers.values(): worker.stop.set()
                        for worker in workers.values(): worker.reader.join(8); worker.processor.join(15)
                        workers.clear()
                        SETTINGS = new_settings; DETECTION_CONFIDENCE = SETTINGS['detection_confidence']
                        revision = status['revision']; reload_error = None; failed_revision = None; logging.info('AI settings reloaded, revision %s', revision)
                    except Exception as exc:
                        reload_error = str(exc); failed_revision = status['revision']; logging.exception('Cannot reload AI settings')
                elif status['revision'] == revision:
                    reload_error = None
                cameras = {c['id']:c for c in json.loads(request('/api/cameras')) if c['enabled']} if enabled else {}
                for camera_id, worker in list(workers.items()):
                    if camera_id not in cameras or cameras[camera_id]['rtsp'] != worker.camera['rtsp'] or not worker.processor.is_alive() or not worker.reader.is_alive():
                        worker.stop.set(); worker.reader.join(8); worker.processor.join(15); del workers[camera_id]
                for camera_id, camera in cameras.items():
                    if camera_id not in workers: workers[camera_id] = CameraWorker(camera, detector, detector_lock)
            except Exception: logging.exception('Cannot synchronize cameras')
            time.sleep(2)
    finally:
        for worker in workers.values(): worker.stop.set()

if __name__ == '__main__': run()
