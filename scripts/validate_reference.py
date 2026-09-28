#!/usr/bin/env python3
"""Differential validation against a pinned upstream libtakum C build.

Only the upstream C library is compiled; our Python implementation has no
runtime dependency on it. Results include the exact revision and test seed.
"""
import argparse
import ctypes
from datetime import datetime, timezone
from fractions import Fraction
import json
import math
import hashlib
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from takum import TakumALU, TakumFormat

REVISION = "776ac0ca7855f640100731ed8bbb0c7cf83b2d94"
URL = "https://github.com/takum-arithmetic/libtakum.git"
SEED = 20260928


def build_reference(mode):
    source = ROOT / ".cache" / "libtakum"
    source.parent.mkdir(exist_ok=True)
    if not source.exists():
        subprocess.run(["git", "clone", URL, str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "checkout", "--detach", REVISION], check=True)
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]):
        raise RuntimeError("Reference checkout has local changes")
    if mode == "portable":
        patched = source.parent / "libtakum-portable"
        shutil.copytree(source, patched, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
        patch = ROOT / "scripts" / "libtakum-portable.patch"
        subprocess.run(["git", "apply", str(patch)], cwd=patched, check=True)
        source = patched
    library = source.parent / ("libtakum.dylib" if sys.platform == "darwin" else "libtakum.so")
    files = ["codec", "conversion", "util", "addition", "subtraction", "multiplication"]
    subprocess.run([os.environ.get("CC", "cc"), "-O2", "-std=c99", "-fPIC", "-shared",
                    *[str(source / "src" / (f + ".c")) for f in files],
                    "-lm", "-o", str(library)], check=True)
    return library


def functions(lib, width):
    integer = {8: ctypes.c_int8, 16: ctypes.c_int16, 32: ctypes.c_int32}[width]
    decode = getattr(lib, f"takum{width}_to_float64")
    decode.argtypes, decode.restype = [integer], ctypes.c_double
    encode = getattr(lib, f"takum{width}_from_float64")
    encode.argtypes, encode.restype = [ctypes.c_double], integer
    operations = {}
    for short, name in (("add", "addition"), ("sub", "subtraction"), ("mul", "multiplication")):
        f = getattr(lib, f"takum{width}_{name}")
        f.argtypes, f.restype = [integer, integer], integer
        operations[short] = f
    return decode, encode, operations


def validate(library, samples):
    start = time.perf_counter()
    lib = ctypes.CDLL(str(library))
    rng = random.Random(SEED)
    groups, mismatches = [], []

    def record(kind, width, total, errors):
        groups.append({"kind": kind, "width": width, "cases": total, "mismatches": errors})

    def mismatch(kind, width, inputs, actual, expected):
        if len(mismatches) < 50:
            mismatches.append({"kind": kind, "width": width, "inputs": inputs,
                               "actual": str(actual), "expected": str(expected)})

    for width in (8, 16, 32):
        fmt, alu = TakumFormat(width), TakumALU(width)
        decode, encode, operations = functions(lib, width)
        patterns = list(range(1 << width)) if width <= 16 else [rng.getrandbits(width) for _ in range(samples)]
        if width == 32:
            patterns += [0, fmt.nar, fmt.nar - 1, fmt.nar + 1, fmt.mask]
            patterns += [((dr << 27) + offset) & fmt.mask for dr in range(32) for offset in (-1, 0, 1)]
        errors = 0
        for bits in patterns:
            reference = decode(bits)
            actual = fmt.decode(bits)
            ok = math.isnan(reference) if actual is None else Fraction(reference) == actual
            if not ok:
                errors += 1
                mismatch("decode", width, [bits], actual, reference)
        record("decode", width, len(patterns), errors)
        errors = 0
        values = [decode(bits) for bits in patterns]
        values += [math.ldexp(rng.uniform(-2, 2), rng.randint(-280, 280)) for _ in range(samples)]
        values += [0.0, -0.0, math.inf, -math.inf, math.nan]
        for value in values:
            expected = encode(value) & fmt.mask
            actual = fmt.encode(value)
            if actual != expected:
                errors += 1
                mismatch("encode", width, [repr(value)], actual, expected)
        record("encode", width, len(values), errors)
        if width == 8:
            pairs = [(a, b) for a in range(256) for b in range(256)]
        else:
            special = [0, 1, fmt.nar - 1, fmt.nar, fmt.nar + 1, fmt.mask,
                       fmt.encode(1), fmt.encode(-1)]
            pairs = [(a, b) for a in special for b in special]
            pairs += [(rng.getrandbits(width), rng.getrandbits(width)) for _ in range(samples)]
        for operation, function in operations.items():
            errors = 0
            for a, b in pairs:
                expected = function(a, b) & fmt.mask
                actual = alu.execute(operation, a, b).bits
                if actual != expected:
                    errors += 1
                    mismatch(operation, width, [a, b], actual, expected)
            record(operation, width, len(pairs), errors)
        print(f"T{width}: validation complete", file=sys.stderr, flush=True)
    return {"reference": URL, "revision": REVISION, "seed": SEED,
            "samples_per_large_width": samples,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "platform": platform.platform(),
            "duration_seconds": round(time.perf_counter() - start, 3),
            "groups": groups, "total_cases": sum(g["cases"] for g in groups),
            "total_mismatches": sum(g["mismatches"] for g in groups),
            "first_mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("--reference-mode", choices=("upstream", "portable"), default="portable")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "reference-validation.json")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    report = validate(build_reference(args.reference_mode), args.samples)
    report["reference_mode"] = args.reference_mode
    report["patch_sha256"] = (hashlib.sha256((ROOT / "scripts" / "libtakum-portable.patch").read_bytes()).hexdigest()
                              if args.reference_mode == "portable" else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['total_cases']} comparisons; {report['total_mismatches']} mismatches")
    return int(report["total_mismatches"] != 0)


if __name__ == "__main__":
    sys.exit(main())
