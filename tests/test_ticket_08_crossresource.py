import subprocess
import sys
import unittest
from pathlib import Path


class Ticket08CrossResourceHttpTest(unittest.TestCase):
    def test_receiver_only_posts_for_durable_event_resource(self):
        fixture = Path(__file__).with_name("ticket08_crossresource_http_fixture.py")
        result = subprocess.run([sys.executable, str(fixture)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"recipient_id": "P1"', result.stdout)
        self.assertNotIn('\"recipient_id\": \"P-OLD\"', result.stdout)

    def test_scheduler_only_posts_for_durable_event_resource_after_restart_boundary(self):
        fixture = Path(__file__).with_name('ticket08_crossresource_scheduler_fixture.py')
        result = subprocess.run([sys.executable, str(fixture)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('\"recipient_id\": \"P1\"', result.stdout)
        self.assertNotIn('\"recipient_id\": \"P-OLD\"', result.stdout)


if __name__ == "__main__":
    unittest.main()
