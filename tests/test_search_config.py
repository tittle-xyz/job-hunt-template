"""The filter and the search config.

Most of these cases are real. The job titles that must NOT match were pulled from
live feeds while building this — they're the false positives that made the filter
title-only in the first place. If someone widens matching back to descriptions or
tags, these fail.
"""

import pytest

from job_hunt import search_config


@pytest.fixture(autouse=True)
def _fresh_cache():
    search_config.load.cache_clear()
    yield
    search_config.load.cache_clear()


def write_config(tmp_path, body):
    (tmp_path / "search.yaml").write_text(body)
    return tmp_path


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Senior DevOps Engineer",
    "Site Reliability Engineer (SRE)",
    "DevOps & Platform Engineer (AWS / CI/CD)",
    "Engineer Sr, DevOps",
    "Staff Platform Engineer",
])
def test_real_infra_titles_match(title):
    assert search_config.wanted(title) is True


@pytest.mark.parametrize("title", [
    "Social Media Manager",          # description said "infrastructure"
    "Sub Agent Net Zero Teeside",    # description said "infrastructure"
    "Business Intelligence Developer",  # description listed AWS
    "Purchase Order Administrator",
    "Medical Support Technician Scheduler Outpatient",
])
def test_noise_titles_do_not_match(title):
    """Every one of these was a real false positive under description matching."""
    assert search_config.wanted(title) is False


def test_tags_are_ignored():
    """A Product role tagged 'aws' is not an infrastructure job.

    Six identical "Staff Software Engineer, Product" posts matched an 'aws' tag on
    Remotive. Tags describe the stack a team uses, not what the job is.
    """
    assert search_config.wanted("Staff Software Engineer, Product", ["aws", "docker"]) is False
    assert search_config.wanted("Frontend Developer", ["kubernetes"]) is False


def test_word_boundaries():
    """'aws' must not match 'laws'; 'sre' must not match 'stressed'."""
    assert search_config.matches("laws clerk") is False
    assert search_config.matches("stressed out") is False
    assert search_config.matches("AWS Cloud Architect") is True


def test_matching_is_case_insensitive():
    assert search_config.wanted("SENIOR DEVOPS ENGINEER") is True
    assert search_config.wanted("senior devops engineer") is True


def test_empty_title_does_not_match():
    assert search_config.wanted("") is False
    assert search_config.matches(None) is False


# --------------------------------------------------------------------------
# config loading
# --------------------------------------------------------------------------

def test_shipped_example_is_platform_flavoured():
    """The default is a deliberate nudge toward platform work."""
    assert search_config.wanted("Senior Platform Engineer") is True
    # 'software engineer' ships commented out, so generic SWE stays out by default.
    assert search_config.wanted("Senior Software Engineer") is False


def test_keywords_are_required(tmp_path, monkeypatch):
    """No keywords means everything matches — refuse rather than ingest the world."""
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(tmp_path, "queries: [x]\n")))
    with pytest.raises(SystemExit) as e:
        search_config.keywords()
    assert "keywords" in str(e.value)


def test_unknown_source_is_an_error(tmp_path, monkeypatch):
    """A typo should be loud. Silently fetching nothing is the confusing outcome."""
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(
        tmp_path, "keywords: [devops]\nsources: [remoteok, builtin_berlin]\n"
    )))
    with pytest.raises(SystemExit) as e:
        search_config.enabled_sources(["remoteok", "hn"])
    assert "builtin_berlin" in str(e.value)


def test_omitted_sources_means_all(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(tmp_path, "keywords: [devops]\n")))
    assert search_config.enabled_sources(["remoteok", "hn"]) == ["remoteok", "hn"]


def test_sources_keep_configured_order(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(
        tmp_path, "keywords: [devops]\nsources: [hn, remoteok]\n"
    )))
    assert search_config.enabled_sources(["remoteok", "hn"]) == ["hn", "remoteok"]


def test_no_locations_still_runs_each_query(tmp_path, monkeypatch):
    """A remote-only searcher has no locations but still wants results."""
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(
        tmp_path, "keywords: [devops]\nqueries: [devops, sre]\nlocations: []\n"
    )))
    assert search_config.query_location_pairs() == [("devops", ""), ("sre", "")]


def test_locations_cross_product(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(
        tmp_path,
        "keywords: [devops]\nqueries: [devops, sre]\nlocations: [Denver, Boulder]\n",
    )))
    assert search_config.query_location_pairs() == [
        ("devops", "Denver"), ("devops", "Boulder"),
        ("sre", "Denver"), ("sre", "Boulder"),
    ]


def test_source_options_default_to_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(tmp_path, "keywords: [devops]\n")))
    assert search_config.source_options("wwr") == {}


def test_a_different_persona_works(tmp_path, monkeypatch):
    """The whole point of the template: someone else's search, same code."""
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(write_config(tmp_path, """
keywords:
  - product designer
  - ux
queries: [product designer]
locations: []
sources: [remoteok, remotive]
""")))
    assert search_config.wanted("Senior Product Designer") is True
    assert search_config.wanted("Senior DevOps Engineer") is False
    assert search_config.enabled_sources(["remoteok", "remotive", "builtinco"]) == [
        "remoteok", "remotive",
    ]


def test_missing_profile_env_points_at_a_real_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_HUNT_PROFILE", str(tmp_path / "nope"))
    with pytest.raises(SystemExit) as e:
        search_config.load()
    assert "does not exist" in str(e.value)
