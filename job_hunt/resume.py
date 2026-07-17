#!/usr/bin/env python3
"""Build a tailored resume PDF from your profile plus a role config.

    python scripts/generate_resume.py sre
    python scripts/generate_resume.py sre --profile ~/private/profile

Facts live in profile/profile.yaml. Emphasis lives in profile/roles/<role>.yaml.
This merges the two and hands the result to the Typst template, which is layout
only and knows nothing about you.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "resumes" / "templates" / "resume.typ"
DEFAULT_PROFILE = REPO_ROOT / "profile"
EXAMPLE_PROFILE = REPO_ROOT / "profile.example"


class ConfigError(Exception):
    """Something in the user's YAML is wrong. Message is shown without a traceback."""


def load_yaml(path: Path) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise ConfigError(f"File not found: {path}")
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML:\n  {e}")


def resolve_profile_dir(explicit: Path | None) -> Path:
    if explicit:
        if not explicit.is_dir():
            raise ConfigError(f"--profile directory not found: {explicit}")
        return explicit
    if DEFAULT_PROFILE.is_dir():
        return DEFAULT_PROFILE
    raise ConfigError(
        f"No profile found at {DEFAULT_PROFILE}\n\n"
        f"Your profile is yours and stays out of git. Create one from the example:\n"
        f"    make init\n"
        f"    (or: cp -r {EXAMPLE_PROFILE.name} {DEFAULT_PROFILE.name})\n\n"
        f"Then edit {DEFAULT_PROFILE.name}/profile.yaml."
    )


def available_roles(profile_dir: Path) -> list[str]:
    roles_dir = profile_dir / "roles"
    if not roles_dir.is_dir():
        return []
    return sorted(p.stem for p in roles_dir.glob("*.yaml"))


def load_role(profile_dir: Path, role: str) -> dict:
    path = profile_dir / "roles" / f"{role}.yaml"
    if not path.exists():
        known = available_roles(profile_dir)
        hint = f"Available roles: {', '.join(known)}" if known else (
            f"No role configs found in {profile_dir / 'roles'}"
        )
        raise ConfigError(f"No role config named '{role}'.\n{hint}")
    return load_yaml(path)


def merge(profile: dict, role: dict) -> dict:
    """Overlay a role config onto the profile to produce the template's input.

    The profile owns the facts; the role owns emphasis and may re-pitch the
    bullets of any job by id. A role that overrides nothing still produces a
    complete resume.
    """
    identity = profile.get("identity") or {}
    if not identity.get("name"):
        raise ConfigError("profile.yaml is missing identity.name — that's the one field a resume can't omit.")

    history = profile.get("experience") or []
    by_id: dict[str, dict] = {}
    for i, job in enumerate(history):
        job_id = job.get("id")
        if not job_id:
            label = job.get("company") or f"entry #{i + 1}"
            raise ConfigError(
                f"Job '{label}' in profile.yaml has no `id`.\n"
                f"Every job needs a stable id so role configs can reference it."
            )
        if job_id in by_id:
            raise ConfigError(f"Duplicate job id '{job_id}' in profile.yaml — ids must be unique.")
        by_id[job_id] = job

    # `experience:` in a role selects and orders jobs. Omitted: all, as listed.
    selected = role.get("experience")
    if selected is None:
        order = [job["id"] for job in history]
    else:
        unknown = [j for j in selected if j not in by_id]
        if unknown:
            raise ConfigError(
                f"Role config lists unknown job id(s): {', '.join(unknown)}\n"
                f"Known ids: {', '.join(by_id) or '(none)'}"
            )
        order = selected

    overrides = role.get("overrides") or {}
    unknown_overrides = [j for j in overrides if j not in by_id]
    if unknown_overrides:
        raise ConfigError(
            f"Role config overrides unknown job id(s): {', '.join(unknown_overrides)}\n"
            f"Known ids: {', '.join(by_id) or '(none)'}"
        )

    jobs = []
    for job_id in order:
        job = {**by_id[job_id], **(overrides.get(job_id) or {})}
        jobs.append(job)

    return {
        "identity": identity,
        "title": role.get("title", ""),
        "summary": clean(role.get("summary", "")),
        "skills": clean(role.get("skills", "")),
        "emphasis": as_list(role.get("emphasis")),
        "technologies": as_list(role.get("technologies")),
        "leadership": clean(role.get("leadership", "")),
        "experience": [normalize_job(j) for j in jobs],
        "certifications": profile.get("certifications") or [],
        "education": profile.get("education") or [],
    }


