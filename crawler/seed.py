import os
import sys
import argparse
from pathlib import Path

import yaml

# Configuration
SEED_FILE = Path(os.getenv("SEED_FILE", "seeds.yml"))

# Helpers
def load_seeds() -> dict:
    if not SEED_FILE.exists():
        return {}
    data = yaml.safe_load(SEED_FILE.read_text())
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"Error: `{SEED_FILE}` must contain a top-level mapping.", file=sys.stderr)
        sys.exit(1)
    return data

def save_seeds(seeds: dict) -> None:
    SEED_FILE.write_text(yaml.safe_dump(seeds, sort_keys=False))

# Commands
def cmd_add(args):
    seeds = load_seeds()
    name = args.name
    if name in seeds:
        print(f"Seed '{name}' already exists.", file=sys.stderr)
        sys.exit(1)

    entry = {}
    if args.rss:
        entry["rss"] = args.rss
    if args.sitemap:
        entry["sitemap"] = args.sitemap
    if args.sections:
        entry["sections"] = args.sections

    if not entry:
        print("You must supply at least one of --rss, --sitemap or --section.", file=sys.stderr)
        sys.exit(1)

    seeds[name] = entry
    save_seeds(seeds)
    print(f"Added seed '{name}'.")

def cmd_rm(args):
    seeds = load_seeds()
    name = args.name
    if name not in seeds:
        print(f"Seed '{name}' not found.", file=sys.stderr)
        sys.exit(1)
    del seeds[name]
    save_seeds(seeds)
    print(f"Removed seed '{name}'.")

def cmd_ls(_args):
    seeds = load_seeds()
    if not seeds:
        print("No seeds defined in seeds.yml.")
        return
    for name, entry in seeds.items():
        print(f"- {name}:")
        for k, v in entry.items():
            if isinstance(v, list):
                for item in v:
                    print(f"    {k}: {item}")
            else:
                print(f"    {k}: {v}")

# CLI Setup
def main():
    p = argparse.ArgumentParser(prog="seed", description="Manage your seeds.yml")
    sub = p.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a new seed source")
    p_add.add_argument("name", help="Unique key for this source")
    p_add.add_argument("--rss",     help="RSS feed URL")
    p_add.add_argument("--sitemap", help="Sitemap URL")
    p_add.add_argument(
        "--section",
        dest="sections",
        action="append",
        help="Section URL (can be used multiple times)"
    )
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("rm", help="Remove a seed source by name")
    p_rm.add_argument("name", help="Name of the source to remove")
    p_rm.set_defaults(func=cmd_rm)

    p_ls = sub.add_parser("ls", help="List all seed sources")
    p_ls.set_defaults(func=cmd_ls)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
