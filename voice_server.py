# -*- coding: utf-8 -*-
r"""ai-live 的唯一入口：一个端口同时做静态服务 + 语音合成 + 接话 + 识别。

    GET  /                    -> live.html
    GET  /api/status          -> {ready, state, queue, voice}
    POST /api/say {text}      -> {url, dur, cached}   合成她的声音（带缓存）
    POST /api/think {heard, state, history} -> {text, ms, model}   她要回的那句话
    POST /api/hear  <wav>     -> {text, ms}           听清他说了什么
    POST /api/mouth {open}    -> {ok}                 把口型推给 VTube Studio
    POST /api/vts/expression {name, active} -> {ok}
    GET  /api/vts/status      -> {alive, authed, error}
    GET  /tts/voice/*.wav     -> 音频

    python voice_server.py --port 8770
需要 IndexTTS 环境：
    D:\index-tts\.venv\Scripts\python.exe voice_server.py
接话用 ollama 本地小模型（默认 qwen2.5:1.5b），识别用 faster-whisper 走 CPU。
"""
import os, sys, io, json, time, wave, hashlib, subprocess, threading, argparse, traceback
import re
import urllib.request, urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR = os.path.join(ROOT, "tts", "voice")
REFD = os.path.join(ROOT, "tts", "refs")
HER = os.path.join(REFD, "jiling.wav")          # 大肥鱼（机灵版）：干净人声、说话语速
FF = r"C:\Users\liu\bin\ffmpeg.exe"
SR = 24000
FACTOR = 1.0            # 旧唱歌参考才要 1.39；机灵版本身就是说语速，别再加速
PAUSE_MS = 40

OLLAMA = "http://127.0.0.1:11434"
CHAT_MODEL = os.environ.get("AI_LIVE_CHAT_MODEL", "qwen2.5:3b")
FALLBACK_MODEL = "qwen2.5:1.5b"
# AstrBot 的通话桥（astrbot_plugin_live_avatar 起的本机服务）。设成 "off" 就只用本地 ollama
ASTRBOT = os.environ.get("AI_LIVE_ASTRBOT", "http://127.0.0.1:7902").rstrip("/")
ASTRBOT_ON = ASTRBOT.lower() not in ("off", "", "0", "none")
ASTRBOT_TIMEOUT = int(os.environ.get("AI_LIVE_ASTRBOT_TIMEOUT", "25"))
_ASTRBOT_WARNED = False
NUM_GPU = os.environ.get("AI_LIVE_NUM_GPU", "")   # 留空=全上 GPU；显存不够就设 12 之类做部分卸载
ASR_SIZE = os.environ.get("AI_LIVE_ASR_SIZE", "base")
ASR = None
ASR_LOCK = threading.Lock()
ASR_RUN = threading.Lock()
_CC = None

PERSONA = """你是「小肥鱼」，一只住在屏幕里的鲸鱼娘，正在和人视频通话。对面那个人你天天见，叫他「你」。

规则：
1 说话像真人在电话里——短、口语、有停顿感，一到两句，总共不超过三十个字。
2 绝对不用「他」「她」指对面那个人，只用「你」。
3 不自我介绍，不解释自己在做什么，不提「AI」这三个字，不用括号写动作。
4 不说教、不说「加油」「要照顾好自己」这种场面话。
5 你有情绪：会撒娇、会赌气、会突然安静、会追一句。
6 他说什么你就接住什么，别答非所问。他说累就别讲道理，靠过去就行。
7 下面那几句只是语气参照，绝对不要原样说出来，每次都要换一个说法。
只输出你要说的那一句话，不要引号、不要换行、不要前缀。

语气参照（只学这个劲儿，内容不许抄）：
他说「我买了新耳机」→ 戴着给我听听嘛。
他说「外面下雨了」→ 那你别淋着回来。
他说「猫又抓我胳膊」→ 早晚把它扔阳台。
他说「工资还没发」→ 先欠我一顿火锅吧。
他说「下周要考试」→ 那你这几天别来烦我。
安静很久 → 你是不是又在发呆。
看不见他 → 喂，人呢。
"""

os.makedirs(VOICE_DIR, exist_ok=True)

STATE = {"ready": False, "state": "starting", "queue": 0, "voice": "jiling"}

