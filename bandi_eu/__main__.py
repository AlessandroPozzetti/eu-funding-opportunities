"""Command-line interface."""

import argparse
import json
from pathlib import Path

from .core import audit, load, rank, sync
from .site import build_site
from .web import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="EU funding: collection and local matching")
    parser.add_argument("--data", type=Path, default=Path("data/opportunities.jsonl"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync", help="Update grants and procurement notices from the EU portal")
    commands.add_parser("audit", help="Summarize the collected dataset and missing fields")
    matching = commands.add_parser("match", help="Find open opportunities relevant to a project")
    matching.add_argument("description", help="Short project description")
    matching.add_argument("--keywords", nargs="*", default=[], help="Keywords, preferably in English")
    matching.add_argument("--limit", type=int, default=10)
    portal = commands.add_parser("serve", help="Start the local matching portal")
    portal.add_argument("--host", default="127.0.0.1")
    portal.add_argument("--port", type=int, default=8000)
    static = commands.add_parser("build-site", help="Build the public static portal")
    static.add_argument("--output", type=Path, default=Path("public_site"))
    args = parser.parse_args()
    if args.command == "sync":
        print(json.dumps(sync(args.data), ensure_ascii=False))
    elif args.command == "audit":
        print(json.dumps(audit(load(args.data)), ensure_ascii=False, indent=2))
    elif args.command == "match":
        print(json.dumps(rank(load(args.data), args.description, args.keywords, args.limit), ensure_ascii=False, indent=2))
    elif args.command == "build-site":
        print(json.dumps(build_site(args.data, args.output), ensure_ascii=False))
    else:
        serve(args.data, args.host, args.port)


if __name__ == "__main__":
    main()
