"""The `job-hunt` command.

    job-hunt ingest                 pull leads from the sources in search.yaml
    job-hunt list --status new      see what came back
    job-hunt show 42                read one
    job-hunt status 42 applied      mark it
    job-hunt resume platform        build a tailored PDF

Runs as `job-hunt` once installed, or `python -m job_hunt` from the repo.
"""

import sys

from . import cli, ingest, resume


def main(argv=None) -> int:
    parser = cli.build_parser(prog="job-hunt")
    # argparse has no public accessor for a parser's subparsers, so take the
    # action object back from build_parser rather than reaching into internals.
    sub = parser._subparsers_action

    # ingest
    p = sub.add_parser("ingest", help="Fetch job leads from configured sources")
    p.add_argument(
        "--source",
        help="Fetch one source only (default: every source in search.yaml)",
    )

    # resume
    p = sub.add_parser("resume", help="Build a tailored resume PDF")
    p.add_argument("role", help="Role config name, e.g. 'platform' for profile/roles/platform.yaml")
    p.add_argument("--profile", help="Profile directory (default: ./profile)")
    p.add_argument("-o", "--output", help="Output PDF path")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "ingest":
        ingest.run_ingestion([args.source] if args.source else None)
        return 0

    if args.command == "resume":
        return resume.build(args.role, profile=args.profile, output=args.output)

    return cli.dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