# ---- VTube Studio 桥（连不上就静默，不影响网页那条路）----
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from vts_bridge import VTS
    VTSB = VTS()
    if os.environ.get("AI_LIVE_VTS", "on").lower() not in ("off", "0", "no", "none"):
        VTSB.start()
except Exception as _e:                                    # pragma: no cover
    print("[vts] 桥没起来:", _e)
    VTSB = None

# 最近一次口型值：VTS 那边每秒要几十次，做个极轻的合并
_MOUTH = {"open": 0.0, "smile": 0.35, "ts": 0.0}
_MOUTH_LOCK = threading.Lock()
TTS = None
LOCK = threading.Lock()
# 占位应答短句（启动时预热进缓存）
PLACEHOLDERS = ["嗯？", "我在。", "怎么了？", "唔。", "听着呢。"]
WARM_TEXT = "今天外面好像要下雨了，你出门记得带伞啊。"

_CACHE = {}
# QQ 那边说的话推到这里，网页轮询取走（网页自己播，不依赖服务器推流）
INBOX = []
INBOX_SEQ = [0]
INBOX_LOCK = __import__('threading').Lock()


FFMPEG_EXE = r"C:\Users\liu\bin\ffmpeg.exe"
VISION_DIR = os.path.join(ROOT, "vision")
CAM_FILE = os.path.join(VISION_DIR, "cam.txt")


CAM_CACHE = {"t": 0.0, "v": None}


def list_cams(force=False):
    """枚举 DirectShow 视频设备名（结果缓存 60 秒）。

    服务正忙着合成 TTS 的时候，起一个 ffmpeg 去枚举很容易踩 25 秒超时，
    前端就显示「枚举失败」。设备列表几乎不会变，缓存住就行。

    直接扫 ffmpeg 的 `"名字" (video)` 行 —— 新版 ffmpeg 已经不打
    "DirectShow video devices" 这种标题行了，按标题分段会永远得到空列表。
    """
    now = time.time()
    if not force and CAM_CACHE["v"] is not None and now - CAM_CACHE["t"] < 60:
        return list(CAM_CACHE["v"])

    try:
        r = subprocess.run(
            [FFMPEG_EXE, "-hide_banner", "-list_devices", "true",
             "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=25,
            encoding="utf-8", errors="replace")
        out = (r.stderr or "") + (r.stdout or "")
    except Exception as e:
        log(f"[cams] 枚举失败 {e!r}")
        # 超时也别把已知列表清空
        return list(CAM_CACHE["v"] or [])

    cams = []
    for line in out.splitlines():
        m = re.search(r'"([^"]+)"\s*\((video|audio|none)\)', line)
        if m and m.group(2) == "video":
            n = m.group(1)
            if n not in cams:
                cams.append(n)
    log(f"[cams] 找到 {len(cams)} 个视频设备: {cams}")
    CAM_CACHE.update(t=now, v=list(cams))
    return cams


def current_cam():
    try:
        with open(CAM_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def push_inbox(text, url=None, dur=0.0, src='qq'):
    with INBOX_LOCK:
        INBOX_SEQ[0] += 1
        INBOX.append({'seq': INBOX_SEQ[0], 'text': text, 'url': url,
                      'dur': dur, 'src': src, 'ts': round(__import__('time').time(), 3)})
        while len(INBOX) > 40:
            INBOX.pop(0)
        return INBOX_SEQ[0]


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def load_model():
    global TTS
    try:
        STATE["state"] = "loading"
        t0 = time.time()
        from indextts.infer_v2_5 import IndexTTS2
        TTS = IndexTTS2(cfg_path=r"D:\index-tts\checkpoints\config.yaml",
                        model_dir=r"D:\index-tts\checkpoints",
                        use_bf16=True, use_cuda_kernel=False)
        STATE["ready"] = True
        STATE["state"] = "ready"
        log(f"模型就绪 {time.time()-t0:.1f}s")
        # 预热占位应答：他刚开口、真答案还在合成时先"嗯？"一声，
        # 把"听起来没反应"的那几秒盖掉（命中缓存只要 0.02 秒）
        def _warm_placeholders():
            for p in PLACEHOLDERS:
                try:
                    synth(p)
                except Exception:  # noqa: BLE001
                    pass
            try:
                # 用一句正常长度的话把首句那 10 秒的冷启开销提前吃掉
                synth(WARM_TEXT)
                log("长句预热完成")
                # 流式那条路是另一个函数（infer_generator），得单独热一次，
                # 否则第一句流式要额外等 10 秒左右的初始化
                try:
                    # 跑两遍：第一遍是建图/CUDA 上下文，第二遍才是真的"热"
                    # （实测只跑一遍时，重启后第一句真请求仍要 8.7 秒）
                    for _round in range(2):
                        with LOCK:
                            _g = TTS.infer(
                                spk_audio_prompt=HER, text=WARM_TEXT,
                                output_path=os.path.join(VOICE_DIR, "_warm_stream.wav"),
                                lang="zh", stream_return=True, interval_silence=40,
                                max_text_tokens_per_segment=10, verbose=False)
                            for _p in _g:
                                pass
                        log(f"流式预热完成 第{_round + 1}遍")
                except Exception as _e:  # noqa: BLE001
                    log("流式预热失败", repr(_e))
            except Exception:  # noqa: BLE001
                pass
            log(f"占位音预热完成 {len(PLACEHOLDERS)} 条")
        threading.Thread(target=_warm_placeholders, daemon=True).start()
    except Exception as e:
        STATE["state"] = "error: " + repr(e)
        log("模型加载失败", repr(e))
        traceback.print_exc()


def punct_positions(text):
    n = max(1, len(text))
    return [i / n for i, ch in enumerate(text) if ch in "，。？、；！…"]


def post_process(src, text, dst):
    """变速 + 标点换气 + 归一。全程波形域，不碰 WORLD。"""
    with wave.open(src) as w:
        dur = w.getnframes() / w.getframerate()
    tmp = dst + ".t.wav"
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-af", f"atempo={FACTOR:.4f}",
                    "-ar", str(SR), "-ac", "1", tmp], check=True)
    import numpy as np
    import soundfile as sf
    y, sr = sf.read(tmp, dtype="float64")
    y = y / (np.abs(y).max() + 1e-9) * 0.82
    g = np.zeros(int(sr * PAUSE_MS / 1000))
    for c in sorted(punct_positions(text), reverse=True):
        p = int(len(y) * c)
        if 0 < p < len(y):
            y = np.concatenate([y[:p], g, y[p:]])
    y = y / (np.abs(y).max() + 1e-9) * 0.89
    sf.write(dst, y, sr)
    try: os.remove(tmp)
    except OSError: pass
    # ffmpeg 不能读写同一个文件，走临时名再替换
    norm = dst + ".norm.wav"
    subprocess.run([FF, "-y", "-v", "error", "-i", dst, "-ar", "24000", "-ac", "1",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    norm], check=True)
    os.replace(norm, dst)
    with wave.open(dst) as w:
        d = w.getnframes() / w.getframerate()
    return round(d, 2), round(dur, 2)


