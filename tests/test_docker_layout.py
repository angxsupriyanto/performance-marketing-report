"""The Docker daemon is not needed: copy exactly what the Dockerfile copies into an empty folder and run the service code there."""
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_service import csv_text  # noqa: E402
from test_table_mode import LEADS  # noqa: E402


def copied_paths():
    sources = []
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts and parts[0] == "COPY" and not any(p.startswith("--") for p in parts[1:]):
            sources.extend(parts[1:-1])
    return sources


class DockerLayoutTests(unittest.TestCase):
    def test_dockerignore_does_not_exclude_anything_the_image_copies(self):
        ignored = {line.strip().rstrip("/") for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}
        for source in copied_paths():
            self.assertNotIn(source.rstrip("/"), ignored, source)
            self.assertTrue((ROOT / source).exists(), source)

    def test_service_runs_from_only_the_copied_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp)
            for source in copied_paths():
                target = app / source
                if (ROOT / source).is_dir():
                    shutil.copytree(ROOT / source, target, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(ROOT / source, target)
            code = "import sys; from service import server; r = server.generate(sys.stdin.buffer.read(), 'bu2', '2026-W39', False); print(r['audit']['metrics']['now']['SQL Value'], len(r['html']) > 1000)"
            result = subprocess.run([sys.executable, "-c", code], input=csv_text(LEADS), capture_output=True, cwd=app, env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"}, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout.decode().strip(), "8000000 True")

    def test_dockerfile_follows_the_security_basics(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^USER report$")
        self.assertIn("HEALTHCHECK", text)
        self.assertNotRegex(text, r"(?i)password|token\s*=|secret\s*=")
        compose = (ROOT / "deploy" / "docker-compose.report-service.example.yml").read_text(encoding="utf-8")
        self.assertNotRegex(compose, r"(?m)^\s+ports:")
        for setting in ("read_only: true", "no-new-privileges:true", "cap_drop"):
            self.assertIn(setting, compose)


if __name__ == "__main__":
    unittest.main()
