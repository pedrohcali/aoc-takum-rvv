PYTHON ?= python3

.PHONY: test reference demo vector artifacts verify fetch bench bench-synthetic summary paper slides package

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
	$(PYTHON) scripts/fetch_matrices.py

bench:
	$(PYTHON) scripts/run_benchmark.py
	$(PYTHON) scripts/summarize_benchmark.py results/spmv-errors.csv

bench-synthetic:
	$(PYTHON) scripts/run_benchmark.py --synthetic 64
	$(PYTHON) scripts/summarize_benchmark.py results/synthetic-errors.csv

paper:
	mkdir -p output/pdf
	cd paper && tectonic --outdir ../output/pdf phase1.tex
	cd paper && tectonic --outdir ../output/pdf final.tex

slides:
	mkdir -p output/pdf
	cd slides && tectonic --outdir ../output/pdf final-slides.tex

package:
	$(PYTHON) scripts/package_delivery.py
