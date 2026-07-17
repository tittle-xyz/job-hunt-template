# 5. The user's data never enters the repo

Date: 2026-07-16

## Status

Accepted

## Context

A job hunt is sensitive. Not embarrassing — sensitive. Who you're talking to, what
you're asking for, the fact that you're looking at all: none of it is your current
employer's business, and some of it is actively dangerous to leak while you still
have a job.

The repo this template came from held all of it: home address, phone number, target
companies, interview prep, notes on live conversations. Committed. Not because
anyone was careless — because the repo was private and personal, and in that
context it was the right call.

The moment such a repo is shared, that history is the problem. Git makes deletion
theatre: removing a file in a new commit leaves it in every clone forever.

## Decision

**Personal data is gitignored from the first commit.** `profile/`, `data/`,
`applications/`, `leads/`, generated PDFs. The rule is that a user's data should be
un-committable by accident, not merely uncommitted by discipline.

**`profile.example/` is tracked; `profile/` never is.** Same shape, different fate.
`make init` copies one to the other, and the copy lands in a directory git already
ignores — so the first thing a new user does produces a file that cannot be
published by mistake.

**This repo has no ancestor history.** It was not forked from the private one. It
was built in a fresh repo, and the first commit deliberately excluded the four
files that still carried personal details, so they could be scrubbed before landing
rather than scrubbed after. Commit one is clean. There is no earlier commit to
find.

**The README tells the user to make their own repo private** (`gh repo create
--private`), because the tool can only protect what it knows about.

## Consequences

- `.gitignore` is a security control, and `git check-ignore` is worth testing rather
  than assuming.
- The tests run with no `profile/` at all, which is both a fresh clone's state and
  proof that nothing in the package depends on personal data existing.
- Cost: the private repo's history — the actual chronology of one job hunt — isn't
  carried over. That history is worth keeping; it just isn't worth publishing. It
  stays where it is, private.
- **What this doesn't protect:** anything the user pastes into a tracked file
  themselves, or their own repo being public. The `profile/` boundary is only as
  good as the habit of keeping personal things behind it. `CLAUDE.md` states the
  rule for agents; the README states it for humans.
