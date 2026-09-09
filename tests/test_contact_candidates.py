import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from prolific.ctc_verification_app.reconciliation import reconcile_current_state
from prolific.ctc_verification_app.contact_candidates import (
    APPROVED_MESSAGE,
    JsonContactLedger,
    build_contact_candidates,
)


class Fresh:
    def __init__(self, result="clear", current=None):
        self.result = result
        self.current = current
        self.calls = []

    def reconcile(self):
        return self.current or report(missing())

    def inspect_messages(self, **kwargs):
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
            history = Fresh(current=report(missing()))
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
            result = build_contact_candidates(report(row), JsonContactLedger(Path(directory) / "contacts.json"), Fresh(), now=datetime.now(timezone.utc))
            self.assertEqual(result["decisions"], [])

    def test_uncertain_evidence_and_history_are_manual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = JsonContactLedger(Path(directory) / "contacts.json")
            now = "2026-09-09T00:10:00Z"
            build_contact_candidates(report(missing(evidence=["other_session_result"])), ledger, Fresh(), now="2026-09-09T00:00:00Z")
            result = build_contact_candidates(report(missing(evidence=["other_session_result"])), ledger, Fresh(), now=now)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review")

            ledger = JsonContactLedger(Path(directory) / "history.json")
            build_contact_candidates(report(missing()), ledger, Fresh(), now="2026-09-09T00:00:00Z")
            result = build_contact_candidates(report(missing()), ledger, Fresh("ambiguous", report(missing())), now=now)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review")

    def test_draft_archive_and_save_error_are_durable_manual_queue_items(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = JsonContactLedger(Path(directory) / "contacts.json")
            rows = [missing(session="D", evidence=["draft"]), missing(session="A", evidence=["archived_result"]), missing(session="E", errors=["save_error"])]
            result = build_contact_candidates(report(*rows), ledger, Fresh(), now="2026-09-09T00:00:00Z")
            self.assertEqual({item["decision"] for item in result["decisions"]}, {"manual_review"})
            saved = ledger.read()["sessions"]
            self.assertEqual({saved[key]["state"] for key in ("D", "A", "E")}, {"manual_review"})

    def test_api_or_storage_failure_stays_pending_and_wrong_study_is_not_contacted(self):
        history = Fresh()
        result = build_contact_candidates({"status": "platform_query_failed", "error": "offline"}, JsonContactLedger(Path(tempfile.mkdtemp()) / "contacts.json"), history)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(history.calls, [])

    def test_existing_request_is_deduplicated_per_session(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = JsonContactLedger(Path(directory) / "contacts.json")
            build_contact_candidates(report(missing()), ledger, Fresh(), now="2026-09-09T00:00:00Z")
            history = Fresh("already_contacted", report(missing()))
            result = build_contact_candidates(report(missing()), ledger, history, now="2026-09-09T00:10:00Z")
            self.assertEqual(result["decisions"][0]["decision"], "already_contacted")

    def test_platform_return_request_is_deduplicated_without_history_guessing(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Fresh("unavailable")
            result = build_contact_candidates(report(missing(return_requested=True)), JsonContactLedger(Path(directory) / "contacts.json"), history, now="2026-09-09T00:10:00Z")
            self.assertEqual(result["decisions"][0]["decision"], "already_contacted")
            self.assertEqual(history.calls, [])

    def test_real_reconciliation_report_requires_fresh_synthetic_api_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "submissions").mkdir()
            (root / "submissions/S1.json").write_text('{"worker":{"study_id":"STUDY","session_id":"S1","prolific_pid":"P1"},"tasks":[]}', encoding="utf-8")

            class Api:
                def __init__(self):
                    self.detail = {"id":"S1", "study_id":"STUDY", "participant":"P1", "status":"AWAITING REVIEW"}
                    self.messages = []
                    self.calls = []
                def list_submissions(self, **kwargs):
                    return {"results":[{"id":"S1"}], "next":None}
                def get_submission(self, submission_id):
                    self.calls.append(("submission", submission_id))
                    return self.detail.copy()
                def get_messages(self, **kwargs):
                    self.calls.append(("messages", kwargs))
                    return {"results":self.messages}

            api = Api()
            initial = reconcile_current_state(api, root, "STUDY")
            from prolific.ctc_verification_app.contact_candidates import ProlificFreshReconciliation
            fresh = ProlificFreshReconciliation(api, root, "STUDY")
            ledger = JsonContactLedger(root / "contacts.json")
            first = build_contact_candidates(initial, ledger, fresh, now="2026-09-09T00:00:00Z")
            self.assertEqual(first["decisions"], [])
            api.detail["participant"] = "P2"
            due = build_contact_candidates(initial, ledger, fresh, now="2026-09-09T00:10:00Z")
            self.assertEqual(due["decisions"][0]["decision"], "manual_review")
            self.assertIn("fresh_identity_mismatch", due["decisions"][0]["evidence"])
            self.assertTrue(any(call[0] == "submission" for call in api.calls))


if __name__ == "__main__":
    unittest.main()
