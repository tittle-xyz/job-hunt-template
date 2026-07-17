---
name: tailor-resume
description: Aim an existing profile at a specific job posting — pick which real work to lead with and how to phrase it. Use when applying to a role, writing a new role config, or rewriting bullets for a posting.
---

# Tailor a resume

The user has written their career down once in `profile/profile.yaml`. Tailoring
decides, for one posting, which parts of it to lead with. It produces a role config
in `profile/roles/<name>.yaml` and nothing else.

## The rule

**Never invent experience.** Not a job, not a tool, not a number, not an outcome.

Everything you write must trace to something already in their profile. This isn't
squeamishness — a resume is a claim the user has to defend in an interview, out
loud, to someone who does this for a living. A fabricated bullet doesn't fail when
you write it. It fails in the room, and they won't see it coming.

If the posting wants something they don't have, **say so**. "You have no Kafka
anywhere in your profile — the posting asks for it twice. Worth a mention that
you'd be learning it, or worth skipping this one?" is useful. Quietly adding Kafka
to their skills line is not.

The honest moves are: choose what to lead with, cut what doesn't serve, reframe
real work in the posting's vocabulary, and surface something true that's currently
buried. That's a lot of room. Use it.

## Reframing vs. inventing

The line matters, so here it is concretely. Given this in their profile:

```yaml
- label: Incident Response
  text: >
    Introduced structured on-call with runbooks and blameless review, taking the
    median time-to-acknowledge from tens of minutes to under five.
```

**Fair game** for a posting about reliability culture:

```yaml
- label: Reliability
  text: >
    Built the on-call practice from scratch — runbooks, blameless review, and an
    acknowledge time that went from tens of minutes to under five.
```

Same facts, same number, aimed differently.

**Not fair game:**

- "...cutting incident volume 40%" — the 40% appeared from nowhere.
- "...across a 200-engineer org" — if the profile says ~60, it says ~60.
- "Led SRE for a Fortune 500" — a new claim wearing an old bullet's clothes.

If you want to say something and can't find its source in the profile, that's not a
phrasing problem. Ask them. It may well be true and merely unwritten — in which
case it belongs in `profile.yaml` first, because it's a fact.

## Steps

1. **Read the posting and the profile.** Note what the posting actually asks for,
   in its own words, and what in their history genuinely answers it.

2. **Say what's missing, before writing anything.** Gaps are the most useful thing
   you can tell them, and the easiest to bury.

3. **Copy an existing role config** as the starting shape. Fill in:

   - `title` — usually match the posting's title
   - `summary` — 2-3 sentences, their real background aimed at this role
   - `skills` — comma-separated, parsed literally by applicant tracking systems.
     Spell out both forms where a recruiter might search either: "Kubernetes
     (K8s)", "Infrastructure as Code (IaC)". Only list things they actually have.
   - `emphasis`, `technologies` — short sidebar lists; the sidebar overflows first
   - `leadership` — one line
   - `experience` — optional; select and order jobs by `id`. This is the pressure
     valve when the history is longer than one page.
   - `overrides` — re-pitch a job's bullets by `id`. Usually the current job: it's
     the one a reader weighs hardest.

4. **Build it and look at it:**

   ```sh
   make resume ROLE=<name>
   ```

   Heed the page warning. One page is the design; an orphaned line on page two
   reads worse than either a tight page or an honest two-pager. Trim `skills` or
   `summary` first — the sidebar spills before the body does.

5. **Diff against a neighbour.** `make resume ROLE=platform && make resume ROLE=sre`
   and compare. If two role configs produce nearly the same PDF, one of them isn't
   doing anything.

## Taste

- **Outcomes, not responsibilities.** "Responsible for CI/CD" says nothing. What
  changed because they were there?
- **Their words over the posting's, when the posting's are bad.** Matching
  vocabulary helps a keyword scan; parroting a job ad reads as parroting a job ad.
- **Specific beats grand.** "Zero-downtime migration across six service teams" is
  worth more than "extensive migration experience".
- **Avoid** "leverage", "synergy", "passionate about", "I am writing to express my
  interest". `cover_letters/template.md` carries the same list.
- **The summary is the only part guaranteed to be read.** Spend the effort there.

## What not to touch

`profile/profile.yaml` is facts. Edit it when the user tells you something new and
true about their history — a job, a date, a real number — not while tailoring. If a
tailoring session keeps wanting to reach into the profile, that's the signal their
profile is incomplete, and worth saying out loud.
