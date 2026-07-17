"""Loads what you're looking for from profile/search.yaml.

Ingestion used to hardcode one person's job hunt — a DevOps keyword list and
Colorado. This is the seam where those preferences became yours.

Resolution order:
    1. $JOB_HUNT_PROFILE, if set
    2. ./profile/search.yaml
    3. ./profile.example/search.yaml

Falling back to the example is deliberate: a fresh clone can fetch real jobs
before you've configured anything, and the cost of getting it wrong is some
irrelevant rows in a local database. The resume generator makes the opposite
call and refuses to run without a real profile, because a resume built from
example data is a thing you might accidentally send.
"""

from __future__ import annotations

import os
import re
import sys
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _config_path() -> Path:
    override = os.environ.get("JOB_HUNT_PROFILE")
    if override:
        path = Path(override).expanduser() / "search.yaml"
        if not path.exists():
            raise SystemExit(f"error: JOB_HUNT_PROFILE is set but {path} does not exist")
        return path

    real = REPO_ROOT / "profile" / "search.yaml"
    if real.exists():
        return real

    example = REPO_ROOT / "profile.example" / "search.yaml"
    if example.exists():
        print(
            "note: no profile/search.yaml — using the example search (Colorado "
            "infrastructure roles).\n"
            "      Run `make init` and edit profile/search.yaml to search for your own work.",
            file=sys.stderr,
        )
        return example

    raise SystemExit("error: no search config found. Expected profile/search.yaml")


@lru_cache(maxsize=1)
def load() -> dict:
    path = _config_path()
    try:
        with open(path) as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise SystemExit(f"error: {path} is not valid YAML:\n  {e}")

    if not config.get("keywords"):
        raise SystemExit(
            f"error: {path} has no `keywords`.\n"
            f"Without them every job matches, and ingestion would pull the entire internet."
        )
    return config


def keywords() -> list[str]:
    """Terms a job must mention to be kept."""
    return [str(k).lower() for k in load().get("keywords", [])]


def queries() -> list[str]:
    """Terms to send to sources that take a search query."""
    return [str(q) for q in load().get("queries", [])] or keywords()[:5]


def locations() -> list[str]:
    """Places to search. Empty means remote-only / anywhere."""
    return [str(loc) for loc in load().get("locations", [])]


def enabled_sources(available: list[str]) -> list[str]:
    """Which fetchers to run, in the order the user listed them.

    An omitted `sources:` key means all of them. An unknown name is a typo worth
    reporting — silently fetching nothing is the confusing outcome.
    """
    configured = load().get("sources")
    if configured is None:
        return list(available)

    unknown = [s for s in configured if s not in available]
    if unknown:
        raise SystemExit(
            f"error: unknown source(s) in search.yaml: {', '.join(unknown)}\n"
            f"Available: {', '.join(available)}"
        )
    return [s for s in configured if s in available]


def source_options(source: str) -> dict:
    """Per-source settings from `source_options:` in search.yaml.

    Most sources need nothing beyond keywords and queries. A couple genuinely do:
    We Work Remotely serves one RSS feed per category, and the Ashby fetcher polls
    a list of named companies. Those are choices, not constants, so they live in
    config rather than in the fetcher.
    """
    return (load().get("source_options") or {}).get(source) or {}


def matches(text: str) -> bool:
    """True if text mentions any configured keyword.

    Word-boundary aware, so 'aws' doesn't match 'laws' and 'sre' doesn't match
    'stressed'.
    """
    if not text:
        return False
    text_lower = text.lower()
    for kw in keywords():
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
            return True
    return False


def wanted(title: str, tags=None) -> bool:
    """Decide whether to keep a job. Titles only.

    A title is a claim about what the job IS. Descriptions and tags merely
    mention things, and both were measured doing far more harm than good:

      - Descriptions: 10 hits out of 100 RemoteOK jobs, all 10 false positives.
        A Social Media Manager whose posting says "infrastructure"; a Servpro ad
        mentioning "reliability".
      - Tags: on Remotive, 1 title match against 22 tag-only matches — every one
        of the 22 noise, including six identical "Staff Software Engineer,
        Product" posts caught by an 'aws' tag. RemoteOK is worse still: it tagged
        a Medical Support Technician with 'golang'.

    Tags describe the stack a team happens to use. That is not the same claim as
    what the job is, so we don't treat it as one.

    The cost is real and worth knowing: an infra role titled "Engineer III" with
    a 'kubernetes' tag now slips through. That's rare, and cheap against a 96%
    noise rate. The lever is `keywords` in search.yaml — list the titles you'd
    accept, not just the tools you know.

    `tags` is accepted and ignored so call sites can keep passing what they have.

    (fetch_hn_whos_hiring is the exception and matches raw text via matches()
    above, because a Who's-Hiring comment is prose with no title field to read.)
    """
    return matches(title)


def query_location_pairs() -> list[tuple[str, str]]:
    """Cross product for location-aware sources.

    With no locations configured, each query runs once with an empty location
    rather than not at all — a remote-only searcher still wants results.
    """
    locs = locations()
    if not locs:
        return [(q, "") for q in queries()]
    return [(q, loc) for q in queries() for loc in locs]
