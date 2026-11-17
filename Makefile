PYTHON ?= python3
BENCH_DIR ?= results

.PHONY: test reference demo vector artifacts verify fetch bench bench-synthetic mlp isa summary paper final-paper slides package

test:
	$(PYTHON) scripts/run_tests.py

reference:
	$(PYTHON) scripts/validate_reference.py

demo:
	$(PYTHON) -m takum demo

vector:
	$(PYTHON) -m takum vector-demo

artifacts:
	$(PYTHON) scripts/export_demo.py

verify: test reference artifacts

# Phase 3: matrix download (network) and benchmark (resumable).
fetch:
	$(PYTHON) scripts/fetch_matrices.py --listed

bench:
	$(PYTHON) scripts/run_benchmark.py --output-dir "$(BENCH_DIR)"
	$(PYTHON) scripts/summarize_benchmark.py "$(BENCH_DIR)/spmv-errors.csv"

bench-synthetic:
	$(PYTHON) scripts/run_benchmark.py --synthetic 64
	$(PYTHON) scripts/summarize_benchmark.py results/synthetic-errors.csv

# Machine learning case: dense layers with ReLU, input scale sweep.
mlp:
	$(PYTHON) scripts/run_mlp.py

# Static analysis: value classes of every bit pattern per format.
isa:
	$(PYTHON) scripts/isa_analysis.py

summary:
	$(PYTHON) scripts/summarize_benchmark.py results/spmv-errors.csv
	$(PYTHON) scripts/run_mlp.py --summarize-only

paper: final-paper
	mkdir -p output/pdf
	cd paper && tectonic --outdir ../output/pdf phase1.tex

final-paper:
	mkdir -p output/pdf
	cd paper && tectonic --outdir ../output/pdf final.tex

slides:
	mkdir -p output/pdf
	cd slides && tectonic --outdir ../output/pdf final-slides.tex

package: final-paper slides
	$(PYTHON) scripts/package_delivery.py
