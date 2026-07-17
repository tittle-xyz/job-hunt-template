"""Merging a profile with a role config, and rendering the result.

The merge is where the template earns its name: one set of facts, many pitches.
Most of this is pure logic. The two tests that shell out to Typst are skipped when
it isn't installed, so `make test` still works on a laptop without it — CI installs
it, so the PDF path is genuinely covered somewhere.
"""

import shutil
from pathlib import Path

import pytest

from job_hunt import resume

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "profile.example"

needs_typst = pytest.mark.skipif(
    not shutil.which("typst"), reason="typst not installed (CI installs it)"
)


@pytest.fixture
def profile():
    return resume.load_yaml(EXAMPLE / "profile.yaml")


# --------------------------------------------------------------------------
# the merge
# --------------------------------------------------------------------------

def test_role_overlays_profile_without_repeating_it(profile):
    role = resume.load_role(EXAMPLE, "platform")
    data = resume.merge(profile, role)

    # facts come from the profile
    assert data["identity"]["name"] == "Jordan Reyes"
    assert len(data["experience"]) == 3
    assert data["certifications"]
    # emphasis comes from the role
    assert data["title"] == "Senior Platform Engineer"
    assert "Developer Experience" in data["emphasis"]


def test_same_history_two_different_pitches(profile):
    """The core promise: identical facts, different emphasis."""
    platform = resume.merge(profile, resume.load_role(EXAMPLE, "platform"))
    sre = resume.merge(profile, resume.load_role(EXAMPLE, "sre"))

    # same person, same jobs, same order
    assert platform["identity"] == sre["identity"]
    assert [j["company"] for j in platform["experience"]] == \
           [j["company"] for j in sre["experience"]]

    # but the current job is pitched differently, and the titles differ
    assert platform["title"] != sre["title"]
    assert platform["experience"][0]["bullets"] != sre["experience"][0]["bullets"]


def test_override_applies_to_the_named_job_only(profile):
    role = {
        "title": "T",
        "overrides": {"cascade": {"bullets": [{"label": "L", "text": "overridden"}]}},
    }
    data = resume.merge(profile, role)
    by_company = {j["company"]: j for j in data["experience"]}
    assert by_company["Cascade Freight"]["bullets"] == [{"label": "L", "text": "overridden"}]
    # untouched jobs keep the profile's bullets
    assert by_company["Northwind Logistics"]["bullets"][0]["label"] == "Platform Tooling"


def test_a_role_that_overrides_nothing_still_builds(profile):
    data = resume.merge(profile, {"title": "Anything"})
    assert len(data["experience"]) == 3
    assert data["experience"][0]["bullets"]


def test_experience_selects_and_orders(profile):
    data = resume.merge(profile, {"experience": ["pinehurst", "northwind"]})
    assert [j["id"] if "id" in j else j["company"] for j in data["experience"]] == [
        "Pinehurst Data", "Northwind Logistics",
    ]


def test_omitted_experience_keeps_profile_order(profile):
    data = resume.merge(profile, {})
    assert [j["company"] for j in data["experience"]] == [
        "Northwind Logistics", "Cascade Freight", "Pinehurst Data",
    ]


# --------------------------------------------------------------------------
# input mistakes should read as sentences, not tracebacks
# --------------------------------------------------------------------------

def test_missing_name_is_rejected():
    with pytest.raises(resume.ConfigError, match="identity.name"):
        resume.merge({"identity": {}}, {})


def test_job_without_id_is_rejected():
    bad = {"identity": {"name": "X"}, "experience": [{"company": "Acme"}]}
    with pytest.raises(resume.ConfigError, match="Acme"):
        resume.merge(bad, {})


def test_duplicate_job_ids_are_rejected():
    bad = {
        "identity": {"name": "X"},
        "experience": [{"id": "a", "company": "A"}, {"id": "a", "company": "B"}],
    }
    with pytest.raises(resume.ConfigError, match="Duplicate"):
        resume.merge(bad, {})


def test_unknown_id_in_experience_names_the_known_ids(profile):
    with pytest.raises(resume.ConfigError) as e:
        resume.merge(profile, {"experience": ["nope"]})
    assert "nope" in str(e.value) and "northwind" in str(e.value)


def test_unknown_id_in_overrides_is_rejected(profile):
    with pytest.raises(resume.ConfigError, match="typo_co"):
        resume.merge(profile, {"overrides": {"typo_co": {"bullets": []}}})


def test_unknown_role_lists_what_exists():
    with pytest.raises(resume.ConfigError) as e:
        resume.load_role(EXAMPLE, "cto")
    assert "platform" in str(e.value) and "sre" in str(e.value)


def test_explicit_profile_dir_that_is_missing_says_so(tmp_path):
    with pytest.raises(resume.ConfigError, match="--profile directory not found"):
        resume.resolve_profile_dir(tmp_path / "nope")


def test_no_profile_at_all_explains_make_init(tmp_path, monkeypatch):
    """The most common first-run error deserves the most useful message.

    DEFAULT_PROFILE is pinned to a temp path so this doesn't pass or fail based on
    whether whoever runs the suite happens to have their own profile/ checked out.
    """
    monkeypatch.setattr(resume, "DEFAULT_PROFILE", tmp_path / "profile")
    with pytest.raises(resume.ConfigError) as e:
        resume.resolve_profile_dir(None)
    assert "make init" in str(e.value)
    # and it should not error out about example data being missing
    assert "profile.example" in str(e.value)


# --------------------------------------------------------------------------
# shapes
# --------------------------------------------------------------------------

def test_bullets_accept_plain_strings():
    """A bare string bullet is allowed; label is optional."""
    job = resume.normalize_job({"title": "T", "bullets": ["did a thing"]})
    assert job["bullets"] == [{"label": "", "text": "did a thing"}]


def test_lists_accept_yaml_lists_or_legacy_strings():
    assert resume.as_list(["a", "b"]) == ["a", "b"]
    assert resume.as_list("a,\nb,\n") == ["a", "b"]
    assert resume.as_list(None) == []


def test_folded_scalars_collapse_to_one_line():
    assert resume.clean("a\n  b\n\n  c") == "a b c"


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

@needs_typst
def test_example_profile_renders_to_one_page(profile, tmp_path):
    """The shipped example must fit the layout it ships with.

    Overflow here is silent — typst exits 0 and you get an orphaned line on page
    two — so it's worth asserting rather than eyeballing.
    """
    for role_name in ("platform", "sre"):
        data = resume.merge(profile, resume.load_role(EXAMPLE, role_name))
        out = resume.render(data, tmp_path / f"{role_name}.pdf")
        assert out.exists() and out.stat().st_size > 1000
        payload = resume.json.dumps(data, separators=(",", ":"))
        assert resume.page_count(payload) == 1, f"{role_name} example spills past one page"


@needs_typst
def test_rendered_pdf_contains_the_persons_details(profile, tmp_path):
    data = resume.merge(profile, resume.load_role(EXAMPLE, "platform"))
    out = resume.render(data, tmp_path / "r.pdf")
    text = _pdf_text(out)
    if text is None:
        pytest.skip("pdftotext not installed")
    assert "Jordan Reyes" in text
    assert "Northwind Logistics" in text


def _pdf_text(path):
    """Extract text via pdftotext, or None if it isn't available."""
    import subprocess
    if not shutil.which("pdftotext"):
        return None
    r = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None
