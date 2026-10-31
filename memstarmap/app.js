"use strict";

/* ================= 常量与调色板 ================= */
const TAU = Math.PI * 2;
const ACCENT_RGB = [217, 196, 154];
const BG_RGB = [11, 15, 21];
const TXT_RGB = [199, 200, 203];
const TXT2_RGB = [138, 143, 150];
const TXT3_RGB = [91, 98, 107];
const GRAY_RGB = [168, 173, 178];

const TYPE_STYLE = {
  fact:   { color: [222, 229, 238], size: 1.0, label: "FACT" },
  topic:  { color: [207, 176, 118], size: 0.92, label: "TOPIC" },
  person: { color: [125, 214, 190], size: 1.22, label: "PERSON" },
};

const TYPE_ORDER = { fact: 0, topic: 1, person: 2, unknown: 3 };
function typeLabel(t) {
  const key = (t || "unknown").toLowerCase();
  const ts = TYPE_STYLE[key];
  if (ts) return ts.label;
  return String(key).toUpperCase();
}

const FOCAL = 200;
const MIN_DIST = 1.2;
const MAX_DIST = 30;
const CAM_INIT = { yaw: 0.7, pitch: 0.5, dist: 5.5 };
const ANIM_MS = 700;

const state = {
  selectedId: null,
  hoverId: null,
  query: "",
  decayThreshold: 0.5,
  dragging: false,
  lastClickT: 0,
  imSliderId: null,
  imSliderVal: 0.5,
  selectedNode: null,
  atoms: [],
  healthBackups: 0,
  lastOp: null,
  opsList: [],
};

let GRAPH = null;
let entries = [];
let byId = new Map();
let W = 0, H = 0, DPR = 1;
const STARS = [];
for (let i = 0; i < 240; i++) {
  STARS.push({ x: hash01("starX" + i), y: hash01("starY" + i), r: 0.4 + hash01("starR" + i) * 0.8, a: 0.08 + hash01("starA" + i) * 0.25 });
}

/* ================= API ================= */
function apiGet(path) {
  return fetch(path).then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); });
}
function apiPost(path, body) {
  return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); });
}

/* ================= 小工具 ================= */
function hash01(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}

function nodeDir(n) {
  const a = hash01("sphA" + n.id);
  const b = hash01("sphB" + n.id);
  const theta = a * TAU;
  const phi = Math.acos(Math.max(-1, Math.min(1, 2 * b - 1)));
  const sp = Math.sin(phi);
  n.x = sp * Math.cos(theta);
  n.y = Math.cos(phi);
  n.z = sp * Math.sin(theta);
}

function visualRadius(n) {
  const base = (0.6 + Math.log2(1 + (n.deg || 0)) * 0.5) * (0.85 + 0.3 * (n.imp || 0.3));
  const ts = TYPE_STYLE[n.type] || TYPE_STYLE.fact;
  let r = base * ts.size;
  if (n.type === "person") r *= 1.18;
  return Math.max(0.7, r);
}

function shadeRGB(base, t) {
  const bright = 0.16 + 0.84 * t;
  const sat = 0.15 + 0.85 * t;
  let r = base[0] * bright;
  let g = base[1] * bright;
  let b = base[2] * bright;
  const l = 0.299 * r + 0.587 * g + 0.114 * b;
  r = l + (r - l) * sat;
  g = l + (g - l) * sat;
  b = l + (b - l) * sat;
  return [r, g, b];
}

function computeDepth(n, cam) {
  const px = Math.cos(cam.pitch) * Math.cos(cam.yaw);
  const py = Math.sin(cam.pitch);
  const pz = Math.cos(cam.pitch) * Math.sin(cam.yaw);
  const fl = Math.hypot(px, py, pz) || 1;
  const fx = -px / fl, fy = -py / fl, fz = -pz / fl;
  const vx = n.x - cam.dist * px, vy = n.y - cam.dist * py, vz = n.z - cam.dist * pz;
  return -(vx * fx + vy * fy + vz * fz);
}

