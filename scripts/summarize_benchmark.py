#!/usr/bin/env python3
"""Summarize the benchmark rows into the files used by the paper and slides.

Outputs (in the same folder as the input):
* <prefix>-cdf.csv and <prefix>-conversion-cdf.csv: per format, the sorted
  log10 errors against the share of matrices, for pgfplots. An exact result
  is drawn at FLOOR; "inf" (NaN or infinity in the result) is left unbounded.
* <prefix>-summary.json: medians, shares and instruction totals per format.
* <prefix>-macros.tex: the same numbers as LaTeX macros.
Works on partial results, so the paper can be drafted while a run continues.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FLOOR = -18.0
ORDER = ["T8", "E4M3", "E5M2", "T16", "FP16", "T32", "FP32", "T8-stepwise", "T16-stepwise", "T32-stepwise"]
TAKUM_OF_WIDTH = {"E4M3": "T8", "E5M2": "T8", "FP16": "T16", "FP32": "T32"}
WORDS = {"T8": "TEight", "E4M3": "EFourMThree", "E5M2": "EFiveMTwo", "T16": "TSixteen", "FP16": "FPSixteen",
         "T32": "TThirtyTwo", "FP32": "FPThirtyTwo", "T8-stepwise": "TEightStep",
         "T16-stepwise": "TSixteenStep", "T32-stepwise": "TThirtyTwoStep"}


def parse(value: str):
    return None if value in ("", "None") else float(value)


def cdf(rows, column, variants, path):
    columns = {v: sorted(x for x in (parse(r[column]) for r in rows if r["variant"] == v) if x is not None)
               for v in variants}
    n = min(len(c) for c in columns.values())
    with path.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["share"] + variants)
        for i in range(n):
            values = [columns[v][i] for v in variants]
            writer.writerow([f"{100 * (i + 1) / n:.4f}"] +
                            ["inf" if x == math.inf else f"{max(x, FLOOR):.6f}" for x in values])
    return columns


def quantile(values, q):
    return values[min(len(values) - 1, int(q * len(values)))] if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "results" / "spmv-errors.csv")
    args = parser.parse_args()
    with args.input.open() as file:
        rows = list(csv.DictReader(file))
    if not rows:
        sys.exit("no rows")
    prefix = args.input.name.removesuffix("-errors.csv")
    folder = args.input.parent
    variants = [v for v in ORDER if any(r["variant"] == v for r in rows)]
    spmv = cdf(rows, "spmv_log10_error", variants, folder / f"{prefix}-cdf.csv")
    conversion = cdf(rows, "conversion_log10_error", variants, folder / f"{prefix}-conversion-cdf.csv")
    matrices = sorted({r["matrix"] for r in rows})
    nnz = sum(int(r["nnz"]) for r in rows if r["variant"] == "T8")
    totals = {v: {"vector": sum(int(r["vector_instructions"]) for r in rows if r["variant"] == v),
                  "scalar": sum(int(r["scalar_instructions"]) for r in rows if r["variant"] == v)}
              for v in variants}
    summary = {"matrices": len(matrices), "nnz_total": nnz,
               "max_nnz": max(int(r["nnz"]) for r in rows), "formats": {}}
    for v in variants:
        errors = spmv[v]
        finite = [x for x in errors if x != math.inf]
        entry = {
            "matrices_with_error": len(errors),
            "spmv_median_log10": quantile(errors, 0.5),
            "spmv_p90_log10": quantile(errors, 0.9),
            "spmv_share_below_100pct": 100 * sum(x < 0 for x in errors) / len(errors),
            "spmv_share_infinite": 100 * (len(errors) - len(finite)) / len(errors),
            "conversion_median_log10": quantile(conversion[v], 0.5),
            "conversion_share_infinite": 100 * sum(x == math.inf for x in conversion[v]) / max(1, len(conversion[v])),
            "matrices_with_saturation": sum(int(r["saturated"]) > 0 for r in rows if r["variant"] == v),
            "matrices_with_overflow": sum(int(r["overflow"]) > 0 for r in rows if r["variant"] == v),
            "matrices_with_flush_to_zero": sum(int(r["flushed_to_zero"]) > 0 for r in rows if r["variant"] == v),
            "vector_instructions": totals[v]["vector"],
            "scalar_instructions": totals[v]["scalar"],
            "vector_instructions_per_nnz": totals[v]["vector"] / nnz,
        }
        if v in TAKUM_OF_WIDTH and TAKUM_OF_WIDTH[v] in totals:
            takum = totals[TAKUM_OF_WIDTH[v]]
            entry["takum_vector_reduction_pct"] = 100 * (1 - takum["vector"] / totals[v]["vector"])
            entry["takum_total_reduction_pct"] = 100 * (
                1 - (takum["vector"] + takum["scalar"]) / (totals[v]["vector"] + totals[v]["scalar"]))
        summary["formats"][v] = entry
    # Matrix-by-matrix comparisons, only where the second format stays in
    # range (its error is not infinite); the infinite cases are reported above.
    by_matrix = {}
    for r in rows:
        by_matrix.setdefault(r["matrix"], {})[r["variant"]] = parse(r["spmv_log10_error"])
    summary["pairs"] = {}
    for takum, other in (("T8", "E4M3"), ("T8", "E5M2"), ("T16", "FP16"), ("T32", "FP32"),
                         ("T8", "T8-stepwise"), ("T16", "T16-stepwise"), ("T32", "T32-stepwise")):
        if takum not in variants or other not in variants:
            continue
        values = [(d[takum], d[other]) for d in by_matrix.values()
                  if d.get(takum) is not None and d.get(other) is not None and d[other] != math.inf]
        summary["pairs"][f"{takum}|{other}"] = {
            "matrices": len(values),
            "first_better": sum(a < b for a, b in values),
            "first_worse": sum(a > b for a, b in values),
            "equal": sum(a == b for a, b in values)}
    (folder / f"{prefix}-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    def number(x, digits=1):
        if x is None:
            return "--"
        return "\\infty" if x == math.inf else f"{x:.{digits}f}"

    lines = [f"% Generated by scripts/summarize_benchmark.py from {args.input.name}",
             f"\\newcommand{{\\BenchMatrices}}{{{len(matrices)}}}",
             f"\\newcommand{{\\BenchNnz}}{{{nnz:,}}}".replace(",", "{,}"),
             f"\\newcommand{{\\BenchMaxNnz}}{{{summary['max_nnz']:,}}}".replace(",", "{,}")]
    for v, e in summary["formats"].items():
        w = WORDS[v]
        lines += [f"\\newcommand{{\\BenchMedian{w}}}{{{number(e['spmv_median_log10'])}}}",
                  f"\\newcommand{{\\BenchConvMedian{w}}}{{{number(e['conversion_median_log10'])}}}",
                  f"\\newcommand{{\\BenchBelowOne{w}}}{{{e['spmv_share_below_100pct']:.0f}}}",
                  f"\\newcommand{{\\BenchInf{w}}}{{{e['spmv_share_infinite']:.0f}}}",
                  f"\\newcommand{{\\BenchSat{w}}}{{{e['matrices_with_saturation']}}}",
                  f"\\newcommand{{\\BenchOverflow{w}}}{{{e['matrices_with_overflow']}}}",
                  f"\\newcommand{{\\BenchFlush{w}}}{{{e['matrices_with_flush_to_zero']}}}",
                  f"\\newcommand{{\\BenchAboveOne{w}}}{{{100 - e['spmv_share_below_100pct']:.0f}}}",
                  f"\\newcommand{{\\BenchVecPerNnz{w}}}{{{e['vector_instructions_per_nnz']:.2f}}}"]
        if "takum_vector_reduction_pct" in e:
            lines += [f"\\newcommand{{\\BenchVecReduction{w}}}{{{e['takum_vector_reduction_pct']:.0f}}}",
                      f"\\newcommand{{\\BenchTotalReduction{w}}}{{{e['takum_total_reduction_pct']:.0f}}}"]
    for pair, counts in summary["pairs"].items():
        first, second = pair.split("|")
        name = WORDS[first] + WORDS[second]
        lines += [f"\\newcommand{{\\BenchInRange{name}}}{{{counts['matrices']}}}",
                  f"\\newcommand{{\\BenchBetter{name}}}{{{counts['first_better']}}}",
                  f"\\newcommand{{\\BenchWorse{name}}}{{{counts['first_worse']}}}",
                  f"\\newcommand{{\\BenchEqual{name}}}{{{counts['equal']}}}"]
    (folder / f"{prefix}-macros.tex").write_text("\n".join(lines) + "\n")
    print(json.dumps({v: {k: e[k] for k in ("spmv_median_log10", "spmv_share_infinite")}
                      for v, e in summary["formats"].items()}, indent=1))


if __name__ == "__main__":
    main()
