# A tour

One run through the codebase, file by file. About ten minutes. By the end you'll
know where everything lives and why a few odd-looking things are that way.

The repo does two separate things that share a directory and nothing else:

1. **Find leads** — pull postings from 14 boards into SQLite.
2. **Build resumes** — merge your facts with a per-role emphasis, render a PDF.

They don't talk to each other. Read whichever you care about.

---

## Part 1: finding leads

```sh
job-hunt ingest --source wwr
```

### `job_hunt/__main__.py` — the front door

One command, one `--help`. `cli.build_parser()` builds the lead-management
subcommands, and `__main__` hangs `ingest` and `resume` off the same subparser
group, so `job-hunt <tab>` shows everything.

`resume` is routed straight to `resume.build()`; everything else goes to
`cli.dispatch()`, which calls `init_db()` first. `resume` deliberately skips that —
building a PDF shouldn't create a job database as a side effect.

### `job_hunt/search_config.py` — what you're looking for

Everything personal about the search is here, read from `profile/search.yaml`.
This module is the seam where "one person's job hunt" became "yours":

```python
keywords()              # the filter
queries()               # what to type in a search box
locations()             # where
enabled_sources(all)    # which boards to hit
source_options('wwr')   # per-source settings
```

Resolution order is `$JOB_HUNT_PROFILE` → `./profile/` → `./profile.example/`. That
last fallback is deliberate and worth understanding: **ingestion falls back to the
example, resume generation refuses to.** Ingesting with example keywords costs you
a few irrelevant rows in a local database. Building a *resume* from example data
means possibly sending someone else's resume to an employer. Same repo, different
blast radius, different answer.

Then the function the whole pipeline turns on:

```python
def wanted(title, tags=None) -> bool:
    return matches(title)
```

That's it. Not the description, not the tags — and `tags` is accepted and ignored
so call sites can keep passing what they have. This looks like an oversight and is
the opposite. [ADR 0003](adr/0003-filter-on-titles-alone.md) has the measurements:
description matching returned 10 of 100 RemoteOK jobs and **all ten were false
positives**; tags gave 1 real match against 22 pieces of noise on Remotive. A title
is a claim about what the job *is*. Everything else just mentions things.

### `job_hunt/ingest.py` — 14 fetchers

Each is a function returning a list of dicts. `fetch_weworkremotely` is
representative and short:

```python
category = search_config.source_options('wwr').get('category', 'remote-devops-sysadmin-jobs')
feed = feedparser.parse(f"https://weworkremotely.com/categories/{category}.rss")

for entry in feed.entries:
    company, role = title.split(':', 1)      # WWR titles are "Company: Role"
    if not wanted(role):
        continue
    jobs.append({...})
```

Three things in eight lines, each a small lesson:

- **The category is config with a default**, not a constant. The devops feed is a
  genuinely good pre-filter (~19 relevant jobs where the all-categories feed gives
  ~12), but *which* category is your choice, not the tool's.
- **The filter runs anyway.** A good pre-filter isn't a perfect one — WWR's own
  devops category carries the occasional Help Desk Guru and Sales Engineer.
- **The dict shape is fixed** and documented in
  [`add-job-source`](../.claude/skills/add-job-source/SKILL.md).

The others vary in shape but not in structure. `fetch_hn_whos_hiring` is the one
exception to the title rule: a Who's Hiring comment is prose with no title field,
so it matches raw text because there's nothing else to read. `fetch_ashby` doesn't
search at all — it asks named companies directly, so its company list *is* the
search. `fetch_adzuna`/`usajobs`/`findwork` return `[]` with a note when their API
key is absent, which is what makes it safe to leave every source enabled.

### `job_hunt/db.py` — where they land

SQLite at `data/jobs.db`. One table, one constraint that carries the design:

```sql
UNIQUE(source, source_id)
```

Re-running ingestion is normal — feeds mostly repeat themselves. So `upsert_job`
looks for `(source, source_id)`, and on a hit **updates the posting but never
touches `status` or `notes`**. Your triage is yours; a re-fetch must not undo it.

`upsert_job` takes a connection and doesn't commit. That's not an oversight either:
`run_ingestion` commits once per source, so a whole board lands as one transaction.

### `job_hunt/cli.py` — reading them

`list`, `show`, `search`, `status`, `stats`. Statuses go `new` → `reviewed` →
`applied` / `rejected` / `archived`. The interesting part isn't the code, it's that
`status` is the only column you own, which is why upsert protects it.

---

## Part 2: building a resume

```sh
job-hunt resume platform
```

### The two files

