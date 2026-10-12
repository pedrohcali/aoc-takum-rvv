#!/usr/bin/env python3
"""Package tracked delivery files; excludes Git metadata, caches, local tools and course inputs."""
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = ("INPUTS/",)
files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
output = ROOT / "output" / "entrega-1.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(filter(None, files)):
        source = ROOT / name
        if source.is_file() and source != output and not name.startswith(EXCLUDED):
            archive.write(source, "aoc-takum-rvv/" + name)
print(output)
