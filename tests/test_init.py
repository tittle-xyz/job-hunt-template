"""scripts/init.py — scaffolding a profile.

Two of these tests exist because the bugs they describe shipped briefly and were
caught by running init rather than reading it. Both were silent, and both ended
with a plausible-looking resume carrying someone else's fake details.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INIT_PY = REPO_ROOT / "scripts" / "init.py"


def load_init():
    spec = importlib.util.spec_from_file_location("init_script", INIT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def init():
    return load_init()


@pytest.fixture
def example_text():
    return (REPO_ROOT / "profile.example" / "profile.yaml").read_text()


# --------------------------------------------------------------------------
# identity substitution
# --------------------------------------------------------------------------

def test_fills_in_every_field(init, example_text):
    text, misses, leftovers = init.substitute_identity(example_text, {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "303-555-0199",
        "location": "Denver, CO",
    })
    assert misses == []
    assert leftovers == []
    assert "name: Ada Lovelace" in text
    assert "Jordan Reyes" not in text


def test_only_the_identity_block_is_touched(init, example_text):
    """`location: Austin, TX` is BOTH Jordan's home and the Northwind job's location.

    A whole-file replace edits whichever comes first. The job's location is a fact
    about the job and must survive having your own location set.
    """
    text, _, _ = init.substitute_identity(example_text, {"location": "Denver, CO"})
    assert "location: Denver, CO" in text
    # the Northwind job keeps its own location
    assert text.count("location: Austin, TX") == 1
    assert "id: northwind" in text


def test_leftover_placeholders_are_reported(init, example_text):
    """Partial fills are the dangerous case: looks done, carries a fake phone."""
    text, misses, leftovers = init.substitute_identity(example_text, {
        "name": "Grace Hopper",
        "email": "grace@example.com",
    })
    assert misses == []
    assert sorted(leftovers) == ["location", "phone"]
    assert '555-0142' in text


def test_fiction_note_survives_while_fake_data_does(init, example_text):
    """Don't strip 'these are deliberately fake' while 555-0142 is still there."""
    text, _, leftovers = init.substitute_identity(example_text, {"name": "Grace Hopper"})
    assert leftovers
    assert "reserved" in text  # the note explaining the fake range


def test_fiction_note_removed_once_nothing_is_fake(init, example_text):
    text, _, leftovers = init.substitute_identity(example_text, {
        "name": "Ada", "email": "a@example.com",
        "phone": "303-555-0199", "location": "Denver, CO",
    })
    assert leftovers == []
    assert "reserved" not in text


def test_drift_between_example_and_script_is_reported(init):
    """If profile.example stops matching IDENTITY_FIELDS, say so — don't no-op."""
    text, misses, _ = init.substitute_identity(
        "identity:\n  name: Someone Else\n\nexperience: []\n", {"phone": "1234"}
    )
    assert "phone" in misses


# --------------------------------------------------------------------------
# search locations
# --------------------------------------------------------------------------

def test_search_locations_replace_the_example(init):
    text = "keywords:\n  - devops\nlocations:\n  - Colorado\n  - Denver\n\nsources:\n  - remoteok\n"
    out = init.substitute_search_locations(text, ["Berlin"])
    assert "  - Berlin\n" in out
    assert "Colorado" not in out
    assert "sources:\n  - remoteok\n" in out  # nothing else disturbed


def test_empty_search_locations_means_remote_only(init):
    text = "locations:\n  - Colorado\n  - Denver\n\nsources: []\n"
    out = init.substitute_search_locations(text, [])
    assert "locations: []" in out
    assert "Colorado" not in out


def test_none_leaves_locations_alone(init):
    text = "locations:\n  - Colorado\n"
    assert init.substitute_search_locations(text, None) == text


# --------------------------------------------------------------------------
# the script end to end
# --------------------------------------------------------------------------

def run_init(cwd, *args):
    """Run init.py as a subprocess, the way a user does."""
    return subprocess.run(
        [sys.executable, str(INIT_PY), *args],
        cwd=str(cwd), capture_output=True, text=True,
    )


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A copy of the repo's example dir, so tests never touch the real profile/."""
    import shutil
    shutil.copytree(REPO_ROOT / "profile.example", tmp_path / "profile.example")
    module = load_init()
    monkeypatch.setattr(module, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(module, "EXAMPLE", str(tmp_path / "profile.example"))
    monkeypatch.setattr(module, "PROFILE", str(tmp_path / "profile"))
    return tmp_path, module


def test_dry_run_changes_nothing(sandbox, monkeypatch):
    tmp_path, module = sandbox
    monkeypatch.setattr(sys, "argv", ["init.py", "--dry-run", "--no-input", "--name", "Ada"])
    assert module.main() == 0
    assert not (tmp_path / "profile").exists()


def test_creates_profile_and_substitutes(sandbox, monkeypatch):
    tmp_path, module = sandbox
    monkeypatch.setattr(sys, "argv", [
        "init.py", "--no-input", "--name", "Ada Lovelace", "--email", "ada@example.com",
        "--phone", "303-555-0199", "--location", "Denver, CO",
    ])
    assert module.main() == 0
    text = (tmp_path / "profile" / "profile.yaml").read_text()
    assert "Ada Lovelace" in text
    assert "Jordan Reyes" not in text


def test_refuses_to_clobber_an_existing_profile(sandbox, monkeypatch):
    tmp_path, module = sandbox
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "profile.yaml").write_text("name: MINE\n")
    monkeypatch.setattr(sys, "argv", ["init.py", "--no-input", "--name", "Nope"])
    assert module.main() == 0
    assert (tmp_path / "profile" / "profile.yaml").read_text() == "name: MINE\n"


def test_comments_survive(sandbox, monkeypatch):
    """The comments are the documentation. A YAML round-trip would drop all 85."""
    tmp_path, module = sandbox
    monkeypatch.setattr(sys, "argv", ["init.py", "--no-input", "--name", "Ada"])
    module.main()
    for name in ("search.yaml", "roles/platform.yaml"):
        before = (tmp_path / "profile.example" / name).read_text().count("#")
        after = (tmp_path / "profile" / name).read_text().count("#")
        assert after == before, f"{name} lost comments"


def test_runs_on_old_python_without_dependencies():
    """init must work on a fresh clone, before `make install`, on stock python3.

    Not a style check: system python on macOS is 3.9, and init is the first thing
    a new user runs.
    """
    r = subprocess.run(
        ["python3", str(INIT_PY), "--help"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    assert "profile" in r.stdout
