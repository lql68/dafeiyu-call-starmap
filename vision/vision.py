r"""鲸鱼娘的眼睛和耳朵 —— 常驻双流采集

视频: HD webcam 640x480@15 -> rawvideo bgr24
音频: 麦克风阵列 16k -> s16le mono

产出 state-vision.json（HUD / 大脑直接读）:
  video: fps / brightness / motion / alive / frames
  audio: rms / peak / floor / alive
  speaking: 自适应底噪判定
  presence: 画面有动静

用法:
  D:\sakana-py\python.exe vision.py                 # 常驻
  D:\sakana-py\python.exe vision.py --once 15 --snap  # 测通
"""
import sys, os, json, time, subprocess, threading, argparse, io, wave, urllib.request
from collections import deque

SP = r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages"
MP = r"D:\sakana-py\mp"          # mediapipe 装在这儿（uv 环境不让装，用 --target）
if MP not in sys.path and os.path.isdir(MP):
    sys.path.insert(0, MP)
if SP not in sys.path and os.path.isdir(SP):
    sys.path.insert(0, SP)
import numpy as np
FT = None
try:
    from face import FaceTracker
except Exception as _e:
    FaceTracker = None
    _FACE_ERR = repr(_e)

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = r"D:\deepseek harness\ai-live\state-vision.json"
SNAP = os.path.join(HERE, "snapshot.jpg")
LIVE = os.path.join(HERE, "latest.jpg")   # 每帧覆盖，给 /cam.mjpg 推流用
LOG = os.path.join(HERE, "vision.log")
YIELD = os.path.join(HERE, "yield.lock")   # 其他进程要独占摄像头时写这个文件，本脚本会主动让位

FFMPEG = r"C:\Users\liu\bin\ffmpeg.exe"
VIDEO_DEV = "video=HD webcam"

# 摄像头可以在网页上换：写一行设备名到这里，采到下一帧就重连
CAM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cam.txt")


def cur_dev():
    """当前要用的摄像头；cam.txt 为空或读不到就退回默认"""
    try:
        with open(CAM_FILE, encoding="utf-8") as f:
            n = f.read().strip()
        if n:
            return n if n.startswith("video=") else "video=" + n
    except Exception:
        pass
    return VIDEO_DEV
AUDIO_DEV = "audio=麦克风阵列 (Senary Audio)"
W, H, FPS = 640, 480, 24   # 15 -> 24：单帧年龄从 67ms 降到 42ms，CPU 还扛得住
FSZ = W * H * 3
ASZ = 16000 * 2 // 10          # 100ms 音频块

SAY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "say.txt")
ASR_URL = "http://127.0.0.1:8770/api/hear"
ASR_ON = True                  # --no-asr 关掉
SIL_BLOCKS = 6                 # 静 600ms 判定一句说完
MIN_BLOCKS = 8                 # 少于 0.8s 当噪声丢掉
MAX_BLOCKS = 150               # 超过 15s 强制切
PREROLL = 3                    # 带上说话前 300ms，避免吃字


def log(msg):
    line = time.strftime("%H:%M:%S") + " " + msg
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.video = {"alive": False, "fps": 0.0, "frames": 0,
                      "brightness": 0.0, "motion": 0.0}
        self.audio = {"alive": False, "rms": 0.0, "peak": 0.0,
                      "floor": 0.003, "base": 0.006, "blocks": 0}
        self.heard = {"text": "", "ts": 0.0, "dur": 0.0, "seq": 0}
        self.face = {"present": False}
        self.want_snap = threading.Event()
        self.stop = threading.Event()


def post_asr(S, chunks, dur):
    """把一句话丢给 voice_server 的 /api/hear，回来的文字写进 shared"""
    pcm = np.concatenate(chunks)
    pcm16 = np.clip(pcm * 32768.0, -32768, 32767).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(pcm16.tobytes())
    data = bio.getvalue()
    try:
        req = urllib.request.Request(ASR_URL, data=data,
                                     headers={"Content-Type": "audio/wav"})
        with urllib.request.urlopen(req, timeout=40) as r:
            j = json.loads(r.read().decode("utf-8"))
        txt = (j.get("text") or "").strip()
        if txt:                       # 空结果（噪声/幻觉）不许覆盖上一句，也不推进 seq
            with S.lock:
                S.heard["seq"] += 1
                S.heard.update(text=txt, ts=round(time.time(), 3), dur=round(dur, 2))
            log(f"[asr] {dur:.1f}s -> {txt!r} ({j.get('ms')}ms)")
        else:
            log(f"[asr] {dur:.1f}s -> 空（丢掉）")
    except Exception as e:
        log(f"[asr] 失败 {e!r}")


