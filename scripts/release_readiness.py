#!/usr/bin/env python3
"""Run reproducible local checks without production database or provider access.

The runner passes a minimal environment to every subprocess, removes inherited
credentials/configuration, and puts Django's test database in a temporary folder.
It does not connect to, migrate, back up, or delete a production database.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
SECRET = "activity20-local-verification-secret-012345678901234567890123456789"
SAFE_ENV_KEYS = {
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP",
    "PYTHONPATH", "VIRTUAL_ENV", "SYSTEMROOT", "WINDIR",
}


def isolated_environment(source: dict[str, str] | None = None, *, sqlite_test_path: Path) -> dict[str, str]:
    """Return only benign runtime variables; never forward DB/provider credentials."""
    source = os.environ if source is None else source
    env = {key: value for key, value in source.items() if key in SAFE_ENV_KEYS}
    env.update({
        "DJANGO_SECRET_KEY": SECRET,
        "DJANGO_DEBUG": "True",
        "DJANGO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "MARIAN_TEST_SQLITE_PATH": str(sqlite_test_path),
    })
    return env


def run(label: str, command: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(f"\n== {label} ==", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def compile_python_sources() -> None:
    """Syntax-check source without writing __pycache__ or .pyc files."""
    roots = [BACKEND / name for name in ("api", "config", "learning", "schools")]
    roots.append(ROOT / "scripts")
    count = 0
    for source_root in roots:
        for source in sorted(source_root.rglob("*.py")):
            if any(part in {"__pycache__", ".venv", "venv"} for part in source.parts):
                continue
            compile(source.read_text(encoding="utf-8"), str(source), "exec")
            count += 1
    print(f"Python syntax check passed for {count} source files (no bytecode written).", flush=True)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="marian-activity20-") as temporary_directory:
        isolated_sqlite = Path(temporary_directory) / "learning-test.sqlite3"
        env = isolated_environment(sqlite_test_path=isolated_sqlite)
        run("Release-runner environment isolation tests", [sys.executable, "-m", "scripts.test_release_readiness"], ROOT, env)
        run("Django system checks", [sys.executable, "manage.py", "check"], BACKEND, env)
        run("Migration drift check", [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"], BACKEND, env)
        run("Activity 18–19 regression tests", [sys.executable, "manage.py", "test", "learning.test_activity18_19", "--verbosity=1"], BACKEND, env)
        run("Learning-domain regression tests", [sys.executable, "manage.py", "test", "learning", "--verbosity=1"], BACKEND, env)
        run("Disposable SQLite backup/restore rehearsal", [sys.executable, str(ROOT / "scripts" / "sqlite_backup_restore_rehearsal.py")], ROOT, env)
        compile_python_sources()
        if (FRONTEND / "node_modules").exists():
            run("Frontend tests", ["npm", "test"], FRONTEND, env)
            run("Frontend lint", ["npm", "run", "lint"], FRONTEND, env)
            run("Frontend production build", ["npm", "run", "build"], FRONTEND, env)
        else:
            print("\n== Frontend checks ==\nSKIPPED: install frontend dependencies first with npm ci", flush=True)
    print(
        "\nActivity 20 local verification completed. Checks used a temporary SQLite test database and no inherited database/provider credentials. "
        "Production PostgreSQL, provider, rights/publishing, backup, restore, device, and operational gates remain explicit release requirements.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
