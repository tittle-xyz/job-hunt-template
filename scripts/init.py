#!/usr/bin/env python3
"""Set up your profile/ from the shipped example.

    make init
    python3 scripts/init.py
    python3 scripts/init.py --dry-run
    python3 scripts/init.py --no-input --name "Ada Lovelace" --email ada@example.com

Copies profile.example/ to profile/ (which is gitignored) and puts your details
in it, so the next command you run builds a resume with your name on it.

Two constraints shape this file:

1. Standard library only, and written for old Pythons. It has to run on a fresh
   clone before `make install`, on whatever `python3` happens to be — which on
   stock macOS is still 3.9. A setup script that needs setup is not a setup
   script.

2. It edits YAML as text, never by parsing it. profile.example/search.yaml is 49%
   comments, and those comments are the documentation: which sources are
   region-locked, why the filter reads titles and not descriptions, what turning
   on 'software engineer' costs. Round-tripping through a YAML parser drops every
   one of them. Text substitution keeps them.

Unlike the init script in llm-monitor-template, this one does not delete itself.
There it renames a package — a genuinely once-only act, after which the script is
dead weight. Here the risk isn't leftover scaffolding, it's overwriting a profile
you've already filled in, which a "refuse if profile/ exists" guard handles
better. Keeping the script also means `rm -rf profile && make init` works when you
want to start over.
"""

from __future__ import print_function

import argparse
import os
import re
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(REPO_ROOT, "profile.example")
PROFILE = os.path.join(REPO_ROOT, "profile")

# The example's placeholder values, anchored exactly. If profile.example changes
# and these stop matching, init reports it rather than silently doing nothing.
IDENTITY_FIELDS = [
    ("name", "name: Jordan Reyes", "name: {value}"),
    ("phone", 'phone: "555-0142"', 'phone: "{value}"'),
    ("email", "email: jordan.reyes@example.com", "email: {value}"),
    ("location", "location: Austin, TX", "location: {value}"),
]

# Explains that the shipped phone/email are deliberately fake. Once they're real,
# it's just confusing.
FICTION_NOTE = """  # 555-01xx is the reserved "fictional" range, and example.com can't receive
  # mail. Both are deliberate: if this persona ever leaks into a real PDF,
  # it's obvious at a glance rather than looking like a plausible human.
"""

PROMPTS = [
    ("name", "Your name", "the one you want on the resume"),
    ("email", "Your email", ""),
    ("phone", "Your phone", "blank to leave it off"),
    ("location", "Your location", "e.g. Denver, CO"),
]


