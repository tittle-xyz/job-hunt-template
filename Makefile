.PHONY: help install init ingest resume list stats test lint clean

# Keep this the first target: `make` with no argument should explain itself.
help:
	@echo "Your job hunt, locally."
	@echo
	@echo "  make install            create a venv and install the tool"
	@echo "  make init              copy profile.example/ -> profile/ (yours, gitignored)"
	@echo
	@echo "  make ingest            fetch leads from the sources in search.yaml"
	@echo "  make list              show the newest leads"
	@echo "  make stats             counts by status and source"
	@echo "  make resume ROLE=sre   build a tailored PDF from profile/roles/sre.yaml"
	@echo
	@echo "  make test              run the tests (no network, no keys needed)"
	@echo "  make lint              check for unused/undefined names"
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

init:
	@$(PY) init.py

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

lint:
	$(PY) -m pyflakes job_hunt tests

clean:
	rm -rf data resumes/tailored
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "Removed the database and generated PDFs. profile/ untouched."
