"""尾巴蒙版 v3：按颜色锁尾鳍（避免把头发切走）
采样结论：
  尾鳍 #365196/#38529d/#39519b/#4557a1  → R 45~75, G 75~100, B 140~175, R/B≈0.38
  上方头发 #71a4e5/#73a4dc              → R/B≈0.53
  裙子   #303262                        → B≈98
判据：B 高、R 低、R/B 小。
顺带生成 chibi_back.png：把尾鳍位置 inpaint 补掉，尾巴转走时不露底色。
"""
import sys
sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np, cv2, os

SRC = r"D:\deepseek harness\ai-live\chibi\chibi_closed.png"
OUT = r"D:\deepseek harness\ai-live\chibi\parts"

img = cv2.imread(SRC, cv2.IMREAD_UNCHANGED)
H, W = img.shape[:2]
b, g, r = [img[:, :, i].astype(np.int32) for i in range(3)]
alpha = img[:, :, 3]

ratio = r / np.maximum(b, 1)
cand = (
    (b > 125) & (b < 195) &
    (r > 30) & (r < 90) &
    (g > 55) & (g < 115) &
    (ratio < 0.50) &
    (alpha > 120)
).astype(np.uint8)

i = np.zeros((H, W), np.uint8)
i[int(0.635 * H):int(0.835 * H), int(0.752 * W):int(0.955 * W)] = 1
cand = cand * i

cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, 8)
if n <= 1:
    raise SystemExit("找不到尾鳍连通域")
order = np.argsort(stats[1:, cv2.CC_STAT_AREA])[::-1] + 1
region = (lab == order[0]).astype(np.uint8)
print("最大域面积", stats[order[0], cv2.CC_STAT_AREA], "前3:", [int(stats[o, cv2.CC_STAT_AREA]) for o in order[:3]])

ff = region.copy()
m2 = np.zeros((H + 2, W + 2), np.uint8)
cv2.floodFill(ff, m2, (0, 0), 1)
region = np.clip(region + (ff == 0).astype(np.uint8), 0, 1)

region = cv2.dilate(region, np.ones((3, 3), np.uint8), iterations=1)
region = region * i
soft = cv2.GaussianBlur(region.astype(np.float32), (0, 0), 2.6)
soft = np.clip(soft, 0, 1)

ys, xs = np.where(region > 0)
print("尾鳍 bbox x[%.3f,%.3f] y[%.3f,%.3f]  像素 %d" %
      (xs.min()/W, xs.max()/W, ys.min()/H, ys.max()/H, int(region.sum())))

aa = (soft * 255).astype(np.uint8)
rgba = np.dstack([np.full_like(aa, 255), np.full_like(aa, 255), np.full_like(aa, 255), aa])
cv2.imwrite(os.path.join(OUT, "mask_tail.png"), rgba)

dil = cv2.dilate(region, np.ones((3, 3), np.uint8), iterations=4)
bgr = img[:, :, :3]
back = cv2.inpaint(bgr, (dil * 255), 14, cv2.INPAINT_TELEA)
back = np.dstack([back, alpha])
cv2.imwrite(r"D:\deepseek harness\ai-live\chibi\chibi_back.png", back)

vis = img.copy()
vis[region > 0, :3] = (60, 60, 255)
cv2.imwrite(os.path.join(OUT, "zones_tail.png"), vis)
print("saved mask_tail.png + chibi_back.png")