def clean(value: str) -> str:
    """Collapse YAML folded-scalar whitespace into a single tidy line."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def as_list(value) -> list[str]:
    """Accept a YAML list, or a legacy comma/newline-separated string."""
    if value is None:
        return []
    if isinstance(value, list):
        return [clean(v) for v in value if clean(v)]
    parts = re.split(r"[\n,]", str(value))
    return [clean(p) for p in parts if clean(p)]


def normalize_job(job: dict) -> dict:
    bullets = []
    for b in job.get("bullets") or []:
        # A bullet may be {label, text} or a bare string.
        if isinstance(b, str):
            bullets.append({"label": "", "text": clean(b)})
        else:
            bullets.append({"label": clean(b.get("label", "")), "text": clean(b.get("text", ""))})
    return {
        "title": clean(job.get("title", "")),
        "company": clean(job.get("company", "")),
        "location": clean(job.get("location", "")),
        "dates": clean(job.get("dates", "")),
        "bullets": bullets,
    }


def page_count(payload: str) -> int | None:
    """Ask the template how many pages it produced. None if we couldn't tell."""
    result = subprocess.run(
        ["typst", "query", str(TEMPLATE), "<page-count>", "--field", "value",
         "--input", f"data={payload}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        return None


def render(data: dict, out_path: Path) -> Path:
    if not shutil.which("typst"):
        raise ConfigError(
            "typst is not installed.\n"
            "    macOS:  brew install typst\n"
            "    other:  https://github.com/typst/typst#installation"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, separators=(",", ":"))

    result = subprocess.run(
        ["typst", "compile", str(TEMPLATE), str(out_path), "--input", f"data={payload}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ConfigError(f"typst failed to compile the template:\n{result.stderr}")

    pages = page_count(payload)
    if pages and pages > 1:
        print(
            f"warning: this resume is {pages} pages — the template is designed for one.\n"
            f"  Overflow is easy to miss, and a lone orphaned line on page 2 reads worse\n"
            f"  than either a tight one-pager or a deliberate two-pager. To trim:\n"
            f"    - shorten `skills` or `summary` in the role config (the sidebar spills first)\n"
            f"    - drop a bullet from an older job\n"
            f"    - list only the jobs you want via `experience:` in the role config",
            file=sys.stderr,
        )
    return out_path


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def build(role: str, profile=None, output=None) -> int:
    """Build one resume. Returns a process exit code.

    A mistake in your YAML should read as a sentence, not a traceback — so
    ConfigError is caught here and printed plainly.
    """
    try:
        profile_dir = resolve_profile_dir(Path(profile) if profile else None)
        profile_data = load_yaml(profile_dir / "profile.yaml")
        role_data = load_role(profile_dir, role)
        data = merge(profile_data, role_data)

        out = Path(output) if output else None
        if out is None:
            name = slugify(data["identity"].get("name", "resume"))
            title = slugify(data.get("title") or role)
            out = REPO_ROOT / "resumes" / "tailored" / f"{name}_{title}.pdf"

        pdf = render(data, out)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Created: {pdf.relative_to(REPO_ROOT) if pdf.is_relative_to(REPO_ROOT) else pdf}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a tailored resume PDF from profile + role config.",
    )
    parser.add_argument("role", help="Role config name, e.g. 'sre' for profile/roles/sre.yaml")
    parser.add_argument("--profile", help="Profile directory (default: ./profile)")
    parser.add_argument("-o", "--output", help="Output PDF path")
    args = parser.parse_args()
    return build(args.role, profile=args.profile, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
