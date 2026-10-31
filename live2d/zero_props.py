# -*- coding: utf-8 -*-
"""把模型自带的「道具/切换」参数全部归零，看看贴在脸上的黑块是不是其中之一。

cdi3 里这些参数的中文名：
  key1~key13   = 黑脸/落泪/圈圈眼/爱心眼/＞＜眼/屑屑眼/脸红/加载/大牙/大钢盆/黑框眼镜/单片眼镜/流冷汗
  Movement1~3 = 狗尾草/抚胸/竖食指
  Clothes1~5  = 长短裙/大小变/胸口衣服/鞋子/尾巴
"""
import io

P = r"D:\deepseek harness\ai-live\live.html"
s = io.open(P, encoding="utf-8").read()

DECL = "const HIDE_PARTS = ['Part19', 'Part26', 'Part74'];   // 按键 ×2、加载图标"

NEW = """const HIDE_PARTS = ['Part19', 'Part26', 'Part74'];
/* 模型自带的一堆「道具/切换」开关（cdi3 里的 key1~13 / Movement1~3 / Clothes1~5）。
   VTS 里它们是手动按的，网页里没人按，某些项回到默认值就会把贴纸/图标画在她脸上。
   这里统一按到 0，只保留裙子长度和尾巴这两个想要的状态。 */
const PROP_PARAMS = [
  'key1','key2','key3','key4','key5','key6','key7','key8','key9','key10','key11','key12','key13',
  'Movement1','Movement2','Movement3',
  'Clothes1','Clothes3','Clothes4','Param34','Param2'
];"""

if "PROP_PARAMS" in s:
    print("already")
else:
    assert DECL in s, "decl anchor missing"
    s = s.replace(DECL, NEW, 1)

    anchor = "  if(!NO_MOUTH){"
    add = ("  for(const pp of PROP_PARAMS){ try{ set(pp, 0); }catch(e){} }\n")
    assert anchor in s, "mouth anchor missing"
    s = s.replace(anchor, add + anchor, 1)
    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("patched, PROP_PARAMS refs:", s.count("PROP_PARAMS"))
