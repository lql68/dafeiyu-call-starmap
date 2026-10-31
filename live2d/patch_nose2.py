# -*- coding: utf-8 -*-
"""把「鼻梁补丁」改成运行时自动对位：
   渲染一帧 → 从 canvas 上把那个黑色小方块找出来 → 按模型归一化坐标摆一块肤色补丁。
   preserveDrawingBuffer 打开后才能在渲染之外读像素。
"""
import io
import re

P = r"D:\deepseek harness\ai-live\live.html"
s = io.open(P, encoding="utf-8").read()

# 1) CSS：只留形状，位置交给 JS（px）
s = re.sub(
    r"\.nose-patch\{position:absolute;left:[\d.]+%;top:[\d.]+%;width:[\d.]+%;height:[\d.]+%;",
    ".nose-patch{position:absolute;left:0;top:0;width:0;height:0;",
    s, count=1)
assert ".nose-patch{position:absolute;left:0" in s, "css 替换失败"

# 2) PIXI 打开 preserveDrawingBuffer
s = s.replace("l2dApp = new PIXI.Application({view:l2dCanvas, width:w, height:h,",
              "l2dApp = new PIXI.Application({view:l2dCanvas, width:w, height:h, preserveDrawingBuffer:true,", 1)

# 3) 插入自动对位逻辑
JS = r"""
/* ── 鼻梁补丁自动对位 ────────────────────────────────────────────────
   模型自带一个黑色小图标贴在两眼之间、鼻梁偏上，pixi-live2d-display 不会读我们
   对 drawable/part opacity 的改动（逐个关掉 715 个 drawable 都没反应），所以只能盖。
   这里在渲染完成后直接从画布上把它扫出来，换算成模型归一化坐标，再每次 fit 时重投。 */
const nosePatch = document.querySelector('.nose-patch');
let patchUV = null;      // {cx, cy, w, h} 相对模型画布的归一化值

function calibratePatch(){
  if(!l2dModel || !l2dApp) return;
  const cv = l2dCanvas, W = cv.width, H = cv.height;
  if(!W || !H) return;
  const tmp = document.createElement('canvas');
  tmp.width = W; tmp.height = H;
  const ctx = tmp.getContext('2d');
  ctx.drawImage(cv, 0, 0);
  const img = ctx.getImageData(0, 0, W, H).data;
  const lum = (x, y) => {
    const i = (y * W + x) * 4;
    if(img[i + 3] < 250) return -1;
    return 0.299 * img[i] + 0.587 * img[i + 1] + 0.114 * img[i + 2];
  };
  // 只在脸中部找：一个近黑像素，四周 10px 都是亮肤色
  let hit = null;
  const x0 = Math.round(W * 0.34), x1 = Math.round(W * 0.66);
  const y0 = Math.round(H * 0.22), y1 = Math.round(H * 0.55);
  for(let y = y0; y < y1 && !hit; y += 2){
    for(let x = x0; x < x1; x += 2){
      const L = lum(x, y);
      if(L < 0 || L > 55) continue;
      const ring = [lum(x - 11, y), lum(x + 11, y), lum(x, y - 11), lum(x, y + 11)];
      if(ring.every(v => v > 165)){ hit = {x, y}; break; }
    }
  }
  if(!hit) return;
  // 取连通块范围
  let bx0 = hit.x, bx1 = hit.x, by0 = hit.y, by1 = hit.y;
  const dark = (x, y) => { const L = lum(x, y); return L >= 0 && L < 70; };
  const stack = [[hit.x, hit.y]], seen = new Set();
  while(stack.length){
    const [x, y] = stack.pop();
    const k = x + ',' + y;
    if(seen.has(k) || seen.size > 4000) continue;
    if(!dark(x, y)) continue;
    seen.add(k);
    if(x < bx0) bx0 = x; if(x > bx1) bx1 = x;
    if(y < by0) by0 = y; if(y > by1) by1 = y;
    stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
  }
  const ow = bx1 - bx0 + 1, oh = by1 - by0 + 1;
  if(ow > W * 0.10 || oh > H * 0.12 || ow < 3 || oh < 3) return;   // 不像那个小图标就放弃
  // 画布像素 → 模型归一化（画布就是模型容器铺满的 el）
  const sc = l2dModel.scale.x;
  patchUV = {
    cx: ((bx0 + bx1) / 2 - l2dModel.x) / (l2dModel.internalModel.originalWidth * sc),
    cy: ((by0 + by1) / 2 - l2dModel.y) / (l2dModel.internalModel.originalHeight * sc),
    w: ow / (l2dModel.internalModel.originalWidth * sc),
    h: oh / (l2dModel.internalModel.originalHeight * sc),
  };
  placePatch();
}

function placePatch(){
  if(!patchUV || !l2dModel || !nosePatch) return;
  const w = l2dCanvas.clientWidth, h = l2dCanvas.clientHeight;
  const sc = l2dModel.scale.x;
  const sx = l2dModel.x + patchUV.cx * l2dModel.internalModel.originalWidth * sc;
  const sy = l2dModel.y + patchUV.cy * l2dModel.internalModel.originalHeight * sc;
  const pw = patchUV.w * l2dModel.internalModel.originalWidth * sc;
  const ph = patchUV.h * l2dModel.internalModel.originalHeight * sc;
  // 画布内 px → 相对 .l2d-wrap 的 px（canvas 与 wrap 左上角对齐）
  nosePatch.style.left = (l2dCanvas.offsetLeft + sx) + 'px';
  nosePatch.style.top  = (l2dCanvas.offsetTop  + sy) + 'px';
  nosePatch.style.width  = (pw * 2.1) + 'px';
  nosePatch.style.height = (ph * 1.5) + 'px';
  nosePatch.style.opacity = '1';
}
"""

anchor = "async function initLive2D(){"
assert anchor in s, "initLive2D anchor missing"
s = s.replace(anchor, JS + "\n" + anchor, 1)

# 4) 在 ready / fit 之后调用
s = s.replace("  fitL2D();\n", "  fitL2D();\n  setTimeout(calibratePatch, 700);\n", 1)
s = s.replace("function fitL2D(){\n", "function fitL2D(){\n  placePatch();\n", 1)
s = s.replace("  window.addEventListener('resize', () => { fitL2D(); });",
              "  window.addEventListener('resize', () => { fitL2D(); });", 1)

# 补丁初始 opacity 0，等校准
s = s.replace(".nose-patch{position:absolute;left:0;top:0;width:0;height:0;",
              ".nose-patch{position:absolute;left:0;top:0;width:0;height:0;opacity:0;", 1)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("ok: calibratePatch", s.count("calibratePatch"), "placePatch", s.count("placePatch"))
