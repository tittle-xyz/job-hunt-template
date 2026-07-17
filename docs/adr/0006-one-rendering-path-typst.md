# 6. One rendering path, and it's Typst

Date: 2026-07-16

## Status

Accepted

## Context

The repo this came from had three ways to build a resume: a `.docx` writer via
python-docx, an HTML template, and a Typst template. That's the natural history of
a personal tool — you try a thing, it's not quite right, you try another, and the
old one stays because deleting it isn't urgent.

For a template it's a different story. Three paths mean three things to keep
working, three things to document, three things for a newcomer to choose between
with no basis for choosing. Two of them had already stopped being maintained: the
one-page tuning, the ATS work, and the recent commits all went into Typst.

The specific pull toward `.docx` deserves an answer, because it's real. Some
application portals want a Word file, and "ATS-friendly" advice often means "send
.docx".

## Decision

Typst only. Delete the HTML template and both other generators.

Typst is a single binary, its input is plain text that diffs cleanly in git, and it
produces PDFs that look designed rather than word-processed. The template is layout
with no person in it (ADR 0002), which is only pleasant to write because the
language is decent.

On `.docx`: a PDF is accepted essentially everywhere, and the ATS parsing story is
better than folklore suggests — text in a well-formed PDF extracts fine, which is
exactly why `pdftotext` is used to verify the output in tests. If a portal demands
Word, converting one PDF once beats maintaining a second renderer forever.

## Consequences

- One thing to keep working, and CI installs Typst so the PDF path is genuinely
  exercised rather than skipped.
- Typst is a real dependency and not a Python one — `make install` says so if it's
  missing, and the resume tests skip (rather than fail) on a machine without it.
- The layout is one page. This is the design, not an accident, and it overflows
  quietly — so `resume.typ` publishes its final page count and the generator warns.
  See `search.yaml`'s neighbours in `roles/*.yaml`: `experience:` selects jobs when
  a career outgrows the page.
- **Reversible if wrong.** The generator hands the template a single JSON blob, so a
  second renderer would consume the same merged data rather than reaching back into
  the profile. If someone genuinely needs `.docx`, that's the seam to build it on.
