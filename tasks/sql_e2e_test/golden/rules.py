"""Rule priority logic with SQLite backing."""
import os
import sqlite3
from pathlib import Path


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize a SQLite DB by applying schema.sql from the repo root."""
    conn = sqlite3.connect(db_path)
    with open(os.path.join(REPO_ROOT, "schema.sql")) as f:
        conn.executescript(f.read())
    return conn


def add_rule(conn: sqlite3.Connection, rule_id: str, start_date: str, end_date: str) -> None:
    conn.execute(
        "INSERT INTO rules(rule_id, start_date, end_date) VALUES (?, ?, ?)",
        (rule_id, start_date, end_date),
    )
    conn.commit()


def priority_first_triggered(conn: sqlite3.Connection, date: str) -> str | None:
    cur = conn.execute(
        "SELECT rule_id FROM rules WHERE start_date <= ? AND end_date >= ? ORDER BY start_date LIMIT 1",
        (date, date),
    )
    row = cur.fetchone()
    return row[0] if row else None
