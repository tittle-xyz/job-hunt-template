# 1. Record architecture decisions

Date: 2026-07-16

## Status

Accepted

## Context

This repo is a template. Whatever is written here gets copied into every job hunt
made from it, and the people copying it won't have been in the conversation that
produced it.

Several decisions here look arbitrary and aren't. The filter ignores job
descriptions. The resume generator refuses to run without a profile while
ingestion happily falls back to the example. There are three dependencies and no
cover-letter generator. Each of those has a reason, and each is the sort of thing a
reasonable person would "fix" on sight.

## Decision

Record the decisions that were expensive to reach, in `docs/adr/`, in the format
Michael Nygard describes: context, decision, consequences.

Where a decision came from a measurement, the ADR carries the numbers. "We filter
on titles because tags are noisy" is an opinion someone can override with a
different opinion. "10 of 100 RemoteOK matches came from descriptions and all 10
were false positives" is evidence, and arguing with it requires better evidence.

## Consequences

- A future maintainer — human or agent — can tell a considered decision from an
  accident, and knows which measurements to redo before reversing one.
- ADRs are immutable. When one is superseded, add a new one and mark the old one
  Superseded. Editing history to look wiser than we were defeats the point.
- Not every choice needs one. Six ADRs for a tool this size is close to the ceiling.
