# === history.py ===
# Lịch sử tác vụ & tài liệu đã xử lý (SQLite): thống kê cho Tổng quan, tìm theo tên và toàn văn OCR,
# lọc theo ngày / loại / trạng thái, gắn nhãn.

import os
import sqlite3
import threading
import time

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created REAL NOT NULL,
    kind TEXT NOT NULL,            -- ocr | split | batch | pdf
    name TEXT NOT NULL,
    source TEXT,
    pages INTEGER DEFAULT 0,
    status TEXT NOT NULL,          -- done | error | cancelled
    seconds REAL DEFAULT 0,
    engine TEXT,
    confidence REAL,
    outputs TEXT,                  -- các file đầu ra, mỗi dòng 1 đường dẫn
    doc_count INTEGER DEFAULT 0,   -- số văn bản (tách AI)
    tags TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    text TEXT DEFAULT ''           -- toàn văn OCR (để tìm kiếm); để trống nếu tắt lưu nội dung
);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created);
"""

KIND_LABELS = {"ocr": "OCR tài liệu", "split": "Tách AI", "batch": "Hàng loạt", "pdf": "Cắt / ghép PDF"}


class History:
    def __init__(self, path=config.HISTORY_DB):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def add(self, kind, name, source="", pages=0, status="done", seconds=0, engine="", confidence=None,
            outputs=(), doc_count=0, detail="", text=""):
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO tasks(created,kind,name,source,pages,status,seconds,engine,confidence,outputs,"
                "doc_count,detail,text) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), kind, name, source, pages, status, seconds, engine, confidence,
                 "\n".join(outputs), doc_count, detail, text))
            self.db.commit()
            return cur.lastrowid

    def search(self, query="", kind="", status="", days=0, limit=300):
        sql, args = "SELECT * FROM tasks WHERE 1=1", []
        if query:
            sql += " AND (name LIKE ? OR text LIKE ? OR tags LIKE ?)"
            args += [f"%{query}%"] * 3
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if status:
            sql += " AND status=?"
            args.append(status)
        if days:
            sql += " AND created>=?"
            args.append(time.time() - days * 86400)
        sql += " ORDER BY created DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self.db.execute(sql, args).fetchall()
        return [self._row(r, snippet_for=query) for r in rows]

    @staticmethod
    def _row(r, snippet_for=""):
        d = dict(r)
        d["kind_label"] = KIND_LABELS.get(d["kind"], d["kind"])
        d["outputs"] = [o for o in (d["outputs"] or "").splitlines() if o]
        text = d.pop("text") or ""
        d["snippet"] = ""
        if snippet_for and snippet_for.lower() in text.lower():
            i = text.lower().index(snippet_for.lower())
            d["snippet"] = ("…" if i > 40 else "") + text[max(0, i - 40):i + 80].replace("\n", " ") + "…"
        return d

    def get(self, task_id):
        with self._lock:
            r = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["kind_label"] = KIND_LABELS.get(d["kind"], d["kind"])
        d["outputs"] = [o for o in (d["outputs"] or "").splitlines() if o]
        return d

    def update(self, task_id, **fields):
        allowed = {k: v for k, v in fields.items() if k in ("name", "tags", "status", "outputs")}
        if "outputs" in allowed and isinstance(allowed["outputs"], (list, tuple)):
            allowed["outputs"] = "\n".join(allowed["outputs"])
        if not allowed:
            return
        with self._lock:
            self.db.execute(f"UPDATE tasks SET {', '.join(k + '=?' for k in allowed)} WHERE id=?",
                            (*allowed.values(), task_id))
            self.db.commit()

    def delete(self, task_id):
        with self._lock:
            self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            self.db.commit()

    def purge(self, days):
        if days and days > 0:
            with self._lock:
                self.db.execute("DELETE FROM tasks WHERE created<?", (time.time() - days * 86400,))
                self.db.commit()

    def stats(self):
        with self._lock:
            r = self.db.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(pages),0) pages, "
                "SUM(status='done') ok, SUM(status='error') err, AVG(confidence) conf, "
                "COALESCE(SUM(doc_count),0) docs FROM tasks").fetchone()
        return {"tasks": r["n"], "pages": r["pages"], "done": r["ok"] or 0, "errors": r["err"] or 0,
                "confidence": round(r["conf"] * 100, 1) if r["conf"] is not None else None,
                "split_docs": r["docs"]}