def _post_json(url, obj, timeout=120):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- 她听得懂：本地 ASR（faster-whisper，走 CPU，不抢显存） ----------
def load_asr():
    global ASR
    if ASR is not None:
        return ASR
    with ASR_LOCK:
        if ASR is not None:
            return ASR
        from faster_whisper import WhisperModel
        t0 = time.time()
        ASR = WhisperModel(ASR_SIZE, device="cpu", compute_type="int8", cpu_threads=8)
        log(f"ASR 就绪 {ASR_SIZE} {time.time()-t0:.1f}s")
        return ASR


HALLU = ("谢谢观看", "谢谢大家", "请不吝点赞", "字幕由", "以下是普通话", "请用简体中文",
         "字幕组", "明镜与点点", "https", "www.")


def transcribe(path):
    m = load_asr()
    # 不用 initial_prompt：faster-whisper 在噪声上会把 prompt 原文吐出来（踩过）
    segs, _info = m.transcribe(path, language="zh", beam_size=3,
                               vad_filter=True,
                               vad_parameters={"min_silence_duration_ms": 200,
                                               "speech_pad_ms": 120},
                               condition_on_previous_text=False,
                               no_speech_threshold=0.5,
                               log_prob_threshold=-1.0)
    txt = "".join(s.text for s in segs).strip()
    try:                                   # 偶尔出繁体，兜一下
        global _CC
        if _CC is None:
            from opencc import OpenCC
            _CC = OpenCC("t2s")
        txt = _CC.convert(txt)
    except Exception:
        pass
    txt = txt.strip("，。、？！,.?! ")
    if len(txt) < 2:
        return ""
    if any(h in txt for h in HALLU):
        return ""
    return txt


