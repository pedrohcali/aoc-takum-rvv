#!/usr/bin/env python3
"""Machine learning case: dense layers y = ReLU(W x) in Takum and IEEE formats.

Each trial is one random bias-free network (64 -> 64 -> 64 -> 16, He
initialisation, Gaussian input; see takum/mlp.py). The input is scaled by
2^k for every k in takum.mlp.SCALES, and for every format the script records
the relative error of the network output against a binary128 reference,
||y_f - y_ref||_2 / ||y_ref||_2 as log10, and the dynamic instruction count.

Outputs:
* results/mlp-errors.csv: one row per (trial, scale, format);
* results/mlp-curve.csv: median log10 error per scale and format, and the
  share of trials whose error is 100% or more (output lost);
* results/mlp-summary.json and results/mlp-macros.tex for the paper;
* results/mlp-run.json: platform and duration.

--summarize-only rebuilds the last four from an existing mlp-errors.csv.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from multiprocessing import Pool
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from takum.mlp import LAYERS, SCALES, mlp_error, mlp_instructions, network, reference_mlp, scaled  # noqa: E402
from takum.spmv import ABLATION, VARIANTS, quantize_values  # noqa: E402
from summarize_benchmark import FLOOR, ORDER, WORDS  # noqa: E402

FIELDS = ["trial", "scale_log2", "variant", "log10_error", "range_events", "vector_instructions",
          "scalar_instructions", "macs"]
VLEN, LMUL = 128, 1
SEED_BASE = 5000


def evaluate(trial: int):
    weights, x = network(SEED_BASE + trial)
    variants = VARIANTS + ABLATION
    quantized = {v.name: [quantize_values(W.values, v)[0] for W in weights] for v in variants}
    weight_events = {}
    for v in variants:
        weight_events[v.name] = 0
        for W in weights:
            stats = quantize_values(W.values, v)[1]
            weight_events[v.name] += stats.saturated + stats.overflow + stats.flushed_to_zero
    counts = {v.name: mlp_instructions(weights, v, VLEN, LMUL) for v in variants}
    rows = []
    for k in SCALES:
        xs = scaled(x, k)
        reference = reference_mlp(weights, xs)
        for v in variants:
            error, events = mlp_error(weights, xs, v, reference, VLEN, LMUL, quantized[v.name])
            rows.append({"trial": trial, "scale_log2": k, "variant": v.name, "log10_error": error,
                         "range_events": events + weight_events[v.name],
                         "vector_instructions": counts[v.name]["vector"],
                         "scalar_instructions": counts[v.name]["scalar"], "macs": counts[v.name]["macs"]})
    return rows


def parse(value: str):
    return None if value in ("", "None") else float(value)


def summarize(errors_path: Path, folder: Path):
    with errors_path.open() as file:
        rows = list(csv.DictReader(file))
    variants = [v for v in ORDER if any(r["variant"] == v for r in rows)]
    table = {}
    for r in rows:
        table.setdefault((r["variant"], int(r["scale_log2"])), []).append(parse(r["log10_error"]))
    scales = sorted({int(r["scale_log2"]) for r in rows})
    trials = len({r["trial"] for r in rows})

    def median(values):
        values = [v for v in values if v is not None]
        return statistics.median_low(sorted(values)) if values else None

    def lost(values):
        values = [v for v in values if v is not None]
        return 100 * sum(v >= 0 for v in values) / len(values)

    with (folder / "mlp-curve.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["scale"] + variants + [f"lost_{v}" for v in variants])
        for k in scales:
            medians = [median(table[v, k]) for v in variants]
            writer.writerow([k] + ["inf" if m == math.inf else f"{max(m, FLOOR):.6f}" for m in medians]
                            + [f"{lost(table[v, k]):.2f}" for v in variants])

    first = {r["variant"]: r for r in rows if r["trial"] == rows[0]["trial"] and int(r["scale_log2"]) == 0}
    summary = {"trials": trials, "scales_log2": scales, "layers": list(LAYERS), "formats": {}}
    for v in variants:
        per_scale = {k: median(table[v, k]) for k in scales}
        usable = [k for k in scales if lost(table[v, k]) == 0]
        summary["formats"][v] = {
            "median_log10_at_scale_0": per_scale[0],
            "median_log10_by_scale": per_scale,
            "lost_share_by_scale": {k: lost(table[v, k]) for k in scales},
            "scales_without_loss": usable,
            "vector_instructions_per_mac": int(first[v]["vector_instructions"]) / int(first[v]["macs"]),
            "vector_instructions": int(first[v]["vector_instructions"]),
            "total_instructions": int(first[v]["vector_instructions"]) + int(first[v]["scalar_instructions"])}
    for ieee, takum in (("E4M3", "T8"), ("E5M2", "T8"), ("FP16", "T16"), ("FP32", "T32")):
        if ieee in summary["formats"] and takum in summary["formats"]:
            a, b = summary["formats"][takum], summary["formats"][ieee]
            b["takum_vector_reduction_pct"] = 100 * (1 - a["vector_instructions"] / b["vector_instructions"])
            b["takum_total_reduction_pct"] = 100 * (1 - a["total_instructions"] / b["total_instructions"])
    ablation = {}
    for w in (8, 16, 32):
        fused, step = f"T{w}", f"T{w}-stepwise"
        if fused in variants and step in variants:
            pairs = [(a, b) for k in scales for a, b in zip(table[fused, k], table[step, k])
                     if a is not None and b is not None]
            ablation[fused] = {"runs": len(pairs), "fused_better": sum(a < b for a, b in pairs),
                               "fused_worse": sum(a > b for a, b in pairs),
                               "median_gain_log10": statistics.median(b - a for a, b in pairs)}
    summary["ablation"] = ablation
    (folder / "mlp-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    def number(x, digits=1):
        return "--" if x is None else "\\infty" if x == math.inf else f"{x:.{digits}f}"

    lines = [f"% Generated by scripts/run_mlp.py from {errors_path.name}",
             f"\\newcommand{{\\MlpTrials}}{{{trials}}}",
             f"\\newcommand{{\\MlpRuns}}{{{trials * len(scales)}}}",
             f"\\newcommand{{\\MlpMacs}}{{{int(rows[0]['macs']):,}}}".replace(",", "{,}")]
    for v, e in summary["formats"].items():
        w = WORDS[v]
        usable = e["scales_without_loss"]
        lines += [f"\\newcommand{{\\MlpMedian{w}}}{{{number(e['median_log10_at_scale_0'])}}}",
                  f"\\newcommand{{\\MlpVecPerMac{w}}}{{{e['vector_instructions_per_mac']:.3f}}}",
                  f"\\newcommand{{\\MlpUsable{w}}}{{{len(usable)}}}",
                  f"\\newcommand{{\\MlpLostLow{w}}}{{{e['lost_share_by_scale'][scales[0]]:.0f}}}",
                  f"\\newcommand{{\\MlpLostHigh{w}}}{{{e['lost_share_by_scale'][scales[-1]]:.0f}}}"]
        if "takum_vector_reduction_pct" in e:
            lines += [f"\\newcommand{{\\MlpVecReduction{w}}}{{{e['takum_vector_reduction_pct']:.0f}}}",
                      f"\\newcommand{{\\MlpTotalReduction{w}}}{{{e['takum_total_reduction_pct']:.0f}}}"]
    for v, a in ablation.items():
        w = WORDS[v]
        lines += [f"\\newcommand{{\\MlpFusedBetter{w}}}{{{a['fused_better']}}}",
                  f"\\newcommand{{\\MlpFusedWorse{w}}}{{{a['fused_worse']}}}",
                  f"\\newcommand{{\\MlpFusedRuns{w}}}{{{a['runs']}}}"]
    (folder / "mlp-macros.tex").write_text("\n".join(lines) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=64)
    parser.add_argument("--jobs", type=int, default=os.cpu_count())
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    errors_path = out / "mlp-errors.csv"
    if not args.summarize_only:
        start = time.perf_counter()
        with errors_path.open("w", newline="") as file, Pool(args.jobs) as pool:
            writer = csv.DictWriter(file, FIELDS)
            writer.writeheader()
            for count, rows in enumerate(pool.imap(evaluate, range(args.trials)), 1):
                writer.writerows(rows)
                if count % 8 == 0 or count == args.trials:
                    print(f"{count}/{args.trials} ({time.perf_counter() - start:.0f} s)", file=sys.stderr, flush=True)
        run = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "python": platform.python_version(), "platform": platform.platform(),
               "trials": args.trials, "seed_base": SEED_BASE, "layers": list(LAYERS),
               "scales_log2": list(SCALES), "vlen": VLEN, "lmul": LMUL, "reference": "binary128",
               "jobs": args.jobs, "duration_seconds": round(time.perf_counter() - start, 1)}
        (out / "mlp-run.json").write_text(json.dumps(run, indent=2) + "\n")
    summary = summarize(errors_path, out)
    print(json.dumps({v: {"median@0": e["median_log10_at_scale_0"], "usable": e["scales_without_loss"]}
                      for v, e in summary["formats"].items()}, indent=1))
    print(json.dumps(summary["ablation"], indent=1))


if __name__ == "__main__":
    main()
