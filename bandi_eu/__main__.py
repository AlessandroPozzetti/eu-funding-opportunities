"""Command-line interface."""

import argparse
import json
from pathlib import Path

from .core import load, rank, sync


def main() -> None:
    parser = argparse.ArgumentParser(description="EU funding: collection and local matching")
    parser.add_argument("--data", type=Path, default=Path("data/opportunities.jsonl"))
    commands = parser.add_subparsers(dest="command", required=True)
    collection = commands.add_parser("sync", help="Update opportunities from the EU portal")
    collection.add_argument("--include-tenders", action="store_true", help="Include procurement notices")
    matching = commands.add_parser("match", help="Find open opportunities relevant to a project")
    matching.add_argument("description", help="Short project description")
    matching.add_argument("--keywords", nargs="*", default=[], help="Keywords, preferably in English")
    matching.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.command == "sync":
        print(json.dumps(sync(args.data, args.include_tenders), ensure_ascii=False))
    else:
        print(json.dumps(rank(load(args.data), args.description, args.keywords, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