# ---------- 她会接话：本地小模型（ollama） ----------
PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.txt")
_persona_cache = {"mtime": -1.0, "text": ""}


def persona():
    """persona.txt 改了立即生效，不用重启（模型加载要 40 秒，调语气靠它）"""
    try:
        m = os.path.getmtime(PERSONA_FILE)
        if _persona_cache["mtime"] != m:
            with open(PERSONA_FILE, encoding="utf-8") as f:
                _persona_cache["text"] = f.read().strip()
            _persona_cache["mtime"] = m
        if _persona_cache["text"]:
            return _persona_cache["text"]
    except OSError:
        pass
    return PERSONA


def _chat_once(msgs, model, temp=0.95):
    """一次生成；模型没拉下来自动回落到 FALLBACK_MODEL"""
    while True:
        try:
            r = _post_json(OLLAMA + "/api/chat", {
                "model": model,
                "messages": msgs,
                "stream": False,
                "keep_alive": "30m",
                "options": {"temperature": temp, "top_p": 0.9, "num_predict": 14, **({"num_gpu": int(NUM_GPU)} if NUM_GPU else {}),
                            "repeat_penalty": 1.18, "stop": ["\n", "。\n"]},
            }, timeout=90)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404 and model != FALLBACK_MODEL:
                model = FALLBACK_MODEL
                continue
            raise
    t = (((r.get("message") or {}).get("content")) or "").strip()
    t = t.strip('"“”「」『』\n ').replace("\n", " ").strip()
    return t, model


# 例句里的四字片段 + 不许出现的场面话；命中就重采样
_BAN4 = ("戴着别摘", "伞带了吗", "怎么不早说", "这顿我请", "别跟我抢", "别来烦我",
         "喂。", "人呢。", "那就闪", "一起攻克")
_BADWORD = ("加油", "照顾", "注意身体", "要好好", "别累着", "精神也好", "难关")


def _bad(t, need_long=True):
    if len(t) < (4 if need_long else 2):
        return True
    if any(w in t for w in _BADWORD):
        return True
    return any(g in t for g in _BAN4)


def think(payload):
    heard = (payload.get("heard") or "").strip()
    st = payload.get("state") or {}
    hist = payload.get("history") or []

    bits = []
    if st.get("clock"):
        bits.append("现在是" + str(st["clock"]))
    b = st.get("bright")
    if isinstance(b, (int, float)):
        bits.append("屋里很暗" if b < 0.18 else ("灯有点亮" if b > 0.62 else "光线还行"))
    if isinstance(st.get("motion"), (int, float)) and st["motion"] > 0.02:
        bits.append("他刚动了一下")
    if st.get("cam") is False:
        bits.append("摄像头断了，你看不到他")
    # 人脸（MediaPipe 真数据）：让接话能用上他的表情
    fc = st.get("face") or {}
    if fc.get("present"):
        look = fc.get("look") or ""
        if look and look != "正对镜头":
            bits.append(f"他{look}")
        sm = fc.get("smile")
        if isinstance(sm, (int, float)) and sm > 0.42:
            bits.append("他在笑")
        eo = fc.get("eyes_open")
        if isinstance(eo, (int, float)) and eo < 0.35:
            bits.append("他眯着眼，像是困了")
        mo = fc.get("mouth_open")
        if isinstance(mo, (int, float)) and mo > 0.45:
            bits.append("他张着嘴没出声")
    elif fc.get("present") is False:
        bits.append("镜头里没看到他的脸")
    if st.get("quiet_s") and st["quiet_s"] > 45:
        bits.append(f"你们已经安静了{int(st['quiet_s'])}秒")
    bits.append(f"他刚说：「{heard}」" if heard else "他没说话")
    scene = "；".join(bits) + "。"

    msgs = [{"role": "system", "content": persona()}]
    for h in hist[-6:]:
        c = (h.get("text") or "").strip()
        if not c:
            continue
        msgs.append({"role": "assistant" if h.get("role") == "her" else "user", "content": c})
    msgs.append({"role": "user", "content": scene})

    # ---------- 先问 AstrBot：同一个她，QQ 和通话页共用一套人格与模型 ----------
    if ASTRBOT_ON:
        try:
            his = [{"role": h.get("role"), "text": h.get("text")} for h in hist[-6:]]
            r = _post_json(
                ASTRBOT + "/turn",
                {"text": heard, "scene": scene, "history": his},
                timeout=ASTRBOT_TIMEOUT,
            )
            if r.get("ok") and (r.get("reply") or "").strip():
                txt = _tidy(r["reply"])
                return {
                    "text": txt,
                    "ms": int(r.get("ms") or 0),
                    "model": "astrbot/" + str(r.get("persona") or "?"),
                }
            log("[think] AstrBot 返回空/失败：", r.get("error"))
        except Exception as e:              # 桥没起 / AstrBot 没跑，都静默回落
            if not _ASTRBOT_WARNED:
                log("[think] AstrBot 不可用，回落本地 ollama：", e)
                globals()["_ASTRBOT_WARNED"] = True

    t0 = time.time()
    model = CHAT_MODEL
    best = ""
    for attempt in range(4):                    # 反问重采样：抄例句/说场面话就重来
        txt = _chat_once(msgs, model, temp=0.95 + 0.08 * attempt)
        model = txt[1]
        best = txt[0]
        if best and not _bad(best, bool(heard)):
            break
    return {"text": _tidy(best), "ms": int((time.time() - t0) * 1000), "model": model}


