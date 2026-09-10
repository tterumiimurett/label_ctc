import subprocess
import sys
import unittest
from pathlib import Path


class ConcurrentDisableIntegrationTest(unittest.TestCase):
    def test_real_two_event_http_scheduler_disable_boundary(self):
        fixture = Path(__file__).with_name("ticket08_concurrent_disable_fixture.py")
        result = subprocess.run([sys.executable, str(fixture)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("\"POSTs\":", result.stdout)
        self.assertIn("\"S3_assignment_preserved\": true", result.stdout)
        self.assertNotIn("'M2'", result.stdout)


if __name__ == "__main__":
    unittest.main()
