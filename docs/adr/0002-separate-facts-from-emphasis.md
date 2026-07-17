# 2. Separate facts from emphasis

Date: 2026-07-16

## Status

Accepted

## Context

This template started as one person's job-hunt repo, and in that repo the resume
generator could tailor exactly one job — the current one. The Typst template
hardcoded the rest of the work history: three employers, their dates, their
bullets. The YAML schema had fields named `<employer>_title` and
`<employer>_content`, after the employer they described.

It worked, because it only had to work for its author. But "use this yourself"
would have meant opening a `.typ` file and deleting someone else's career from it,
which is not a template — it's a hand-me-down.

The underlying confusion was that two different kinds of data were living in the
same places. Where you worked is a **fact**. Which parts of that you lead with, for
a given posting, is **emphasis**. The old design put facts in the template and
emphasis in the config, then hardcoded the one job where the two overlapped.

## Decision

Split them.

**`profile/profile.yaml` is facts.** Identity, full work history, certifications,
education. Every job carries a stable `id`. This file doesn't change between
applications.

**`profile/roles/<name>.yaml` is emphasis.** An overlay: title, summary, skills,
sidebar lists. It can select and order jobs with `experience:` and re-pitch any
job's bullets via `overrides:` keyed by `id`. It states nothing that the profile
already states.

`resume.typ` becomes layout with no person in it. All data arrives as one JSON blob
through `--input`.

The generalisation matters: the old design made the current job special because
that's the one its author kept re-pitching. Now *any* job can be overridden by
`id`, and it's a property of the schema rather than a hardcoded case.

## Consequences

- The example ships two role configs over one history — same facts, different
  pitch. That contrast is the clearest available explanation of what the tool does,
  so it's the README's headline.
- Stable `id`s mean a job can change title or company without breaking role configs
  that reference it.
- `experience:` doubles as the pressure valve for a one-page layout: as a career
  outgrows the page, select rather than overflow.
- **The rule this creates:** if a role config restates history, the fact belongs in
  the profile. If a tailoring session keeps reaching into `profile.yaml`, the
  profile is incomplete. Both are stated in the `tailor-resume` skill.
- Cost: two files instead of one, and a merge step to understand. Worth it — the
  merge is small, about half of it validation, and it's what makes the repo
  shareable at all.
