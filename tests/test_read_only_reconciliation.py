import json
import tempfile
import unittest
from pathlib import Path

from prolific.ctc_verification_app.reconciliation import reconcile_current_state


class PagedPlatform:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list_submissions(self, *, study_id, cursor=None, page_size=100):
        self.calls.append((study_id, cursor, page_size))
        page = self.pages[0] if cursor is None else self.pages[1]
        return page


class ReadOnlyReconciliationTest(unittest.TestCase):
    def write(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_reconciles_all_pages_and_separates_platform_local_and_claim_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root / "submissions/S1.json", {"worker": {
                "study_id": "STUDY", "session_id": "S1", "prolific_pid": "P1"
            }, "tasks": [{"candidate_id": "C1"}]})
            self.write(root / "drafts/S2.json", {"worker": {
                "study_id": "STUDY", "session_id": "S2", "prolific_pid": "P2"
            }})
            self.write(root / "assignments.json", {
                "S2": {"study_id": "STUDY", "session_id": "S2", "prolific_pid": "P2",
                        "candidate_ids": ["C2"], "submitted": False}
            })
            platform = PagedPlatform([
                {"results": [{"id": "S1", "study_id": "STUDY", "participant_id": "P1",
                              "status": "AWAITING REVIEW", "entered_code": "OK"}],
                 "next_cursor": "next"},
                {"results": [{"id": "S2", "study_id": "STUDY", "participant_id": "P2",
                              "status": "AWAITING REVIEW", "entered_code": "NOCODE"}],
                 "next_cursor": None},
            ])

            report = reconcile_current_state(platform, root, "STUDY")

            self.assertEqual(platform.calls, [("STUDY", None, 100), ("STUDY", "next", 100)])
            self.assertEqual(report["counts"], {"platform_submissions": 2,
                                                 "local_final_results": 1,
                                                 "temporary_claims": 1})
            self.assertEqual(report["submissions"][0]["classification"], "matched")
            self.assertEqual(report["submissions"][1]["classification"], "awaiting_without_final_result")
            self.assertEqual(report["submissions"][1]["completion_code_class"], "nocode")
            self.assertEqual(report["submissions"][1]["proposed_action"], "review_missing_result")

    def test_identity_mismatch_other_session_and_archived_evidence_are_not_absence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root / "excluded-results/S3.json", {"worker": {
                "study_id": "STUDY", "session_id": "S3", "prolific_pid": "P3"
            }, "tasks": [{"candidate_id": "C3"}]})
            self.write(root / "submissions/OTHER.json", {"worker": {
                "study_id": "STUDY", "session_id": "OTHER", "prolific_pid": "P3"
            }, "tasks": [{"candidate_id": "C3"}]})
            platform = PagedPlatform([
                {"results": [
                    {"id": "S3", "study_id": "STUDY", "participant_id": "P9",
                     "status": "RETURNED", "entered_code": "UNKNOWN"},
                    {"id": "S4", "study_id": "STUDY", "participant_id": "P4",
                     "status": "TIMED-OUT", "entered_code": "OK"}], "next_cursor": None},
                {},
            ])

            report = reconcile_current_state(platform, root, "STUDY")

            by_id = {item["session_id"]: item for item in report["submissions"]}
            self.assertEqual(by_id["S3"]["classification"], "identity_mismatch")
            self.assertIn("archived_result", by_id["S3"]["evidence"])
            self.assertIn("other_session_result", by_id["S3"]["evidence"])
            self.assertEqual(by_id["S4"]["proposed_action"], "release_claim_proposal")
            self.assertFalse(report["writes_performed"])

    def test_platform_failure_is_failure_not_missing_result(self):
        class Broken:
            def list_submissions(self, **kwargs):
                raise OSError("offline")

        with tempfile.TemporaryDirectory() as temporary:
            report = reconcile_current_state(Broken(), Path(temporary), "STUDY")
            self.assertEqual(report["status"], "platform_query_failed")
            self.assertEqual(report["submissions"], [])
            self.assertFalse(report["writes_performed"])


if __name__ == "__main__":
    unittest.main()
