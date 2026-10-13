#!/usr/bin/env python3
"""Build the submission archive from source, tests, results and paper files."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    "README.md", "Makefile", "pyproject.toml",
    "takum/*.py", "tests/*.py", "scripts/*.py",
    "scripts/*.patch", "scripts/libtakum-LICENSE",
    "results/*.json", "results/*.csv",
    "paper/*.tex", "paper/*.cls", "output/pdf/phase1.pdf",
)
files = sorted({path for pattern in PATTERNS for path in ROOT.glob(pattern)
                if path.is_file()})
output = ROOT / "output" / "entrega-1.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for source in files:
        archive.write(source, "aoc-takum-rvv/" + source.relative_to(ROOT).as_posix())
print(output)
