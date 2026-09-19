"""SQLite transactions enforce assignment, approval, and capacity invariants."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12].upper()


@contextmanager
def db(write=False):
    connection = sqlite3.connect(config.DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    try:
        if write:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO metadata VALUES('schema_version','1');
        CREATE TABLE IF NOT EXISTS engineers(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, team TEXT NOT NULL,
          skills TEXT NOT NULL, available INTEGER NOT NULL CHECK(available IN (0,1)),
          on_call INTEGER NOT NULL CHECK(on_call IN (0,1)),
          baseline_load INTEGER NOT NULL CHECK(baseline_load>=0),
          capacity INTEGER NOT NULL CHECK(capacity>0));
        CREATE TABLE IF NOT EXISTS incidents(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
          product TEXT NOT NULL, component TEXT NOT NULL, team TEXT NOT NULL,
          category TEXT NOT NULL, severity TEXT NOT NULL,
          resolved_by TEXT NOT NULL REFERENCES engineers(id),
          root_cause TEXT NOT NULL, resolution TEXT NOT NULL,
          resolution_minutes INTEGER NOT NULL CHECK(resolution_minutes>0));
        CREATE TABLE IF NOT EXISTS tickets(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
          severity TEXT NOT NULL, team TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          recommendation TEXT, session_id TEXT, turn_id TEXT,
          agent_output TEXT NOT NULL DEFAULT '', error TEXT,
          events TEXT NOT NULL DEFAULT '[]', run_started REAL,
          version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS approvals(
          ticket_id TEXT PRIMARY KEY REFERENCES tickets(id), engineer_id TEXT NOT NULL REFERENCES engineers(id),
          actor TEXT NOT NULL, expires_at REAL NOT NULL, recommendation_version INTEGER NOT NULL,
          consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0,1)));
        CREATE TABLE IF NOT EXISTS assignments(
          ticket_id TEXT PRIMARY KEY REFERENCES tickets(id), engineer_id TEXT NOT NULL REFERENCES engineers(id),
          approved_by TEXT NOT NULL, assigned_at TEXT NOT NULL, completed_at TEXT);
        CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
          actor TEXT NOT NULL, action TEXT NOT NULL, ticket_id TEXT, details TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS incidents_resolver ON incidents(resolved_by);
        CREATE INDEX IF NOT EXISTS assignments_engineer ON assignments(engineer_id,completed_at);
        """)


def audit(c, actor, action, ticket_id=None, details=None):
    c.execute(
        "INSERT INTO audit(timestamp,actor,action,ticket_id,details) VALUES(?,?,?,?,?)",
        (now(), actor, action, ticket_id, json.dumps(details or {})),
    )


def engineer_rows(c):
    rows = c.execute("""SELECT e.*, e.baseline_load +
       (SELECT COUNT(*) FROM assignments a WHERE a.engineer_id=e.id AND a.completed_at IS NULL) AS active_tickets,
       (SELECT COUNT(*) FROM incidents i WHERE i.resolved_by=e.id) AS resolved_count
       FROM engineers e ORDER BY e.name""").fetchall()
    return [
        {
            **dict(r),
            "skills": json.loads(r["skills"]),
            "available": bool(r["available"]),
            "on_call": bool(r["on_call"]),
        }
        for r in rows
    ]


def ticket_row(c, ticket_id):
    row = c.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if row is None:
        raise ValueError("Ticket not found")
    result = dict(row)
    result["recommendation"] = (
        json.loads(result["recommendation"]) if result["recommendation"] else None
    )
    result["events"] = json.loads(result["events"])
    assignment = c.execute(
        "SELECT a.*,e.name FROM assignments a JOIN engineers e ON e.id=a.engineer_id WHERE ticket_id=?",
        (ticket_id,),
    ).fetchone()
    result["assignment"] = dict(assignment) if assignment else None
    return result