function camBasis(cam) {
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
  const px = cp * Math.cos(cam.yaw), py = sp, pz = cp * Math.sin(cam.yaw);
  const fl = Math.hypot(px, py, pz) || 1;
  const fx = -px / fl, fy = -py / fl, fz = -pz / fl;
  const rx = -fz, ry = 0, rz = fx;
  const rl = Math.hypot(rx, ry, rz) || 1;
  const bx = rx / rl, by = ry / rl, bz = rz / rl;
  const ux = by * fz - bz * fy, uy = bz * fx - bx * fz, uz = bx * fy - by * fx;
  const ul = Math.hypot(ux, uy, uz) || 1;
  return { f: { x: fx, y: fy, z: fz }, r: { x: bx, y: by, z: bz }, u: { x: ux / ul, y: uy / ul, z: uz / ul } };
}

function fmtTime(ts) {
  const d = new Date((ts || 0) * 1000);
  const p = (x) => (x < 10 ? "0" + x : "" + x);
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}

function fmtDays(x) {
  if (x == null || isNaN(x)) return "?";
  return Number(x).toFixed(1);
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function matchesQuery(n, q) {
  if (!q) return true;
  const s = (n.value || "").toLowerCase();
  const qc = q.toLowerCase();
  return s.indexOf(qc) >= 0;
}

/* ================= 相机与动画 ================= */
const cam = { yaw: CAM_INIT.yaw, pitch: CAM_INIT.pitch, dist: CAM_INIT.dist };
let anim = null;

function flyToNode(n) {
  const yawN = Math.atan2(n.z, n.x);
  const pitchN = Math.asin(Math.max(-0.95, Math.min(0.95, n.y)));
  const depth = computeDepth(n, cam);
  anim = { fromYaw: cam.yaw, fromPitch: cam.pitch, fromDist: cam.dist, toYaw: yawN, toPitch: pitchN, toDist: Math.max(1.5, depth * 1.4), t0: performance.now() };
}

function resetCamAnim() {
  anim = { fromYaw: cam.yaw, fromPitch: cam.pitch, fromDist: cam.dist, toYaw: CAM_INIT.yaw, toPitch: CAM_INIT.pitch, toDist: CAM_INIT.dist, t0: performance.now() };
}

function applyAnim(now) {
  if (!anim) return false;
  const t = Math.min(1, (now - anim.t0) / ANIM_MS);
  const e = 1 - Math.pow(1 - t, 3);
  cam.yaw = anim.fromYaw + (anim.toYaw - anim.fromYaw) * e;
  cam.pitch = anim.fromPitch + (anim.toPitch - anim.fromPitch) * e;
  cam.dist = anim.fromDist + (anim.toDist - anim.fromDist) * e;
  if (t >= 1) anim = null;
  return true;
}

/* ================= 渲染 ================= */
function render() {
  const cv = document.getElementById("view");
  const ctx = cv.getContext("2d");
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.fillStyle = "rgb(" + BG_RGB.join(",") + ")";
  ctx.fillRect(0, 0, W, H);

  for (const s of STARS) {
    ctx.globalAlpha = s.a;
    ctx.fillStyle = "rgb(210,214,224)";
    ctx.beginPath();
    ctx.arc(s.x * W, s.y * H, s.r, 0, TAU);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  const campos = {
    x: cam.dist * Math.cos(cam.pitch) * Math.cos(cam.yaw),
    y: cam.dist * Math.sin(cam.pitch),
    z: cam.dist * Math.cos(cam.pitch) * Math.sin(cam.yaw),
  };
  const basis = camBasis(cam);
  const newEntries = [];
  const nodes = (GRAPH && GRAPH.nodes) || [];
  for (const n of nodes) {
    const ts = TYPE_STYLE[n.type] || TYPE_STYLE.fact;
    let dim = 0;
    if (state.decayThreshold > 0) {
      dim = Math.min(1, Math.max(0, (state.decayThreshold - (n.decay || 0)) / (state.decayThreshold + 1e-6)));
    }
    let t = (n.decay || 0) * (1 - 0.92 * dim);
    if (n.type === "person") t = Math.min(1, t * 1.35 + 0.12);
    const r = visualRadius(n);
    const depth = computeDepth(n, cam);
    const da = Math.max(0, 1 - (depth - cam.dist) * 0.25);
    let alpha = (0.28 + 0.66 * t) * da;
    alpha *= (1 - 0.88 * dim);
    if (state.query) alpha *= matchesQuery(n, state.query) ? 1.25 : 0.10;
    const size = Math.max(0.4, r * cam.dist / depth);
    const vx = n.x - campos.x, vy = n.y - campos.y, vz = n.z - campos.z;
    const cx = vx * basis.r.x + vy * basis.r.y + vz * basis.r.z;
    const cy = vx * basis.u.x + vy * basis.u.y + vz * basis.u.z;
    newEntries.push({
      n: n, depth: depth, sx: W / 2 + cx * r / depth, sy: H / 2 - cy * r / depth,
      size: size, alpha: alpha, rgb: shadeRGB(ts.color, t), fresh: t, da: da,
      match: !!state.query && matchesQuery(n, state.query),
    });
  }
  byId.clear();
  for (const e of newEntries) byId.set(e.n.id, e);
  entries = newEntries;
  entries.sort((a, b) => a.depth - b.depth); // 远 -> 近

  /* ---- 边：按 alpha 分桶，每桶一条路径一次 stroke（保持高帧率） ---- */
  const buckets = new Map();
  const edges = (GRAPH && GRAPH.edges) || [];
  for (const e of edges) {
    const a = byId.get(e.s), b = byId.get(e.t);
    if (!a || !b) continue;
    if (a.alpha <= 0.01 || b.alpha <= 0.01) continue;
    const alpha = 0.10 * (0.35 + 0.65 * Math.min(a.fresh, b.fresh)) * Math.min(a.da, b.da);
    const lw = Math.max(0.2, 0.8 * Math.min(a.da, b.da));
    const key = alpha.toFixed(3) + "|" + lw.toFixed(2);
    let bkt = buckets.get(key);
    if (!bkt) { bkt = { alpha: alpha, lw: lw, segs: [] }; buckets.set(key, bkt); }
    bkt.segs.push([a.sx, a.sy, b.sx, b.sy]);
  }
  for (const bkt of buckets.values()) {
    ctx.globalAlpha = bkt.alpha;
    ctx.strokeStyle = "rgb(" + GRAY_RGB.join(",") + ")";
    ctx.lineWidth = bkt.lw;
    ctx.beginPath();
    for (const s of bkt.segs) { ctx.moveTo(s[0], s[1]); ctx.lineTo(s[2], s[3]); }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  /* ---- 节点：远 -> 近 ---- */
  for (const e of entries) {
    if (e.alpha < 0.01) continue;
    const rs = e.size * (state.hoverId === e.n.id ? 1.55 : 1);
    ctx.globalAlpha = e.alpha;
    ctx.fillStyle = "rgb(" + e.rgb.join(",") + ")";
    ctx.beginPath();
    ctx.arc(e.sx, e.sy, rs, 0, TAU);
    ctx.fill();
    if (state.hoverId === e.n.id) {
      ctx.globalAlpha = 0.9;
      ctx.strokeStyle = "rgb(" + ACCENT_RGB.join(",") + ")";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(e.sx, e.sy, rs * 2.0, 0, TAU); ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (state.selectedId === e.n.id) {
      ctx.globalAlpha = 0.95;
      ctx.strokeStyle = "rgb(" + ACCENT_RGB.join(",") + ")";
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(e.sx, e.sy, rs * 2.3, 0, TAU); ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (e.match) {
      ctx.globalAlpha = Math.min(1, e.alpha * 1.4);
      ctx.strokeStyle = "rgb(" + ACCENT_RGB.join(",") + ")";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);
      ctx.beginPath(); ctx.arc(e.sx, e.sy, rs * 2.6, 0, TAU); ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    }
    ctx.globalAlpha = 1;
  }
}

/* ================= 命中测试 ================= */
function hitTest(x, y) {
  let best = null, bestD = Infinity;
  for (const e of entries) {
    const dx = e.sx - x, dy = e.sy - y;
    const d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = e; }
  }
  if (best && Math.sqrt(bestD) < Math.max(8, best.size * 2)) return best;
  return null;
}

/* ================= toast ================= */
function showToast(msg, ok) {
  const t = document.getElementById("toast");
  const m = document.getElementById("toast-msg");
  m.textContent = msg;
  t.className = "toast" + (ok === false ? " fail" : " ok");
  t.style.display = "block";
  clearTimeout(showToast._tm);
  showToast._tm = setTimeout(function () { t.style.display = "none"; }, 2600);
}

/* ================= 状态条 ================= */
function renderStatus() {
  const c = document.getElementById("st-counts");
  const o = document.getElementById("st-ops");
  const nodes = (GRAPH && GRAPH.nodes) ? GRAPH.nodes.length : 0;
  const edges = (GRAPH && GRAPH.edges) ? GRAPH.edges.length : 0;
  const atoms = (GRAPH && GRAPH.atoms) ? GRAPH.atoms.length : 0;
  c.textContent = nodes + " 节点 / " + edges + " 边 / " + atoms + " 原子 / 备份 " + (state.healthBackups || 0) + " 份";
  if (state.lastOp) {
    o.textContent = "最近操作:" + (state.lastOp.action || "op") + " atom#" + (state.lastOp.atom_id != null ? state.lastOp.atom_id : "-");
  }
}

/* ================= 详情面板 · 节点信息 ================= */
function renderNodeInfo(n, atomCount) {
  const tp = document.getElementById("p-type");
  const pv = document.getElementById("p-value");
  tp.textContent = typeLabel(n.type);
  pv.textContent = (n.value || "").slice(0, 80);
  const html = '<div class="p-sec">';
  html += '<div class="p-sec-title">Node Record</div>';
  const rows = [
    ["TYPE", typeLabel(n.type)],
    ["DEG", String(n.deg == null ? 0 : n.deg)],
    ["CREATED", fmtTime(n.created)],
    ["DECAY", (n.decay == null ? 0 : n.decay).toFixed(2)],
    ["ATOMS", String(atomCount == null ? 0 : atomCount)],
  ];
  for (const r of rows) {
    html += '<div class="p-row"><span class="p-label">' + r[0] + '</span><span class="p-val">' + r[1] + '</span></div>';
  }
  html += '</div>';
  document.getElementById("p-node-sec").innerHTML = html;
}

/* ================= 详情面板 · 关联记忆列表 ================= */
function renderAtomList(node, atoms) {
  const sec = document.getElementById("p-atoms-sec");
  let html = '<div class="p-sec">';
  html += '<div class="p-sec-title">Atom Records</div>';
  const list = atoms || [];
  if (list.length === 0) {
    html += '<div class="p-sec-title" style="color:#5B626B;margin-top:4px;">NO ATOM MATCH</div>';
    sec.innerHTML = html + '</div>';
    return;
  }
  for (const a of list) {
    const expired = (a.left_days != null && a.left_days < 0);
    const conf = a.confidence == null ? 0 : a.confidence;
    let ops = "";
    if (state.imSliderId === a.id) {
      ops = '<div class="p-imp-row">';
      ops += '<input type="range" id="impSlider" min="0" max="1" step="0.01" value="' + (state.imSliderVal == null ? (a.importance || 0.5) : state.imSliderVal) + '" data-atom-id="' + a.id + '" />';
      ops += '<span class="hud-value" id="impVal-' + a.id + '">' + (state.imSliderVal == null ? (a.importance || 0.5) : state.imSliderVal).toFixed(2) + '</span>';
      ops += '<button class="hud-btn" data-op="imp-confirm" data-atom-id="' + a.id + '">确认</button>';
      ops += '<button class="hud-btn" data-op="imp-cancel" data-atom-id="' + a.id + '">取消</button>';
      ops += '</div>';
    } else {
      ops = '<div class="p-atom-ops">';
      ops += '<button class="hud-btn" data-op="reinforce" data-atom-id="' + a.id + '">强化</button>';
      ops += '<button class="hud-btn" data-op="importance" data-atom-id="' + a.id + '">重要性</button>';
      ops += '<button class="hud-btn hud-btn-danger" data-op="forget" data-atom-id="' + a.id + '">淡忘</button>';
      ops += '</div>';
    }
    html += '<div class="p-atom' + (expired ? " expired" : "") + '" data-atom-id="' + a.id + '">';
    html += '<div class="p-atom-top"><span class="p-atom-type">' + typeLabel(a.atom_type) + '</span><span class="p-atom-imp">IMP ' + (a.importance == null ? 0 : a.importance).toFixed(2) + '</span></div>';
    html += '<div class="p-atom-text">' + escapeHtml(a.content) + '</div>';
    html += '<div class="p-atom-meta">LEFT ' + fmtDays(a.left_days) + 'D · CONF ' + conf.toFixed(2) + ' · TTL ' + fmtDays(a.ttl_days) + 'D</div>';
    if (expired) {
      html += '<div class="p-atom-exp">已过期 EXPIRED</div>';
    }
    html += ops;
    html += '</div>';
  }
  html += '</div>';
  sec.innerHTML = html;
}

function openPanel(n) {
  state.selectedId = n.id;
  state.selectedNode = n;
  state.imSliderId = null;
  renderNodeInfo(n, n.atoms);
  const panel = document.getElementById("panel");
  panel.classList.add("open");
  document.getElementById("app").classList.add("panel-open");
  loadAtoms(n);
}

function closePanel() {
  state.selectedId = null;
  state.selectedNode = null;
  state.imSliderId = null;
  document.getElementById("panel").classList.remove("open");
  document.getElementById("app").classList.remove("panel-open");
}

/* ================= 操作：强化 / 淡忘 / 重要性 ================= */
function loadAtoms(node) {
  apiGet("/api/atoms?node=" + encodeURIComponent(String(node.id)) + "&limit=8")
    .then(function (res) {
      if (res.status !== 200) {
        document.getElementById("p-atoms-sec").innerHTML = '<div class="p-sec"><div class="p-sec-title">Atom Records</div><div class="p-sec-title" style="color:#5B626B;margin-top:4px;">API ERROR</div></div>';
        return;
      }
      state.atoms = res.data;
      renderAtomList(node, res.data);
    })
    .catch(function () {
      document.getElementById("p-atoms-sec").innerHTML = '<div class="p-sec"><div class="p-sec-title">Atom Records</div><div class="p-sec-title" style="color:#5B626B;margin-top:4px;">API ERROR</div></div>';
    });
}

function refreshAtoms() {
  if (state.selectedNode) loadAtoms(state.selectedNode);
}

function doReinforce(atomId) {
  apiPost("/api/atom/reinforce", { id: atomId })
    .then(function (res) {
      if (res.status !== 200 || !res.data || res.data.ok !== true) {
        showToast("强化失败: " + (res.data && res.data.error ? res.data.error : "unknown"), false);
        return;
      }
      showToast("已强化 atom #" + atomId);
      state.lastOp = res.data;
      loadOps();
      refreshAtoms();
    })
    .catch(function (e) { showToast("强化失败: " + (e && e.message ? e.message : "network"), false); });
}

function doForget(atomId) {
  apiPost("/api/atom/forget", { id: atomId })
    .then(function (res) {
      if (res.status !== 200 || !res.data || res.data.ok !== true) {
        showToast("淡忘失败: " + (res.data && res.data.error ? res.data.error : "unknown"), false);
        return;
      }
      showToast("已淡忘 atom #" + atomId);
      state.lastOp = res.data;
      loadOps();
      refreshAtoms();
    })
    .catch(function (e) { showToast("淡忘失败: " + (e && e.message ? e.message : "network"), false); });
}

function doImportance(atomId, value) {
  apiPost("/api/atom/importance", { id: atomId, value: value })
    .then(function (res) {
      if (res.status !== 200 || !res.data || res.data.ok !== true) {
        showToast("重要性修改失败: " + (res.data && res.data.error ? res.data.error : "unknown"), false);
        return;
      }
      showToast("重要性已更新 atom #" + atomId + " -> " + Number(value).toFixed(2));
      state.lastOp = res.data;
      loadOps();
      refreshAtoms();
    })
    .catch(function (e) { showToast("重要性修改失败: " + (e && e.message ? e.message : "network"), false); });
}

/* ================= 操作日志 ================= */
function loadOps() {
  return apiGet("/api/ops").then(function (res) {
    if (res.status !== 200) return;
    state.lastOp = null;
    state.opsList = res.data || [];
    renderStatus();
  });
}

/* ================= 帧循环 ================= */
let last = performance.now();
function loop(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  if (!applyAnim(now)) {
    if (!state.dragging) cam.yaw += dt * 0.06;
  }
  render();
  requestAnimationFrame(loop);
}

/* ================= 启动 ================= */
function wireTopbar() {
  const searchInput = document.getElementById("searchInput");
  const searchCount = document.getElementById("searchCount");
  const decaySlider = document.getElementById("decaySlider");
  const decayValue = document.getElementById("decayValue");

  searchInput.addEventListener("input", function () {
    state.query = searchInput.value.trim();
    let cnt = 0;
    if (state.query) { for (const n of (GRAPH && GRAPH.nodes) || []) { if (matchesQuery(n, state.query)) cnt++; } }
    searchCount.textContent = state.query ? (cnt > 0 ? "MATCH " + cnt : "NO MATCH") : "";
    render();
  });
  searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      let first = null;
      if (state.query) { for (const n of (GRAPH && GRAPH.nodes) || []) { if (matchesQuery(n, state.query)) { first = n; break; } } }
      if (first) flyToNode(first);
    }
  });

  decaySlider.addEventListener("input", function (e) {
    state.decayThreshold = parseFloat(e.target.value);
    decayValue.textContent = state.decayThreshold.toFixed(2);
    render();
  });

  document.getElementById("p-close").addEventListener("click", function () { closePanel(); });
}