**`profile/profile.yaml` is facts.** Who you are, where you worked, what you did.
Doesn't change between applications. Every job has a stable `id`.

**`profile/roles/platform.yaml` is emphasis.** For this kind of job, what do you
lead with? It restates nothing — just a title, a summary, sidebar lists, and
optionally `overrides:` re-pitching a job's bullets by `id`.

The shipped example has two roles over one history. Build both and diff them:

```sh
make resume ROLE=platform && make resume ROLE=sre
```

Same person, same jobs, same truth — the current job pitched as "the paved road,
not a gate" in one and "alerting that pages a human only when a human helps" in the
other. Nothing is invented between them; the on-call work is in `profile.yaml`
either way. That's the whole trick, and [ADR 0002](adr/0002-separate-facts-from-emphasis.md)
explains why it used to be impossible: the old template hardcoded the work history
and made the current employer a special case in the schema, named after them.

### `job_hunt/resume.py` — the merge

`merge(profile, role)` is the heart of it, and it's short — about half of it is
validation:

1. Index the profile's jobs by `id`, refusing duplicates and missing ids.
2. Take the role's `experience:` list as the selection and order — or all of them,
   profile order, if omitted.
3. For each, overlay `overrides[id]` if present.
4. Emit one flat dict: identity + role emphasis + resolved jobs + certs + education.

Every failure is a `ConfigError` with a sentence in it — unknown role names list the
ones that exist, unknown job ids list the known ids. A typo in your YAML shouldn't
greet you with a traceback while you're stressed and applying to things.

### `resumes/templates/resume.typ` — the layout

No person in it. Data arrives as one JSON blob:

```python
typst compile resume.typ out.pdf --input data='{"identity":{...},...}'
```

```typst
#let data = json(bytes(sys.inputs.at("data", default: "{}")))
```

`--input` only carries strings, so JSON is the transport. It beats the alternatives:
no temp files, no `--root` path wrangling, and no shoving multi-line text through
shell arguments.

Then one odd line near the top:

```typst
#context [#metadata(counter(page).final().first()) <page-count>]
```

The layout is one page and **overflows silently** — Typst exits 0, prints nothing,
and you get a single orphaned line on page two, which reads worse than either a
tight page or an honest two-pager. So the template publishes its own final page
count, `resume.page_count()` reads it back with `typst query`, and the generator
warns. This was found the honest way: the SRE example did exactly that while being
written.

---

## Part 3: the parts around the edges

### `scripts/init.py`

Copies `profile.example/` → `profile/` and fills in your details. Two constraints
explain everything odd about it:

**Standard library only, and old-Python-safe.** It runs on a fresh clone *before*
`make install`, on whatever `python3` exists — which on stock macOS is still 3.9. A
setup script that needs setup isn't a setup script. CI runs it on 3.9 with nothing
installed to keep that true.

**It edits YAML as text, never through a parser.** `search.yaml` is 49% comments and
those comments are the documentation — which sources are region-locked, why the
filter reads titles, what enabling `software engineer` costs. `safe_load` +
`safe_dump` drops all 85 of them.

It also only ever edits inside the `identity:` block, because `location: Austin, TX`
appears twice in the example — once as Jordan's home, once as the Northwind job's
location. A whole-file replace edits whichever comes first.

### `tests/`

79 of them, under a second, and they run with **no network, no API keys, and no
`profile/`** — enforced in `conftest.py`, not trusted. An autouse fixture makes any
unmocked `urlopen` or `feedparser.parse` raise, so CI can't fail because a job board
is down at 3am.

Fixtures in `tests/fixtures/` are real responses, trimmed. That matters: these APIs
return shapes nobody would invent. RemoteOK opens its feed with a legal notice
instead of a job, and serves double-encoded text.

The filter tests *are* the false positives — "Social Media Manager", "Sub Agent Net
Zero Teeside", a Product role tagged `aws`. Each one came off a live feed. Widen the
filter back and they fail, with the reason in the docstring.

### `docs/adr/`

Six decisions and why. The two worth reading first are
[0002](adr/0002-separate-facts-from-emphasis.md) (facts vs emphasis — the design)
and [0003](adr/0003-filter-on-titles-alone.md) (titles only — the measurements).

---

## The shape of it

```
you ──> profile/search.yaml ──> ingest ──> SQLite ──> job-hunt list
                                   ^
                                   └── wanted(title)   <- the whole filter

you ──> profile/profile.yaml ─┐
                              ├──> merge() ──> JSON ──> resume.typ ──> PDF
        profile/roles/x.yaml ─┘
```

Two pipelines, one rule each. Ingestion trusts titles and nothing else. Resumes
trust your profile and nothing else.
