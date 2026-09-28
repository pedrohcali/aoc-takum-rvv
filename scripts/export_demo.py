#!/usr/bin/env python3
"""Export reproducible T8 values and the arithmetic demonstration."""
import contextlib
import csv
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from takum import TakumFormat
from takum.cli import main

out = ROOT / "results"
out.mkdir(exist_ok=True)
fmt = TakumFormat(8)
with (out / "t8-values.csv").open("w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["hex", "binary", "S", "D", "R", "r", "C", "c", "p", "F", "ghost_bits", "exact_value"])
    for bits in range(256):
        f = fmt.fields(bits)
        writer.writerow([f"0x{bits:02x}", f"{bits:08b}", f.sign, f.direction,
                         f.regime, f.characteristic_width, f.characteristic_bits,
                         f.characteristic, f.fraction_width, f.fraction_bits,
                         f.ghost_bits, "NaR" if f.value is None else str(f.value)])
with (out / "demo.json").open("w") as file, contextlib.redirect_stdout(file):
    main(["demo"])
