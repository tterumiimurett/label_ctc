import subprocess
import sys
import unittest
from pathlib import Path


class ApprovedTransitionTest(unittest.TestCase):
    def test_approved_after_missing_observation_is_manual_with_identity(self):
        fixture = Path(__file__).with_name("ticket08_approved_transition_fixture.py")
        result = subprocess.run([sys.executable, str(fixture), "approved"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"state": "manual_review"', result.stdout)
        self.assertIn('answer_or_status_arrived_after_missing_detection', result.stdout)
        self.assertIn('\"POSTs\": []', result.stdout)


    def test_complete_answer_after_reconstructed_wait_resolves_without_manual_or_post(self):
        fixture = Path(__file__).with_name("ticket08_approved_transition_fixture.py")
        result = subprocess.run([sys.executable, str(fixture), "answer"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"state": "resolved"', result.stdout)
        self.assertIn('"resolution": "complete_answer_arrived"', result.stdout)
        self.assertNotIn('answer_or_status_arrived_after_missing_detection', result.stdout)
        self.assertIn('"POSTs": []', result.stdout)

    def test_complete_answer_at_initial_observation_resolves_without_candidate(self):
        fixture = Path(__file__).with_name("ticket08_approved_transition_fixture.py")
        result = subprocess.run([sys.executable, str(fixture), "initial_answer"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"state": "resolved"', result.stdout)
        self.assertIn('"POSTs": []', result.stdout)


if __name__ == "__main__":
    unittest.main()
