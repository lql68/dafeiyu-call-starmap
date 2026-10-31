"""分区诊断：按颜色族出掩码图 + 关键行剖面，用来定 Live2D 拆层的多边形"""
import sys
sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np, cv2

SRC = r"D:\deepseek harness\ai-live\chibi\chibi_closed.png"
OUT = r"D:\deepseek harness\ai-live\live2d"

bgra = cv2.imread(SRC, cv2.IMREAD_UNCHANGED)
b, g, r, a = cv2.split(bgra)
H, W = a.shape
alpha = (a.astype(np.float32) / 255)[:, :, None]
comp = (bgra[:, :, :3].astype(np.float32) * alpha + 255.0 * (1 - alpha)).astype(np.uint8)

hsv = cv2.cvtColor(comp, cv2.COLOR_BGR2HSV)
hh, ss, vv = cv2.split(hsv)
op = a > 100

# 1) 皮肤：cream，亮度高、饱和度低、色相橙黄
skin = op & (vv > 200) & (ss < 70) & (hh < 35) & (hh > 5)
# 2) 纯白（围裙/头饰/袜子）：亮度极高 + 极低饱和
white = op & (vv > 232) & (ss < 24)
# 3) 深色描边/眼线
dark = op & (vv < 95)
# 4) 蓝（头发+衣服+尾巴）
blue = op & (hh > 95) & (hh < 135) & (ss > 45)
# 5) 粉色腮红
pink = op & (hh > 330) | (op & (hh < 8) & (ss > 40) & (vv > 200))

def paint(mask, color_bgr, base):
    o = base.copy()
    o[mask] = color_bgr
    return o

vis = comp.copy()
vis = paint(skin,  (140, 220, 255), vis)
vis = paint(white, (255, 255, 255), vis)
vis = paint(dark,  (60, 30, 30), vis)
vis = paint(blue,  (200, 120, 40), vis)
cv2.imwrite(OUT + r"\seg_colors.png", vis)

for name, m in [("skin", skin), ("white", white), ("dark", dark), ("blue", blue)]:
    cv2.imwrite(OUT + rf"\mask_{name}.png", (m * 255).astype(np.uint8))
    print(f"{name:6s} {m.sum():7d} 像素  {m.sum()/op.sum()*100:5.1f}%")

# 逐行：皮肤与蓝各自的 x 跨度（找脖子窄处、脸的范围）
print("\n逐行（每 2% 高度）：皮肤跨度 / 蓝色跨度 / 总跨度")
for i in range(50):
    y = int(H * (i * 2 + 1) / 100)
    def span(m):
        xs = np.where(m[y])[0]
        return f"{xs.min():3d}-{xs.max():3d}" if len(xs) else "  -  "
    xs = np.where(op[y])[0]
    tot = f"{xs.min():3d}-{xs.max():3d}" if len(xs) else "  -  "
    print(f"  y={y:3d} ({i*2:2d}%)  skin {span(skin)}   blue {span(blue)}   all {tot}")

# 找轮廓最窄处（脖子）
print("\n宽度剖面（找脖子）")
for y in range(300, 400, 5):
    xs = np.where(op[y])[0]
    if len(xs):
        print(f"  y={y}  宽 {xs.max()-xs.min()+1:3d}  x[{xs.min()},{xs.max()}]")