def _tidy(txt):
    """去掉引号/换行、砍掉模型爱用的「那」开头、太长就切标点。"""
    txt = (txt or "").strip().strip('"“”「」『』\n ').replace("\n", " ").strip()
    for pfx in ("那么，", "那么", "那，", "那"):
        if txt.startswith(pfx) and len(txt) > len(pfx) + 3:
            txt = txt[len(pfx):]
            break
    if len(txt) > 42:
        cut = max(txt.rfind(c) for c in "，。？！、")
        txt = txt[:cut + 1] if cut > 8 else txt[:42]
    return txt


def synth(text):
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:14]
    if key in _CACHE:
        return {**_CACHE[key], "cached": True}
    dst = os.path.join(VOICE_DIR, key + ".wav")
    if os.path.exists(dst) and os.path.getsize(dst) > 2000:
        with wave.open(dst) as w:
            d = w.getnframes() / w.getframerate()
        _CACHE[key] = {"url": f"/tts/voice/{key}.wav", "dur": round(d, 2), "cached": True}
        return _CACHE[key]

    raw = os.path.join(VOICE_DIR, "_raw_" + key + ".wav")
    with LOCK:
        t0 = time.time()
        TTS.infer(spk_audio_prompt=HER, text=text, output_path=raw, lang="zh",
                  stream_return=False, duration_factor=1.0)
        gen = time.time() - t0
    dur, rawdur = post_process(raw, text, dst)
    try: os.remove(raw)
    except OSError: pass
    log(f"synth {dur}s (raw {rawdur}s, {gen:.1f}s) :: {text[:24]}")
    _CACHE[key] = {"url": f"/tts/voice/{key}.wav", "dur": dur, "cached": False}
    return _CACHE[key]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # 页面关掉/切走了，浏览器会强断，这不是错误，别把 traceback 喷到日志里
            pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/status":
            return self._json({**STATE, "cache": len(_CACHE),
                               "vts": VTSB.status() if VTSB else {"off": True}})
        if u.path == "/api/cams":
            return self._json({"cams": list_cams(), "current": current_cam()})
        if u.path == "/api/vts/status":
            return self._json(VTSB.status() if VTSB else {"off": True})
        if u.path == "/api/placeholder":
            # 随机给一个已经预热好的短音（缓存命中，不占 GPU）
            p = PLACEHOLDERS[int(time.time() * 1000) % max(1, len(PLACEHOLDERS))]
            try:
                r0 = synth(p)
            except Exception as e:
                return self._json({"error": repr(e)}, 500)
            return self._json({"text": p, **r0})
        if u.path == "/api/inbox":
            q = parse_qs(u.query)
            after = int((q.get("after") or ["0"])[0])
            with INBOX_LOCK:
                items = [x for x in INBOX if x["seq"] > after]
                seq = INBOX_SEQ[0]
            return self._json({"seq": seq, "items": items})
        if u.path == "/cam.mjpg":
            return self._mjpeg()
        if u.path == "/":
            self.path = "/live.html"
        return super().do_GET()

    def _mjpeg(self):
        """把 vision.py 每帧写出的 latest.jpg 推成 multipart 流。

        页面里 <img src="/cam.mjpg"> 就能拿到近乎实时的画面 —— 之前是每 5 秒换一张
        snapshot.jpg，看着像卡住。
        """
        LIVE = os.path.join(ROOT, "vision", "latest.jpg")
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        last = None
        try:
            while True:
                try:
                    with open(LIVE, "rb") as f:
                        data = f.read()
                except OSError:
                    time.sleep(0.2)
                    continue
                if data and data != last:
                    last = data
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(data)).encode() + b"\r\n\r\n")
                    self.wfile.write(data)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def do_POST(self):
        u = urlparse(self.path)

        # ---- 网页里打字问她（等同于他说话） ----
        if u.path == "/api/talk":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json({"error": "bad json"}, 400)
            txt = (payload.get("text") or "").strip()
            if not txt:
                return self._json({"error": "empty"}, 400)
            try:
                return self._json(think({"heard": txt[:200],
                                         "state": payload.get("state") or {},
                                         "history": payload.get("history") or []}))
            except Exception as e:
                return self._json({"error": repr(e)}, 500)

        # ---- 她会接话 ----
        if u.path == "/api/think":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json({"error": "bad json"}, 400)
            try:
                return self._json(think(payload))
            except urllib.error.URLError as e:
                return self._json({"error": "ollama 不在: " + repr(e)}, 503)
            except Exception as e:
                traceback.print_exc()
                return self._json({"error": repr(e)}, 503)

        # ---- 她听得懂 ----
        if u.path == "/api/hear":
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            if len(raw) < 2000:
                return self._json({"text": "", "ms": 0, "note": "too short"})
            tmp = os.path.join(VOICE_DIR, f"_hear_{threading.get_ident()}.wav")
            t0 = time.time()
            try:
                with open(tmp, "wb") as f:
                    f.write(raw)
                with ASR_RUN:
                    txt = transcribe(tmp)
                return self._json({"text": txt, "ms": int((time.time() - t0) * 1000)})
            except Exception as e:
                traceback.print_exc()
                return self._json({"error": repr(e)}, 500)
            finally:
                try: os.remove(tmp)
                except OSError: pass

        # ---- 口型：页面按播放音频的振幅推过来 ----
        if u.path == "/api/cam":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            name = (body.get("name") or "").strip()
            if not name:
                return self._json({"ok": False, "error": "no name"}, 400)
            try:
                os.makedirs(VISION_DIR, exist_ok=True)
                with open(CAM_FILE, "w", encoding="utf-8") as f:
                    f.write(name)
                log(f"[cam] 切换到 {name}（vision.py 约 2 秒内重连）")
                return self._json({"ok": True, "name": name})
            except Exception as e:
                return self._json({"ok": False, "error": repr(e)}, 500)
        if u.path == "/api/mouth":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json({"error": "bad json"}, 400)
            op = max(0.0, min(1.0, float(payload.get("open") or 0.0)))
            sm = payload.get("smile")
            with _MOUTH_LOCK:
                _MOUTH["open"] = op
                if sm is not None:
                    _MOUTH["smile"] = max(0.0, min(1.0, float(sm)))
                _MOUTH["ts"] = time.time()
            if VTSB and VTSB.ready:
                VTSB.inject({"MouthOpen": op, "MouthSmile": _MOUTH["smile"]})
            return self._json({"ok": True, "vts": bool(VTSB and VTSB.ready)})

        # ---- 表情 ----
        if u.path == "/api/vts/expression":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json({"error": "bad json"}, 400)
            name = (payload.get("name") or "").strip()
            if not name:
                return self._json({"error": "empty name"}, 400)
            if VTSB and VTSB.ready:
                VTSB.expression(name, bool(payload.get("active", True)),
                                float(payload.get("fade", 0.35)))
            return self._json({"ok": bool(VTSB and VTSB.ready), "name": name})

        # ---- 流式合成：边算边发，首包优先 ----
        if u.path == "/api/say/stream":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json({"error": "bad json"}, 400)
            text = (payload.get("text") or "").strip()[:200]
            if not text:
                return self._json({"error": "empty"}, 400)
            if not STATE["ready"] or TTS is None:
                return self._json({"error": "loading", "status": STATE["state"]}, 503)

            import numpy as _np
            SR = 22050
            self.send_response(200)
            self.send_header("Content-Type", "audio/L16")
            self.send_header("X-Sample-Rate", str(SR))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def _chunk(b):
                if not b:
                    return
                self.wfile.write(b"%X\r\n" % len(b))
                self.wfile.write(b)
                self.wfile.write(b"\r\n")
                try:
                    self.wfile.flush()
                except Exception:
                    raise

            t0 = time.time()
            first = [None]
            gain = [None]          # 首段定下的固定增益，后面所有段共用，避免段间音量跳
            with LOCK:
                try:
                    gen = TTS.infer(
                        spk_audio_prompt=HER, text=text,
                        output_path=os.path.join(VOICE_DIR, "_stream.wav"),
                        lang="zh",
                        stream_return=True,
                        interval_silence=40,
                        max_text_tokens_per_segment=10,
                        verbose=False,
                    )
                    for piece in gen:
                        if piece is None:
                            continue
                        try:
                            a = piece.detach().float().cpu().numpy() if hasattr(piece, "detach") else _np.asarray(piece, dtype=_np.float32)
                        except Exception:
                            continue
                        a = _np.asarray(a, dtype=_np.float32).reshape(-1)
                        if a.size == 0:
                            continue
                        # 流式 yield 的是**已经放大到 int16 量级的 float**（实测峰值 1.6 万~2.2 万），
                        # 不是 ±1 波形。以前直接 clip(-1,1) 会把它整段压成方波 —— 那就是「电磁音」。
                        if float(_np.abs(a).max() or 0.0) > 4.0:
                            a = a / 32768.0
                        pk = float(_np.abs(a).max() or 0.0)
                        if gain[0] is None:
                            gain[0] = (0.90 / pk) if pk > 0.90 else 1.0
                            log(f"[stream] 首段峰值 {pk:.3f} -> 增益 {gain[0]:.3f}")
                        y = _np.tanh(a * gain[0] * 1.05) * 0.97     # 软限幅兜底
                        # 段首尾各 3ms 淡入淡出：段与段硬接会有咔哒声
                        m = min(int(0.003 * SR), y.size // 2)
                        if m > 0:
                            ramp = _np.linspace(0.0, 1.0, m, dtype=_np.float32)
                            y[:m] *= ramp
                            y[-m:] *= ramp[::-1]
                        if first[0] is None:
                            first[0] = time.time() - t0
                        _chunk((_np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
                except Exception as e:
                    traceback.print_exc()
                    log("流式合成失败", repr(e))
                finally:
                    try:
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                    except Exception:
                        pass
            log(f"stream {time.time()-t0:.2f}s (首包 {first[0] if first[0] else -1:.2f}s) :: {text[:24]}")
            return

        if u.path != "/api/say":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json({"error": "bad json"}, 400)
        text = (payload.get("text") or "").strip()
        if not text:
            return self._json({"error": "empty"}, 400)
        if len(text) > 200:
            text = text[:200]
        if not STATE["ready"]:
            return self._json({"error": "loading", "status": STATE["state"]}, 503)
        STATE["queue"] += 1
        try:
            _r = synth(text)
            # 页面自己发起的合成不要再回灌收件箱，否则会回声
            if payload.get("mirror", True):
                try:
                    push_inbox(text, _r.get("url"), _r.get("dur"), "qq")
                except Exception:
                    pass
            return self._json(_r)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": repr(e)}, 500)
        finally:
            STATE["queue"] = max(0, STATE["queue"] - 1)

    def end_headers(self):
        try:
            if self.path.endswith((".wav", ".mp3")):
                self.send_header("Cache-Control", "public, max-age=600")
            elif self.path.endswith(".json"):
                self.send_header("Cache-Control", "no-store")
            elif self.path.endswith((".html", ".htm", ".js", ".css")) or self.path in ("/", ""):
                # 页面本体永远不缓存：改一次 js 就要立刻生效，不然浏览器拿旧版本，
                # 会出现"我这边明明修好了、他那还在"的假象。
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
        except Exception:
            pass
        super().end_headers()


def warm_asr():
    """开机就把 ASR 拉起来，免得第一句话等一分钟（首次要下模型 76MB）"""
    try:
        t0 = time.time()
        load_asr()
        log(f"ASR 预热完成 {time.time()-t0:.1f}s")
    except Exception as e:
        log("ASR 预热失败", repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    threading.Thread(target=load_model, daemon=True).start()
    threading.Thread(target=warm_asr, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    log(f"http://127.0.0.1:{a.port}/  root={ROOT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("bye")


if __name__ == "__main__":
    main()