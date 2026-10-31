r"""从三视图设定图里抠出 Q 版立绘（正视图）

白底 floodfill -> 透明；保留白围裙/白头饰内部
输出: chibi.png (透明) / chibi_meta.json (bbox + 关键点估算)
"""
import sys, os, json
SP = r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages"
if SP not in sys.path:
    sys.path.insert(0, SP)
import cv2
import numpy as np

SRC = r"C:\Users\liu\.dsh\attachments\v1\objects\9b\9b855d27023672001e7496f06d5d59e69039ad1666ec3eef7d1b769cb701bd30"
OUT = r"D:\deepseek harness\ai-live\chibi"
os.makedirs(OUT, exist_ok=True)

img = cv2.imread(SRC, cv2.IMREAD_UNCHANGED)
if img.shape[2] == 4:
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
H, W = img.shape[:2]
print("原图", W, "x", H)

# ---- 1) 粗裁上半部分左块（正视图）----
top_h = int(H * 0.575)
left_w = int(W * 0.385)
crop = img[0:top_h, 0:left_w].copy()
cv2.imwrite(os.path.join(OUT, "step1_crop.png"), crop)
print("粗裁", crop.shape[1], "x", crop.shape[0])

# ---- 2) 找前景 bbox（离白色最远的像素范围）----
g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
fg = (g < 245).astype(np.uint8)
# 去掉少量噪点
fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
ys, xs = np.where(fg > 0)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
print(f"bbox = x[{x0},{x1}] y[{y0},{y1}]  -> {x1-x0+1}x{y1-y0+1}")
body = crop[y0:y1+1, x0:x1+1]
cv2.imwrite(os.path.join(OUT, "step2_bbox.png"), body)

# ---- 3) 四角 floodfill 白底 -> 透明 ----
h, w = body.shape[:2]
mask = np.zeros((h + 2, w + 2), np.uint8)
ff = body.copy()
flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
tol = (12, 12, 12)
seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0)]
for sx, sy in seeds:
    if ff[sy, sx].mean() > 235:      # 只有真的是白底才填
        cv2.floodFill(ff, mask, (sx, sy), 0, tol, tol, flags)

bg = mask[1:-1, 1:-1]
fgmask = (bg == 0).astype(np.uint8) * 255

# 轻微收边 + 羽化，去掉白边
fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
alpha = cv2.GaussianBlur(fgmask, (3, 3), 0.6)

rgba = cv2.cvtColor(body, cv2.COLOR_BGR2BGRA)
rgba[:, :, 3] = alpha
cv2.imwrite(os.path.join(OUT, "chibi.png"), rgba)
print("抠图完成", rgba.shape)

# ---- 4) 缩放到 512 宽（HUD 够用，省显存）----
scale = 512 / rgba.shape[1]
small = cv2.resize(rgba, (512, int(rgba.shape[0] * scale)), interpolation=cv2.INTER_AREA)
cv2.imwrite(os.path.join(OUT, "chibi_512.png"), small)

# ---- 5) 估算关键点（按比例，后面做微动要用）----
OH, OW = rgba.shape[:2]
meta = {
    "source": SRC,
    "canvas": {"w": int(OW), "h": int(OH)},
    "bbox_in_crop": [int(x0), int(y0), int(x1), int(y1)],
    "ratios": {
        "head_top": 0.02, "eyes_y": 0.30, "mouth_y": 0.36,
        "chin_y": 0.42, "shoulder_y": 0.47, "waist_y": 0.68, "feet_y": 0.98,
        "eye_left_x": 0.36, "eye_right_x": 0.60, "face_center_x": 0.48,
        "tail_x": 0.84, "tail_y": 0.72,
    },
    "note": "ratios 是相对抠图后画布的估算，实际用前要对着图校一次",
}
with open(os.path.join(OUT, "chibi_meta.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print(json.dumps(meta["canvas"], ensure_ascii=False))
print("输出目录:", OUT)