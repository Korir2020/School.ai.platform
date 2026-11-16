#!/usr/bin/env python3
"""Rehearse SQLite backup/restore without touching the project database.

This is a local verification aid, not a production backup implementation. The
production database remains PostgreSQL and must use an operator-approved backup
provider and restore procedure.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="marian-activity20-") as directory:
        source = Path(directory) / "source.sqlite3"
        backup = Path(directory) / "backup.sqlite3"
        restored = Path(directory) / "restored.sqlite3"
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE release_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT INTO release_probe(value) VALUES (?)", ("activity20",))
            db.commit()
            with sqlite3.connect(backup) as copy:
                db.backup(copy)
        with sqlite3.connect(backup) as db, sqlite3.connect(restored) as copy:
            db.backup(copy)
        with sqlite3.connect(restored) as db:
            row = db.execute("SELECT value FROM release_probe WHERE id=1").fetchone()
            assert row == ("activity20",), row
    print("Disposable SQLite backup/restore rehearsal passed; no application database was touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
