# -*- coding: utf-8 -*-
"""用 MediaPipe FaceLandmarker（Tasks API）读人脸状态。纯 CPU，不占显存。

mediapipe 1.2 已经没有 mp.solutions 了，只能走 tasks：
    mediapipe.tasks.python.vision.FaceLandmarker
模型文件：vision/models/face_landmarker.task（3.6 MB）

输出字段：
  present, yaw/pitch/roll, look, eyes_open, blink, mouth_open, smile,
  gaze_x/gaze_y, fx, dist, emo，以及 blendshapes 里的关键几项
"""
import math
import os

import numpy as np

MODEL = r"D:\deepseek harness\ai-live\vision\models\face_landmarker.task"

MP_OK = False
_ERR = ""
try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision as mpv
    MP_OK = True
except Exception as e:  # noqa: BLE001
    _ERR = repr(e)

# FaceMesh 关键点（478 点含虹膜）
L_EYE = (33, 133, 159, 145)
R_EYE = (362, 263, 386, 374)
MOUTH = (61, 291, 13, 14)
NOSE, CHIN, FOREHEAD = 1, 152, 10
L_IRIS, R_IRIS = 468, 473

_MODEL_3D = np.array([
    (0.0, 0.0, 0.0),
    (0.0, -63.6, -12.5),
    (-43.3, 32.7, -26.0),
    (43.3, 32.7, -26.0),
    (-28.9, -28.9, -24.1),
    (28.9, -28.9, -24.1),
], dtype=np.float64)

# blendshape 名字 → 我们要的短名
_BS = {
    "eyeBlinkLeft": "blink_l", "eyeBlinkRight": "blink_r",
    "jawOpen": "jaw", "mouthSmileLeft": "smile_l", "mouthSmileRight": "smile_r",
    "eyeLookUpLeft": "lookup", "eyeLookDownLeft": "lookdown",
    "eyeLookInLeft": "lookin", "eyeLookOutLeft": "lookout",
    "browInnerUp": "brow", "mouthPucker": "pucker",
}


def _ema(old, new, a):
    return new if old is None else old + (new - old) * a


