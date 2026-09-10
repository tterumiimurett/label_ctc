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


    def test_complete_answer_arrives_after_first_missing_before_due_and_resolves_after_reconstruction(self):
        fixture = Path(__file__).with_name("ticket08_approved_transition_fixture.py")
        result = subprocess.run([sys.executable, str(fixture), "answer"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"state": "resolved"', result.stdout)
        self.assertIn('"resolution": "complete_answer_arrived"', result.stdout)
        self.assertNotIn('answer_or_status_arrived_after_missing_detection', result.stdout)
        self.assertIn('"POSTs": []', result.stdout)

    def test_answer_arrival_after_five_minutes_resolves_and_repeats_without_post(self):
        fixture = Path(__file__).with_name("ticket08_approved_transition_fixture.py")
        result = subprocess.run([sys.executable, str(fixture), "answer5"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"state": "resolved"', result.stdout)
        self.assertIn('"POSTs": []', result.stdout)

    def test_due_outer_missing_then_fresh_reconciliation_sees_answer(self):
        fixture = Path(__file__).with_name("ticket08_approved_transition_fixture.py")
        result = subprocess.run([sys.executable, str(fixture), "fresh_only"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"state": "resolved"', result.stdout)
        self.assertIn('"POSTs": []', result.stdout)
        self.assertIn('"classification": "awaiting_without_final_result"', result.stdout)
        self.assertIn('"classification": "matched"', result.stdout)
        self.assertNotIn('"decision": "candidate"', result.stdout)

    def test_complete_answer_at_initial_observation_resolves_without_candidate(self):
        fixture = Path(__file__).with_name("ticket08_approved_transition_fixture.py")
        result = subprocess.run([sys.executable, str(fixture), "initial_answer"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"state": "resolved"', result.stdout)
        self.assertIn('"POSTs": []', result.stdout)


if __name__ == "__main__":
    unittest.main()
