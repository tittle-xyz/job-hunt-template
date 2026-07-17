"""The SQLite store.

The behaviour that matters most is dedup: ingestion runs repeatedly against feeds
that mostly repeat themselves. If re-running created duplicates, the database
would be useless within a week — and if it overwrote status, you'd lose your own
triage every time you fetched.
"""

import pytest

from job_hunt import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    db.init_db()


def add(conn, **overrides):
    """upsert + commit. upsert_job deliberately leaves the commit to its caller,
    so a whole source lands as one transaction; tests follow the same contract."""
    is_new = db.upsert_job(conn, a_job(**overrides))
    conn.commit()
    return is_new


def a_job(**overrides):
    job = {
        "source": "remoteok",
        "source_id": "1",
        "company": "Example Co",
        "title": "Senior DevOps Engineer",
        "location": "Remote",
        "salary_min": 150000,
        "salary_max": 190000,
        "url": "https://example.com/1",
        "description": "Own the platform.",
        "tags": ["devops", "aws"],
        "remote": True,
        "posted_at": "2026-07-15",
    }
    job.update(overrides)
    return job


def test_a_new_job_is_new():
    conn = db.get_connection()
    assert add(conn) is True


def test_the_same_job_twice_is_not_new():
    conn = db.get_connection()
    add(conn)
    assert add(conn) is False
    assert db.get_stats()["total"] == 1


def test_same_id_different_source_is_a_different_job():
    conn = db.get_connection()
    add(conn, source="remoteok", source_id="1")
    add(conn, source="remotive", source_id="1")
    assert db.get_stats()["total"] == 2


def test_reingesting_does_not_clobber_your_triage():
    """Your status is yours. A re-fetch must not reset it to 'new'."""
    conn = db.get_connection()
    add(conn)
    job_id = db.get_jobs()[0]["id"]
    db.update_status(job_id, "applied", "sent 2026-07-16")

    add(conn, title="Senior DevOps Engineer (updated)")

    job = db.get_jobs()[0]
    assert job["status"] == "applied"
    assert job["notes"] == "sent 2026-07-16"


def test_tags_round_trip_as_a_list():
    """Stored as JSON, handed back as a list — callers never see the encoding."""
    conn = db.get_connection()
    add(conn, tags=["devops", "k8s"])
    assert db.get_jobs()[0]["tags"] == ["devops", "k8s"]


def test_filters():
    conn = db.get_connection()
    add(conn, source_id="1", source="remoteok")
    add(conn, source_id="2", source="remotive")
    db.update_status(db.get_jobs(source="remoteok")[0]["id"], "applied")

    assert len(db.get_jobs(source="remoteok")) == 1
    assert len(db.get_jobs(status="applied")) == 1
    assert len(db.get_jobs(status="new")) == 1
    assert len(db.get_jobs(limit=1)) == 1


def test_stats_counts_by_status_and_source():
    conn = db.get_connection()
    add(conn, source_id="1", source="remoteok")
    add(conn, source_id="2", source="wwr")
    stats = db.get_stats()
    assert stats["total"] == 2
    assert stats["by_status"]["new"] == 2
    assert stats["by_source"] == {"remoteok": 1, "wwr": 1}


def test_fetch_log_records_a_run():
    conn = db.get_connection()
    db.log_fetch(conn, "remoteok", jobs_found=10, jobs_new=3)
    conn.commit()
    assert db.get_stats()["last_fetch"]["remoteok"]["total_new"] == 3


def test_missing_optional_fields_are_fine():
    conn = db.get_connection()
    assert add(
        conn, salary_min=None, salary_max=None, location=None, posted_at=None, description=None
    ) is True