class FaceTracker:
    def __init__(self):
        self.ok = MP_OK and os.path.exists(MODEL)
        self.err = _ERR if not MP_OK else ("" if os.path.exists(MODEL) else "模型文件不存在")
        self.lm = None
        self._s = {}
        self._prev_blink = False
        if not self.ok:
            return
        opts = mpv.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL),
            running_mode=mpv.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=False,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.lm = mpv.FaceLandmarker.create_from_options(opts)
        self._t0 = 0

    def close(self):
        if self.lm is not None:
            try:
                self.lm.close()
            except Exception:  # noqa: BLE001
                pass

    def process(self, frame_bgr, ts_ms=None):
        if not self.ok:
            return {"present": False, "reason": self.err or "未就绪"}
        import cv2
        h, w = frame_bgr.shape[:2]
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        if ts_ms is None:
            ts_ms = int(__import__("time").time() * 1000)
        if ts_ms <= getattr(self, "_last_ts", -1):
            ts_ms = getattr(self, "_last_ts", -1) + 1
        self._last_ts = ts_ms
        try:
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res = self.lm.detect_for_video(img, ts_ms)
        except Exception as e:  # noqa: BLE001
            return {"present": False, "reason": repr(e)}

        if not res.face_landmarks:
            self._s = {}
            return {"present": False}

        pts = [(p.x * w, p.y * h) for p in res.face_landmarks[0]]

        # ---- 头部姿态（用关键点几何量，比 solvePnP 稳，也不会翻 180 度） ----
        eye_l, eye_r = np.array(pts[L_EYE[0]]), np.array(pts[R_EYE[1]])
        eye_mid = (eye_l + eye_r) / 2
        nose = np.array(pts[NOSE])
        chin = np.array(pts[CHIN])
        face_w = max(math.dist(pts[234], pts[454]), 1e-6)      # 左右脸颊
        roll = math.degrees(math.atan2(eye_r[1] - eye_l[1], eye_r[0] - eye_l[0]))
        yaw = math.degrees(math.atan2(nose[0] - eye_mid[0], face_w * 0.5)) * 1.55
        eye_chin = max(chin[1] - eye_mid[1], 1e-6)
        ratio = (nose[1] - eye_mid[1]) / eye_chin
        pitch = (0.32 - ratio) * 120.0                          # 正 = 抬头；0.32 是正脸时鼻尖相对位置（实测 0.295）

        # ---- blendshapes（有就用，比纯几何稳） ----
        bs = {}
        try:
            if res.face_blendshapes:
                for c in res.face_blendshapes[0]:
                    n = _BS.get(c.category_name)
                    if n:
                        bs[n] = float(c.score)
        except Exception:  # noqa: BLE001
            pass

        def ear(idx):
            a, b, c, d = idx
            return math.dist(pts[c], pts[d]) / max(math.dist(pts[a], pts[b]), 1e-6)

        ear_v = (ear(L_EYE) + ear(R_EYE)) / 2
        eyes_geo = float(np.clip((ear_v - 0.10) / 0.22, 0, 1))
        eyes_open = 1.0 - (bs.get("blink_l", 0) + bs.get("blink_r", 0)) / 2 if bs else eyes_geo
        eyes_open = float(np.clip(eyes_open, 0, 1))

        mv = math.dist(pts[MOUTH[2]], pts[MOUTH[3]])
        mw = max(math.dist(pts[MOUTH[0]], pts[MOUTH[1]]), 1e-6)
        mouth_geo = float(np.clip((mv / mw - 0.08) / 0.55, 0, 1))
        mouth_open = float(np.clip(bs.get("jaw", mouth_geo), 0, 1)) if bs else mouth_geo

        smile = float(np.clip((bs.get("smile_l", 0) + bs.get("smile_r", 0)) / 2, 0, 1)) if bs else 0.0
        if not bs:
            corner_y = (pts[MOUTH[0]][1] + pts[MOUTH[1]][1]) / 2
            lip_y = (pts[MOUTH[2]][1] + pts[MOUTH[3]][1]) / 2
            smile = float(np.clip((lip_y - corner_y) / (mw * 0.22), 0, 1))

        blink = eyes_open < 0.3
        blink_evt = blink and not self._prev_blink
        self._prev_blink = blink

        # ---- 视线 ----
        gx = gy = 0.0
        try:
            def gaze(iris, eye):
                ic = np.mean([pts[i] for i in range(iris, iris + 5)], axis=0)
                lo, hi = np.array(pts[eye[0]]), np.array(pts[eye[1]])
                up, dn = np.array(pts[eye[2]]), np.array(pts[eye[3]])
                cx = (lo[0] + hi[0]) / 2
                cy = (up[1] + dn[1]) / 2
                return ((ic[0] - cx) / max(abs(hi[0] - lo[0]) / 2, 1e-6),
                        (ic[1] - cy) / max(abs(dn[1] - up[1]) / 2, 1e-6))
            a, b = gaze(L_IRIS, L_EYE), gaze(R_IRIS, R_EYE)
            gx = float(np.clip((a[0] + b[0]) / 2, -1.5, 1.5))
            gy = float(np.clip((a[1] + b[1]) / 2, -1.5, 1.5))
        except Exception:  # noqa: BLE001
            pass

        fx = float(np.mean([pts[i][0] for i in (NOSE, CHIN)]) / w)
        face_h = abs(pts[CHIN][1] - pts[FOREHEAD][1]) / h if len(pts) > FOREHEAD else 0.0

        s = self._s
        for k, v in (("yaw", yaw), ("pitch", pitch), ("roll", roll),
                     ("eyes_open", eyes_open), ("mouth_open", mouth_open),
                     ("smile", smile), ("gaze_x", gx), ("gaze_y", gy),
                     ("fx", fx), ("dist", face_h)):
            s[k] = _ema(s.get(k), v, 0.45)

        look = "正对镜头"
        if s["pitch"] > 16:
            look = "抬头"
        elif s["pitch"] < -14:
            look = "低头"
        elif abs(s["yaw"]) > 33:
            look = "转开头"
        elif abs(s["yaw"]) > 17:
            look = "侧过脸"

        if s["smile"] > 0.42 and s["eyes_open"] > 0.45:
            emo = "笑"
        elif s["mouth_open"] > 0.45:
            emo = "张嘴"
        elif s["eyes_open"] < 0.35:
            emo = "眯眼"
        elif abs(s["yaw"]) > 33:
            emo = "没在看"
        elif s["smile"] < 0.12 and s["eyes_open"] > 0.5:
            emo = "平静"
        else:
            emo = "一般"

        out = {
            "present": True,
            "yaw": round(s["yaw"], 1), "pitch": round(s["pitch"], 1), "roll": round(s["roll"], 1),
            "look": look,
            "eyes_open": round(s["eyes_open"], 3),
            "blink": bool(blink_evt),
            "mouth_open": round(s["mouth_open"], 3),
            "smile": round(s["smile"], 3),
            "gaze_x": round(s["gaze_x"], 3), "gaze_y": round(s["gaze_y"], 3),
            "fx": round(s["fx"], 3),
            "dist": round(s["dist"], 4),
            "emo": emo,
        }
        if bs:
            out["bs"] = {k: round(v, 3) for k, v in bs.items() if v > 0.05}
        return out
