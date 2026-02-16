"""CLI entry point for parsing ACF export and generating field mappings."""

import argparse
import json
import logging
import sys
from pathlib import Path

from acf.parser import parse_acf_export, pretty_print_mapping


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse ACF export JSON and generate field mapping"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to ACF export JSON file",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output path for mapping JSON file (default: print to stdout)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print human-readable summary instead of raw JSON",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s %(levelname)s: %(message)s",
    )

    mapping = parse_acf_export(args.input)

    if args.pretty:
        pretty_print_mapping(mapping)
    elif args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
        print(f"Mapping written to {args.output}")
    else:
        json.dump(mapping, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
