#!/usr/bin/env python3
"""Build the submission archive: abhedya-chakra.zip.

What goes in: source, docs (markdown), tools, the sample dataset and the
sample documents. What stays out: node_modules, build output, caches, the
generated PDF/DOCX tree (they are large and regenerable with `make docs`),
and the DuckDB/Parquet artifacts (regenerable by ingesting).

    python3 tools/make_zip.py
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "abhedya-chakra.zip"
TOP = "abhedya-chakra"

INCLUDE_FILES = [
    "README.md", "CODE_README.md", "ABHEDYA_CHAKRA_PRD.md", "Makefile", "run.sh",
]
INCLUDE_GLOBS = [
    ("backend", "**/*.py"),
    ("backend", "requirements.txt"),
    ("frontend", "src/**/*"),
    ("frontend", "index.html"),
    ("frontend", "package.json"),
    ("frontend", "package-lock.json"),
    ("frontend", "vite.config.js"),
    ("frontend-demo", "src/**/*"),
    ("frontend-demo", "test/**/*"),
    ("frontend-demo", "index.html"),
    ("frontend-demo", "package.json"),
    ("frontend-demo", "package-lock.json"),
    ("frontend-demo", "vite.config.js"),
    ("frontend-demo", "README.md"),
    ("frontend-demo", "run_tests.sh"),
    ("tools", "*.py"),
    ("docs", "*.md"),
    ("data/raw", "SYNTHETIC_DEV_250k.csv"),
    ("data/cases", "*.json"),
    ("samples", "*.pdf"),
]
SKIP_PARTS = {"node_modules", "dist", "__pycache__", ".pytest_cache", ".vite",
              "build", "out", ".cache"}


def wanted(p: Path) -> bool:
    return p.is_file() and not any(part in SKIP_PARTS for part in p.parts) \
        and not p.name.startswith("_") and not p.name.endswith(".pyc")


def main() -> int:
    files: list[Path] = []
    for name in INCLUDE_FILES:
        p = ROOT / name
        if p.exists():
            files.append(p)
    for base, pattern in INCLUDE_GLOBS:
        for p in sorted((ROOT / base).glob(pattern)):
            if wanted(p):
                files.append(p)

    seen, uniq = set(), []
    for p in files:
        if p not in seen:
            seen.add(p)
            uniq.append(p)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in uniq:
            z.write(p, f"{TOP}/{p.relative_to(ROOT).as_posix()}")

    size = OUT.stat().st_size
    print(f"{OUT.name}: {len(uniq)} entries, {size / 1e6:.1f} MB")
    groups: dict[str, int] = {}
    for p in uniq:
        groups[p.relative_to(ROOT).parts[0]] = \
            groups.get(p.relative_to(ROOT).parts[0], 0) + 1
    for k in sorted(groups):
        print(f"  {k:<16} {groups[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