function wireCanvas() {
  const cv = document.getElementById("view");
  const ctx = cv.getContext("2d");
  let drag = null;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(window.innerWidth * dpr);
    cv.height = Math.round(window.innerHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    W = window.innerWidth;
    H = window.innerHeight;
    DPR = dpr;
  }
  resize();
  window.addEventListener("resize", resize);

  for (const n of (GRAPH && GRAPH.nodes) || []) nodeDir(n);

  cv.addEventListener("pointerdown", function (e) {
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, yaw: cam.yaw, pitch: cam.pitch, downX: e.clientX, downY: e.clientY, downT: performance.now() };
    state.dragging = true;
    cv.setPointerCapture(e.pointerId);
  });
  cv.addEventListener("pointermove", function (e) {
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      cam.yaw = drag.yaw - dx * 0.006;
      cam.pitch = Math.max(-1.45, Math.min(1.45, drag.pitch + dy * 0.006));
      drag.x = e.clientX;
      drag.y = e.clientY;
      render();
    } else {
      const hit = hitTest(e.clientX, e.clientY);
      state.hoverId = hit ? hit.n.id : null;
      const tip = document.getElementById("tooltip");
      if (hit) {
        tip.querySelector(".tt-text").textContent = (hit.n.value || "").slice(0, 40);
        tip.querySelector(".tt-sub").textContent = typeLabel(hit.n.type) + " · DECAY " + (hit.n.decay || 0).toFixed(2);
        tip.style.display = "block";
        tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 260) + "px";
        tip.style.top = Math.max(8, e.clientY - 10) + "px";
      } else {
        tip.style.display = "none";
      }
    }
  });
  cv.addEventListener("pointerup", function (e) {
    if (drag && drag.id === e.pointerId) {
      const moved = Math.abs(e.clientX - drag.downX) + Math.abs(e.clientY - drag.downY);
      const dt = performance.now() - drag.downT;
      if (moved < 6 && dt < 400) {
        const nowT = performance.now();
        const hit = hitTest(e.clientX, e.clientY);
        if (nowT - state.lastClickT < 350) {
          // 双击：复位相机
          resetCamAnim();
        } else {
          state.lastClickT = nowT;
          if (hit) openPanel(hit.n); else closePanel();
        }
      }
      drag = null;
      state.dragging = false;
    }
  });
  cv.addEventListener("pointercancel", function (e) { if (drag && drag.id === e.pointerId) { drag = null; state.dragging = false; } });
  cv.addEventListener("wheel", function (e) { e.preventDefault(); cam.dist = Math.max(MIN_DIST, Math.min(MAX_DIST, cam.dist * Math.exp(-e.deltaY * 0.0012))); render(); }, { passive: false });

  window.addEventListener("keydown", function (e) { if (e.key === "Escape") closePanel(); });
}

