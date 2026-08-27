import os
import subprocess
import sys
from pathlib import Path


def test_worker_entrypoint_loads_complete_model_registry(tmp_path: Path) -> None:
    """The standalone worker must configure ORM relationships without importing FastAPI."""
    project_root = Path(__file__).resolve().parents[2]
    database = tmp_path / "worker-startup.sqlite3"
    environment = {
        **os.environ,
        "CARHIBOU_DATABASE_URL": f"sqlite:///{database}",
        "CARHIBOU_LOG_LEVEL": "WARNING",
    }
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert migration.returncode == 0, migration.stderr

    worker = subprocess.run(
        [sys.executable, "-m", "backend.app.worker", "--once"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert worker.returncode == 0, worker.stderr
