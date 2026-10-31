#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""摄像头低延迟实验台（demo 用，不加载 TTS，零显存）

为什么单独写一个：正式链路是 vision.py 写 latest.jpg → voice_server 轮询文件推流，
那里有三处固定延迟（每 2 帧才写一次、50ms 轮询、写盘+改名）。要对比就得能单独
调这些机制，而 voice_server 一启动要 50 秒 + 5GB 显存，不适合反复试。

关键约束：**摄像头设备只能被一个进程打开**，所以这里只跑一路 ffmpeg（30fps +
nobuffer/low_delay），同一路原始帧分发给两种消费者，差别只在搬运机制：

  old  每 2 帧才「落一次」（复刻 vision.py 的 every=2），消费者 50ms 轮询取最新
  new  每帧都发，消费者用条件变量等 —— 零轮询、零排队

延迟不是编出来的，是每帧头上带的采集时刻，页面自己算「采集 → 我看到」。

跑法（必须占住摄像头，先停 vision.py）：
  D:\\sakana-py\\python.exe cam_server.py --port 8788
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import threading
import time

sys.path.insert(0, r"D:/deepseek harness/astrbot-lab/AstrBot/.venv/Lib/site-packages")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from urllib.parse import urlparse, parse_qs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = r"C:\Users\liu\bin\ffmpeg.exe"
DEV = "video=HD webcam"
W, H = 640, 480
MAGIC = b"JPEG"
CAP_FPS = 30          # 采集帧率（两种模式共用这一路）
LOWDELAY = True


class Hub:
    """只保留最新一帧；new 模式用条件变量等，old 模式故意用轮询。"""

    def __init__(self):
        self.cond = threading.Condition()
        self.jpeg = None
        self.ts = 0.0
        self.seq = 0
        self.fps = 0.0
        self.sent = 0

    def put(self, jpeg, ts):
        with self.cond:
            self.jpeg = jpeg
            self.ts = ts
            self.seq += 1
            self.cond.notify_all()

    def wait_newer(self, last_seq, timeout=2.0):
        with self.cond:
            if self.seq == last_seq:
                self.cond.wait(timeout)
            return (self.jpeg, self.ts, self.seq)

    def latest(self):
        with self.cond:
            return (self.jpeg, self.ts, self.seq)


HUBS = {"old": Hub(), "new": Hub()}
PROC = {"p": None}
STATS = {"fps": 0.0, "frames": 0}


def start_cam():
    if PROC["p"] and PROC["p"].poll() is None:
        return
    args = [FFMPEG, "-hide_banner", "-loglevel", "error"]
    if LOWDELAY:
        args += ["-fflags", "nobuffer", "-flags", "low_delay",
                 "-probesize", "32", "-analyzeduration", "0"]
    args += ["-f", "dshow", "-rtbufsize", "8M",
             "-video_size", "%dx%d" % (W, H), "-framerate", str(CAP_FPS),
             "-i", DEV, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, bufsize=W * H * 3)
    PROC["p"] = p
    threading.Thread(target=_reader, args=(p,), daemon=True).start()
    print("[cam] 采集启动 fps=%d lowdelay=%s" % (CAP_FPS, LOWDELAY), flush=True)


def _reader(p):
    size = W * H * 3
    n = 0
    t0 = time.time()
    try:
        while True:
            raw = p.stdout.read(size)
            if not raw or len(raw) < size:
                break
            n += 1
            ts = time.time() * 1000.0            # 采集时刻
            frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3)

            # new：每帧都发，质量 60
            ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            if ok:
                HUBS["new"].put(enc.tobytes(), ts)

            # old：每 2 帧才「落一次」，质量 68（复刻 vision.py 的做法）
            if not (n % 2):
                ok2, enc2 = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 68])
                if ok2:
                    HUBS["old"].put(enc2.tobytes(), ts)

            el = time.time() - t0
            if el >= 1.0:
                STATS["fps"] = round(n / el, 1)
                STATS["frames"] = n
                n = 0
                t0 = time.time()
                for h in HUBS.values():
                    h.fps = STATS["fps"]
    except Exception as e:
        print("[cam] 读取异常 %r" % (e,), flush=True)
    finally:
        try:
            p.kill()
        except Exception:
            pass


class H2(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        mode = (q.get("mode", ["new"])[0] or "new").lower()
        if mode not in HUBS:
            mode = "new"

        if u.path in ("/", "/cam_lag.html"):
            return self._file(os.path.join(HERE, "cam_lag.html"), "text/html; charset=utf-8")
        if u.path == "/stats":
            h = HUBS[mode]
            return self._json({"mode": mode, "fps": h.fps, "seq": h.seq,
                               "sent": h.sent, "cap_fps": STATS["fps"]})
        if u.path == "/cam.mjpg":
            return self._stream(mode)
        return self._json({"error": "not found"}, 404)

    def _stream(self, mode):
        start_cam()
        hub = HUBS[mode]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        last = -1
        try:
            while True:
                if mode == "old":
                    # 复刻现在的做法：每 50ms 去「看一眼文件」有没有新的
                    time.sleep(0.05)
                    jpeg, ts, seq = hub.latest()
                else:
                    # 有就立刻推，没有就阻塞等 —— 零轮询
                    jpeg, ts, seq = hub.wait_newer(last)
                if jpeg is None or seq == last:
                    continue
                last = seq
                self.wfile.write(MAGIC + struct.pack("<dI", ts, len(jpeg)) + jpeg)
                self.wfile.flush()
                hub.sent += 1
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return self._json({"error": "missing"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8788)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H2)
    srv.daemon_threads = True
    print("[cam] http://127.0.0.1:%d/cam_lag.html" % a.port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if PROC["p"]:
            try:
                PROC["p"].kill()
            except Exception:
                pass


if __name__ == "__main__":
    main()
