#!/usr/bin/env python3
"""Package the final submission, including the inputs used to build both PDFs."""
from pathlib import Path
from tempfile import NamedTemporaryFile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "entrega-aoc.zip"
FILES = """
README.md DECISIONS.md Makefile pyproject.toml
paper/final.tex paper/IEEEtran.cls slides/final-slides.tex
output/pdf/final.pdf output/pdf/final-slides.pdf
scripts/libtakum-portable.patch scripts/libtakum-LICENSE
results/unit-tests.json results/reference-validation.json results/demo.json results/t8-values.csv
results/reference-upstream-linux.json results/reference-upstream-macos.json
results/matrix-list.csv results/benchmark-run.json results/benchmark-skipped.csv
results/spmv-errors.csv results/spmv-cdf.csv results/spmv-conversion-cdf.csv
results/spmv-summary.json results/spmv-macros.tex
results/mlp-errors.csv results/mlp-curve.csv results/mlp-summary.json results/mlp-run.json
results/mlp-macros.tex results/isa-encodings.csv results/isa-macros.tex
""".split()


def main():
    files = [ROOT / name for name in FILES]
    for folder in ("takum", "tests", "scripts"):
        sources = sorted((ROOT / folder).glob("*.py"))
        if not sources:
            raise FileNotFoundError(f"No Python files in {folder}/")
        files.extend(sources)
    OUTPUT.parent.mkdir(exist_ok=True)
    with NamedTemporaryFile(dir=OUTPUT.parent, suffix=".zip", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(files):
                archive.write(source, "aoc-takum-rvv/" + source.relative_to(ROOT).as_posix())
        path.replace(OUTPUT)
    finally:
        path.unlink(missing_ok=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
