#!/usr/bin/env python3
"""Download the real sparse matrices used in the phase 3 benchmark.

Source: the NIST Matrix Market (https://math.nist.gov/MatrixMarket/), whose
collections (Harwell-Boeing, SPARSKIT, NEP, misc) are also part of the
SuiteSparse collection. The SuiteSparse file server refused every download
during this project (HTTP 403 AccessDenied from its storage, even for known
matrices), so it could not be used.

Selection: every real, integer or pattern coordinate matrix with at most
50,000 nonzeros after symmetric expansion, the same bound as Hunhold (2025).
Files are cached in .cache/matrices/ (not versioned). results/matrix-list.csv
records the selection and the SHA-256 of every downloaded file.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "matrices"
INDEX_URL = "https://math.nist.gov/MatrixMarket/matrices.html"
FILE_URL = "https://math.nist.gov/pub/MatrixMarket2/{path}.mtx.gz"
USER_AGENT = "takum-rvv-benchmark/1.0 (UFMG computer architecture course project)"
FIELDS = ["group", "name", "nrows", "ncols", "nnz", "field", "symmetry", "file", "sha256"]


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def matrix_paths(index_html: str) -> list[str]:
    paths = re.findall(r'href="/MatrixMarket/data/([^"]+)\.html"', index_html, flags=re.IGNORECASE)
    return sorted(set(paths))


def inspect(text: str):
    """Header fields and nonzeros after symmetric expansion, or None."""
    lines = iter(text.splitlines())
    header = next(lines).split()
    if len(header) != 5 or header[0] != "%%MatrixMarket":
        return None
    layout, field, symmetry = (h.lower() for h in header[2:])
    if layout != "coordinate" or field not in ("real", "integer", "pattern"):
        return None
    line = next(lines)
    while line.startswith("%") or not line.strip():
        line = next(lines)
    nrows, ncols, entries = map(int, line.split())
    nnz = entries
    if symmetry != "general":
        diagonal = 0
        for _ in range(entries):
            parts = next(lines).split()
            diagonal += parts[0] == parts[1]
        nnz = 2 * entries - diagonal
    return {"nrows": nrows, "ncols": ncols, "nnz": nnz, "field": field, "symmetry": symmetry}


def download(path: str, max_nnz: int):
    group, name = path.rsplit("/", 1)
    target = CACHE / (path.replace("/", "__") + ".mtx")
    if target.exists():
        data = target.read_bytes()
    else:
        try:
            data = gzip.decompress(fetch(FILE_URL.format(path=path)))
        except urllib.error.HTTPError as error:
            if error.code == 300:  # elemental (unassembled) matrices have no .mtx file
                return None
            raise
    if not target.exists():
        target.write_bytes(data)
    info = inspect(data.decode("ascii", errors="replace"))
    if info is None or info["nnz"] > max_nnz:
        return None
    return {"group": group, "name": name, **info, "file": target.name,
            "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-nnz", type=int, default=50000)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    index = CACHE / "matrices.html"
    if not index.exists():
        index.write_bytes(fetch(INDEX_URL))
    paths = matrix_paths(index.read_text(errors="replace"))
    print(f"{len(paths)} matrices listed", file=sys.stderr)
    selected, failed, excluded = [], [], 0
    with ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(download, p, args.max_nnz): p for p in paths}
        for count, future in enumerate(futures, 1):
            try:
                result = future.result()
            except Exception as error:  # report and continue
                failed.append(futures[future])
                print(f"failed: {futures[future]}: {error}", file=sys.stderr)
                continue
            if result is None:
                excluded += 1
            else:
                selected.append(result)
            if count % 50 == 0:
                print(f"{count}/{len(paths)}", file=sys.stderr, flush=True)
    selected.sort(key=lambda m: (m["nnz"], m["group"], m["name"]))
    with (ROOT / "results" / "matrix-list.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        writer.writerows(selected)
    print(f"{len(selected)} selected, {excluded} excluded (complex, dense, elemental or over {args.max_nnz} nnz), "
          f"{len(failed)} failed", file=sys.stderr)
    return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main())
