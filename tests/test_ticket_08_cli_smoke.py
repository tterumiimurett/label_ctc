"""Regression tests for the executable Ticket 8 smoke harness."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class CliSmokeFaultRegressionTest(unittest.TestCase):
    def test_scheduler_fault_is_nonzero_and_reports_stderr(self) -> None:
        script = Path(__file__).with_name("ticket08_cli_smoke.py")
        result = subprocess.run(
            [sys.executable, str(script), "--fault-scheduler"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("injected scheduler fault", result.stderr)
        self.assertIn("scheduler exited early", result.stderr)


if __name__ == "__main__":
    unittest.main()
