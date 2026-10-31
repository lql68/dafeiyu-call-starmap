# -*- coding: utf-8 -*-
"""把 live.html 的立绘层换成真 Live2D（大肥鱼），保留 HUD / 摄像头 / 字幕 / 语音链路。"""
import io
import re
import sys

P = r"D:\deepseek harness\ai-live\live.html"
src = io.open(P, encoding="utf-8").read()
orig = src

# ---------------- 1) HTML：四层图 → 一个 canvas ----------------
html_new = '''    <div class="l2d-wrap" id="l2dWrap">
      <canvas id="l2dCanvas"></canvas>
      <div class="l2d-loading" id="l2dLoading">加载模型…</div>
    </div>
  </div>'''
src, n1 = re.subn(
    r'<div class="chibi-wrap" id="chibiWrap">.*?\n    </div>\n  </div>',
    html_new, src, flags=re.S)
print("HTML 替换:", n1)

# ---------------- 2) CSS：加 canvas 容器样式 ----------------
css_anchor = "  .mouth.open .cavity{opacity:1}"
css_new = css_anchor + '''

  /* ===== 真 Live2D（大肥鱼 DeepSeek-chan）===== */
  .l2d-wrap{
    position:relative;flex:1;min-height:0;height:100%;
    display:flex;align-items:flex-end;justify-content:center;
    /* 辉光/投影加在 canvas 上，模型透明背景能直接吃到 */
    filter:drop-shadow(0 18px 34px rgba(4,20,40,.85)) drop-shadow(0 0 42px rgba(47,127,212,.28));
  }
  #l2dCanvas{display:block;max-width:100%;max-height:100%}
  .l2d-loading{
    position:absolute;left:50%;bottom:12%;transform:translateX(-50%);
    font:12px/1 ui-monospace,Consolas,monospace;letter-spacing:.16em;
    color:rgba(160,210,235,.75);transition:opacity .4s;
  }
  .l2d-loading.done{opacity:0;pointer-events:none}'''
src, n2 = src.replace(css_anchor, css_new, 1), src.count(css_anchor)
print("CSS 插入:", "ok" if "l2d-wrap{" in src else "FAIL")

