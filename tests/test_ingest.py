"""Fetchers, against recorded responses.

Every fixture in tests/fixtures/ is a real response, trimmed. That matters: these
APIs return shapes nobody would invent — RemoteOK leads with a legal notice rather
than a job, and serves double-encoded text. Fixtures keep those quirks in the
suite without making CI depend on a third party being up at 3am.

The one synthetic entry is labelled as such in remoteok.json: the live feed had no
infrastructure job to record when it was captured, which is itself the finding
that motivated title-only filtering.
"""

import pytest

from job_hunt import ingest


# --------------------------------------------------------------------------
# remoteok
# --------------------------------------------------------------------------

def test_remoteok_keeps_infra_and_drops_noise(http, fixture_bytes):
    http({"remoteok.com/api": fixture_bytes("remoteok.json")})
    jobs = ingest.fetch_remoteok()

    titles = [j["title"] for j in jobs]
    assert "Senior DevOps Engineer" in titles
    # Matched only because its description said "infrastructure".
    assert not any("Product Director" in t for t in titles)


def test_remoteok_skips_the_legal_notice(http, fixture_bytes):
    """RemoteOK's feed opens with a legal notice, not a job."""
    http({"remoteok.com/api": fixture_bytes("remoteok.json")})
    jobs = ingest.fetch_remoteok()
    assert all(j.get("company") for j in jobs)
    assert not any("legal" in (j["title"] or "").lower() for j in jobs)


def test_remoteok_maps_fields(http, fixture_bytes):
    http({"remoteok.com/api": fixture_bytes("remoteok.json")})
    job = next(j for j in ingest.fetch_remoteok() if j["title"] == "Senior DevOps Engineer")
    assert job["source"] == "remoteok"
    assert job["company"] == "Example Co"
    assert job["salary_min"] == 150000
    assert job["remote"] is True
    assert job["posted_at"] == "2026-07-15"
    assert job["url"].startswith("https://")


# --------------------------------------------------------------------------
# remotive
# --------------------------------------------------------------------------

def test_remotive_filters_on_title_not_tags(http, fixture_bytes):
    """The fixture holds a real Product role tagged 'aws'. It is not an infra job."""
    http({"remotive.com/api": fixture_bytes("remotive.json")})
    titles = [j["title"] for j in ingest.fetch_remotive()]
    assert any("DevOps" in t for t in titles)
    assert not any("Product" in t for t in titles)


# --------------------------------------------------------------------------
# we work remotely
# --------------------------------------------------------------------------

def test_wwr_parses_company_and_role(rss):
    """WWR titles are 'Company: Role'."""
    rss("wwr.rss")
    jobs = ingest.fetch_weworkremotely()
    assert jobs, "expected the fixture's DevOps roles to survive filtering"
    for job in jobs:
        assert job["source"] == "wwr"
        assert job["company"], "company should be split out of the title"
        assert ":" not in job["title"], "role should have the company stripped"


def test_wwr_category_is_configurable(rss, monkeypatch, tmp_path):
    """The devops category is a default, not a constant — a designer needs another."""
    seen = rss("wwr.rss")
    (tmp_path / "search.yaml").write_text(
        "keywords: [design]\nsource_options:\n  wwr:\n    category: remote-design-jobs\n"
    )
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(tmp_path))
    from job_hunt import search_config
    search_config.load.cache_clear()

    ingest.fetch_weworkremotely()
    assert "remote-design-jobs.rss" in seen["url"]


def test_wwr_filters_its_own_category(rss, monkeypatch, tmp_path):
    """The category is a good pre-filter, not a perfect one.

    WWR's devops feed carries the occasional Help Desk and Sales Engineer, which is
    why the title filter runs over it regardless.
    """
    rss("wwr.rss")
    (tmp_path / "search.yaml").write_text("keywords:\n  - nothing-matches-this\n")
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(tmp_path))
    from job_hunt import search_config
    search_config.load.cache_clear()

    assert ingest.fetch_weworkremotely() == []


# --------------------------------------------------------------------------
# sources that need credentials
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fetch", [
    ingest.fetch_adzuna,
    ingest.fetch_usajobs,
    ingest.fetch_findwork,
])
def test_keyed_sources_skip_themselves_without_credentials(fetch):
    """Skipping is the designed behaviour — it's why enabling them all is safe.

    The no_network fixture would raise on any HTTP call, so this also proves they
    return before touching the wire.
    """
    assert fetch() == []


def test_ashby_skips_when_no_companies_configured(tmp_path, monkeypatch):
    """Ashby doesn't search, it polls named companies. No list, nothing to do."""
    (tmp_path / "search.yaml").write_text("keywords: [devops]\n")
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(tmp_path))
    from job_hunt import search_config
    search_config.load.cache_clear()

    assert ingest.fetch_ashby() == []


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def test_run_ingestion_stores_and_dedups(http, fixture_bytes, tmp_path, monkeypatch):
    """Ingest twice; the second run should add nothing."""
    monkeypatch.setattr("job_hunt.db.DB_PATH", tmp_path / "jobs.db")
    http({"remoteok.com/api": fixture_bytes("remoteok.json")})

    from job_hunt import db
    ingest.run_ingestion(["remoteok"])
    first = db.get_stats()["total"]
    assert first >= 1

    ingest.run_ingestion(["remoteok"])
    assert db.get_stats()["total"] == first


def test_one_source_failing_does_not_stop_the_rest(http, fixture_bytes, tmp_path, monkeypatch):
    """A scraper breaking is routine. It shouldn't take the whole run down."""
    monkeypatch.setattr("job_hunt.db.DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setitem(ingest.FETCHERS, "boom", _explode)
    http({"remoteok.com/api": fixture_bytes("remoteok.json")})

    from job_hunt import db
    ingest.run_ingestion(["boom", "remoteok"])
    assert db.get_stats()["total"] >= 1, "remoteok should still have run"


def _explode():
    raise RuntimeError("source is down")