/* ================= 全局事件：atom 操作按钮 ================= */
document.addEventListener("click", function (e) {
  const btn = e.target && e.target.closest ? e.target.closest("[data-op]") : null;
  if (!btn) return;
  const atomId = parseInt(btn.getAttribute("data-atom-id"));
  const op = btn.getAttribute("data-op");
  const node = state.selectedNode;
  if (!node) return;
  if (op === "reinforce") { doReinforce(atomId); }
  else if (op === "forget") { openForgetModal(atomId); }
  else if (op === "importance") { state.imSliderId = atomId; state.imSliderVal = 0.5; renderAtomList(node, state.atoms); }
  else if (op === "imp-confirm") { doImportance(atomId, state.imSliderVal); }
  else if (op === "imp-cancel") { state.imSliderId = null; renderAtomList(node, state.atoms); }
});

/* ================= 二次确认弹框 ================= */
function openForgetModal(atomId) {
  const t = document.getElementById("modal-text");
  t.innerHTML = "确定对 <b style='color:#D9C49A'>atom #" + atomId + "</b> 执行软删除（<span style='color:#7FD3C0'>status &rarr; forgotten</span>）？此操作仅改状态，不物理删除。";
  const mask = document.getElementById("modalMask");
  mask.classList.add("open");
  mask.style.display = "flex";
  document.getElementById("modal-ok").onclick = function () {
    mask.classList.remove("open");
    mask.style.display = "none";
    doForget(atomId);
  };
}
function closeForgetModal() {
  const mask = document.getElementById("modalMask");
  mask.classList.remove("open");
  mask.style.display = "none";
}
document.getElementById("modal-cancel").addEventListener("click", closeForgetModal);
document.getElementById("modalMask").addEventListener("click", function (e) { if (e.target === this) closeForgetModal(); });

