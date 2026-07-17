.PHONY: help install init ingest resume list stats test lint clean

# Keep this the first target: `make` with no argument should explain itself.
help:
	@echo "Your job hunt, locally."
	@echo
	@echo "  make install           create a venv and install the tool"
	@echo "  make run               see it work: build both example resumes"
	@echo "  make init              copy profile.example/ -> profile/ (yours, gitignored)"
	@echo
	@echo "  make ingest            fetch leads from the sources in search.yaml"
	@echo "  make list              show the newest leads"
	@echo "  make stats             counts by status and source"
	@echo "  make resume ROLE=sre   build a tailored PDF from profile/roles/sre.yaml"
	@echo
	@echo "  make test              run the tests (no network, no keys needed)"
	@echo "  make coverage          tests + a coverage report"
	@echo "  make lint              check for unused/undefined names"
	@echo "  make badge             refresh the readiness badge in the README"
	@echo "  make clean             remove the database and generated PDFs"
	@echo
	@echo "Everything about you lives in profile/ and is gitignored."

VENV := venv
PY := $(VENV)/bin/python

# Find an interpreter new enough for pyproject's requires-python. Plain `python3`
# is 3.9 on stock macOS, which builds a venv that then can't install the package —
# a confusing failure a few steps after the real problem. Look for a usable one up
# front and say so plainly if there isn't one. Override with: make install PYTHON=...
PYTHON ?= $(shell for p in python3.13 python3.12 python3.11 python3; do \
	command -v $$p >/dev/null 2>&1 && \
	$$p -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null && \
	{ echo $$p; break; }; \
	done)

$(VENV):
	@test -n "$(PYTHON)" || { \
	  echo "error: no Python 3.11+ found (this tool needs it; stock macOS ships 3.9)."; \
	  echo "  macOS:  brew install python@3.13"; \
	  echo "  other:  https://www.python.org/downloads/"; \
	  echo "  or:     make install PYTHON=/path/to/python3.11"; \
	  exit 1; }
	$(PYTHON) -m venv $(VENV)

install: $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e ".[dev]"
	@echo "Installed ($$($(PY) --version)). Next: make init"
	@command -v typst >/dev/null 2>&1 || echo "NOTE: typst not found — needed for resumes. macOS: brew install typst"

# Clone -> see the thing work, in one command, before committing to anything.
# Builds both example resumes from profile.example so the contrast is visible:
# one history, two pitches. --profile is explicit here because the generator
# refuses to guess — building a resume from example data is exactly the mistake
# worth being loud about, so a demo has to ask for it by name.
run: $(VENV)
	@$(PY) -m job_hunt resume platform --profile profile.example -o resumes/tailored/example_platform.pdf
	@$(PY) -m job_hunt resume sre      --profile profile.example -o resumes/tailored/example_sre.pdf
	@echo
	@echo "Two resumes, one invented career. Same facts, aimed differently — open them"
	@echo "side by side; that contrast is what this tool is for."
	@echo "Now make it yours:  make init"

# Deliberately not $(PY): init is stdlib-only and must work before `make install`,
# on whatever python3 the machine has.
init:
	@python3 scripts/init.py

ingest:
	$(PY) -m job_hunt ingest $(if $(SOURCE),--source $(SOURCE),)

list:
	$(PY) -m job_hunt list

stats:
	$(PY) -m job_hunt stats

# ROLE is required: there's no sensible default, and guessing would build the
# wrong resume silently.
resume:
	@test -n "$(ROLE)" || { echo "usage: make resume ROLE=<name>   (e.g. ROLE=platform)"; exit 1; }
	$(PY) -m job_hunt resume $(ROLE)

test:
	$(PY) -m pytest

coverage:
	$(PY) -m pytest --cov --cov-report=term

# Same set CI lints. If `make lint` checks less than CI does, it isn't the check.
lint:
	$(PY) -m pyflakes job_hunt scripts tests

# Refresh the readiness badge in the README.
#
# Manual on purpose, and it was tried the other way first — see
# tittle-xyz/toaster-ready#28.
#
# toaster's "CI green" signal asks for the newest run on the default branch across
# all workflows, and treats an in-progress run as no-data (-6). Any workflow that
# scores the repo is itself a run on the default branch, and cannot be complete
# while it's running. So a badge generated inside Actions races its own workflow
# and lands on 94 or 88 depending on which run the API lists first. Two attempts
# to fix that from this side (waiting for ci; scoring the repo by slug instead of
# the checkout) each fixed a real bug and neither fixed the race, because the race
# isn't ours.
#
# Generated from a laptop there's no race, and the number is right. The CI gate at
# 85 means a stale badge can only ever understate a repo that improved.
#
# When #28 lands (filter to the newest *completed* run), this can move into the
# release workflow and refresh itself on the release PR — that branch isn't
# protected, so the bot can commit there.
badge:
	@command -v toaster >/dev/null || { echo "toaster not installed: go install github.com/tittle-xyz/toaster-ready/cmd/toaster@latest"; exit 1; }
	@toaster check . --format svg > docs/badge.svg
	@echo "docs/badge.svg -> $$(grep -o 'aria-label=\"[^\"]*\"' docs/badge.svg | head -1)"

clean:
	rm -rf data resumes/tailored
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "Removed the database and generated PDFs. profile/ untouched."
