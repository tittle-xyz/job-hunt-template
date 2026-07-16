#!/usr/bin/env python3
"""
Job leads database schema and utilities.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def get_connection():
    """Get a database connection, creating the db if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_id TEXT,
            company TEXT,
            title TEXT NOT NULL,
            location TEXT,
            salary_min INTEGER,
            salary_max INTEGER,
            url TEXT,
            description TEXT,
            tags TEXT,  -- JSON array
            remote INTEGER DEFAULT 0,
            posted_at TEXT,
            fetched_at TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            notes TEXT,
            UNIQUE(source, source_id)
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_fetched ON jobs(fetched_at);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);

        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            jobs_found INTEGER DEFAULT 0,
            jobs_new INTEGER DEFAULT 0,
            error TEXT
        );
    """)
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def upsert_job(conn, job: dict) -> bool:
    """
    Insert or update a job. Returns True if new, False if existing.

    Expected job dict keys:
        source, source_id, company, title, location, salary_min, salary_max,
        url, description, tags (list), remote (bool), posted_at
    """
    cursor = conn.cursor()

    # Check if exists
    cursor.execute(
        "SELECT id FROM jobs WHERE source = ? AND source_id = ?",
        (job['source'], job.get('source_id'))
    )
    existing = cursor.fetchone()

    now = datetime.utcnow().isoformat()
    tags_json = json.dumps(job.get('tags', []))

    if existing:
        # Update (but don't overwrite status/notes)
        cursor.execute("""
            UPDATE jobs SET
                company = ?,
                title = ?,
                location = ?,
                salary_min = ?,
                salary_max = ?,
                url = ?,
                description = ?,
                tags = ?,
                remote = ?,
                posted_at = ?,
                fetched_at = ?
            WHERE id = ?
        """, (
            job.get('company'),
            job.get('title'),
            job.get('location'),
            job.get('salary_min'),
            job.get('salary_max'),
            job.get('url'),
            job.get('description'),
            tags_json,
            1 if job.get('remote') else 0,
            job.get('posted_at'),
            now,
            existing['id']
        ))
        return False
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO jobs (
                source, source_id, company, title, location,
                salary_min, salary_max, url, description, tags,
                remote, posted_at, fetched_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
        """, (
            job['source'],
            job.get('source_id'),
            job.get('company'),
            job.get('title'),
            job.get('location'),
            job.get('salary_min'),
            job.get('salary_max'),
            job.get('url'),
            job.get('description'),
            tags_json,
            1 if job.get('remote') else 0,
            job.get('posted_at'),
            now
        ))
        return True


def log_fetch(conn, source: str, jobs_found: int, jobs_new: int, error: str = None):
    """Log a fetch operation."""
    conn.execute("""
        INSERT INTO fetch_log (source, fetched_at, jobs_found, jobs_new, error)
        VALUES (?, ?, ?, ?, ?)
    """, (source, datetime.utcnow().isoformat(), jobs_found, jobs_new, error))


def get_jobs(status: str = None, source: str = None, limit: int = 50) -> list:
    """Query jobs with optional filters."""
    conn = get_connection()
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if source:
        query += " AND source = ?"
        params.append(source)

    query += " ORDER BY fetched_at DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Parse tags JSON
    for job in jobs:
        job['tags'] = json.loads(job['tags']) if job['tags'] else []

    return jobs


def update_status(job_id: int, status: str, notes: str = None):
    """Update a job's status and optionally notes."""
    conn = get_connection()
    if notes is not None:
        conn.execute(
            "UPDATE jobs SET status = ?, notes = ? WHERE id = ?",
            (status, notes, job_id)
        )
    else:
        conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ?",
            (status, job_id)
        )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Get summary statistics."""
    conn = get_connection()

    stats = {}

    # By status
    cursor = conn.execute("""
        SELECT status, COUNT(*) as count FROM jobs GROUP BY status
    """)
    stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}

    # By source
    cursor = conn.execute("""
        SELECT source, COUNT(*) as count FROM jobs GROUP BY source
    """)
    stats['by_source'] = {row['source']: row['count'] for row in cursor.fetchall()}

    # Total
    cursor = conn.execute("SELECT COUNT(*) as count FROM jobs")
    stats['total'] = cursor.fetchone()['count']

    # Last fetch per source
    cursor = conn.execute("""
        SELECT source, MAX(fetched_at) as last_fetch,
               SUM(jobs_new) as total_new
        FROM fetch_log GROUP BY source
    """)
    stats['last_fetch'] = {
        row['source']: {'time': row['last_fetch'], 'total_new': row['total_new']}
        for row in cursor.fetchall()
    }

    conn.close()
    return stats


if __name__ == "__main__":
    init_db()