/* ================= 启动 ================= */
function start() {
  wireTopbar();
  wireCanvas();
  requestAnimationFrame(loop);
  const errEl = document.getElementById("errorMsg");
  apiGet("/api/graph").then(function (res) {
    if (res.status !== 200) {
      errEl.textContent = "GRAPH_NOT_FOUND: data/graph.json 不存在，请先运行 export_graph.py";
      errEl.style.display = "block";
      return;
    }
    return res.data;
  }).then(function (d) {
    GRAPH = d;
    if (GRAPH.nodes) { for (const n of GRAPH.nodes) nodeDir(n); }
    renderStatus();
    return apiGet("/api/health");
  }).then(function (res) {
    if (res.status === 200) {
      state.healthBackups = (res.data && res.data.backups) ? res.data.backups : 0;
      renderStatus();
    }
    return apiGet("/api/ops");
  }).then(function (res) {
    if (res.status === 200) {
      state.opsList = res.data || [];
      state.lastOp = state.opsList.length ? state.opsList[state.opsList.length - 1] : null;
      renderStatus();
    }
  }).catch(function (e) {
    errEl.textContent = "NETWORK_ERROR: 无法加载 /api/graph (" + (e && e.message ? e.message : "unknown") + ")";
    errEl.style.display = "block";
  });
}

start();
