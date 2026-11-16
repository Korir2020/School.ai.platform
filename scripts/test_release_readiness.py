import tempfile
import unittest
from pathlib import Path

from scripts.release_readiness import SECRET, isolated_environment


class ReleaseReadinessIsolationTests(unittest.TestCase):
    def test_environment_drops_database_and_provider_secrets(self):
        source = {
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "DB_NAME": "production_db",
            "DB_PASSWORD": "do-not-forward",
            "DATABASE_URL": "postgres://production",
            "PGPASSWORD": "do-not-forward",
            "OPENAI_API_KEY": "do-not-forward",
            "ANTHROPIC_API_KEY": "do-not-forward",
            "STRIPE_SECRET_KEY": "do-not-forward",
            "DJANGO_SECRET_KEY": "inherited-secret",
            "NODE_OPTIONS": "--require injected.js",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            sqlite_path = Path(temporary_directory) / "tests.sqlite3"
            env = isolated_environment(source, sqlite_test_path=sqlite_path)

        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["HOME"], "/tmp/home")
        self.assertEqual(env["DJANGO_SECRET_KEY"], SECRET)
        self.assertEqual(env["MARIAN_TEST_SQLITE_PATH"], str(sqlite_path))
        for blocked in (
            "DB_NAME", "DB_PASSWORD", "DATABASE_URL", "PGPASSWORD", "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY", "STRIPE_SECRET_KEY", "NODE_OPTIONS",
        ):
            self.assertNotIn(blocked, env)

    def test_environment_enables_debug_only_for_local_verification(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = isolated_environment({}, sqlite_test_path=Path(temporary_directory) / "test.sqlite3")
        self.assertEqual(env["DJANGO_DEBUG"], "True")
        self.assertEqual(env["DJANGO_ALLOWED_HOSTS"], "testserver,localhost,127.0.0.1")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")


if __name__ == "__main__":
    unittest.main()
