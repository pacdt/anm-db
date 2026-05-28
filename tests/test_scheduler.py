import pytest
import tempfile
import os
from db import DatabaseManager


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
async def db(db_path):
    database = DatabaseManager(db_path)
    await database.init_db()
    yield database
    await database.close()


async def test_scheduler_import():
    from scheduler import create_scheduler
    scheduler = create_scheduler()
    assert scheduler is not None
    jobs = scheduler.get_jobs()
    job_ids = [j.id for j in jobs]
    assert "jikan_sync" in job_ids
    assert "episode_scan" in job_ids


async def test_main_import():
    from main import main
    assert callable(main)


async def test_db_path_env():
    os.environ["DB_PATH"] = "/tmp/test_env.db"
    from db import DatabaseManager
    db = DatabaseManager()
    assert db.db_path == "/tmp/test_env.db"
    os.environ.pop("DB_PATH", None)
