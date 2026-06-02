"""
Testes do scheduler: jobs + create_scheduler.
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def test_scheduler_import():
    """create_scheduler funciona e tem 4 jobs."""
    from scheduler import create_scheduler
    scheduler = create_scheduler()
    jobs = scheduler.get_jobs()
    job_ids = [j.id for j in jobs]
    assert "jikan_sync" in job_ids
    assert "episode_scan" in job_ids
    assert "backfill_skip_times" in job_ids
    assert "missing_scan_translate" in job_ids
    assert len(jobs) == 4


def test_main_import():
    from main import main
    assert callable(main)


async def test_db_path_env():
    os.environ["DB_PATH"] = "/tmp/test_env.db"
    from anm_db.config import reload_settings
    reload_settings()
    from db import DatabaseManager
    db = DatabaseManager()
    assert db.db_path == "/tmp/test_env.db"
    os.environ.pop("DB_PATH", None)
    reload_settings()


def test_jobs_module_exports():
    from anm_db.scheduler import jobs
    assert callable(jobs.sync_jikan_job)
    assert callable(jobs.scan_ongoing_episodes)
    assert callable(jobs.backfill_skip_times_job)
    assert callable(jobs.missing_scan_translate_job)
    assert callable(jobs.create_scheduler)


def test_missing_scan_translate_uses_missing_scanner(db):
    """O job missing_scan_translate deve usar o MissingEpisodeScanner."""
    from anm_db.scheduler import jobs
    from anm_db.services.missing_scanner import MissingEpisodeScanner

    # Mocka ambos os servicos para evitar chamadas reais
    with patch.object(MissingEpisodeScanner, "scan", new_callable=AsyncMock) as mock_scan:
        mock_scan.return_value = MagicMock(
            total_scanned=0, without_eps=0, with_gaps=0,
            stale_finished=0, eps_added=0, cdn_hits=0, af_fallbacks=0,
        )
        # Executa o job (sem Gemini configurado, so roda o scan)
        asyncio.run(jobs.missing_scan_translate_job())

    assert mock_scan.called


def test_missing_scan_translate_skips_translation_without_api_key(db, monkeypatch):
    """Sem GEMINI_API_KEY, o job pula a traducao."""
    from anm_db.config import get_settings, reload_settings
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    reload_settings()

    from anm_db.scheduler import jobs
    from anm_db.services.missing_scanner import MissingEpisodeScanner

    with patch.object(MissingEpisodeScanner, "scan", new_callable=AsyncMock) as mock_scan:
        mock_scan.return_value = MagicMock(
            total_scanned=0, without_eps=0, with_gaps=0,
            stale_finished=0, eps_added=0, cdn_hits=0, af_fallbacks=0,
        )
        # Nao deve levantar mesmo sem API key
        asyncio.run(jobs.missing_scan_translate_job())

    assert mock_scan.called


def test_create_scheduler_jobs_have_cron_triggers():
    """Todos os jobs tem triggers cron."""
    from scheduler import create_scheduler
    scheduler = create_scheduler()
    for job in scheduler.get_jobs():
        assert job.trigger is not None
        # CronTrigger tem hora/minuto/dia
        assert hasattr(job.trigger, "fields")


def test_missing_scan_translate_runs_sunday_3am():
    """Job de traducao roda domingo 03:00."""
    from scheduler import create_scheduler
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "missing_scan_translate")
    trigger = job.trigger
    fields = {f.name: str(f) for f in trigger.fields}
    assert "3" in fields["hour"] or fields["hour"] == "3"
    assert "sun" in fields["day_of_week"].lower() or fields["day_of_week"] == "0"
