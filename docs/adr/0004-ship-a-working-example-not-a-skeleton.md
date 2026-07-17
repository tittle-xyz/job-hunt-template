# 4. Ship a working example, not a skeleton

Date: 2026-07-16

## Status

Accepted

## Context

The argument here is not original. It's made in full in
[`llm-monitor-template`'s ADR 0004](https://github.com/tittle-xyz/llm-monitor-template/blob/main/docs/adr/0004-ship-a-working-example-not-a-skeleton.md),
and it applies unchanged: a skeleton can't be run, so it can't be tested, so its CI
is decorative, so it rots — and the first person to use it inherits a repo that has
never once worked end to end.

Restated for this repo, plus what's different.

What's different is the stakes. The example here is a **person**, and the artifact
is a **resume someone sends to an employer**. A monitor shipping with placeholder
prompts produces a wrong chart. A resume tool shipping with placeholder identity
produces a document with someone else's name and a fake phone number on it, and the
failure lands in front of a hiring manager.

## Decision

Ship a complete, runnable job hunt with an invented person: Jordan Reyes, platform
engineer, three jobs, two role configs.

The example is real enough to be useful — it exercises every field, so it doubles
as the schema documentation, and the two role configs over one history demonstrate
the whole point of the tool. It's obviously not anyone's actual career.

Because the artifact is a resume, the fake data is **marked fake in ways that
survive**:

- `555-0142` — the reserved fictional range. Not a number that reaches a human.
- `jordan.reyes@example.com` — a domain that cannot receive mail.
- A comment in `profile.yaml` saying both are deliberate.

If the persona ever leaks into a real PDF, it's obvious at a glance rather than
looking like a plausible human.

The boundary: **nothing in `job_hunt/` knows who Jordan Reyes is.** The example
lives entirely in `profile.example/`. If rendering ever needs to touch the package,
the persona has leaked and that leak is the bug.

## Consequences

- A fresh clone builds a real PDF before the user has typed anything, and CI proves
  it on every push.
- The example is load-bearing for tests: the suite runs against `profile.example/`
  with no `profile/` present, which is exactly a fresh clone's state.
- Every new user starts by **editing** a working thing rather than filling in a
  signature — and can run it the whole way.
- **Risk we accept:** someone half-fills their profile and sends a resume carrying
  `555-0142`. This is not hypothetical; it happened while writing `init.py`, when
  skipping the phone prompt kept Jordan's number *and* stripped the comment
  explaining it was fake. `init.py` now names every field still holding example
  data and keeps that comment until none are left. We're betting a loud fake number
  beats a plausible one — hence the reserved range over something realistic.
