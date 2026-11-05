"""Small Streamlit UI for vehicle plate detection and OCR."""

from __future__ import annotations

import cv2
import numpy as np
import onnxruntime as ort
import streamlit as st
from fast_alpr import ALPR
from PIL import Image
import os
import sys
import time
import threading
from collections import defaultdict, deque
from pathlib import Path


def configure_cuda_runtime():
    """Expose CUDA 13 DLLs installed in NVIDIA Python packages to ONNX Runtime."""
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    cuda_bin = site_packages / "nvidia" / "cu13" / "bin" / "x86_64"
    cudnn_bin = site_packages / "nvidia" / "cudnn" / "bin"
    cuda_runtime_dir = site_packages / "nvidia" / "cuda_runtime" / "bin"
    dll_dirs = [cuda_bin, cudnn_bin, cuda_runtime_dir]

    for dll_dir in dll_dirs:
        if dll_dir.is_dir():
            os.add_dll_directory(str(dll_dir))
            os.environ["PATH"] = f"{dll_dir};{os.environ.get('PATH', '')}"

    # The CUDA runtime wheel does not currently publish a Windows package, so
    # use the portable NVIDIA redistributable if present in the user cache.
    cuda_cache = Path(os.environ.get("TEMP", "")) / "cuda-cudart-13.0.48"
    for cudart in cuda_cache.glob("**/bin/x64"):
        if (cudart / "cudart64_13.dll").exists():
            os.add_dll_directory(str(cudart))
            os.environ["PATH"] = f"{cudart};{os.environ.get('PATH', '')}"

    ort.preload_dlls(directory="")


st.set_page_config(page_title="Nhận diện biển số", page_icon="🚘", layout="wide")


def start_rtsp_tracking(source: str, confidence: float, trail_seconds: float):
    """Start a reader thread that always keeps the freshest RTSP frame."""
    from boxmot import ByteTrack

    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("Không mở được RTSP. Kiểm tra URL và MediaMTX/FFmpeg.")
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    latest = {"frame": None, "lock": threading.Lock(), "stop": threading.Event()}

    def read_frames():
        while not latest["stop"].is_set():
            ok, frame = cap.read()
            if ok:
                with latest["lock"]:
                    latest["frame"] = frame
            else:
                latest["stop"].wait(0.02)

    reader = threading.Thread(target=read_frames, daemon=True)
    reader.start()
    st.session_state.rtsp_state = {
        "alpr": load_models(),
        "tracker": ByteTrack(),
        "capture": cap,
        "latest": latest,
        "reader": reader,
        "confidence": confidence,
        "trail_seconds": trail_seconds,
        "frame_count": 0,
        "last_frame_time": time.monotonic(),
        "trails": defaultdict(deque),
        "seen_ids": set(),
        "ocr_by_id": {},
        "fps": 0.0,
    }
    st.session_state.rtsp_active = True


@st.fragment(run_every=0.03)
def render_rtsp_frame():
    """Detect and display the newest frame while the reader drops stale frames."""
    state = st.session_state.get("rtsp_state")
    if not state or not st.session_state.get("rtsp_active", False):
        return
    with state["latest"]["lock"]:
        frame = state["latest"]["frame"]
        frame = frame.copy() if frame is not None else None
    if frame is None:
        st.info("Đang chờ frame RTSP...")
        return

    alpr = state["alpr"]
    detections = alpr.detector.predict(frame)
    source_detections, rows = [], []
    for detection in detections:
        box = detection.bounding_box
        score = float(detection.confidence or 0.0)
        if score >= state["confidence"]:
            rows.append([box.x1, box.y1, box.x2, box.y2, score, 0])
            source_detections.append(detection)

    detection_array = np.asarray(rows, dtype=np.float32).reshape(-1, 6)
    tracked = np.asarray(state["tracker"].update(detection_array, frame))
    annotated, active_ids = frame.copy(), set()
    state["frame_count"] += 1
    for tracked_row in tracked:
        box = tracked_row[:4]
        track_id = int(tracked_row[4])
        x1, y1, x2, y2 = map(int, box)
        center = ((x1 + x2) // 2, (y1 + y2) // 2)
        active_ids.add(track_id)
        state["seen_ids"].add(track_id)
        state["trails"][track_id].append((time.monotonic(), center))
        detection = min(source_detections, key=lambda item: abs(item.bounding_box.x1 - box[0]) +
                        abs(item.bounding_box.y1 - box[1]), default=None)
        if detection is not None and track_id not in state["ocr_by_id"]:
            crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
            if crop.size:
                text = alpr.ocr.predict(crop)
                if text and text.text:
                    state["ocr_by_id"][track_id] = text.text
        plate_text = state["ocr_by_id"].get(track_id, "Biển số")
        score = float(tracked_row[5]) if len(tracked_row) > 5 else 0.0
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (45, 210, 120), 2)
        cv2.putText(annotated, f"ID {track_id} {plate_text} {score:.2f}",
                    (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (45, 210, 120), 2)

    now = time.monotonic()
    cutoff = now - state["trail_seconds"]
    for track_id, trail in list(state["trails"].items()):
        while trail and trail[0][0] < cutoff:
            trail.popleft()
        if not trail:
            del state["trails"][track_id]
            continue
        points = [point for _, point in trail]
        for previous, current in zip(points, points[1:]):
            cv2.line(annotated, previous, current, (255, 180, 30), 2)

    state["fps"] = 1 / max(now - state["last_frame_time"], 1e-6)
    state["last_frame_time"] = now
    preview = cv2.resize(annotated, (1280, 720), interpolation=cv2.INTER_AREA)
    st.image(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB), channels="RGB", width=1280)
    st.caption(f"{frame.shape[1]}×{frame.shape[0]} · FPS xử lý: {state['fps']:.1f} · "
               f"Biển số hiện tại: {len(active_ids)} · Tổng ID: {len(state['seen_ids'])}")

