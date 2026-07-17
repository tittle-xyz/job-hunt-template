"""Shared test setup.

Three rules, enforced here rather than trusted:

1. No network. Every fetcher test feeds a recorded fixture through a fake
   urlopen. Nothing in CI should break because RemoteOK is down or this month's
   Who's-Hiring thread doesn't exist yet.
2. No API keys. The key-gated sources skip themselves; that's a behaviour worth
   testing, not a hole in the suite.
3. No profile/. The tests run against profile.example/, exactly like a fresh
   clone. If the shipped example ever stops working, that's a failure — it's the
   first thing a new user runs.
"""

import io
import sys
from pathlib import Path

import feedparser
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(REPO_ROOT))

# Grabbed before no_network replaces it, so fixtures can still be parsed for real.
_real_feedparser_parse = feedparser.parse


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly on any unmocked HTTP call, rather than quietly hitting the net."""
    def boom(*args, **kwargs):
        raise AssertionError(
            "test tried to make a real HTTP request — mock it with the `http` fixture"
        )

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("feedparser.parse", boom)


@pytest.fixture(autouse=True)
def no_api_keys(monkeypatch):
    """Guarantee the key-gated sources see no credentials."""
    for var in (
        "ADZUNA_APP_ID", "ADZUNA_APP_KEY",
        "USAJOBS_API_KEY", "USAJOBS_USER_AGENT",
        "FINDWORK_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def example_profile(monkeypatch, tmp_path):
    """Point config resolution at profile.example/ and the DB at a temp file.

    search_config caches its load, so the cache is cleared around every test —
    otherwise the first test to read config would decide it for all the others.
    """
    from job_hunt import search_config

    search_config.load.cache_clear()
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(REPO_ROOT / "profile.example"))
    yield
    search_config.load.cache_clear()


@pytest.fixture
def fixture_bytes():
    """Read a recorded response from tests/fixtures/."""
    def _read(name):
        return (FIXTURES / name).read_bytes()
    return _read


@pytest.fixture
def rss(monkeypatch):
    """Serve a recorded RSS fixture to feedparser.

    Returns the dict it records the requested URL into, so a test can assert on
    which feed was asked for:

        seen = rss("wwr.rss")
        ...
        assert "remote-design-jobs" in seen["url"]
    """
    def _install(name):
        parsed = _real_feedparser_parse((FIXTURES / name).read_bytes())
        seen = {}

        def fake_parse(url, *args, **kwargs):
            seen["url"] = url
            return parsed

        monkeypatch.setattr("feedparser.parse", fake_parse)
        return seen

    return _install


@pytest.fixture
def http(monkeypatch):
    """Serve recorded bytes to urllib, keyed by substring of the requested URL.

        http({"remoteok.com/api": fixture_bytes("remoteok.json")})
    """
    def _install(routes):
        def fake_urlopen(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            for needle, payload in routes.items():
                if needle in url:
                    return _FakeResponse(payload)
            raise AssertionError("no fixture registered for URL: %s" % url)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    return _install


class _FakeResponse(io.BytesIO):
    """Just enough of an HTTP response for the fetchers: read() and a context manager."""

    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
