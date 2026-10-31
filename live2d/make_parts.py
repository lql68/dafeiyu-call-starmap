"""为「2.5D 立绘」生成三张互补蒙版：头 / 尾 / 身
思路：不拆图、不补洞。同一张立绘叠三层，各层用蒙版裁出区域，
接缝用羽化过渡 —— 头可以转头、尾巴可以摆，身体不动。
body = 1 - head - tail（互补，保证不出现重影）
"""
import sys
sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np, cv2, os

SRC = r"D:\deepseek harness\ai-live\chibi\chibi_closed.png"
OUT = r"D:\deepseek harness\ai-live\chibi\parts"
os.makedirs(OUT, exist_ok=True)

img = cv2.imread(SRC, cv2.IMREAD_UNCHANGED)
H, W = img.shape[:2]
print("源图", W, "x", H)

def smooth_ellipse(cx, cy, rx, ry, feather):
    """返回 0..1 的椭圆权重场，feather 是羽化宽度（占 rx/ry 的比例）"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx / W - cx) / rx) ** 2 + ((yy / H - cy) / ry) ** 2)
    return np.clip((1.0 + feather - d) / feather, 0, 1)

# ---- 头：椭圆 + 底部一个平滑的下切 ----
# 中心偏上（chibi 头占到大半），下沿控制在 y≈0.50 附近，往下渐隐
head = smooth_ellipse(0.470, 0.235, 0.470, 0.285, 0.20)

yy = np.mgrid[0:H, 0:W][0].astype(np.float32) / H
# 底部软切：0.44 之前是 1，到 0.56 降到 0
bottom = np.clip((0.545 - yy) / 0.075, 0, 1)
bottom = bottom * bottom * (3 - 2 * bottom)      # smoothstep
head = head * bottom
# 顶部别切到呆毛：y<0.06 强制 1
head = np.where(yy < 0.06, 1.0, head)

# ---- 尾巴：直接读 make_tail.py 生成的贴形蒙版（没有才退回椭圆） ----
tp = os.path.join(OUT, "mask_tail.png")
if os.path.exists(tp):
    tail = (cv2.imread(tp, cv2.IMREAD_UNCHANGED)[:, :, 3].astype(np.float32) / 255.0)
    print("  尾巴蒙版：读自 mask_tail.png")
else:
    tail = smooth_ellipse(0.895, 0.775, 0.150, 0.175, 0.26)
    print("  尾巴蒙版：退回椭圆")

# ---- 身体：互补 ----
body = np.clip(1.0 - head - tail, 0, 1)

def save(name, arr):
    """存成 RGBA：RGB 全白、A = 蒙版值。
    CSS 的 mask-image 默认取 alpha 通道，灰度图存的 alpha 全是 255 = 不遮，所以必须写成 alpha。"""
    p = os.path.join(OUT, name)
    a = (arr * 255).astype(np.uint8)
    rgba = np.dstack([np.full_like(a, 255), np.full_like(a, 255), np.full_like(a, 255), a])
    cv2.imwrite(p, rgba)
    print(f"  {name:16s} 覆盖 {arr.mean()*100:5.1f}%  非零 {(arr>0.01).mean()*100:5.1f}%")

save("mask_head.png", head)
save("mask_tail.png", tail)
save("mask_body.png", body)

# ---- 诊断图：把三块区域涂色看覆盖有没有漏 ----
vis = np.full((H, W, 3), 30, np.uint8)
a = (img[:, :, 3:4].astype(np.float32) / 255)
rgb = img[:, :, :3].astype(np.float32)
base = (rgb * a + 255 * (1 - a)).astype(np.uint8)

vis = base.copy()
vis = (vis * 0.25).astype(np.uint8)
vis[:, :, 2] = (vis[:, :, 2] + head * 200).clip(0, 255)     # 头 -> 红
vis[:, :, 1] = (vis[:, :, 1] + tail * 220).clip(0, 255)     # 尾 -> 绿
vis[:, :, 0] = (vis[:, :, 0] + body * 200).clip(0, 255)     # 身 -> 蓝
cv2.imwrite(os.path.join(OUT, "zones.png"), vis)

# 覆盖率检查：三层加起来应该处处 ≈1（在不透明区内）
tot = head + tail + body
inside = img[:, :, 3] > 128
print("\n不透明区内三层之和: min %.3f  mean %.3f  max %.3f" %
      (tot[inside].min(), tot[inside].mean(), tot[inside].max()))
print("漏掉的像素(和<0.9):", int((tot[inside] < 0.9).sum()), "/", int(inside.sum()))
