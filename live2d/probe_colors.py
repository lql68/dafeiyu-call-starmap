"""探测 chibi_closed.png 的配色与主要区域，给拆层定阈值"""
import sys, json
# 用 D:\sakana-py\python.exe（py312，Medium 完整性）跑，依赖挂 AstrBot 的 site-packages
sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np, cv2

P = r"D:\deepseek harness\ai-live\chibi\chibi_closed.png"
bgra = cv2.imread(P, cv2.IMREAD_UNCHANGED)
print("shape", bgra.shape)
b, g, r, a = cv2.split(bgra)
H, W = a.shape
print("alpha>0 像素", int((a > 16).sum()), " 占比", round((a > 16).mean()*100, 1), "%")

# 透明底 -> 白底合成，避免边缘黑
rgb = bgra[:, :, :3].astype(np.float32)
alpha = (a.astype(np.float32) / 255)[:, :, None]
white = np.ones_like(rgb) * 255
comp = (rgb * alpha + white * (1 - alpha)).astype(np.uint8)

# k-means 看主色
mask = (a > 200)
px = comp[mask].reshape(-1, 3).astype(np.float32)
K = 10
crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5)
_, lab, cen = cv2.kmeans(px, K, None, crit, 6, cv2.KMEANS_PP_CENTERS)
cen = cen.astype(np.uint8)
cnt = np.bincount(lab.ravel(), minlength=K)
order = np.argsort(-cnt)
print("\n主色（BGR -> #RRGGBB, 占比）")
for i in order:
    bb, gg, rr = int(cen[i][0]), int(cen[i][1]), int(cen[i][2])
    print(f"  #{rr:02x}{gg:02x}{bb:02x}  {cnt[i]/cnt.sum()*100:5.1f}%   ({rr},{gg},{bb})")

# 关键采样点（用之前的标定：眼 34%/40.1%、52.2%/40%、嘴 42.9%/45.6%）
def at(fx, fy, tag):
    x, y = int(fx * W), int(fy * H)
    c = comp[y, x]
    print(f"  {tag:14s} ({x:3d},{y:3d}) -> #{c[2]:02x}{c[1]:02x}{c[0]:02x}  alpha={a[y,x]}")
print("\n采样点")
at(0.34, 0.401, "左眼中心"); at(0.522, 0.400, "右眼中心")
at(0.429, 0.456, "嘴"); at(0.42, 0.30, "额头")
at(0.30, 0.47, "左脸颊"); at(0.50, 0.60, "脖子/领口")
at(0.50, 0.78, "围裙"); at(0.50, 0.90, "裙摆")
at(0.15, 0.55, "左侧发"); at(0.82, 0.55, "右侧发")
at(0.50, 0.12, "头顶发"); at(0.80, 0.62, "尾巴")
at(0.22, 0.25, "头饰白")

# 行/列剖面：看清结构分层位置
print("\n每 5% 高度的不透明像素占比")
for i in range(20):
    y0, y1 = int(H*i/20), int(H*(i+1)/20)
    seg = (a[y0:y1] > 16)
    xs = np.where(seg.any(axis=0))[0]
    rng = f"x[{xs.min():3d},{xs.max():3d}]" if len(xs) else "x[ - ]"
    print(f"  y {i*5:2d}-{i*5+5:2d}%  {seg.mean()*100:5.1f}%  {rng}")
