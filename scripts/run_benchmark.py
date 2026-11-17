#!/usr/bin/env python3
"""Phase 3 benchmark: SpMV y = A x in Takum and IEEE formats.

For each matrix (ascending nnz) and each format it records:
* the relative error of converting A, ||A_f - A||_F / ||A||_F, against the
  exact decimal values of the Matrix Market file;
* the relative error of y, ||y_f - y_ref||_2 / ||y_ref||_2, where y_ref is
  computed in binary128 (inputs, products and sums rounded to binary128);
* conversion statistics and the dynamic instruction count of the kernel.

x is the vector of ones. Errors are stored as log10; +inf marks a NaN or an
infinity in the result. Results are appended row by row, so an interrupted run
resumes where it stopped. Use --synthetic for an offline run.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from fractions import Fraction
from multiprocessing import Pool
import os
from pathlib import Path
import platform
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from takum.spmv import (ABLATION, CSR, VARIANTS, count_instructions, log10_relative_error,  # noqa: E402
                        quantize_values, read_matrix_market, reference_spmv, spmv_fast)

FIELDS = ["matrix", "nrows", "ncols", "nnz", "variant", "conversion_log10_error", "spmv_log10_error",
          "inexact", "saturated", "overflow", "flushed_to_zero", "vector_instructions",
          "scalar_instructions", "strips"]
VLEN, LMUL = 128, 1


def synthetic(index: int) -> CSR:
    """Deterministic random matrices with decimal entries, as in Matrix Market files."""
    rng = random.Random(1000 + index)
    n = rng.randint(20, 400)
    spread = rng.choice([2, 8, 16, 40])
    triplets = [(rng.randrange(n), rng.randrange(n),
                 Fraction(f"{rng.uniform(-1, 1):.6e}") * Fraction(2) ** rng.randint(-spread, spread))
                for _ in range(rng.randint(n, 20 * n))]
    return CSR.from_triplets(n, n, triplets, f"synthetic-{index:04d}")


def evaluate(job):
    name, source, use_ablation = job
    try:
        A = synthetic(int(source)) if name.startswith("synthetic-") else read_matrix_market(source, name)
    except (ValueError, IndexError, ZeroDivisionError) as error:
        return name, None, str(error)
    start = time.perf_counter()
    reference = reference_spmv(A)
    lengths = A.row_lengths()
    rows = []
    for variant in VARIANTS + (ABLATION if use_ablation else []):
        a, stats = quantize_values(A.values, variant)
        x, _ = quantize_values([Fraction(1)] * A.n_cols, variant)
        y = spmv_fast(A, variant, a, x, VLEN, LMUL)
        counts = count_instructions(lengths, variant, VLEN, LMUL)
        rows.append({"matrix": name, "nrows": A.n_rows, "ncols": A.n_cols, "nnz": A.nnz,
                     "variant": variant.name,
                     "conversion_log10_error": log10_relative_error(a, A.values),
                     "spmv_log10_error": log10_relative_error(y, reference),
                     "inexact": stats.inexact, "saturated": stats.saturated, "overflow": stats.overflow,
                     "flushed_to_zero": stats.flushed_to_zero,
                     "vector_instructions": counts["vector"], "scalar_instructions": counts["scalar"],
                     "strips": counts["strips"]})
    return name, rows, round(time.perf_counter() - start, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", type=int, help="Use N synthetic matrices instead of the downloaded ones")
    parser.add_argument("--limit", type=int, help="Only the N smallest matrices")
    parser.add_argument("--jobs", type=int, default=os.cpu_count())
    parser.add_argument("--no-ablation", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    if args.synthetic:
        jobs = [(f"synthetic-{i:04d}", str(i)) for i in range(args.synthetic)]
        errors_path, skipped_path = out / "synthetic-errors.csv", out / "synthetic-skipped.csv"
        list_hash = "synthetic"
    else:
        listing = ROOT / "results" / "matrix-list.csv"
        if not listing.exists():
            parser.error("results/matrix-list.csv not found; run scripts/fetch_matrices.py first")
        with listing.open() as file:
            matrices = list(csv.DictReader(file))
        list_hash = hashlib.sha256(listing.read_bytes()).hexdigest()
        jobs = [(f"{m['group']}/{m['name']}", str(ROOT / ".cache" / "matrices" / m["file"])) for m in matrices]
        errors_path, skipped_path = out / "spmv-errors.csv", out / "benchmark-skipped.csv"
    jobs = jobs[:args.limit]
    done = set()
    if errors_path.exists():
        with errors_path.open() as file:
            done = {row["matrix"] for row in csv.DictReader(file)}
    pending = [(name, source, not args.no_ablation) for name, source in jobs if name not in done]
    print(f"{len(done)} done, {len(pending)} pending", file=sys.stderr)
    if not pending and errors_path.exists():
        return
    start = time.perf_counter()
    new_file = not errors_path.exists()
    with errors_path.open("a", newline="") as file, skipped_path.open("a", newline="") as skipped, \
            Pool(args.jobs) as pool:
        writer = csv.DictWriter(file, FIELDS)
        if new_file:
            writer.writeheader()
        for count, (name, rows, info) in enumerate(pool.imap_unordered(evaluate, pending), 1):
            if rows is None:
                skipped.write(f"{name},{info}\n")
            else:
                writer.writerows(rows)
                file.flush()
            if count % 20 == 0 or count == len(pending):
                print(f"{count}/{len(pending)} ({time.perf_counter() - start:.0f} s)", file=sys.stderr, flush=True)
    run = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
           "python": platform.python_version(), "platform": platform.platform(),
           "matrices_requested": len(jobs), "matrix_list_sha256": list_hash,
           "vlen": VLEN, "lmul": LMUL, "x": "ones", "reference": "binary128",
           "ablation": not args.no_ablation, "jobs": args.jobs,
           "duration_seconds_this_session": round(time.perf_counter() - start, 1)}
    name = "synthetic-run.json" if args.synthetic else "benchmark-run.json"
    (out / name).write_text(json.dumps(run, indent=2) + "\n")


if __name__ == "__main__":
    main()
