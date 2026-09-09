import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
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

    def test_errors_recursive_archive_identity_status_and_claim_semantics(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root / "excluded_submissions/2026-09/S3.json", {"worker": {"study_id": "STUDY", "session_id": "S3", "prolific_pid": "P3"}})
            (root / "submissions").mkdir()
            (root / "submissions/S4.json").write_text("{broken", encoding="utf-8")
            self.write(root / "assignments.json", {
                "S5": {"study_id": "STUDY", "session_id": "S5", "prolific_pid": "P5", "submitted": True, "assigned_at": "2020-01-01T00:00:00Z"},
                "S6": {"study_id": "STUDY", "session_id": "S6", "prolific_pid": "P6", "submitted": False, "assigned_at": "2020-01-01T00:00:00Z"},
            })
            platform = PagedPlatform([{"results": [
                {"id": "S3", "study_id": "STUDY", "participant": {"id": "P9"}, "status": "RETURNED", "entered_code": "REAL-CODE"},
                {"id": "S4", "study_id": "STUDY", "participant": {"id": "P4"}, "status": "AWAITING REVIEW"},
                {"id": "S5", "study_id": "STUDY", "participant": {"id": "P5"}, "status": "TIMED-OUT"},
            ], "next_cursor": None}, {}])
            report = reconcile_current_state(platform, root, "STUDY", {"REAL-CODE"}, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            rows = {row["session_id"]: row for row in report["submissions"]}
            self.assertEqual(rows["S3"]["classification"], "identity_mismatch")
            self.assertIn("archived_result", rows["S3"]["evidence"])
            self.assertEqual(rows["S3"]["completion_code_class"], "normal")
            self.assertEqual(rows["S4"]["classification"], "local_read_error")
            self.assertEqual(rows["S5"]["classification"], "timed_out_without_local_result")
            self.assertEqual(report["counts"]["temporary_claims"], 0)

    def test_returned_and_timed_out_results_are_not_matched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for session in ("S1", "S2"):
                self.write(root / f"submissions/{session}.json", {"worker": {"study_id": "STUDY", "session_id": session, "prolific_pid": session}, "tasks": []})
            platform = PagedPlatform([{"results": [
                {"id": "S1", "study_id": "STUDY", "participant_id": "S1", "status": "RETURNED"},
                {"id": "S2", "study_id": "STUDY", "participant_id": "S2", "status": "TIMED-OUT"}], "next_cursor": None}, {}])
            rows = {r["session_id"]: r for r in reconcile_current_state(platform, root, "STUDY")["submissions"]}
            self.assertEqual(rows["S1"]["classification"], "returned_with_local_result")
            self.assertEqual(rows["S2"]["classification"], "timed_out_with_local_result")

    def test_api_client_sends_read_only_auth_and_retries_rate_limit(self):
        class Headers:
            def get(self, key, default=None):
                return "0"
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"results": [], "next_cursor": null}'
        calls = []
        def open_url(request, timeout):
            calls.append((request.get_method(), request.full_url, request.get_header("Authorization"), timeout))
            if len(calls) == 1: raise HTTPError(request.full_url, 429, "rate limited", Headers(), None)
            return Response()
        with patch("prolific.ctc_verification_app.reconciliation.urlopen", side_effect=open_url):
            result = ProlificSubmissionClient("synthetic", "https://api.test/v1", retries=1).list_submissions(study_id="STUDY", cursor="CUR", page_size=7)
        self.assertEqual(result["results"], [])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call[0] == "GET" and call[2] == "Token synthetic" for call in calls))
        self.assertIn("study_id=STUDY", calls[0][1])
        self.assertIn("cursor=CUR", calls[0][1])


if __name__ == "__main__":
    unittest.main()
