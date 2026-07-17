#!/usr/bin/env python3
"""
Simple CLI for managing job leads.

Usage:
    python jobs_cli.py list [--status STATUS] [--source SOURCE] [--limit N]
    python jobs_cli.py show <job_id>
    python jobs_cli.py status <job_id> <status> [--notes NOTES]
    python jobs_cli.py stats
    python jobs_cli.py search <query>
"""

import argparse
import json
from .db import get_connection, get_jobs, update_status, get_stats, init_db


def cmd_list(args):
    """List jobs with optional filters."""
    jobs = get_jobs(status=args.status, source=args.source, limit=args.limit)

    if not jobs:
        print("No jobs found.")
        return

    for job in jobs:
        salary = ""
        if job['salary_min'] or job['salary_max']:
            sal_min = f"${job['salary_min']:,}" if job['salary_min'] else "?"
            sal_max = f"${job['salary_max']:,}" if job['salary_max'] else "?"
            salary = f" | {sal_min}-{sal_max}"

        remote = " | Remote" if job['remote'] else ""
        status_icon = {
            'new': '🆕',
            'reviewed': '👀',
            'applied': '📨',
            'rejected': '❌',
            'archived': '📦'
        }.get(job['status'], '  ')

        print(f"{status_icon} [{job['id']:3}] {job['company'] or 'Unknown'}: {job['title']}")
        print(f"       {job['source']}{salary}{remote}")
        if job['location']:
            print(f"       📍 {job['location']}")
        print()


def cmd_show(args):
    """Show details for a specific job."""
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (args.job_id,))
    job = cursor.fetchone()
    conn.close()

    if not job:
        print(f"Job {args.job_id} not found.")
        return

    job = dict(job)
    job['tags'] = json.loads(job['tags']) if job['tags'] else []

    print(f"ID: {job['id']}")
    print(f"Source: {job['source']} ({job['source_id']})")
    print(f"Status: {job['status']}")
    print(f"Company: {job['company']}")
    print(f"Title: {job['title']}")
    print(f"Location: {job['location']}")
    print(f"Remote: {'Yes' if job['remote'] else 'No'}")

    if job['salary_min'] or job['salary_max']:
        sal_min = f"${job['salary_min']:,}" if job['salary_min'] else "?"
        sal_max = f"${job['salary_max']:,}" if job['salary_max'] else "?"
        print(f"Salary: {sal_min} - {sal_max}")

    print(f"URL: {job['url']}")
    print(f"Posted: {job['posted_at']}")
    print(f"Fetched: {job['fetched_at']}")

    if job['tags']:
        print(f"Tags: {', '.join(job['tags'])}")

    if job['notes']:
        print(f"Notes: {job['notes']}")

    if job['description']:
        print(f"\n--- Description ---\n{job['description'][:1000]}...")


def cmd_status(args):
    """Update job status."""
    valid_statuses = ['new', 'reviewed', 'applied', 'rejected', 'archived']
    if args.new_status not in valid_statuses:
        print(f"Invalid status. Choose from: {', '.join(valid_statuses)}")
        return

    update_status(args.job_id, args.new_status, args.notes)
    print(f"Job {args.job_id} status updated to '{args.new_status}'")


def cmd_stats(args):
    """Show summary statistics."""
    stats = get_stats()

    print("=== Job Lead Statistics ===\n")

    print(f"Total jobs: {stats['total']}\n")

    print("By Status:")
    for status, count in sorted(stats['by_status'].items()):
        icon = {'new': '🆕', 'reviewed': '👀', 'applied': '📨', 'rejected': '❌', 'archived': '📦'}.get(status, '  ')
        print(f"  {icon} {status}: {count}")

    print("\nBy Source:")
    for source, count in sorted(stats['by_source'].items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")

    if stats['last_fetch']:
        print("\nLast Fetch:")
        for source, info in stats['last_fetch'].items():
            print(f"  {source}: {info['time']} ({info['total_new']} total new)")


def cmd_search(args):
    """Search jobs by keyword."""
    conn = get_connection()
    query = f"%{args.query}%"
    cursor = conn.execute("""
        SELECT * FROM jobs
        WHERE title LIKE ? OR company LIKE ? OR description LIKE ?
        ORDER BY fetched_at DESC
        LIMIT 50
    """, (query, query, query))

    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not jobs:
        print(f"No jobs matching '{args.query}'")
        return

    print(f"Found {len(jobs)} jobs matching '{args.query}':\n")

    for job in jobs:
        status_icon = {'new': '🆕', 'reviewed': '👀', 'applied': '📨', 'rejected': '❌', 'archived': '📦'}.get(job['status'], '  ')
        print(f"{status_icon} [{job['id']:3}] {job['company'] or 'Unknown'}: {job['title']}")
        print(f"       {job['source']} | {job['url']}")
        print()


COMMANDS = {
    'list': cmd_list,
    'show': cmd_show,
    'status': cmd_status,
    'stats': cmd_stats,
    'search': cmd_search,
}


def build_parser(prog=None):
    """Build the parser for the lead-management commands.

    __main__ adds `ingest` and `resume` to the subparsers this returns, so the
    whole tool is one command with one --help.
    """
    parser = argparse.ArgumentParser(prog=prog, description="Your job hunt, locally.")
    subparsers = parser.add_subparsers(dest='command', metavar='<command>')

    # list
    list_parser = subparsers.add_parser('list', help='List jobs')
    list_parser.add_argument('--status', '-s', help='Filter by status')
    list_parser.add_argument('--source', help='Filter by source')
    list_parser.add_argument('--limit', '-n', type=int, default=20, help='Max results')

    # show
    show_parser = subparsers.add_parser('show', help='Show job details')
    show_parser.add_argument('job_id', type=int, help='Job ID')

    # status
    status_parser = subparsers.add_parser('status', help='Update job status')
    status_parser.add_argument('job_id', type=int, help='Job ID')
    status_parser.add_argument('new_status', help='New status')
    status_parser.add_argument('--notes', '-n', help='Add notes')

    # stats
    subparsers.add_parser('stats', help='Show statistics')

    # search
    search_parser = subparsers.add_parser('search', help='Search jobs')
    search_parser.add_argument('query', help='Search query')

    # argparse offers no public way to get a parser's subparsers back, and
    # __main__ needs to hang `ingest` and `resume` off the same group.
    parser._subparsers_action = subparsers
    return parser


def dispatch(args) -> int:
    """Run a lead-management command. Assumes args.command is one of COMMANDS."""
    init_db()
    COMMANDS[args.command](args)
    return 0
