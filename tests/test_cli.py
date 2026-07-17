"""The `job-hunt` command.

Coverage put cli.py at 0% while the rest of the suite was healthy — these are the
commands a user touches every day, and nothing exercised them. That's exactly the
gap a coverage number is for.

These go through `main(argv)` rather than calling the command functions directly,
so argument parsing and dispatch are covered too.
"""

import pytest

from job_hunt import __main__, db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    db.init_db()


@pytest.fixture
def a_job():
    conn = db.get_connection()
    db.upsert_job(conn, {
        "source": "wwr", "source_id": "1", "company": "Example Co",
        "title": "Senior DevOps Engineer", "location": "Remote",
        "salary_min": 150000, "salary_max": 190000,
        "url": "https://example.com/1", "description": "Own the platform.",
        "tags": ["devops"], "remote": True, "posted_at": "2026-07-15",
    })
    conn.commit()
    conn.close()
    return db.get_jobs()[0]["id"]


def run(*argv):
    return __main__.main(list(argv))


# --------------------------------------------------------------------------

def test_no_command_prints_help(capsys):
    assert run() == 0
    assert "job-hunt" in capsys.readouterr().out


def test_help_lists_every_command(capsys):
    """One command, one --help. ingest and resume are grafted on in __main__."""
    with pytest.raises(SystemExit):
        run("--help")
    out = capsys.readouterr().out
    for cmd in ("list", "show", "status", "stats", "search", "ingest", "resume"):
        assert cmd in out


def test_list(a_job, capsys):
    assert run("list") == 0
    out = capsys.readouterr().out
    assert "Senior DevOps Engineer" in out
    assert "Example Co" in out


def test_list_on_an_empty_db_says_so(capsys):
    assert run("list") == 0
    assert "No jobs found" in capsys.readouterr().out


def test_show(a_job, capsys):
    assert run("show", str(a_job)) == 0
    out = capsys.readouterr().out
    assert "Senior DevOps Engineer" in out
    assert "https://example.com/1" in out


def test_show_a_missing_job_does_not_explode(capsys):
    assert run("show", "9999") == 0
    assert "not found" in capsys.readouterr().out


def test_status_updates_and_persists(a_job, capsys):
    assert run("status", str(a_job), "applied", "--notes", "referred by Sam") == 0
    job = db.get_jobs()[0]
    assert job["status"] == "applied"
    assert job["notes"] == "referred by Sam"


def test_status_rejects_a_bogus_value(a_job, capsys):
    """Free-text status would silently create a state nothing else knows about."""
    run("status", str(a_job), "banana")
    assert "Invalid status" in capsys.readouterr().out
    assert db.get_jobs()[0]["status"] == "new"


def test_list_filters_by_status(a_job, capsys):
    run("status", str(a_job), "applied")
    capsys.readouterr()

    assert run("list", "--status", "applied") == 0
    assert "Senior DevOps Engineer" in capsys.readouterr().out

    assert run("list", "--status", "new") == 0
    assert "No jobs found" in capsys.readouterr().out


def test_search(a_job, capsys):
    assert run("search", "devops") == 0
    assert "Senior DevOps Engineer" in capsys.readouterr().out


def test_search_with_no_hits(a_job, capsys):
    assert run("search", "underwater basket weaving") == 0
    assert "No jobs matching" in capsys.readouterr().out


def test_stats(a_job, capsys):
    assert run("stats") == 0
    out = capsys.readouterr().out
    assert "Total jobs: 1" in out
    assert "wwr" in out


def test_resume_without_a_profile_explains_itself(capsys):
    """The most likely first mistake gets the most useful message."""
    rc = run("resume", "platform", "--profile", "/nonexistent")
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_resume_builds_from_the_example(tmp_path, capsys):
    import shutil
    if not shutil.which("typst"):
        pytest.skip("typst not installed")
    out = tmp_path / "r.pdf"
    rc = run("resume", "platform", "--profile", "profile.example", "-o", str(out))
    assert rc == 0
    assert out.exists()
