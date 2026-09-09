import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from prolific.ctc_verification_app.contact_candidates import (
    APPROVED_MESSAGE,
    JsonContactLedger,
    build_contact_candidates,
)


class History:
    def __init__(self, result="clear"):
        self.result = result
        self.calls = []

    def inspect(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def report(*rows):
    return {"status": "ok", "study_id": "STUDY", "submissions": list(rows)}


def missing(session="S1", participant="P1", **extra):
    value = {"session_id": session, "study_id": "STUDY", "participant_id": participant,
             "status": "AWAITING REVIEW", "classification": "awaiting_without_final_result",
             "evidence": [], "errors": []}
    value.update(extra)
    return value


class ContactCandidateTest(unittest.TestCase):
    def test_waits_ten_minutes_and_persists_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = JsonContactLedger(Path(directory) / "contacts.json")
            history = History()
            first = build_contact_candidates(report(missing()), ledger, history, now="2026-09-09T00:00:00Z")
            self.assertEqual(first["decisions"], [])
            waiting = build_contact_candidates(report(missing()), JsonContactLedger(Path(directory) / "contacts.json"), history, now="2026-09-09T00:09:59Z")
            self.assertEqual(waiting["decisions"][0]["decision"], "waiting")
            due = build_contact_candidates(report(missing()), JsonContactLedger(Path(directory) / "contacts.json"), history, now="2026-09-09T00:10:00Z")
            self.assertEqual(due["decisions"][0]["decision"], "candidate")
            self.assertEqual(due["decisions"][0]["message"], APPROVED_MESSAGE.format(SESSION_ID="S1"))
            again = build_contact_candidates(report(missing()), JsonContactLedger(Path(directory) / "contacts.json"), history, now="2026-09-09T01:00:00Z")
            self.assertEqual(again["decisions"], [])
            self.assertEqual(len(history.calls), 1)

    def test_complete_result_and_completion_code_do_not_create_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            row = missing(classification="matched", completion_code_class="nocode")
            result = build_contact_candidates(report(row), JsonContactLedger(Path(directory) / "contacts.json"), History(), now=datetime.now(timezone.utc))
            self.assertEqual(result["decisions"], [])

    def test_uncertain_evidence_and_history_are_manual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = JsonContactLedger(Path(directory) / "contacts.json")
            now = "2026-09-09T00:10:00Z"
            build_contact_candidates(report(missing(evidence=["other_session_result"])), ledger, History(), now="2026-09-09T00:00:00Z")
            result = build_contact_candidates(report(missing(evidence=["other_session_result"])), ledger, History(), now=now)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review")

            ledger = JsonContactLedger(Path(directory) / "history.json")
            build_contact_candidates(report(missing()), ledger, History(), now="2026-09-09T00:00:00Z")
            result = build_contact_candidates(report(missing()), ledger, History("ambiguous"), now=now)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review")

    def test_api_or_storage_failure_stays_pending_and_wrong_study_is_not_contacted(self):
        history = History()
        result = build_contact_candidates({"status": "platform_query_failed", "error": "offline"}, JsonContactLedger(Path(tempfile.mkdtemp()) / "contacts.json"), history)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(history.calls, [])

    def test_existing_request_is_deduplicated_per_session(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = JsonContactLedger(Path(directory) / "contacts.json")
            build_contact_candidates(report(missing()), ledger, History(), now="2026-09-09T00:00:00Z")
            history = History("already_contacted")
            result = build_contact_candidates(report(missing()), ledger, history, now="2026-09-09T00:10:00Z")
            self.assertEqual(result["decisions"][0]["decision"], "already_contacted")

    def test_platform_return_request_is_deduplicated_without_history_guessing(self):
        with tempfile.TemporaryDirectory() as directory:
            history = History("unavailable")
            result = build_contact_candidates(report(missing(return_requested=True)), JsonContactLedger(Path(directory) / "contacts.json"), history, now="2026-09-09T00:10:00Z")
            self.assertEqual(result["decisions"][0]["decision"], "already_contacted")
            self.assertEqual(history.calls, [])


if __name__ == "__main__":
    unittest.main()
