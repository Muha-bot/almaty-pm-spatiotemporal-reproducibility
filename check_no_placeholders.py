#!/usr/bin/env python3
"""Fail if unresolved bracket placeholders remain before a public release.

Scans tracked text files for the literal placeholder tokens used throughout
this repository ([Author], [Institution], [Journal name], [repository URL]
and similar), so that a Public GitHub release or Zenodo deposit cannot go
out with them unfilled by accident.

This script does not fill in or guess any value; it only reports where
placeholders remain. Filling them in with the real author list is a
decision for the authors to make outside of this script.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Only text-ish files; skip binary data/figures.
TEXT_SUFFIXES = {".md", ".cff", ".txt", ".yaml", ".yml", ".py", ".sh", ".cfg", ".json"}

PLACEHOLDER_RE = re.compile(
    r"\[(Author|Institution|Journal name|repository URL[^\]]*|Country|"
    r"Dataset|Grant number|Ethics approval|Company|Location)\]"
)

# This script's own docstring/body legitimately mentions the placeholder
# tokens as documentation; skip it explicitly.
SELF_PATH = Path(__file__).resolve()


def main() -> int:
    hits: list[tuple[Path, int, str]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == SELF_PATH:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if PLACEHOLDER_RE.search(line):
                hits.append((path.relative_to(ROOT), lineno, line.strip()))

    if hits:
        print("Unresolved placeholders found (expected before final release,")
        print("but must be resolved before making the repository Public):\n")
        for rel_path, lineno, line in hits:
            print(f"  {rel_path}:{lineno}: {line}")
        print(f"\n{len(hits)} placeholder occurrence(s) remaining.")
        return 1

    print("No unresolved placeholders found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
