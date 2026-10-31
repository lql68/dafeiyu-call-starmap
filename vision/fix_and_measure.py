r"""修掉抠图残留（只保留最大连通域）+ 标定关键部位坐标"""
import sys, os, json
SP = r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages"
if SP not in sys.path:
    sys.path.insert(0, SP)
import cv2
import numpy as np

OUT = r"D:\deepseek harness\ai-live\chibi"
p = os.path.join(OUT, "chibi.png")
img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
h, w = img.shape[:2]
alpha = img[:, :, 3]

# ---- 最大连通域 ----
n, lab, stats, _ = cv2.connectedComponentsWithStats((alpha > 8).astype(np.uint8), 8)
if n > 1:
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = (lab == biggest).astype(np.uint8) * 255
    dropped = int((alpha > 8).sum() - keep.sum() / 255)
    alpha = cv2.GaussianBlur(keep, (3, 3), 0.6)
    img[:, :, 3] = alpha
    cv2.imwrite(p, img)
    print(f"连通域 {n-1} 块，保留最大块，丢弃 {dropped} px")
else:
    print("单一连通域，无需修")

ys, xs = np.where(alpha > 8)
bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
print(f"新 bbox x[{bx0},{bx1}] y[{by0},{by1}]  {bx1-bx0+1}x{by1-by0+1}")

# ---- 标定：按比例给候选点，画十字验证 ----
pts = {
    "ahoge_tip":   (0.500, 0.030),
    "head_top":    (0.500, 0.100),
    "eye_l":       (0.355, 0.432),
    "eye_r":       (0.567, 0.432),
    "mouth":       (0.461, 0.532),
    "chin":        (0.461, 0.600),
    "neck":        (0.461, 0.630),
    "shoulder":    (0.461, 0.680),
    "apron":       (0.461, 0.800),
    "feet":        (0.461, 0.965),
    "tail_root":   (0.800, 0.700),
    "tail_tip":    (0.960, 0.860),
}
dbg = img.copy()
for name, (rx, ry) in pts.items():
    x, y = int(rx * w), int(ry * h)
    cv2.drawMarker(dbg, (x, y), (0, 0, 255, 255), cv2.MARKER_CROSS, 18, 2)
    cv2.putText(dbg, name, (x + 10, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.34,
                (0, 0, 255, 255), 1, cv2.LINE_AA)
# 画九宫格参考线
for i in range(1, 10):
    cv2.line(dbg, (0, int(h * i / 10)), (w, int(h * i / 10)), (0, 200, 255, 90), 1)
    cv2.line(dbg, (int(w * i / 10), 0), (int(w * i / 10), h), (0, 200, 255, 90), 1)
cv2.imwrite(os.path.join(OUT, "debug_points.png"), dbg)
print("标定图 ->", os.path.join(OUT, "debug_points.png"))

# ---- 顺便把眼睛/嘴区域单独裁出来看（做眨眼/口型要用）----
def crop_region(name, cx, cy, rw, rh):
    x0 = max(0, int((cx - rw / 2) * w)); x1 = min(w, int((cx + rw / 2) * w))
    y0 = max(0, int((cy - rh / 2) * h)); y1 = min(h, int((cy + rh / 2) * h))
    cv2.imwrite(os.path.join(OUT, f"zone_{name}.png"), img[y0:y1, x0:x1])
    print(f"  {name}: [{x0},{y0}]-[{x1},{y1}]")

crop_region("face", 0.461, 0.470, 0.42, 0.30)
crop_region("tail", 0.860, 0.780, 0.28, 0.28)

meta = {"canvas": {"w": int(w), "h": int(h)},
        "bbox": [int(bx0), int(by0), int(bx1), int(by1)],
        "points": {k: {"x": round(v[0], 4), "y": round(v[1], 4)} for k, v in pts.items()}}
with open(os.path.join(OUT, "chibi_meta.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print("meta 已更新")