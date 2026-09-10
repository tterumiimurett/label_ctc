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

class ConsentAndHistoricalContractTest(unittest.TestCase):
    def test_consent_evidence_is_identity_bound_and_fails_closed(self):
        import tempfile
        from datetime import datetime, timezone
        from unittest.mock import Mock
        from prolific.ctc_verification_app.activation import RealApiAdapter
        from prolific.ctc_verification_app.contact_candidates import VerifiedMessageScope
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reader = Mock()
            reader.list_submissions.return_value = {'results': [{'id': 'S1', 'study_id': 'STUDY', 'participant': 'P1', 'status': 'RETURNED', 'started_at': '2026-01-01T00:00:00Z'}], 'meta': {'count': 1}}
            reader.get_submission.return_value = {'id': 'S1', 'study_id': 'STUDY', 'participant': 'P1', 'status': 'RETURNED', 'started_at': '2026-01-01T00:00:00Z'}
            source = root / 'consent.json'
            source.write_text(json.dumps({'records': [{'record_id': 'C1', 'session_id': 'S1', 'study_id': 'STUDY', 'participant_id': 'P1', 'consent_withdrawn': True}]}), encoding='utf-8')
            scope = VerifiedMessageScope('R', 'W', datetime(2025, 12, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc), True, 'controlled', datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc))
            adapter = RealApiAdapter(reader, root / 'data', 'STUDY', scope=scope, consent_evidence_path=source)
            adapter.fresh.reconcile = lambda: {'status': 'ok', 'submissions': [{'session_id': 'S1', 'study_id': 'STUDY', 'participant_id': 'P1', 'status': 'RETURNED'}]}
            report = adapter.reconcile()
            self.assertTrue(report['submissions'][0]['consent_withdrawn'])
            source.write_text('{malformed', encoding='utf-8')
            self.assertEqual(adapter.reconcile()['status'], 'pending')

    def test_historical_approval_records_are_not_empty_or_arbitrary(self):
        from prolific.ctc_verification_app.activation import Approval
        approval = Approval('STUDY', 'digest', ('S1',), ('S1',), (), True, 'now', 'reviewer', ({'session_id': 'S1', 'study_id': 'STUDY', 'participant_id': 'P1', 'action': 'release_claim', 'preview_sha256': 'digest'},))
        self.assertEqual(approval.historical_records[0]['participant_id'], 'P1')
        self.assertNotEqual(approval.historical_records, ())
