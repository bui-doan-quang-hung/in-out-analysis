# Chạy giao diện nhận diện biển số

Repo này cung cấp phần OCR cho ảnh đã được cắt biển số. Ứng dụng nhỏ `app.py` ghép detector biển số FastALPR với OCR `fast-plate-ocr` để xử lý ảnh xe đầy đủ. Cả detector và OCR ưu tiên CUDA trên GPU NVIDIA, đồng thời cho phép ONNX Runtime dùng CPU dự phòng khi một node không được CUDA hỗ trợ.

## Cài đặt (Windows)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-app.txt
```

Gói GPU cần CUDA/cuDNN tương thích với ONNX Runtime. `requirements-app.txt` cài ONNX Runtime GPU cùng cuDNN/cuBLAS 13; app tự nạp các DLL từ môi trường Python. CUDA runtime DLL được lưu trong cache local dưới `%TEMP%\cuda-cudart-13.0.48`.

Hoặc chạy `run_app.bat` sau khi cài requirements. Mở địa chỉ Streamlit hiện trong terminal (thường là http://localhost:8501), tải ảnh JPG/PNG lên rồi bấm **Nhận diện biển số**. Lần chạy đầu cần internet để tải model; các lần sau model được lưu trong cache.

## Theo dõi biển số từ camera RTSP

Mở mục **Theo dõi biển số từ camera RTSP (ByteTrack)**, nhập URL như `rtsp://user:password@192.168.1.10:554/stream1` rồi bấm **Bắt đầu tracking**. Ứng dụng dùng detector biển số FastALPR hiện có để tìm biển số trên từng khung hình, sau đó ByteTrack ghép các hộp qua thời gian và gán ID. Video hiển thị hộp biển số, ID, OCR khi có, độ tin cậy và vệt di chuyển. Bấm **Dừng luồng** để giải phóng kết nối camera.

Cài `boxmot` trong cùng môi trường Python với app để dùng tracker ByteTrack. RTSP phải truy cập được từ máy chạy Streamlit. Hiệu năng tùy tốc độ luồng, GPU và độ phân giải ảnh.