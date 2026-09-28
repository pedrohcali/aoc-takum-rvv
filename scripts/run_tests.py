#!/usr/bin/env python3
"""Run the complete offline suite and persist its actual outcome."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
start = time.perf_counter()
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
          "python": platform.python_version(), "platform": platform.platform(),
          "tests": result.testsRun, "failures": len(result.failures),
          "errors": len(result.errors), "skipped": len(result.skipped),
          "duration_seconds": round(time.perf_counter() - start, 3),
          "success": result.wasSuccessful(),
          "exhaustive_t8_operation_cases": 3 * 256**2,
          "exhaustive_t8_t16_roundtrip_patterns": 256 + 65536}
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "unit-tests.json").write_text(json.dumps(report, indent=2) + "\n")
sys.exit(not result.wasSuccessful())
