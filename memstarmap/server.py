# -*- coding: utf-8 -*-
"""记忆星图 MEMORY STARMAP — local web server (Python 3.12, stdlib only).

Endpoints:
  GET  /               -> static files (index.html / app.js / style.css / data/graph.json)
  GET  /api/graph      -> data/graph.json content
  GET  /api/atoms?node=<node_id>&limit=8
  POST /api/atom/forget    {"id": 123}
  POST /api/atom/reinforce {"id": 123}
  POST /api/atom/importance {"id": 123, "value": 0.6}
  GET  /api/ops
  GET  /api/health

Writes are soft-only: status / reinforcement_count / ttl_days / expires_at /
last_reinforced_at / confidence / importance on memory_atoms. No physical DELETE.
Every write is preceded by a VACUUM INTO backup (max 20 kept) inside a short
BEGIN IMMEDIATE transaction, then appended to ops.log.
"""

import json
import os
import sqlite3
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = r"D:\deepseek harness\astrbot-lab\AstrBot\data\plugin_data\astrbot_plugin_livingmemory\livingmemory.db"
GRAPH_PATH = os.path.join(BASE_DIR, "data", "graph.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
OPS_LOG = os.path.join(BASE_DIR, "ops.log")
MAX_BACKUPS = 20
HOST = "127.0.0.1"
PORT = 8772

ATOM_SELECT = ("id, atom_type, content, importance, confidence, ttl_days, "
               "expires_at, status, reinforcement_count, decay_type")

BASE = {
    "episodic": 7,
    "planned": 2,
    "factual": 180,
    "relational": 90,
    "preference": 60,
    "unknown": 30,
}


# ───────────────────────── helpers ──────────────────────────

def backup():
    """VACUUM INTO backup, keep at most MAX_BACKUPS files."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(BACKUP_DIR, "livingmemory-%s.db" % ts)
    n = 0
    while os.path.exists(path):
        n += 1
        path = os.path.join(BACKUP_DIR, "livingmemory-%s-%d.db" % (ts, n))
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    try:
        conn.execute("VACUUM INTO ?", (path,))
    finally:
        conn.close()
    try:
        files = sorted(
            f for f in os.listdir(BACKUP_DIR)
            if f.startswith("livingmemory-") and f.endswith(".db")
        )
        while len(files) > MAX_BACKUPS:
            victim = files.pop(0)
            try:
                os.remove(os.path.join(BACKUP_DIR, victim))
            except OSError:
                pass
    except OSError:
        pass
    return path


def append_ops(action, atom_id, before, after):
    rec = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "atom_id": atom_id,
        "before": before,
        "after": after,
    }
    with open(OPS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


def read_ops(limit=50):
    ops = []
    if not os.path.exists(OPS_LOG):
        return ops
    with open(OPS_LOG, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    for ln in lines[-limit:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            ops.append(json.loads(ln))
        except Exception:
            ops.append({"ts": ln, "action": "unknown", "atom_id": None, "before": {}, "after": {}})
    return ops


def health():
    atoms = 0
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        atoms = int(conn.execute("SELECT COUNT(*) FROM memory_atoms").fetchone()[0])
        conn.close()
    except Exception:
        pass
    backups = 0
    try:
        if os.path.isdir(BACKUP_DIR):
            backups = len([
                f for f in os.listdir(BACKUP_DIR)
                if f.startswith("livingmemory-") and f.endswith(".db")
            ])
    except Exception:
        pass
    return {"ok": True, "atoms": atoms, "backups": backups}


def get_atoms_for_node(node_id, limit=8):
    """atoms whose content contains node value[:12], status='active',
    ordered by importance DESC, max `limit` rows. Returns list."""
    try:
        node_id = int(node_id)
    except Exception:
        return []
    try:
        limit = max(1, min(50, int(limit or 8)))
    except Exception:
        limit = 8
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, node_value, node_type FROM graph_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return []
        value = row["node_value"] or ""
        prefix = value[:12]
        atoms = []
        if prefix:
            sql = ("SELECT %s FROM memory_atoms "
                   "WHERE status = 'active' AND content LIKE ? "
                   "ORDER BY importance DESC LIMIT ?") % ATOM_SELECT
            for r in conn.execute(sql, ("%{}%".format(prefix), limit)):
                exp = float(r["expires_at"] or 0.0)
                atoms.append({
                    "id": int(r["id"]),
                    "atom_type": r["atom_type"],
                    "content": r["content"],
                    "importance": float(r["importance"] or 0.5),
                    "confidence": float(r["confidence"] or 0.7),
                    "ttl_days": float(r["ttl_days"] or 30.0),
                    "expires_at": exp,
                    "left_days": round((exp - time.time()) / 86400.0, 1),
                    "status": r["status"],
                    "reinforcement_count": int(r["reinforcement_count"] or 0),
                    "decay_type": r["decay_type"],
                })
        return atoms
    finally:
        conn.close()


# ───────────────────────── write ops ────────────────────────

def op_forget(atom_id):
    before_status = None
    backup()
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status FROM memory_atoms WHERE id = ?", (atom_id,)
        ).fetchone()
        before_status = row[0] if row else None
        cur = conn.execute(
            "UPDATE memory_atoms SET status = 'forgotten' WHERE id = ?",
            (atom_id,),
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    append_ops("forget", atom_id, {"status": before_status}, {"status": "forgotten"})
    ok = cur.rowcount > 0
    return {"ok": ok, "action": "forget", "atom_id": atom_id,
            "before": {"status": before_status}, "after": {"status": "forgotten"},
            "rowcount": cur.rowcount}


def op_reinforce(atom_id):
    backup()
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.isolation_level = None
    before = {}
    after = {}
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT atom_type, importance, confidence, reinforcement_count,
                      ttl_days, expires_at
                 FROM memory_atoms WHERE id = ?""",
            (atom_id,),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return {"ok": False, "error": "atom not found: %d" % atom_id}
        atom_type, importance, confidence, reinf, ttl, exp = row
        base = BASE.get(atom_type, 30)
        new_reinf = int(reinf or 0) + 1
        ttl_new = max(1.0, base * (0.5 + float(importance or 0.5)) * (1 + min(0.5, new_reinf * 0.1)))
        expires_new = time.time() + ttl_new * 86400
        new_conf = min(1.0, float(confidence or 0.7) + 0.05)
        conn.execute(
            """UPDATE memory_atoms
                  SET reinforcement_count = ?, ttl_days = ?, expires_at = ?,
                      last_reinforced_at = ?, confidence = MIN(1.0, confidence + 0.05)
                WHERE id = ?""",
            (new_reinf, ttl_new, expires_new, time.time(), atom_id),
        )
        conn.execute("COMMIT")
        before = {"reinforcement_count": int(reinf or 0), "ttl_days": float(ttl or 0.0),
                  "expires_at": float(exp or 0.0), "confidence": float(confidence or 0.7)}
        after = {"reinforcement_count": new_reinf, "ttl_days": ttl_new, "expires_at": expires_new,
                 "confidence": new_conf}
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    append_ops("reinforce", atom_id, before, after)
    return {"ok": True, "action": "reinforce", "atom_id": atom_id, "before": before, "after": after}


def op_importance(atom_id, value):
    try:
        new_imp = min(1.0, max(0.01, float(value)))
    except Exception:
        return {"ok": False, "error": "invalid importance value"}
    backup()
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.isolation_level = None
    before = {}
    after = {}
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT atom_type, reinforcement_count, importance, ttl_days, expires_at
                 FROM memory_atoms WHERE id = ?""",
            (atom_id,),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return {"ok": False, "error": "atom not found: %d" % atom_id}
        atom_type, reinf, imp, ttl, exp = row
        base = BASE.get(atom_type, 30)
        ttl_new = max(1.0, base * (0.5 + new_imp) * (1 + min(0.5, int(reinf or 0) * 0.1)))
        expires_new = time.time() + ttl_new * 86400
        conn.execute(
            "UPDATE memory_atoms SET importance = ?, ttl_days = ?, expires_at = ? WHERE id = ?",
            (new_imp, ttl_new, expires_new, atom_id),
        )
        conn.execute("COMMIT")
        before = {"importance": float(imp or 0.5), "ttl_days": float(ttl or 0.0),
                  "expires_at": float(exp or 0.0), "reinforcement_count": int(reinf or 0)}
        after = {"importance": new_imp, "ttl_days": ttl_new, "expires_at": expires_new}
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    append_ops("importance", atom_id, before, after)
    return {"ok": True, "action": "importance", "atom_id": atom_id, "before": before, "after": after}


# ───────────────────────── http handler ─────────────────────

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MemoryStarMap/1.0"

    # ── low level ──
    def _send_bytes(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send_bytes(code, "application/json; charset=utf-8", body)

    def _send_file(self, path, fallback_code=404):
        ctype = MIME.get(os.path.splitext(path)[1], "application/octet-stream")
        with open(path, "rb") as f:
            body = f.read()
        self._send_bytes(200, ctype, body)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    # ── GET ──
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            return self._send_file(os.path.join(BASE_DIR, "index.html"))
        if path == "/style.css":
            return self._send_file(os.path.join(BASE_DIR, "style.css"))
        if path == "/app.js":
            return self._send_file(os.path.join(BASE_DIR, "app.js"))
        if path == "/data/graph.json":
            if not os.path.exists(GRAPH_PATH):
                return self._send_json(404, {"ok": False, "error": "GRAPH_NOT_FOUND: run export_graph.py first"})
            return self._send_file(GRAPH_PATH)
        if path == "/api/graph":
            if not os.path.exists(GRAPH_PATH):
                return self._send_json(404, {"ok": False, "error": "GRAPH_NOT_FOUND: run export_graph.py first"})
            with open(GRAPH_PATH, "rb") as f:
                body = f.read()
            return self._send_bytes(200, "application/json; charset=utf-8", body)
        if path == "/api/health":
            return self._send_json(200, health())
        if path == "/api/ops":
            return self._send_json(200, read_ops())
        if path == "/api/atoms":
            qs = parse_qs(parsed.query)
            node_id = (qs.get("node") or ["0"])[0]
            limit = (qs.get("limit") or ["8"])[0]
            atoms = get_atoms_for_node(node_id, limit)
            return self._send_json(200, atoms)
        return self._send_json(404, {"ok": False, "error": "not found"})

    # ── POST ──
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()
        if path == "/api/atom/forget":
            try:
                atom_id = int(body.get("id") or 0)
            except Exception:
                atom_id = 0
            return self._send_json(200, op_forget(atom_id))
        if path == "/api/atom/reinforce":
            try:
                atom_id = int(body.get("id") or 0)
            except Exception:
                atom_id = 0
            return self._send_json(200, op_reinforce(atom_id))
        if path == "/api/atom/importance":
            try:
                atom_id = int(body.get("id") or 0)
            except Exception:
                atom_id = 0
            return self._send_json(200, op_importance(atom_id, body.get("value")))
        return self._send_json(404, {"ok": False, "error": "not found"})

    # ── unsupported ──
    def do_PUT(self):
        return self._send_json(405, {"ok": False, "error": "method not allowed"})

    def do_DELETE(self):
        return self._send_json(405, {"ok": False, "error": "method not allowed"})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("MEMORY STARMAP server listening on http://%s:%d/" % (HOST, PORT), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
