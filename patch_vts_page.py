# -*- coding: utf-8 -*-
"""让 live.html 在播放时把口型/表情推给 VTube Studio，并支持 ?render=vts（不画 canvas）。"""
import io

P = r"D:\deepseek harness\ai-live\live.html"
s = io.open(P, encoding="utf-8").read()
before = len(s)

# ---------- 1) 情绪：同时推给 VTS ----------
old_emo = '''function setEmotion(text){
  if(!l2dReady || !text) return;
  for(const [re, name] of EMO){
    if(re.test(text)){
      try{ l2dModel.expression(name); }catch(e){}
      emotionNow = name; emotionUntil = performance.now() + 6000;
      return;
    }
  }
}'''
new_emo = '''function setEmotion(text){
  if(!text) return;
  const hit = EMO.find(([re]) => re.test(text));
  if(!hit) return;
  const name = hit[1];
  if(l2dReady){ try{ l2dModel.expression(name); }catch(e){} }
  emotionNow = name; emotionUntil = performance.now() + 6000;
  /* VTS 那边要文件名，Exp3 里就是 名字.exp3.json */
  vtsPost('/api/vts/expression', {name: name + '.exp3.json', active: true, fade: 0.35});
}

/* ---------- VTube Studio：把口型推过去 ----------
   VTS 认的是它自己的输入参数 MouthOpen（0~1），不是模型的 ParamMouthOpenY。
   节流 40ms（25Hz）就够，接口在本机，延迟 1~2ms。 */
const VTS_MOUTH = location.search.includes('render=vts') || !location.search.includes('novts');
let vtsLastSent = 0, vtsLastVal = -1;
function vtsPost(path, body){
  try{
    return fetch(path, {
      method: 'POST', cache: 'no-store',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body || {})
    }).catch(() => {});
  }catch(e){ return null; }
}
function pushMouth(t, open, smile){
  if(!VTS_MOUTH) return;
  if(t - vtsLastSent < 40) return;
  if(Math.abs(open - vtsLastVal) < 0.012 && open > 0.01) return;   // 变化太小就不发
  vtsLastSent = t; vtsLastVal = open;
  vtsPost('/api/mouth', {open: open, smile: smile});
}'''
assert old_emo in s, 'setEmotion 锚点没找到'
s = s.replace(old_emo, new_emo, 1)

# ---------- 2) 帧循环里推口型 ----------
anchor = '''  /* 头肩取景要「顶对齐」'''
assert anchor in s, '帧循环锚点没找到'
# 帧循环在别处；先找 mouthOpen 平滑那一段
import re
m = re.search(r"\n(\s*)mouthOpen \+= \(tgtOpen - mouthOpen\)", s)
assert m, 'mouthOpen 平滑那行没找到'
indent = m.group(1)
ins = ("\n" + indent + "pushMouth(t, mouthOpen, 0.35 + 0.45 * mouthOpen);")
pos = s.index("\n", m.end())
s = s[:pos] + ins + s[pos:]

# ---------- 3) ?render=vts 时把 canvas 藏掉 ----------
old_css = '  .l2d-wrap{'
assert old_css in s, 'CSS 锚点没找到'
s = s.replace(old_css, '''  body.render-vts .l2d-wrap{display:none}
  body.render-vts #vtsHint{display:flex}
  #vtsHint{display:none;position:absolute;inset:0;align-items:center;justify-content:center;
    color:#5d7590;font-size:13px;letter-spacing:.16em;flex-direction:column;gap:10px}
  #vtsHint b{color:#8fd8f0;font-weight:600;font-size:15px;letter-spacing:.1em}
  .l2d-wrap{''', 1)

if 'id="vtsHint"' not in s:
    s = s.replace('<canvas id="l2dCanvas"></canvas>',
                  '<canvas id="l2dCanvas"></canvas>\n'
                  '      <div id="vtsHint"><b>已交给 VTube Studio 渲染</b>'
                  '<span>看旁边的 VTS 窗口 · 口型与表情由这里驱动</span></div>', 1)

# ---------- 4) JS 里加类名 ----------
if "render-vts" not in s.split("<script>")[-1]:
    s = s.rstrip()
    assert s.endswith("</html>")
    s = s[:-len("</html>")] + '''<script>
/* 渲染目标：默认还是 canvas；?render=vts 就把画面交给 VTube Studio */
if(location.search.includes('render=vts')) document.body.classList.add('render-vts');
</script>
</html>
'''

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("live.html 已改：%d -> %d 字符" % (before, len(s)))
for k in ("pushMouth", "render-vts", "vtsHint", "/api/vts/expression"):
    print("  ", k, "->", s.count(k))