def video_loop(S):
    global FT
    prev = None
    while not S.stop.is_set():
        if os.path.exists(YIELD):
            time.sleep(0.8)
            continue
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error",
               # 低延迟三件套：nobuffer 不让解复用攒帧、low_delay 关掉内部
               # 重排序、probesize/analyzeduration 压到最小跳过探测。
               "-fflags", "nobuffer", "-flags", "low_delay",
               "-probesize", "32", "-analyzeduration", "0",
               "-f", "dshow", "-rtbufsize", "8M",
               "-video_size", f"{W}x{H}", "-framerate", str(FPS),
               "-i", cur_dev(),
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=FSZ * 2)
        except Exception as e:
            log(f"[video] 起不来: {e}")
            time.sleep(2)
            continue

        _dev = cur_dev()
        log(f"[video] 已启动 pid={p.pid} dev={_dev}")
        stamps = deque(maxlen=24)       # 滑动窗口算真 fps
        fno = 0
        while not S.stop.is_set():
            if os.path.exists(YIELD):
                log("[video] 让位：外部进程要用摄像头")
                try: p.kill()
                except Exception: pass
                break
            buf = p.stdout.read(FSZ)
            if len(buf) < FSZ:
                log("[video] 流断了，重连")
                break
            frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            gray = frame[:, :, 1].astype(np.float32)
            bright = float(gray.mean() / 255.0)
            motion = float(np.abs(gray - prev).mean() / 255.0) if prev is not None else 0.0
            prev = gray
            fno += 1
            if fno % 120 == 0 and cur_dev() != _dev:
                log(f"[video] 设备切换 {_dev} -> {cur_dev()}")
                try: p.kill()
                except Exception: pass
                break
            now = time.perf_counter()
            stamps.append(now)
            fps = (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) > 2 else 0.0
            with S.lock:
                S.video.update(alive=True, frames=S.video["frames"] + 1,
                               brightness=round(bright, 4), motion=round(motion, 4),
                               fps=round(fps, 1))
            # 每 2 帧写一张 latest.jpg（约 7.5fps），写临时文件再改名，避免读到半张图
            if True:   # 每帧都写（原来每 2 帧一次）：15fps 下省掉约 33ms
                try:
                    import cv2
                    ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 68])
                    if ok:
                        tmp = LIVE + ".tmp"
                        with open(tmp, "wb") as fh:
                            fh.write(enc.tobytes())
                        os.replace(tmp, LIVE)
                except Exception as e:
                    if fno % 300 == 0:
                        log(f"[video] latest.jpg 失败 {e}")
            # 人脸：每 3 帧一次（单帧 40ms，15fps 下约 20% 单核）
            if fno % 3 == 0:
                try:
                    if FT is None:
                        FT = FaceTracker()
                        log('[face] 初始化 ' + ('OK' if FT.ok else '不可用: ' + str(FT.err)))
                    if FT.ok:
                        fr = FT.process(frame, int(now * 1000))
                        with S.lock:
                            S.face = fr
                except Exception as e:
                    if fno % 300 == 0:
                        log(f'[face] 失败 {e}')
            if S.want_snap.is_set():
                S.want_snap.clear()
                try:
                    import cv2
                    cv2.imwrite(SNAP, frame)
                    log(f"[video] 快照 -> {SNAP}")
                except Exception as e:
                    log(f"[video] 快照失败 {e}")
        p.kill()
        with S.lock:
            S.video["alive"] = False
        time.sleep(1.0)


