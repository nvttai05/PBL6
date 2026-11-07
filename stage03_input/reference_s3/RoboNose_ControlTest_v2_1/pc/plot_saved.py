#!/usr/bin/env python3
"""Reopen a saved CSV. Works while acquisition is stopped; does not modify it."""
import argparse
import json
from pathlib import Path
from dashboard import export_saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Path to samples.csv")
    parser.add_argument("--window", type=float, default=600, help="Last N seconds to plot")
    parser.add_argument("--output", type=Path, help="Output PNG; defaults to review.png beside CSV")
    args = parser.parse_args()
    if args.window <= 0:
        parser.error("--window must be > 0")
    source = args.csv.resolve()
    metadata_file = source.parent / "metadata.json"
    mode = json.loads(metadata_file.read_text(encoding="utf-8")).get("mode", "HARDWARE") if metadata_file.exists() else "UNKNOWN"
    target = args.output or source.parent / "review.png"
    export_saved(source, target, args.window, mode)
    print(target)


if __name__ == "__main__":
    main()
