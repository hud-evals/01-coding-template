"""Hidden tests for rule priority — mirrors Haocheng's bug report pattern."""
import os
import sys
import sqlite3
import pytest

REPO_ROOT = os.environ.get("AST_PILOT_REPO_ROOT", "/home/ubuntu/workspace")
sys.path.insert(0, REPO_ROOT)

from rules import init_db, add_rule, priority_first_triggered


class TestRulePriorityOrder:
    def test_in_memory_priority_first_triggered_wins(self, tmp_path):
        db = str(tmp_path / "t.db")
        conn = init_db(db)
        add_rule(conn, "R1", "2026-01-01", "2026-12-31")
        add_rule(conn, "R2", "2026-06-01", "2026-06-30")
        assert priority_first_triggered(conn, "2026-06-15") == "R1"