def ask(label, hint):
    suffix = " (%s)" % hint if hint else ""
    try:
        return raw_input("  %s%s: " % (label, suffix)).strip()  # noqa: F821  (py2 safety)
    except NameError:
        return input("  %s%s: " % (label, suffix)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def split_identity_block(text):
    """Return (before, identity_block, after).

    Everything happens inside the identity block, never on the whole file. The
    placeholders are not unique: `location: Austin, TX` is both Jordan's home and
    the Northwind job's location. A whole-file replace would edit whichever came
    first and a whole-file search would report the job's copy as unfilled
    identity. Both are wrong, and both are silent.
    """
    match = re.search(r"^identity:\n", text, flags=re.MULTILINE)
    if not match:
        return text, "", ""
    start = match.end()
    # The block ends at the next line starting in column 0 that isn't blank.
    end_match = re.search(r"^(?=[^\s#])", text[start:], flags=re.MULTILINE)
    end = start + (end_match.start() if end_match else len(text[start:]))
    return text[:start], text[start:end], text[end:]


def substitute_identity(text, values):
    """Replace the example's identity values. Returns (text, misses, leftovers).

    misses    = fields we were asked to set but whose placeholder wasn't found
                (profile.example drifted from IDENTITY_FIELDS)
    leftovers = fields still holding the example's fake data
    """
    before, block, after = split_identity_block(text)
    if not block:
        return text, [key for key, _, _ in IDENTITY_FIELDS if values.get(key)], []

    misses = []
    for key, needle, replacement in IDENTITY_FIELDS:
        value = values.get(key)
        if not value:
            continue
        if needle not in block:
            misses.append(key)
            continue
        block = block.replace(needle, replacement.format(value=value), 1)

    # Anything still matching the example is fake data the user now owns.
    leftovers = [key for key, needle, _ in IDENTITY_FIELDS if needle in block]

    # Only drop the "these are deliberately fake" note once nothing fake is left.
    # Stripping it while 555-0142 is still in the file is how someone ends up
    # mailing a resume with a fictional phone number on it.
    if not leftovers:
        block = block.replace(FICTION_NOTE, "")
    return before + block + after, misses, leftovers


def substitute_search_locations(text, locations):
    """Rewrite the `locations:` block in search.yaml.

    Colorado is right for exactly one person and wrong for everyone else, so this
    is the single most important thing to change for a new user.
    """
    if locations is None:
        return text
    if locations:
        block = "locations:\n" + "".join("  - %s\n" % loc for loc in locations)
    else:
        block = "locations: []\n"
    new_text, n = re.subn(
        r"^locations:\n(?:  - .*\n)+",
        block,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    return new_text if n else text


def read(path):
    f = open(path)
    try:
        return f.read()
    finally:
        f.close()


def write(path, text):
    f = open(path, "w")
    try:
        f.write(text)
    finally:
        f.close()


def main():
    parser = argparse.ArgumentParser(
        description="Create profile/ from profile.example/ and make it yours."
    )
    parser.add_argument("--dry-run", action="store_true", help="Say what would happen; change nothing")
    parser.add_argument("--no-input", action="store_true", help="Don't prompt (use with --name etc.)")
    parser.add_argument("--name")
    parser.add_argument("--email")
    parser.add_argument("--phone")
    parser.add_argument("--location")
    parser.add_argument(
        "--search-location",
        action="append",
        metavar="PLACE",
        help="Where to search for jobs; repeatable. Use --search-location '' for remote-only.",
    )
    args = parser.parse_args()

    if not os.path.isdir(EXAMPLE):
        print("error: %s is missing — is this the right directory?" % EXAMPLE, file=sys.stderr)
        return 1

    if os.path.isdir(PROFILE):
        print("You already have a profile/ — leaving it alone.")
        print()
        print("  Nothing was changed. To start over from the example:")
        print("      rm -rf profile && make init")
        return 0

    values = {
        "name": args.name,
        "email": args.email,
        "phone": args.phone,
        "location": args.location,
    }
    search_locations = args.search_location

    if not args.no_input:
        print("Setting up your profile. Press Enter to skip any of these —")
        print("you can edit profile/profile.yaml by hand at any point.")
        print()
        for key, label, hint in PROMPTS:
            if not values.get(key):
                values[key] = ask(label, hint)
        if search_locations is None:
            raw = ask("Where do you want to work", "comma-separated; blank = remote only")
            search_locations = [p.strip() for p in raw.split(",") if p.strip()]
        print()

    if search_locations is not None:
        search_locations = [loc for loc in search_locations if loc]

    if args.dry_run:
        print("Would copy %s -> %s" % (rel(EXAMPLE), rel(PROFILE)))
        for key, _, _ in IDENTITY_FIELDS:
            if values.get(key):
                print("  would set identity.%s = %s" % (key, values[key]))
        if search_locations is not None:
            print("  would set search locations = %s" % (search_locations or "[] (remote only)"))
        print("\nNothing was changed (--dry-run).")
        return 0

    shutil.copytree(EXAMPLE, PROFILE)

    profile_yaml = os.path.join(PROFILE, "profile.yaml")
    text, misses, leftovers = substitute_identity(read(profile_yaml), values)
    write(profile_yaml, text)

    search_yaml = os.path.join(PROFILE, "search.yaml")
    if os.path.exists(search_yaml) and search_locations is not None:
        write(search_yaml, substitute_search_locations(read(search_yaml), search_locations))

    print("Created %s" % rel(PROFILE))
    if misses:
        # The example drifted from what this script expects. Say so — the copy
        # still happened, so the fix is a two-minute edit, not a rerun.
        print()
        print("warning: couldn't find the expected placeholder for: %s" % ", ".join(misses))
        print("         Set those by hand in %s" % rel(profile_yaml))

    if leftovers:
        # Say exactly which fields are still the example persona. "Mostly filled
        # in" is the dangerous state: a resume that looks finished and quietly
        # carries a fictional phone number.
        print()
        print("Still example data — %s in %s:" % (", ".join(leftovers), rel(profile_yaml)))
        for key, needle, _ in IDENTITY_FIELDS:
            if key in leftovers:
                print("    %s" % needle)
        print("  Fix these before you send anything built from this profile.")

    print()
    print("Next:")
    print("    make resume ROLE=platform     build a PDF from profile/roles/platform.yaml")
    print("    make ingest                   fetch leads (edit profile/search.yaml first)")
    print()
    print("profile/ is gitignored. Your details stay on your machine.")
    return 0


def rel(path):
    try:
        return os.path.relpath(path, REPO_ROOT)
    except ValueError:
        return path


if __name__ == "__main__":
    sys.exit(main())
