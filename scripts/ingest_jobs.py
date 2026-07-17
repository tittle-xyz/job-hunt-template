#!/usr/bin/env python3
"""
Job ingestion script - fetches from all configured sources.

Usage:
    python ingest_jobs.py [--source SOURCE]

Sources: remoteok, hn, hn_jobs, adzuna, wwr, usajobs, findwork, builtinco, linkedin, remotive, workingnomads, himalayas, jobicy, ashby
"""

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

import feedparser
from dotenv import load_dotenv

import search_config
from jobs_db import get_connection, init_db, upsert_job, log_fetch

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")


def matches_keywords(text: str) -> bool:
    """Check if text mentions any keyword from profile/search.yaml."""
    return search_config.matches(text)


def wanted(title, tags=None) -> bool:
    """Keep this job? Judged on title and tags — not description. See search_config.wanted."""
    return search_config.wanted(title or "", tags)


# =============================================================================
# Source Fetchers
# =============================================================================

def fetch_remoteok() -> list:
    """Fetch jobs from RemoteOK API."""
    print("Fetching RemoteOK...")
    req = urllib.request.Request(
        "https://remoteok.com/api",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode())

    jobs = []
    for item in data[1:]:  # Skip first item (legal notice)
        tags = [t.lower() for t in item.get('tags', [])]
        title = item.get('position', '')
        desc = item.get('description', '')

        if wanted(title, tags):
            jobs.append({
                'source': 'remoteok',
                'source_id': str(item.get('id')),
                'company': item.get('company'),
                'title': title,
                'location': item.get('location', 'Remote'),
                'salary_min': item.get('salary_min') or None,
                'salary_max': item.get('salary_max') or None,
                'url': item.get('url'),
                'description': desc[:5000] if desc else None,
                'tags': item.get('tags', []),
                'remote': True,
                'posted_at': item.get('date', '')[:10] if item.get('date') else None
            })

    return jobs


