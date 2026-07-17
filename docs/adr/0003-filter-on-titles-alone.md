# 3. Filter on titles alone

Date: 2026-07-16

## Status

Accepted

## Context

Ingestion keeps a job if it matches a keyword list. The question is *what* to match
against, and the intuitive answer — match everything you have, to avoid missing
anything — is wrong in a way you only see by looking at the output.

The original filter matched title, tags, **and the full job description**. Measured
against RemoteOK's live feed:

> 10 matches out of 100 jobs. **All 10 were false positives.** A Social Media
> Manager whose posting contains the word "infrastructure". A Servpro
> advertisement mentioning "reliability". A "Sub Agent Net Zero Teeside" — net zero
> *infrastructure*. A Business Intelligence Developer that lists AWS among its
> tools.

Precision was zero. Not low — zero. Words like "infrastructure", "reliability", and
"aws" appear in almost any job description, because descriptions are marketing
prose and marketing prose mentions everything.

Dropping descriptions and keeping tags was better, and still bad:

> Remotive: **1 title match against 22 tag-only matches**, every one of the 22
> noise — including six identical "Staff Software Engineer, Product" posts caught
> by an `aws` tag. RemoteOK tags a Medical Support Technician with `golang`.

Tags describe the stack a team happens to use, or on some boards are auto-generated
sludge. Either way they are not a claim about what the job is.

## Decision

Match **job titles only**.

A title is a claim about what the job *is*. A description mentions things. A tag
labels a stack. Store the description and the tags — they're useful once you're
reading a posting — but filter on neither.

One exception: `fetch_hn_whos_hiring` matches raw text, because a Who's Hiring
comment is prose with no title field. There is nothing else to read.

## Consequences

- Precision went from unusable to good. Across Remotive/WWR/Himalayas the same
  config returns overwhelmingly real DevOps and SRE roles; We Work Remotely's
  category feed went from 21 jobs (including a Help Desk Guru and a Sales Engineer)
  to 19, all genuine.
- **The keyword list is now load-bearing**, and this is the real cost. Applied to a
  live 1,877-job database, title filtering cut 76% of rows — and some of what it
  cut was wanted: genuine backend and infra roles whose titles just say "Senior
  Software Engineer". Adding that one keyword moved matches from 24% to 37% (+244
  jobs), surfacing a "Software Engineer, Platform — Denver" role that was otherwise
  invisible, along with every iOS posting on the board.
- So `search.yaml` says, in the file: **list the titles you'd accept, not the tools
  you know.** `software engineer` ships commented out with that measurement
  attached — one line away, with the cost stated.
- Titles that name tools still misfire: "Senior Partner Development Manager, AWS" is
  a sales job caught by the `aws` keyword. Titles are a better claim than tags, not
  a perfect one.
- The tests are the false positives themselves. Widen the filter back and
  `test_noise_titles_do_not_match` fails with the reason in its docstring.