def audio_loop(S):
    floor = 0.003
    while not S.stop.is_set():
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error",
               "-f", "dshow", "-audio_buffer_size", "50",
               "-i", AUDIO_DEV,
               "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=ASZ * 4)
        except Exception as e:
            log(f"[audio] 起不来: {e}")
            time.sleep(2)
            continue

        log(f"[audio] 已启动 pid={p.pid}")
        hist = deque(maxlen=25)          # 2.5 秒内的 rms 历史，算中位数基线
        ring = deque(maxlen=20)          # 说话前的预录，避免吃字
        ut, sil, collecting = [], 0, False
        while not S.stop.is_set():
            buf = p.stdout.read(ASZ)
            if len(buf) < ASZ:
                log("[audio] 流断了，重连")
                break
            a = np.frombuffer(buf, np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt((a * a).mean()))
            peak = float(np.abs(a).max())
            hist.append(rms)
            base = float(np.median(hist)) if len(hist) >= 8 else max(rms, 0.006)
            # 底噪跟踪：快速下降、极慢上升
            floor = rms if rms < floor else floor * 0.9995 + rms * 0.0005
            floor = max(0.0008, min(floor, 0.06))
            with S.lock:
                S.audio.update(alive=True, rms=round(rms, 4), peak=round(peak, 3),
                               floor=round(floor, 4), base=round(base, 4),
                               blocks=S.audio["blocks"] + 1)

            # ---------- 断句：一句话说完就丢给本地 ASR ----------
            if ASR_ON:
                loud = rms > max(0.022, base * 2.6) and peak > 0.05
                if loud:
                    if not collecting:
                        collecting, sil = True, 0
                        ut = list(ring)[-PREROLL:]
                    ut.append(a)
                elif collecting:
                    sil += 1
                    ut.append(a)
                    if sil >= SIL_BLOCKS:      # 静够久了，收尾
                        keep = ut[: len(ut) - max(1, sil - 2)]   # 末尾留一点点尾音
                        n = len(keep)
                        # 能量闸：整段平均要真的像人说话，窗声/风扇不许过
                        loud_enough = False
                        if n >= MIN_BLOCKS:
                            pcm = np.concatenate(keep)
                            loud_enough = (float(np.sqrt((pcm * pcm).mean()))
                                           > max(0.030, base * 2.2))
                        if loud_enough:
                            threading.Thread(target=post_asr, args=(S, keep, n * 0.1),
                                             daemon=True).start()
                        ut, sil, collecting = [], 0, False
                else:
                    ring.append(a)
                if collecting and len(ut) >= MAX_BLOCKS:          # 说太久了强制切
                    threading.Thread(target=post_asr, args=(S, ut, len(ut) * 0.1),
                                     daemon=True).start()
                    ut, sil, collecting = [], 0, False
        p.kill()
        with S.lock:
            S.audio["alive"] = False
        time.sleep(1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", type=float, default=0, help="跑 N 秒后退出")
    ap.add_argument("--snap", action="store_true", help="退出前存快照")
    ap.add_argument("--snap-every", type=float, default=0, help="常驻时每 N 秒存快照")
    ap.add_argument("--no-asr", action="store_true", help="不把麦克风送去识别")
    a = ap.parse_args()

    global ASR_ON
    ASR_ON = not a.no_asr

    S = Shared()
    log("=" * 56)
    log(f"vision 启动  python={sys.executable}")
    threading.Thread(target=video_loop, args=(S,), daemon=True).start()
    threading.Thread(target=audio_loop, args=(S,), daemon=True).start()

    t_start = time.perf_counter()
    last_tick = 0.0
    last_snap = t_start
    say_mtime = 0.0
    try:
        while True:
            time.sleep(0.4)
            # say.txt 手动注入：不想说话、或想测她接话时，把话写进这个文件
            try:
                _m = os.path.getmtime(SAY_FILE)
            except OSError:
                _m = 0.0
            if _m and _m != say_mtime:
                say_mtime = _m
                try:
                    with open(SAY_FILE, encoding="utf-8") as _f:
                        _t = _f.read().strip()
                except OSError:
                    _t = ""
                if _t:
                    with S.lock:
                        S.heard["seq"] += 1
                        S.heard.update(text=_t, ts=round(time.time(), 3), dur=0.0)
                    log(f"[say] 手动注入 -> {_t}")
            with S.lock:
                v = dict(S.video)
                au = dict(S.audio)
                heard = dict(S.heard)
                fc = dict(S.face)
            speaking = bool(au["rms"] > max(0.010, au.get("base", 0.006) * 2.2)
                            and au["peak"] > 0.02)
            presence = v["motion"] > 0.004
            payload = {
                "ts": round(time.time(), 3),
                "uptime": round(time.perf_counter() - t_start, 1),
                "video": v, "audio": au,
                "speaking": speaking, "presence": presence,
                "heard": heard,
                "face": fc,
                "device": {"video": VIDEO_DEV, "audio": AUDIO_DEV},
            }
            try:
                tmp = STATE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                for _i in range(5):          # 有别的进程正好在读这个文件时 replace 会 WinError 5，重试几次
                    try:
                        os.replace(tmp, STATE)
                        break
                    except Exception:
                        if _i == 4:
                            raise
                        time.sleep(0.03)
            except Exception as e:
                log(f"写 state 失败: {e}")

            if time.perf_counter() - last_tick >= 1.0:
                last_tick = time.perf_counter()
                log(f"V {'OK' if v['alive'] else '--'} {v['fps']:>5.1f}fps "
                    f"亮{v['brightness']:.2f} 动{v['motion']:.4f} | "
                    f"A {'OK' if au['alive'] else '--'} rms{au['rms']:.3f} "
                    f"floor{au['floor']:.3f} {'说话' if speaking else '静'}")

            if a.snap_every > 0 and time.perf_counter() - last_snap >= a.snap_every:
                last_snap = time.perf_counter()
                S.want_snap.set()

            if a.once and time.perf_counter() - t_start > a.once:
                if a.snap:
                    S.want_snap.set()
                    time.sleep(1.2)
                break
    except KeyboardInterrupt:
        pass
    finally:
        S.stop.set()
        log("vision 退出")
        try:
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump({"alive": False, "ts": time.time()}, f)
        except Exception:
            pass


if __name__ == "__main__":
    main()