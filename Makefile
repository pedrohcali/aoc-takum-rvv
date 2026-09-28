PYTHON ?= python3

.PHONY: test reference demo artifacts verify paper package

test:
	$(PYTHON) scripts/run_tests.py

reference:
	$(PYTHON) scripts/validate_reference.py

demo:
	$(PYTHON) -m takum demo

artifacts:
	$(PYTHON) scripts/export_demo.py

verify: test reference artifacts

paper:
	mkdir -p output/pdf
	tectonic --outdir output/pdf paper/phase1.tex

package:
	$(PYTHON) scripts/package_delivery.py
