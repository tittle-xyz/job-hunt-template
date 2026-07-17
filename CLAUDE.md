# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What this is

A local job-hunt tool: pull leads from 14 job boards into SQLite, keep one set of
career facts, build a resume tailored to each role from it.

The person using this is job hunting, which is stressful and has real stakes. Two
things follow.

**Their data is theirs.** Everything personal lives in `profile/`, gitignored from
the first commit. Never move personal details into tracked files — not into
`job_hunt/`, not into `profile.example/`, not into a test fixture. If you need a
person for an example, use the fictional one already here.

**Never invent experience.** This is the one hard rule. You can help decide which
of their real work to lead with, and how to phrase it. You cannot add a job, a
skill, a number, or an outcome that isn't already in their profile. A resume is a
claim someone has to defend in an interview, and a fabricated one is worse than a
weak one. If a posting wants something they don't have, say so.

## Commands

```sh
make install            # venv + editable install (finds a python 3.11+)
make init               # profile.example/ -> profile/  (stdlib only, runs on 3.9)
make test               # 79 tests, no network/keys/profile needed
make lint

job-hunt ingest [--source S]
job-hunt list [--status new] [--source wwr] [--limit 20]
job-hunt show <id>
job-hunt status <id> applied --notes "..."
job-hunt search <query>
job-hunt resume <role> [--profile DIR] [-o OUT]
```

## Layout

```
job_hunt/            the tool. knows nothing about who's running it
  ingest.py          14 fetchers + run_ingestion
  search_config.py   reads profile/search.yaml — the filter lives here
  db.py              SQLite schema, upsert, stats
  cli.py, __main__.py
  resume.py          merge profile + role, render via Typst
profile.example/     fictional sample. tracked, and doubles as the schema docs
profile/             the user's real data. GITIGNORED. never commit it
resumes/templates/   resume.typ — layout only, no person in it
tests/               fixtures are recorded real responses
docs/adr/            why things are the way they are
```

## The two-layer profile

`profile/profile.yaml` holds **facts** — identity, full work history (each job has
a stable `id`), certifications, education. It doesn't change between applications.

`profile/roles/<name>.yaml` holds **emphasis** — an overlay: title, summary,
skills, sidebar lists, an optional `experience:` list selecting and ordering jobs,
and `overrides:` keyed by job `id` to re-pitch that job's bullets.

Facts go in the profile. Emphasis goes in the role. If you find yourself restating
history in a role config, it belongs in the profile.

## Decisions worth knowing before you change things

**The filter reads titles only** (`search_config.wanted`). Not descriptions, not
tags. Both were measured failing: description matching gave 10 hits out of 100
RemoteOK jobs, all 10 false positives; tags gave 1 title match against 22 tag
matches on Remotive, all 22 noise. `fetch_hn_whos_hiring` is the sole exception —
a Who's Hiring comment is prose with no title field. Tests pin all of this; if you
widen it, they'll fail and tell you why.

**The resume is one page and overflows silently.** Typst exits 0 and leaves an
orphan on page two. `resume.typ` publishes its page count and the generator warns.
Don't remove that.

**Ingestion falls back to `profile.example/`; resume generation refuses to.** Not
an inconsistency. Ingesting with example keywords costs a few irrelevant rows in a
local database. Building a resume from example data means possibly sending someone
else's resume to an employer.

**`upsert_job` doesn't commit** — the caller does, so a whole source lands as one
transaction. It also never overwrites `status` or `notes`: the user's triage
survives re-ingestion.

**Three dependencies, on purpose.** urllib, sqlite3, Typst. Think hard before
adding a fourth.

**No cover letter generator, on purpose.** A cover letter that reads like a machine
wrote it is worse than none.

## Skills

- [`.claude/skills/add-job-source`](.claude/skills/add-job-source/SKILL.md) — wire up a new board
- [`.claude/skills/tailor-resume`](.claude/skills/tailor-resume/SKILL.md) — aim a profile at a posting

## Working on this

Tests must keep passing with no network, no API keys, and no `profile/` — that's
the state a fresh clone is in, and `conftest.py` enforces it rather than trusting
it. Fixtures live in `tests/fixtures/` as recorded real responses.

Scrapers break; that's normal. `run_ingestion` already isolates a failing source so
one dead board doesn't take down the run.