def fetch_hn_whos_hiring() -> list:
    """Fetch jobs from Hacker News Who's Hiring thread."""
    print("Fetching HN Who's Hiring...")

    # Find the latest Who's Hiring thread
    # December 2024 thread ID - in production you'd search for latest
    thread_id = 42575537

    req = urllib.request.Request(
        f"https://hacker-news.firebaseio.com/v0/item/{thread_id}.json"
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        thread = json.loads(response.read().decode())

    kids = thread.get('kids', [])[:100]  # First 100 comments
    jobs = []

    for kid_id in kids:
        try:
            req = urllib.request.Request(
                f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                comment = json.loads(response.read().decode())

            # The exception to the title-and-tags rule: a Who's Hiring post is a
            # freeform comment with no title field, so raw text is all there is.
            text = comment.get('text', '')
            if not text or not matches_keywords(text):
                continue

            # Extract company name (usually first line)
            first_line = re.sub(r'<[^>]+>', '', text.split('<p>')[0])[:100]
            company = first_line.split('|')[0].strip()

            jobs.append({
                'source': 'hn',
                'source_id': str(kid_id),
                'company': company,
                'title': 'See posting',  # HN doesn't have structured titles
                'location': None,
                'salary_min': None,
                'salary_max': None,
                'url': f"https://news.ycombinator.com/item?id={kid_id}",
                'description': re.sub(r'<[^>]+>', ' ', text)[:5000],
                'tags': [],
                'remote': 'remote' in text.lower(),
                'posted_at': None
            })
        except Exception:
            continue

    return jobs


def fetch_adzuna() -> list:
    """Fetch jobs from Adzuna API."""
    print("Fetching Adzuna...")

    app_id = os.getenv('ADZUNA_APP_ID')
    app_key = os.getenv('ADZUNA_APP_KEY')

    if not app_id or not app_key:
        print("  Skipping - no API credentials")
        return []

    jobs = []

    seen_ids = set()

    for keyword, location in search_config.query_location_pairs():
        url = (
            f"https://api.adzuna.com/v1/api/jobs/us/search/1"
            f"?app_id={app_id}&app_key={app_key}"
            f"&results_per_page=50&what={urllib.parse.quote(keyword)}"
            f"&where={urllib.parse.quote(location)}"
        )

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())

            for item in data.get('results', []):
                job_id = str(item.get('id'))
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                title = item.get('title', '')
                # Skip security clearance jobs
                if 'clearance' in title.lower():
                    continue

                salary_min = item.get('salary_min')
                salary_max = item.get('salary_max')

                jobs.append({
                    'source': 'adzuna',
                    'source_id': job_id,
                    'company': item.get('company', {}).get('display_name'),
                    'title': title,
                    'location': item.get('location', {}).get('display_name'),
                    'salary_min': int(salary_min) if salary_min else None,
                    'salary_max': int(salary_max) if salary_max else None,
                    'url': item.get('redirect_url'),
                    'description': item.get('description', '')[:5000],
                    'tags': [],
                    'remote': False,
                    'posted_at': item.get('created', '')[:10] if item.get('created') else None
                })
        except Exception as e:
            print(f"  Error fetching {keyword}: {e}")

    return jobs


def fetch_weworkremotely() -> list:
    """Fetch jobs from a We Work Remotely category RSS feed."""
    print("Fetching We Work Remotely...")

    # WWR publishes one feed per category. The category is a real pre-filter and
    # worth keeping — the devops feed yields ~19 relevant jobs where the
    # all-categories feed yields ~12, because the latter's newest 100 are mostly
    # other disciplines. But which category is a choice, so it's configurable.
    category = search_config.source_options('wwr').get(
        'category', 'remote-devops-sysadmin-jobs'
    )
    feed = feedparser.parse(
        f"https://weworkremotely.com/categories/{category}.rss"
    )

    jobs = []
    for entry in feed.entries:
        title = entry.get('title', '')

        # Parse "Company: Role" format
        if ':' in title:
            company, role = title.split(':', 1)
            company = company.strip()
            role = role.strip()
        else:
            company = None
            role = title

        # The category is a good pre-filter, not a perfect one: WWR's own
        # devops/sysadmin feed carries the occasional Help Desk or Sales Engineer.
        if not wanted(role):
            continue

        jobs.append({
            'source': 'wwr',
            'source_id': entry.get('id') or entry.get('link'),
            'company': company,
            'title': role,
            'location': 'Remote',
            'salary_min': None,
            'salary_max': None,
            'url': entry.get('link'),
            'description': entry.get('summary', '')[:5000] if entry.get('summary') else None,
            'tags': [],
            'remote': True,
            'posted_at': entry.get('published', '')[:10] if entry.get('published') else None
        })

    return jobs


def fetch_usajobs() -> list:
    """Fetch jobs from USAJOBS API."""
    print("Fetching USAJOBS...")

    api_key = os.getenv('USAJOBS_API_KEY')
    user_agent = os.getenv('USAJOBS_USER_AGENT')

    if not api_key or not user_agent:
        print("  Skipping - no API credentials")
        return []

    jobs = []
    seen_ids = set()

    # USAJOBS has no separate location parameter here — the location rides along
    # in the keyword string, which is how the API's free-text search works.
    searches = [f"{q} {loc}".strip() for q, loc in search_config.query_location_pairs()]

    for keyword in searches:
        url = (
            f"https://data.usajobs.gov/api/search"
            f"?Keyword={urllib.parse.quote(keyword)}&ResultsPerPage=50"
        )

        try:
            req = urllib.request.Request(url, headers={
                'Authorization-Key': api_key,
                'User-Agent': user_agent
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())

            for item in data.get('SearchResult', {}).get('SearchResultItems', []):
                job = item.get('MatchedObjectDescriptor', {})
                job_id = job.get('PositionID')

                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                title = job.get('PositionTitle', '')
                if 'clearance' in title.lower():
                    continue

                salary = job.get('PositionRemuneration', [{}])[0]
                sal_min = salary.get('MinimumRange')
                sal_max = salary.get('MaximumRange')

                jobs.append({
                    'source': 'usajobs',
                    'source_id': job_id,
                    'company': job.get('OrganizationName'),
                    'title': title,
                    'location': job.get('PositionLocationDisplay'),
                    'salary_min': int(float(sal_min)) if sal_min else None,
                    'salary_max': int(float(sal_max)) if sal_max else None,
                    'url': job.get('PositionURI'),
                    'description': None,  # Would need separate API call
                    'tags': [],
                    'remote': 'remote' in job.get('PositionLocationDisplay', '').lower(),
                    'posted_at': job.get('PublicationStartDate', '')[:10] if job.get('PublicationStartDate') else None
                })
        except Exception as e:
            print(f"  Error fetching {keyword}: {e}")

    return jobs


def fetch_builtincolorado() -> list:
    """Fetch jobs from Built In Colorado via JSON-LD structured data."""
    import time

    print("Fetching Built In Colorado...")

    job_urls = []
    seen_ids = set()

    searches = search_config.queries()
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    # Pass 1: Get job URLs from search results
    for keyword in searches:
        url = f"https://www.builtincolorado.com/jobs?search={urllib.parse.quote(keyword)}"

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode()

            match = re.search(r'<script type="application/ld\+json">\s*({.*?})\s*</script>', html, re.DOTALL)
            if not match:
                continue

            data = json.loads(match.group(1))

            for item in data.get('@graph', []):
                if item.get('@type') == 'ItemList':
                    for job_item in item.get('itemListElement', []):
                        job_url = job_item.get('url', '')
                        job_id = job_url.split('/')[-1] if job_url else None
                        title = job_item.get('name', '')

                        if not job_id or job_id in seen_ids:
                            continue

                        # Filter before fetching details — this listing carries no
                        # tags, so the title is all we have to go on, and it's the
                        # part worth trusting anyway.
                        if not wanted(title):
                            continue

                        seen_ids.add(job_id)
                        job_urls.append(job_url)

            time.sleep(1)  # Be polite between search requests

        except Exception as e:
            print(f"  Error fetching search '{keyword}': {e}")

    print(f"  Found {len(job_urls)} relevant jobs, fetching details...")

    # Pass 2: Fetch full details from each job page
    jobs = []
    for i, job_url in enumerate(job_urls):
        try:
            req = urllib.request.Request(job_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode()

            match = re.search(r'<script type="application/ld\+json">\s*({.*?})\s*</script>', html, re.DOTALL)
            if not match:
                continue

            data = json.loads(match.group(1))

            for item in data.get('@graph', []):
                if item.get('@type') == 'JobPosting':
                    job_id = job_url.split('/')[-1]

                    # Extract salary
                    salary = item.get('baseSalary', {}).get('value', {})
                    salary_min = salary.get('minValue') if isinstance(salary, dict) else None
                    salary_max = salary.get('maxValue') if isinstance(salary, dict) else None

                    # Extract location
                    locations = item.get('jobLocation', [])
                    if locations and isinstance(locations, list):
                        addr = locations[0].get('address', {})
                        location = f"{addr.get('addressLocality', '')}, {addr.get('addressRegion', '')}"
                    else:
                        location = 'Colorado'

                    # Extract tags from industry
                    tags = item.get('industry', [])
                    if isinstance(tags, str):
                        tags = [tags]

                    jobs.append({
                        'source': 'builtinco',
                        'source_id': job_id,
                        'company': item.get('hiringOrganization', {}).get('name'),
                        'title': item.get('title', ''),
                        'location': location.strip(', '),
                        'salary_min': int(salary_min) if salary_min else None,
                        'salary_max': int(salary_max) if salary_max else None,
                        'url': job_url,
                        'description': re.sub(r'<[^>]+>', ' ', item.get('description', ''))[:5000],
                        'tags': tags,
                        'remote': 'remote' in item.get('title', '').lower() or 'remote' in location.lower(),
                        'posted_at': item.get('datePosted')
                    })
                    break

            # Progress indicator every 10 jobs
            if (i + 1) % 10 == 0:
                print(f"  Fetched {i + 1}/{len(job_urls)} job details...")

            time.sleep(1.5)  # Be polite between detail requests

        except Exception as e:
            print(f"  Error fetching {job_url}: {e}")
            continue

    return jobs


def fetch_linkedin() -> list:
    """Fetch jobs from LinkedIn via guest API."""
    import time

    print("Fetching LinkedIn...")

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    job_ids = []
    seen_ids = set()

    # Pass 1: Get job IDs from search results
    for keyword, location in search_config.query_location_pairs():
        # Fetch first 50 results (start=0 and start=25)
        for start in [0, 25]:
            url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={urllib.parse.quote(keyword)}"
                f"&location={urllib.parse.quote(location or 'Remote')}&start={start}"
            )

            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    html = response.read().decode()

                # Extract job IDs from data-entity-urn="urn:li:jobPosting:4338983979"
                for match in re.finditer(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html):
                    job_id = match.group(1)
                    if job_id not in seen_ids:
                        seen_ids.add(job_id)
                        job_ids.append(job_id)

                time.sleep(1)

            except Exception as e:
                print(f"  Error fetching search '{keyword}' start={start}: {e}")

    print(f"  Found {len(job_ids)} unique jobs, fetching details...")

    # Pass 2: Fetch full details from each job page
    jobs = []
    for i, job_id in enumerate(job_ids):
        try:
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode()

            # Extract title
            title_match = re.search(r'<h2[^>]*class="[^"]*top-card-layout__title[^"]*"[^>]*>([^<]+)</h2>', html)
            title = title_match.group(1).strip() if title_match else None

            if not wanted(title):
                continue

            # Extract company
            company_match = re.search(r'<a[^>]*class="[^"]*topcard__org-name-link[^"]*"[^>]*>([^<]+)</a>', html)
            if not company_match:
                company_match = re.search(r'<span[^>]*class="[^"]*topcard__flavor[^"]*"[^>]*>([^<]+)</span>', html)
            company = company_match.group(1).strip() if company_match else None

            # Extract location. When the page doesn't say, fall back to the first
            # place we searched rather than claiming to know.
            location_match = re.search(r'<span[^>]*class="[^"]*topcard__flavor topcard__flavor--bullet[^"]*"[^>]*>([^<]+)</span>', html)
            searched_locations = search_config.locations()
            default_location = searched_locations[0] if searched_locations else 'Remote'
            location = location_match.group(1).strip() if location_match else default_location

            # Extract salary if present
            salary_min = None
            salary_max = None
            salary_match = re.search(r'\$([0-9,]+)(?:\.00)?(?:/yr)?\s*[-–]\s*\$([0-9,]+)', html)
            if salary_match:
                salary_min = int(salary_match.group(1).replace(',', ''))
                salary_max = int(salary_match.group(2).replace(',', ''))

            # Extract description
            desc_match = re.search(r'<div[^>]*class="[^"]*description__text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            description = re.sub(r'<[^>]+>', ' ', desc_match.group(1))[:5000] if desc_match else None

            # Extract employment type
            remote = False
            if 'remote' in html.lower():
                remote = True

            jobs.append({
                'source': 'linkedin',
                'source_id': job_id,
                'company': company,
                'title': title,
                'location': location,
                'salary_min': salary_min,
                'salary_max': salary_max,
                'url': f"https://www.linkedin.com/jobs/view/{job_id}",
                'description': description,
                'tags': [],
                'remote': remote,
                'posted_at': None  # Could parse "X days ago" but skipping for now
            })

            # Progress indicator every 10 jobs
            if (i + 1) % 10 == 0:
                print(f"  Fetched {i + 1}/{len(job_ids)} job details...")

            time.sleep(1.5)  # Be polite

        except Exception as e:
            print(f"  Error fetching job {job_id}: {e}")
            continue

    return jobs


def fetch_remotive() -> list:
    """Fetch jobs from Remotive API."""
    print("Fetching Remotive...")

    jobs = []
    url = "https://remotive.com/api/remote-jobs?category=software-dev"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())

        for item in data.get('jobs', []):
            title = item.get('title', '')
            desc = item.get('description', '')
            tags = [t.lower() for t in item.get('tags', [])]

            if not wanted(title, tags):
                continue

            # Parse salary if present (format varies: "$220k-$300k", "$100,000 - $150,000", etc.)
            salary_min = None
            salary_max = None
            salary_str = item.get('salary', '')
            if salary_str:
                # Try to extract numbers
                amounts = re.findall(r'\$?([\d,]+)k?', salary_str, re.IGNORECASE)
                if len(amounts) >= 2:
                    sal1 = int(amounts[0].replace(',', ''))
                    sal2 = int(amounts[1].replace(',', ''))
                    # Handle "k" notation
                    if 'k' in salary_str.lower():
                        if sal1 < 1000:
                            sal1 *= 1000
                        if sal2 < 1000:
                            sal2 *= 1000
                    salary_min = min(sal1, sal2)
                    salary_max = max(sal1, sal2)

            jobs.append({
                'source': 'remotive',
                'source_id': str(item.get('id')),
                'company': item.get('company_name'),
                'title': title,
                'location': item.get('candidate_required_location', 'Remote'),
                'salary_min': salary_min,
                'salary_max': salary_max,
                'url': item.get('url'),
                'description': re.sub(r'<[^>]+>', ' ', desc)[:5000] if desc else None,
                'tags': item.get('tags', []),
                'remote': True,
                'posted_at': item.get('publication_date', '')[:10] if item.get('publication_date') else None
            })

    except Exception as e:
        print(f"  Error: {e}")

    return jobs


def fetch_workingnomads() -> list:
    """Fetch jobs from Working Nomads API."""
    print("Fetching Working Nomads...")

    jobs = []
    url = "https://www.workingnomads.com/api/exposed_jobs/"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())

        for item in data:
            title = item.get('title', '')
            desc = item.get('description', '')
            tags_str = item.get('tags', '')

            if not wanted(title, tags_str):
                continue

            # Extract job ID from URL (e.g., /job/go/1272909/)
            url_path = item.get('url', '')
            job_id = url_path.rstrip('/').split('/')[-1] if url_path else None

            jobs.append({
                'source': 'workingnomads',
                'source_id': job_id,
                'company': item.get('company_name'),
                'title': title,
                'location': item.get('location', 'Remote'),
                'salary_min': None,
                'salary_max': None,
                'url': item.get('url'),
                'description': re.sub(r'<[^>]+>', ' ', desc)[:5000] if desc else None,
                'tags': [t.strip() for t in tags_str.split(',')] if tags_str else [],
                'remote': True,
                'posted_at': item.get('pub_date', '')[:10] if item.get('pub_date') else None
            })

    except Exception as e:
        print(f"  Error: {e}")

    return jobs


def fetch_himalayas() -> list:
    """Fetch jobs from Himalayas RSS feed."""
    print("Fetching Himalayas...")

    jobs = []

    try:
        feed = feedparser.parse("https://himalayas.app/jobs/rss")

        for entry in feed.entries:
            title = entry.get('title', '')
            # Description is in content:encoded or summary
            desc = ''
            if hasattr(entry, 'content') and entry.content:
                desc = entry.content[0].get('value', '')
            elif entry.get('summary'):
                desc = entry.get('summary', '')

            if not wanted(title):
                continue

            # Extract company from custom namespace
            company = None
            if hasattr(entry, 'himalayasjobs_companyname'):
                company = entry.himalayasjobs_companyname

            # Extract location
            location = 'Remote'
            if hasattr(entry, 'himalayasjobs_locationrestriction'):
                location = entry.himalayasjobs_locationrestriction

            # Extract job ID from URL
            url = entry.get('link', '')
            job_id = entry.get('id') or url.split('/')[-1] if url else None

            jobs.append({
                'source': 'himalayas',
                'source_id': job_id,
                'company': company,
                'title': title,
                'location': location,
                'salary_min': None,
                'salary_max': None,
                'url': url,
                'description': re.sub(r'<[^>]+>', ' ', desc)[:5000] if desc else None,
                'tags': [tag.term for tag in entry.get('tags', [])] if hasattr(entry, 'tags') else [],
                'remote': True,
                'posted_at': entry.get('published', '')[:10] if entry.get('published') else None
            })

    except Exception as e:
        print(f"  Error: {e}")

    return jobs


def fetch_jobicy() -> list:
    """Fetch jobs from Jobicy API."""
    print("Fetching Jobicy...")

    jobs = []
    seen_ids = set()

    # Jobicy filters by tag from its own fixed vocabulary, not free text. Your
    # queries are used as tags, so a multi-word query ('site reliability
    # engineer') matches nothing here rather than erroring. The single-word ones
    # ('devops', 'kubernetes') are what do the work.
    for tag in search_config.queries():
        url = f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={urllib.parse.quote(tag)}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())

            for item in data.get('jobs', []):
                job_id = str(item.get('id'))
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                title = item.get('jobTitle', '')
                desc = item.get('jobDescription', '')

                # Jobicy already filtered by tag; confirm the title agrees.
                if not wanted(title):
                    continue

                # Parse salary
                salary_min = item.get('salaryMin')
                salary_max = item.get('salaryMax')

                jobs.append({
                    'source': 'jobicy',
                    'source_id': job_id,
                    'company': item.get('companyName'),
                    'title': title,
                    'location': item.get('jobGeo', 'Remote'),
                    'salary_min': int(salary_min) if salary_min else None,
                    'salary_max': int(salary_max) if salary_max else None,
                    'url': item.get('url'),
                    'description': re.sub(r'<[^>]+>', ' ', desc)[:5000] if desc else None,
                    'tags': item.get('jobIndustry', []),
                    'remote': True,
                    'posted_at': item.get('pubDate', '')[:10] if item.get('pubDate') else None
                })

        except Exception as e:
            print(f"  Error fetching tag '{tag}': {e}")

    return jobs


