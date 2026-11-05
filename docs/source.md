https://github.com/ankandrew/fast-plate-ocr
https://github.com/FoundationVision/ByteTrack?utm_source=chatgpt.com

"C:\ffmpeg\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe" -re -stream_loop -1 -i "C:\Users\pc\Downloads\1.mp4" -an -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/test

rtsp://127.0.0.1:8554/test