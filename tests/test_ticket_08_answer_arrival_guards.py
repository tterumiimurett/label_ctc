"""Answer-arrival identity and prior-contact guard regressions."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from prolific.ctc_verification_app.contact_candidates import (
    JsonContactLedger, build_contact_candidates,
)


class FreshNoop:
    def reconcile(self):
        raise AssertionError("fresh reconciliation must not run for invalid stored identity")

    def inspect_messages(self, **kwargs):
        raise AssertionError("message history must not run for invalid stored identity")


class AnswerArrivalGuardTest(unittest.TestCase):
    def report(self, participant: str = "P2") -> dict:
        return {"status": "ok", "study_id": "STUDY", "submissions": [{
            "session_id": "S1", "study_id": "STUDY", "participant_id": participant,
            "status": "AWAITING REVIEW", "classification": "matched",
            "evidence": ["assignment", "final_result"], "errors": [],
        }]}

    def assess(self, entry: dict, report: dict) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = JsonContactLedger(Path(temporary) / "contacts.json")
            ledger.write({"sessions": {"S1": entry}})
            result = build_contact_candidates(
                report, ledger, FreshNoop(), now=datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
                candidate_origin="new",
            )
            return result | {"ledger": ledger.read()}

    def test_matching_answer_cannot_resolve_conflicting_stored_identity(self):
        result = self.assess({
            "state": "observed", "study_id": "STUDY", "participant_id": "P1",
            "first_missing_at": "2026-09-10T11:00:00Z",
        }, self.report("P2"))
        self.assertEqual(result["ledger"]["sessions"]["S1"]["state"], "manual_review")
        self.assertEqual(result["ledger"]["sessions"]["S1"]["participant_id"], "P1")
        self.assertIn("answer_or_status_arrived_after_missing_detection", result["ledger"]["sessions"]["S1"]["reason"])

    def test_contacted_without_attempt_metadata_stays_manual(self):
        result = self.assess({
            "state": "contacted", "study_id": "STUDY", "participant_id": "P1",
            "first_missing_at": "2026-09-10T11:00:00Z",
        }, self.report("P1"))
        self.assertEqual(result["ledger"]["sessions"]["S1"]["state"], "manual_review")
        self.assertEqual(result["ledger"]["sessions"]["S1"]["reason"], "prior_contact_requires_confirmation")

    def test_delivery_unknown_without_attempt_metadata_stays_manual(self):
        result = self.assess({
            "state": "delivery_unknown", "study_id": "STUDY", "participant_id": "P1",
            "first_missing_at": "2026-09-10T11:00:00Z",
        }, self.report("P1"))
        self.assertEqual(result["ledger"]["sessions"]["S1"]["state"], "delivery_unknown")
        self.assertEqual(result["decisions"][0]["decision"], "manual_review")
        self.assertEqual(result["decisions"][0]["reason"], "outbound_attempt_requires_recovery")


if __name__ == "__main__":
    unittest.main()
