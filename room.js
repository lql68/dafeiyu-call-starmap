/* 程序化画一间「虚焦的暖房间」当底图。
   比纯 CSS 渐变多一点内容：书架 + 书脊、月光窗、台灯、地板缝、桌上杂物。
   全部一次性画完，靠 CSS 的 blur 做景深；0 依赖、0 显存。 */
(function room(){
  const cv = document.getElementById('roomCv');
  if(!cv) return;
  const W = 1920, H = 1080;
  cv.width = W; cv.height = H;
  const c = cv.getContext('2d');

  /* 固定种子，每次刷新看到的房间是同一间 */
  let seed = 20261031;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  const rr = (a, b) => a + rnd() * (b - a);

  /* ── 墙 ─────────────────────────────────────────── */
  let g = c.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0,   '#3A2D20');
  g.addColorStop(0.52,'#4A3A28');
  g.addColorStop(1,   '#2A2118');
  c.fillStyle = g;
  c.fillRect(0, 0, W, H);

  /* ── 地板 ───────────────────────────────────────── */
  const floorY = H * 0.705;
  g = c.createLinearGradient(0, floorY, 0, H);
  g.addColorStop(0, '#5C472E');
  g.addColorStop(1, '#1E1710');
  c.fillStyle = g;
  c.fillRect(0, floorY, W, H - floorY);

  /* 地板缝：越远越密（透视） */
  c.strokeStyle = 'rgba(20,15,10,.34)';
  c.lineWidth = 2;
  for(let i = 1; i <= 9; i++){
    const t = i / 9;
    const y = floorY + Math.pow(t, 1.9) * (H - floorY);
    c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke();
  }

  /* ── 左侧书架 ───────────────────────────────────── */
  const SX = 40, SW = 700, SY = 70, SH = 700, ROWS = 5;
  const RH = SH / ROWS;
  /* 书架背板 */
  g = c.createLinearGradient(SX, 0, SX + SW, 0);
  g.addColorStop(0, '#3A2C1C');
  g.addColorStop(0.5, '#2E2317');
  g.addColorStop(1, '#241B12');
  c.fillStyle = g;
  c.fillRect(SX, SY, SW, SH);

  const SPINE = ['#7A5B33', '#8A6438', '#6B4A2A', '#5E4830',
                 '#7F3F32', '#6A4632', '#55602F', '#8C7150',
                 '#4E3A28', '#7A6A45'];

  for(let r = 0; r < ROWS; r++){
    const top = SY + r * RH;
    const bh = RH * 0.86;              // 书脊高度
    let x = SX + 8;
    while(x < SX + SW - 16){
      const w = rr(12, 30);
      if(x + w > SX + SW - 8) break;
      const h = bh * rr(0.62, 1.0);
      c.fillStyle = SPINE[(rnd() * SPINE.length) | 0];
      c.globalAlpha = rr(0.55, 0.95);
      c.fillRect(x, top + RH - h, w, h);
      /* 个别书有心里的亮条 */
      if(rnd() > 0.72){
        c.fillStyle = 'rgba(214,190,150,.22)';
        c.fillRect(x + 2, top + RH - h + 4, w - 4, 3);
      }
      c.globalAlpha = 1;
      x += w + rr(1, 4);
    }
    /* 隔板 */
    c.fillStyle = 'rgba(24,18,12,.72)';
    c.fillRect(SX, top + RH - 4, SW, 7);
  }
  /* 书架外框 */
  c.strokeStyle = 'rgba(30,22,14,.8)';
  c.lineWidth = 10;
  c.strokeRect(SX, SY, SW, SH);

  /* ── 右上：一束斜下来的柔光 ───────────────────────
     原来画了整扇窗，模糊后成了一块灰蓝色纸板，还正好压在识海球后面。
     改成只有光、没有形体：冷色的空气感，不挡任何东西。 */
  g = c.createRadialGradient(1760, 30, 24, 1760, 30, 760);
  g.addColorStop(0, 'rgba(214,226,244,.22)');
  g.addColorStop(0.40, 'rgba(158,180,208,.075)');
  g.addColorStop(1, 'rgba(120,140,170,0)');
  c.fillStyle = g;
  c.fillRect(960, -240, 960, 1160);

  /* ── 台灯（右中，暖光团） ───────────────────────── */
  const LX = 1010, LY = 660;
  g = c.createRadialGradient(LX, LY, 6, LX, LY, 330);
  g.addColorStop(0, 'rgba(255,236,190,.72)');
  g.addColorStop(0.22, 'rgba(243,212,150,.34)');
  g.addColorStop(0.62, 'rgba(180,140,90,.10)');
  g.addColorStop(1, 'rgba(120,90,58,0)');
  c.fillStyle = g;
  c.beginPath(); c.arc(LX, LY, 330, 0, 6.284); c.fill();

  /* 灯罩 */
  c.fillStyle = 'rgba(58,44,30,.9)';
  c.beginPath();
  c.moveTo(LX - 74, LY - 26);
  c.lineTo(LX + 74, LY - 26);
  c.lineTo(LX + 46, LY - 96);
  c.lineTo(LX - 46, LY - 96);
  c.closePath(); c.fill();
  c.fillStyle = 'rgba(255,232,186,.55)';
  c.fillRect(LX - 66, LY - 24, 132, 5);

  /* ── 桌面上几摞书 + 一个杯子（都是暗剪影） ──────── */
  for(let i = 0; i < 3; i++){
    const bx = 900 + i * 26, by = 830 - i * 14;
    c.fillStyle = 'rgba(30,23,16,' + (0.55 + i * 0.08) + ')';
    c.fillRect(bx, by, 150 - i * 10, 12 + i * 3);
  }
  c.fillStyle = 'rgba(26,20,14,.8)';
  c.fillRect(1230, 838, 54, 46);
  c.beginPath(); c.eliminate = null;
  c.arc(1257, 838, 27, Math.PI, 6.284); c.fill();

  /* ── 一层柔和的暖雾，把细节压成"虚焦背景" ──────── */
  g = c.createRadialGradient(W * 0.46, H * 0.44, 80,
                             W * 0.46, H * 0.44, W * 0.72);
  g.addColorStop(0, 'rgba(96,74,50,.10)');
  g.addColorStop(0.6, 'rgba(52,40,28,.26)');
  g.addColorStop(1, 'rgba(18,14,10,.62)');
  c.fillStyle = g;
  c.fillRect(0, 0, W, H);

  /* 噪点：压住渐变的色带 */
  const id = c.getImageData(0, 0, W, H);
  const d = id.data;
  for(let i = 0; i < d.length; i += 4){
    const n = (Math.random() - 0.5) * 12;
    d[i] += n; d[i + 1] += n; d[i + 2] += n;
  }
  c.putImageData(id, 0, 0);

  console.log('[room] 背景画好了 ' + W + 'x' + H);
})();