# ---------------- 3) JS：换掉旧立绘驱动 ----------------
js_new = '''/* ================= 真 Live2D：大肥鱼（DeepSeek-chan）=================
   原图拆分版已废弃：桌面那份是完整 moc3 模型，自带物理、眨眼、表情和 idle 动作，
   这里只负责把「她的声音振幅」和「鼠标/空闲注意力」喂成参数。
   模型署名：原画/拆分 神宫凉子 · Live2D 建模 霓虹猫_NeonNeko */
const l2dWrap = $('l2dWrap'), l2dCanvas = $('l2dCanvas'), l2dLoading = $('l2dLoading');
const L2D_URL = 'live2d/model/大肥鱼/大肥鱼.model3.json';
const FRAME_FULL = /frame=full/.test(location.search);   // 默认头肩取景，加参数看全身
const BUST = 0.46;                                        // 取景占模型总高的比例
let l2dModel = null, l2dApp = null, l2dCore = null, l2dReady = false;
let mouthP = 0, emotionNow = '', emotionUntil = 0;

async function initLive2D(){
  if(!(window.PIXI && PIXI.live2d)){ l2dLoading.textContent = 'Live2D 运行时没加载'; return; }
  try{
    const w = l2dWrap.clientWidth || 560, h = l2dWrap.clientHeight || 900;
    l2dApp = new PIXI.Application({view:l2dCanvas, width:w, height:h,
      backgroundAlpha:0, antialias:true, autoDensity:true,
      resolution:Math.min(2, window.devicePixelRatio || 1)});
    l2dModel = await PIXI.live2d.Live2DModel.from(L2D_URL, {autoInteract:false, idleMotionGroup:'Idle'});
    l2dApp.stage.addChild(l2dModel);
    l2dCore = l2dModel.internalModel.coreModel;
    l2dReady = true;
    fitL2D();
    /* 关键：必须在 coreModel.update 之前改参数，否则改的是上一帧 */
    l2dModel.internalModel.on('beforeModelUpdate', driveL2D);
    l2dModel.expression('默认体型');
    l2dLoading.classList.add('done');
  }catch(e){
    l2dLoading.textContent = '模型加载失败：' + (e && e.message ? e.message : e);
    console.error('[l2d]', e);
  }
}

function fitL2D(){
  if(!l2dReady || !l2dApp) return;
  const w = l2dWrap.clientWidth, h = l2dWrap.clientHeight;
  if(!w || !h) return;
  l2dApp.renderer.resize(w, h);
  const im = l2dModel.internalModel;
  const ow = im.originalWidth, oh = im.originalHeight;
  const frac = FRAME_FULL ? 1 : BUST;
  const s = h / (oh * frac);
  l2dModel.scale.set(s);
  l2dModel.x = (w - ow * s) / 2;
  l2dModel.y = h - oh * s;                       // 底边贴容器底
}
window.addEventListener('resize', fitL2D);
setInterval(fitL2D, 1500);

/* 每帧把「状态」写进模型参数 */
function driveL2D(){
  if(!l2dCore) return;
  const t = performance.now();
  const set = (id, v) => { try{ l2dCore.setParameterValueById(id, v); }catch(e){} };
  set('ParamMouthOpenY', mouthP);
  set('ParamMouthForm', 1 - mouthP * 0.6);       // 张嘴时嘴角收一点，像在说话
  set('ParamAngleX', poseX * 26 + Math.sin(t / 2100) * 3);
  set('ParamAngleY', -poseY * 18 + Math.sin(t / 1700) * 2);
  set('ParamAngleZ', Math.sin(t / 2600) * 5 + poseX * 4);
  set('ParamBodyAngleX', poseX * 8);
  set('ParamBodyAngleY', -poseY * 5);
  set('ParamEyeBallX', poseX * 0.7);
  set('ParamEyeBallY', -poseY * 0.6);
  set('ParamBreath', 0.5 + 0.5 * Math.sin(t / 2600));
  if(emotionNow && t > emotionUntil){
    emotionNow = '';
    try{ l2dModel.expression('默认体型'); }catch(e){}
  }
}

/* 文字 → 表情（用的是模型自带的 Exp3） */
const EMO = [
  [/爱你|喜欢你|抱抱|亲|贴贴/, '爱心眼'],
  [/脸红|害羞|不好意思|想你了/, '脸红'],
  [/生气|哼|讨厌|不理你|过分|凶/, '黑脸'],
  [/哭|难过|委屈|伤心|呜呜/, '流泪'],
  [/害怕|好怕|吓|紧张|不敢/, '流冷汗'],
  [/晕|困惑|不懂|啥啊|啊？/, '圈圈眼'],
  [/＞＜|>_<|扭|撒娇/, '＞＜'],
  [/笑|开心|好耶|嘿嘿|哈哈|嘻嘻/, '兔牙'],
  [/得意|厉害|偷偷|屑/, '屑屑眼'],
];
function setEmotion(text){
  if(!l2dReady || !text) return;
  for(const [re, name] of EMO){
    if(re.test(text)){
      try{ l2dModel.expression(name); }catch(e){}
      emotionNow = name; emotionUntil = performance.now() + 6000;
      return;
    }
  }
}

/* ---------- 注意力：鼠标跟随；2.6 秒没人动就自己东张西望 ---------- */
const POSE_FIX = /pose=(1|max)/.test(location.search);
let poseX = 0, poseY = 0, targetX = 0, targetY = 0;
let lastMouseT = 0, wanderX = 0, wanderY = 0, wanderT = 0;
window.addEventListener('mousemove', e => {
  targetX = (e.clientX / innerWidth  - .5) * 2;
  targetY = (e.clientY / innerHeight - .5) * 2;
  lastMouseT = performance.now();
});
function poseStep(t){
  if(POSE_FIX){ targetX = 0.92; targetY = -0.30; }
  else if(t - lastMouseT > 2600){
    if(t - wanderT > 1500){
      wanderT = t;
      wanderX = (Math.random() * 2 - 1) * 0.55;
      wanderY = (Math.random() * 2 - 1) * 0.45;
    }
    targetX = wanderX; targetY = wanderY;
  }
  poseX += (targetX - poseX) * 0.055;
  poseY += (targetY - poseY) * 0.045;
}
(function poseLoop(){ poseStep(performance.now()); requestAnimationFrame(poseLoop); })();

/* 等 Pixi 与模型脚本就绪再初始化（它们在本脚本之后才加载） */
window.addEventListener('load', () => setTimeout(initLive2D, 60));'''

start = src.index("const eyeL = $('eyeL'), eyeR = $('eyeR');")
end = src.index("setTimeout(blink, 1200);") + len("setTimeout(blink, 1200);")
src = src[:start] + js_new + src[end:]
print("JS 主块替换: ok")

# 4) 口型：不再写 CSS 变量，改成给 mouthP
old_mouth = re.search(
    r"    mouthEl\.style\.setProperty\('--open'.*?mouthEl\.classList\.toggle\('open', mouthOpen > 0\.04\);",
    src, flags=re.S)
if old_mouth:
    src = src.replace(old_mouth.group(0),
        "    /* 真 Live2D：口型交给 ParamMouthOpenY，0~1 只取 85% 免得夸张 */\n"
        "    mouthP = Math.min(1, mouthOpen * 0.85);")
    print("口型接线: ok")
else:
    print("口型接线: 没找到锚点")

# 5) 字幕打出来时顺手触发表情
if "setEmotion(line)" not in src:
    src = src.replace("speak(line)", "setEmotion(line); speak(line)", 1)  # 兜底，见下
print("__check__ speak 处:", src.count("setEmotion(line)"))

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("写入完成，长度", len(orig), "->", len(src))
