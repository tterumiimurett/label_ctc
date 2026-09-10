import json
import subprocess
import sys
import unittest
from pathlib import Path

class LifecycleGuardIntegrationTest(unittest.TestCase):
    def test_all_five_lifecycle_guards_preserve_assignment_and_audit_manual_uncertainty(self):
        fixture = Path(__file__).with_name("ticket08_lifecycle_guards_fixture.py")
        for mode in ("default_off", "wrong_study", "read_error", "consent", "routine"):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, str(fixture), mode], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                value = json.loads(result.stdout)
                if mode in ("default_off", "wrong_study", "read_error", "consent"):
                    self.assertTrue(value["unchanged"], value)
                    self.assertTrue(value["remaining"], value)
                if mode in ("wrong_study", "read_error", "consent"):
                    self.assertEqual(value["result"]["results"][0]["outcome"]["status"], "manual_review", value)
                elif mode == "default_off":
                    self.assertEqual(value["result"]["status"], "preview_only", value)
                else:
                    self.assertFalse(value["unchanged"], value)

if __name__ == "__main__":
    unittest.main()