@st.cache_resource(show_spinner="Loading ALPR detector and OCR models...")
def load_models():
    """Load the end-to-end detector and fast-plate-ocr-backed recognizer once."""
    configure_cuda_runtime()
    return ALPR(
        detector_model="yolo-v9-t-384-license-plate-end2end",
        detector_providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        ocr_model="cct-s-v2-global-model",
        ocr_device="cuda",
        ocr_providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )


st.title("🚘 Nhận diện biển số xe")
st.caption("Tải ảnh xe lên để phát hiện vị trí biển số và đọc ký tự bằng fast-plate-ocr.")

with st.expander("Theo dõi biển số từ camera RTSP (ByteTrack)", expanded=True):
    st.caption("Phát hiện biển số bằng chính detector FastALPR của app, rồi ByteTrack gán ID và vẽ vệt di chuyển.")
    rtsp_url = st.text_input("Địa chỉ RTSP", placeholder="rtsp://user:password@192.168.1.10:554/stream1")
    rtsp_confidence = st.slider("Ngưỡng tin cậy detector biển số", 0.1, 0.9, 0.35, 0.05)
    trail_size = st.slider("Thời gian giữ vệt tracking (giây)", 1.0, 8.0, 3.0, 0.5)
    if st.button("Bắt đầu tracking", type="primary", key="start_rtsp"):
        if not rtsp_url.strip().lower().startswith("rtsp://"):
            st.error("Địa chỉ cần bắt đầu bằng rtsp://")
        else:
            try:
                start_rtsp_tracking(rtsp_url.strip(), rtsp_confidence, trail_size)
            except Exception as exc:
                st.error(f"Tracking không chạy được: {exc}")
                st.info("Cài dependencies trong requirements-app.txt và kiểm tra kết nối RTSP.")

    if st.session_state.get("rtsp_active", False):
        if st.button("Dừng luồng", key="stop_rtsp"):
            st.session_state.rtsp_state["latest"]["stop"].set()
            st.session_state.rtsp_state["capture"].release()
            st.session_state.rtsp_state["reader"].join(timeout=1)
            st.session_state.rtsp_active = False
            st.success("Đã dừng luồng RTSP.")
        else:
            render_rtsp_frame()
st.divider()
st.subheader("Nhận diện biển số từ ảnh")

with st.sidebar:
    st.subheader("Cài đặt")
    st.markdown("**Detector:** YOLOv9-t license plate\n\n**OCR:** cct-s-v2-global-model")
    st.caption("Hai model tự tải ở lần đầu. Detector và OCR ưu tiên GPU NVIDIA, có CPU dự phòng.")

upload = st.file_uploader("Chọn ảnh xe", type=["jpg", "jpeg", "png", "webp", "bmp"])

if upload:
    image = Image.open(upload).convert("RGB")
    col_image, col_results = st.columns([1.2, 1])
    with col_image:
        st.image(image, caption=upload.name, use_container_width=True)
    with col_results:
        if st.button("Nhận diện biển số", type="primary", use_container_width=True):
            try:
                alpr = load_models()
                rgb = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                with st.spinner("Đang tìm biển số và nhận dạng ký tự..."):
                    detections = alpr.predict(rgb)

                if not detections:
                    st.warning("Không tìm thấy biển số trong ảnh.")
                else:
                    annotated = rgb.copy()
                    results = []
                    for index, detection in enumerate(detections, start=1):
                        box = detection.detection.bounding_box
                        x1, y1, x2, y2 = map(int, (box.x1, box.y1, box.x2, box.y2))
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(rgb.shape[1], x2), min(rgb.shape[0], y2)
                        crop = rgb[y1:y2, x1:x2]
                        if crop.size == 0:
                            continue
                        plate_text = detection.ocr.text if detection.ocr else "(không đọc được)"
                        score = detection.detection.confidence
                        results.append((index, plate_text, score, crop))
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (45, 210, 120), 3)
                        cv2.putText(annotated, plate_text, (x1, max(25, y1 - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (45, 210, 120), 2)

                    if not results:
                        st.warning("Không đọc được vùng biển số nào trong ảnh.")
                    else:
                        st.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
                                 caption="Ảnh đã đánh dấu vị trí biển số", use_container_width=True)
                        for index, plate_text, score, crop in results:
                            st.markdown(f"### Biển số {index}: `{plate_text}`")
                            if score is not None:
                                st.caption(f"Độ tin cậy detector: {score:.1%}")
                            st.image(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), width=280,
                                     caption=f"Vùng biển số {index}")
            except Exception as exc:  # show actionable runtime errors in the UI
                st.error(f"Không thể chạy mô hình: {exc}")
                st.info("Kiểm tra đã cài dependencies và kết nối mạng để tải model lần đầu.")
else:
    st.info("Chọn ảnh có xe và biển số rõ nét để bắt đầu.")
