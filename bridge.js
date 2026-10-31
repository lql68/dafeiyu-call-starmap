// bridge.js — AI 直播间状态桥（零依赖，Node 18+）
// 作用：给 OBS 浏览器源提供 panel.html + 一个可被任意脚本 POST 的状态接口
//
//   node bridge.js            默认 http://127.0.0.1:8765
//   node bridge.js 9000       换端口
//
// 接口：
//   GET  /               → panel.html
//   GET  /state          → 当前状态 JSON
//   POST /push           → body 为对象，浅合并进状态（token/game/ai 这类子对象也做一层合并）
//   POST /danmaku        → {user,text,gift?} 追加一条弹幕，保留最近 12 条
//   POST /song           → {user,title} 追加点歌
//   POST /reset          → 恢复 state.default.json

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = Number(process.argv[2] || 8765);
const DIR = __dirname;
const STATE_FILE = path.join(DIR, 'state.json');
const DEFAULT_FILE = path.join(DIR, 'state.default.json');

const DEFAULT_STATE = {
  streamer: '小肥鱼（AI版）',
  sub: '主播 · AI 自动游玩 · 弹幕实时驱动',
  viewers: 0,
  uptimeSec: 0,
  link: '实时数据已连接',
  token: { balance: 0, earned: 0, note: '等待唱演' },
  game: { title: '泰拉瑞亚', status: '游戏运行中', a: '关卡 —', b: '进度 —', c: '—', last: '—' },
  ai: { face: '🐟', line: '……', ts: '刚刚' },
  danmaku: [],
  songs: []
};

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); }
  catch { return JSON.parse(JSON.stringify(DEFAULT_STATE)); }
}
function saveState(s) {
  try { fs.writeFileSync(STATE_FILE, JSON.stringify(s, null, 2), 'utf8'); } catch {}
}
function deepishMerge(dst, patch) {
  for (const k of Object.keys(patch || {})) {
    const v = patch[k];
    if (v && typeof v === 'object' && !Array.isArray(v) && dst[k] && typeof dst[k] === 'object' && !Array.isArray(dst[k]))
      deepishMerge(dst[k], v);
    else dst[k] = v;
  }
  return dst;
}

let state = loadState();
if (!fs.existsSync(DEFAULT_FILE)) fs.writeFileSync(DEFAULT_FILE, JSON.stringify(DEFAULT_STATE, null, 2), 'utf8');
// 开播计时
const startedAt = Date.now() - (state.uptimeSec || 0) * 1000;
setInterval(() => { state.uptimeSec = Math.floor((Date.now() - startedAt) / 1000); }, 1000);
setInterval(() => saveState(state), 5000);

function body(req) {
  return new Promise(resolve => {
    let b = '';
    req.on('data', c => { b += c; if (b.length > 1e6) req.destroy(); });
    req.on('end', () => {
      try { resolve(b ? JSON.parse(b) : {}); } catch { resolve({ _raw: b }); }
    });
  });
}
function json(res, code, obj) {
  const s = JSON.stringify(obj);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'content-type',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
  });
  res.end(s);
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  const p = u.pathname;
  if (req.method === 'OPTIONS') return json(res, 204, {});

  try {
    if (p === '/' || p === '/panel' || p === '/panel.html') {
      const html = fs.readFileSync(path.join(DIR, 'panel.html'));
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      return res.end(html);
    }
    if (p === '/state') return json(res, 200, state);
    if (p === '/health') return json(res, 200, { ok: true, port: PORT, uptimeSec: state.uptimeSec });

    if (req.method === 'POST' && p === '/push') {
      const patch = await body(req);
      deepishMerge(state, patch);
      return json(res, 200, { ok: true });
    }
    if (req.method === 'POST' && p === '/danmaku') {
      const d = await body(req);
      if (!d.text) return json(res, 400, { ok: false, error: 'text required' });
      state.danmaku.push({ user: d.user || '观众', text: String(d.text).slice(0, 80), gift: !!d.gift });
      if (state.danmaku.length > 12) state.danmaku = state.danmaku.slice(-12);
      return json(res, 200, { ok: true, n: state.danmaku.length });
    }
    if (req.method === 'POST' && p === '/song') {
      const d = await body(req);
      if (!d.title) return json(res, 400, { ok: false, error: 'title required' });
      state.songs.push({ user: d.user || '观众', title: String(d.title).slice(0, 40), state: '排队中' });
      if (state.songs.length > 20) state.songs = state.songs.slice(-20);
      return json(res, 200, { ok: true });
    }
    if (req.method === 'POST' && p === '/reset') {
      state = JSON.parse(JSON.stringify(DEFAULT_STATE));
      saveState(state);
      return json(res, 200, { ok: true });
    }
    json(res, 404, { ok: false, error: 'not found' });
  } catch (e) {
    json(res, 500, { ok: false, error: String(e && e.message || e) });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[bridge] http://127.0.0.1:${PORT}/`);
  console.log(`[bridge] OBS 浏览器源填: http://127.0.0.1:${PORT}/  (1920x1080)`);
});