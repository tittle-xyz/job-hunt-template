---
name: add-job-source
description: Add a new job board to the ingestion pipeline. Use when wiring up a job site, an ATS, a company careers feed, or any other source of postings.
---

# Add a job source

A source is one function that returns a list of job dicts, plus one line in
`FETCHERS`. Everything else — filtering, dedup, storage, status — already happens
around it. Touches `job_hunt/ingest.py` and, if the source needs settings,
`profile.example/search.yaml`.

## The contract

Return a list of dicts with these keys. Missing optional values should be `None`,
not invented:

```python
{
    'source':     'newboard',        # the FETCHERS key, always
    'source_id':  '12345',           # stable per-source id; with source, it's the dedup key
    'company':    'Example Co',
    'title':      'Senior DevOps Engineer',
    'location':   'Remote',          # or None
    'salary_min': 150000,            # int or None. never guess
    'salary_max': 190000,
    'url':        'https://...',
    'description': text[:5000],      # stored, never filtered on
    'tags':       ['devops', 'aws'], # list; stored, never filtered on
    'remote':     True,
    'posted_at':  '2026-07-15',      # YYYY-MM-DD or None
}
```

`(source, source_id)` is a UNIQUE constraint. If `source_id` isn't stable across
fetches, every run creates duplicates — derive it from the posting's own id or a
stable URL slug, never from a timestamp or list position.

## Filtering

Call `wanted(title)` and keep the job only if it's true:

```python
if not wanted(title):
    continue
```

**Do not filter on descriptions or tags.** This is the load-bearing rule of the
pipeline and it's measured, not stylistic:

- Descriptions: 10 hits out of 100 RemoteOK jobs, all 10 false positives — a Social
  Media Manager whose posting says "infrastructure", a Servpro ad mentioning
  "reliability", a BI Developer that lists AWS among its tools.
- Tags: on Remotive, 1 title match against 22 tag-only matches, all 22 noise —
  including six identical "Staff Software Engineer, Product" posts caught by an
  `aws` tag. RemoteOK tagged a Medical Support Technician with `golang`.

A title is a claim about what the job **is**. Descriptions and tags mention things.
Store both; filter on neither. (`fetch_hn_whos_hiring` is the one exception: a
Who's Hiring comment is prose with no title field.)

## Steps

1. **Write the fetcher.** Print what you're doing, and never let one source's
   failure escape as a crash — `run_ingestion` catches, but be tidy anyway:

   ```python
   def fetch_newboard() -> list:
       """Fetch jobs from New Board."""
       print("Fetching New Board...")
       jobs = []
       for keyword in search_config.queries():
           url = f"https://newboard.example/api?q={urllib.parse.quote(keyword)}"
           try:
               req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
               with urllib.request.urlopen(req, timeout=30) as response:
                   data = json.loads(response.read().decode())
           except Exception as e:
               print(f"  Error fetching '{keyword}': {e}")
               continue

           for item in data.get('results', []):
               title = item.get('title', '')
               if not wanted(title):
                   continue
               jobs.append({...})
       return jobs
   ```

2. **Take the search from config, never hardcode it.** `search_config.queries()`
   for search terms, `.locations()` or `.query_location_pairs()` for places,
   `.source_options('newboard')` for anything source-specific. Hardcoding "devops"
   or "Colorado" is exactly what this template exists to undo. If the source needs
   its own settings (a feed category, a company list), add them under
   `source_options:` in `profile.example/search.yaml` **with a comment explaining
   what to change them to** — that file's comments are the documentation.

3. **Register it:**

   ```python
   FETCHERS = {
       ...
       'newboard': fetch_newboard,
   }
   ```

4. **List it in `profile.example/search.yaml`** under `sources:`, with a note if
   it's region-locked or needs a key. Say so plainly — `builtinco` is Colorado-only
   and useless to anyone else, and the file says that.

5. **Keys go in `.env`**, read via `os.getenv`, and the source must skip itself
   with a message when the key is absent:

   ```python
   if not api_key:
       print("  Skipping - no API credentials")
       return []
   ```

   That's what makes it safe to leave every source enabled. Add the variable to
   `.env.example`.

6. **Record a fixture and test it.** Save a real, trimmed response to
   `tests/fixtures/newboard.json` and add a test:

   ```python
   def test_newboard_keeps_infra_and_drops_noise(http, fixture_bytes):
       http({"newboard.example": fixture_bytes("newboard.json")})
       titles = [j["title"] for j in ingest.fetch_newboard()]
       assert "Senior DevOps Engineer" in titles
       assert not any("Product Manager" in t for t in titles)
   ```

   Use a real response, not an invented one — these APIs return shapes nobody would
   guess. RemoteOK opens its feed with a legal notice instead of a job and serves
   double-encoded text. Trim descriptions so the fixture stays readable, and label
   anything synthetic.

   The suite forbids real network calls (`conftest.no_network`), so an unmocked
   request fails loudly rather than making CI depend on a job board's uptime. RSS
   sources use the `rss` fixture instead of `http`.

## Scraping

`linkedin` and `builtinco` parse HTML, and it will break — that's inherent, not a
bug to be fixed once. If you add a scraper: set a real User-Agent, sleep between
requests (`builtinco` uses `time.sleep(1)`), and prefer structured data when the
page offers it — `builtinco` reads JSON-LD rather than guessing at divs.

Be a good citizen. This is someone's job board, and a friend's laptop hammering it
helps nobody.