def fetch_hn_jobs() -> list:
    """Fetch jobs from Hacker News /jobs (YC company postings)."""
    print("Fetching HN Jobs (YC companies)...")

    jobs = []

    try:
        # Get job story IDs
        req = urllib.request.Request(
            "https://hacker-news.firebaseio.com/v0/jobstories.json"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            job_ids = json.loads(response.read().decode())

        # Fetch first 50 job stories
        for job_id in job_ids[:50]:
            try:
                req = urllib.request.Request(
                    f"https://hacker-news.firebaseio.com/v0/item/{job_id}.json"
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    item = json.loads(response.read().decode())

                if not item or item.get('type') != 'job':
                    continue

                title = item.get('title', '')
                text = item.get('text', '')  # Some jobs have inline description

                # Filter for relevant jobs
                if not wanted(title):
                    continue

                # Parse company from title (format: "Company (YC Batch) Is Hiring Role")
                company = None
                company_match = re.match(r'^([^(]+)\s*\(YC', title)
                if company_match:
                    company = company_match.group(1).strip()

                jobs.append({
                    'source': 'hn_jobs',
                    'source_id': str(job_id),
                    'company': company,
                    'title': title,
                    'location': None,
                    'salary_min': None,
                    'salary_max': None,
                    'url': item.get('url') or f"https://news.ycombinator.com/item?id={job_id}",
                    'description': re.sub(r'<[^>]+>', ' ', text)[:5000] if text else None,
                    'tags': [],
                    'remote': 'remote' in title.lower() or 'remote' in text.lower(),
                    'posted_at': None  # Could convert unix timestamp but skipping
                })

            except Exception:
                continue

    except Exception as e:
        print(f"  Error: {e}")

    return jobs


def fetch_ashby() -> list:
    """Fetch jobs from Ashby ATS for target companies."""
    print("Fetching Ashby (target companies)...")

    # Which companies to poll. Unlike the job boards, this source doesn't search —
    # it walks a named list and asks each one directly, so the list IS the search.
    # Yours to edit: source_options.ashby.companies in search.yaml.
    ASHBY_COMPANIES = search_config.source_options('ashby').get('companies') or []
    if not ASHBY_COMPANIES:
        print("  Skipping - no companies configured (source_options.ashby.companies)")
        return []

    jobs = []
    seen_ids = set()

    for company_slug in ASHBY_COMPANIES:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}?includeCompensation=true"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())

            company_jobs = data.get('jobs', [])
            matched = 0

            for item in company_jobs:
                job_id = item.get('id')
                if job_id in seen_ids:
                    continue

                title = item.get('title', '')
                desc_plain = item.get('descriptionPlain', '')

                # Filter for relevant roles
                if not wanted(title):
                    continue

                seen_ids.add(job_id)
                matched += 1

                # Extract salary from compensation
                salary_min = None
                salary_max = None
                compensation = item.get('compensation', {})
                if compensation:
                    for component in compensation.get('summaryComponents', []):
                        if component.get('compensationType') == 'Salary':
                            salary_min = component.get('minValue')
                            salary_max = component.get('maxValue')
                            break

                # Extract location
                location = item.get('location', '')
                if item.get('isRemote'):
                    location = f"{location} (Remote)" if location else "Remote"

                # Extract company name from posting URL or use slug
                job_url = item.get('jobUrl', '')
                company_name = company_slug.title()  # Fallback

                jobs.append({
                    'source': 'ashby',
                    'source_id': f"{company_slug}_{job_id}",
                    'company': company_name,
                    'title': title,
                    'location': location,
                    'salary_min': int(salary_min) if salary_min else None,
                    'salary_max': int(salary_max) if salary_max else None,
                    'url': job_url,
                    'description': desc_plain[:5000] if desc_plain else None,
                    'tags': [item.get('department', ''), item.get('team', '')],
                    'remote': item.get('isRemote', False),
                    'posted_at': item.get('publishedAt', '')[:10] if item.get('publishedAt') else None
                })

            if matched > 0:
                print(f"  {company_slug}: {matched} relevant jobs (of {len(company_jobs)} total)")

        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Company doesn't use Ashby or wrong slug - skip silently
                pass
            else:
                print(f"  Error fetching {company_slug}: {e}")
        except Exception as e:
            print(f"  Error fetching {company_slug}: {e}")

    return jobs


def fetch_findwork() -> list:
    """Fetch jobs from Findwork API."""
    print("Fetching Findwork...")

    api_key = os.getenv('FINDWORK_API_KEY')

    if not api_key:
        print("  Skipping - no API credentials")
        return []

    jobs = []
    seen_ids = set()

    for keyword in search_config.queries():
        url = f"https://findwork.dev/api/jobs/?search={urllib.parse.quote(keyword)}&remote=true"

        try:
            req = urllib.request.Request(url, headers={
                'Authorization': f'Token {api_key}'
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())

            for item in data.get('results', []):
                job_id = str(item.get('id'))
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                jobs.append({
                    'source': 'findwork',
                    'source_id': job_id,
                    'company': item.get('company_name'),
                    'title': item.get('role'),
                    'location': item.get('location'),
                    'salary_min': None,
                    'salary_max': None,
                    'url': item.get('url'),
                    'description': item.get('text', '')[:5000] if item.get('text') else None,
                    'tags': item.get('keywords', []),
                    'remote': item.get('remote', False),
                    'posted_at': item.get('date_posted', '')[:10] if item.get('date_posted') else None
                })
        except Exception as e:
            print(f"  Error fetching {keyword}: {e}")

    return jobs


# =============================================================================
# Main
# =============================================================================

FETCHERS = {
    'remoteok': fetch_remoteok,
    'hn': fetch_hn_whos_hiring,
    'hn_jobs': fetch_hn_jobs,
    'adzuna': fetch_adzuna,
    'wwr': fetch_weworkremotely,
    'usajobs': fetch_usajobs,
    'findwork': fetch_findwork,
    'builtinco': fetch_builtincolorado,
    'linkedin': fetch_linkedin,
    'remotive': fetch_remotive,
    'workingnomads': fetch_workingnomads,
    'himalayas': fetch_himalayas,
    'jobicy': fetch_jobicy,
    'ashby': fetch_ashby,
}


def run_ingestion(sources: list = None):
    """Run ingestion for the given sources.

    With none given, use whatever `sources:` in search.yaml says — which is how
    someone outside Colorado turns off the Colorado-only board.
    """
    init_db()
    conn = get_connection()

    if sources is None:
        sources = search_config.enabled_sources(list(FETCHERS.keys()))

    total_found = 0
    total_new = 0

    for source in sources:
        if source not in FETCHERS:
            print(f"Unknown source: {source}")
            continue

        try:
            jobs = FETCHERS[source]()
            new_count = 0

            for job in jobs:
                is_new = upsert_job(conn, job)
                if is_new:
                    new_count += 1

            conn.commit()
            log_fetch(conn, source, len(jobs), new_count)
            conn.commit()

            print(f"  Found {len(jobs)} jobs, {new_count} new")
            total_found += len(jobs)
            total_new += new_count

        except Exception as e:
            print(f"  Error: {e}")
            log_fetch(conn, source, 0, 0, str(e))
            conn.commit()

    conn.close()
    print(f"\nTotal: {total_found} jobs found, {total_new} new")


def main():
    parser = argparse.ArgumentParser(description="Ingest job listings from various sources")
    parser.add_argument(
        '--source', '-s',
        choices=list(FETCHERS.keys()),
        help="Specific source to fetch (default: all)"
    )
    args = parser.parse_args()

    sources = [args.source] if args.source else None
    run_ingestion(sources)


if __name__ == "__main__":
    import urllib.parse
    main()
