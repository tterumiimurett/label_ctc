import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient, reconcile_current_state


class PagedPlatform:
    def __init__(self, pages):
        self.pages, self.calls, self.details = pages, [], {}
        for page in pages:
            for item in page.get("results", []):
                self.details[item["id"]] = {"id": item["id"], "study_id": item.get("study_id", "STUDY"),
                                            "participant": item.get("participant_id", item.get("participant")),
                                            "status": item.get("status", "AWAITING_REVIEW"),
                                            "entered_code": item.get("entered_code")}

    def list_submissions(self, *, study, page=1, page_size=100):
        self.calls.append((study, page, page_size))
        return self.pages[page - 1]

    def get_submission(self, submission_id):
        return self.details[submission_id]


class ReadOnlyReconciliationTest(unittest.TestCase):
    def write(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_official_list_detail_pagination_and_separate_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root / "submissions/S1.json", {"worker": {"study_id": "STUDY", "session_id": "S1", "prolific_pid": "P1"}, "tasks": [{"candidate_id": "C1"}]})
            self.write(root / "assignments.json", {"S2": {"study_id": "STUDY", "session_id": "S2", "prolific_pid": "P2", "submitted": False, "assigned_at": "2026-09-09T00:00:00Z"}})
            platform = PagedPlatform([
                {"results": [{"id": "S1", "participant_id": "P1", "study_code": "CODE"}], "next": "https://api.test/api/v1/submissions/?study=STUDY&page=2&page_size=100"},
                {"results": [{"id": "S2", "participant_id": "P2", "study_code": "CODE"}], "next": None},
            ])
            report = reconcile_current_state(platform, root, "STUDY", {"REAL"}, now=datetime(2026, 9, 9, 1, tzinfo=timezone.utc))
            self.assertEqual(platform.calls, [("STUDY", 1, 100), ("STUDY", 2, 100)])
            self.assertEqual(report["counts"], {"platform_submissions": 2, "local_final_results": 1, "temporary_claims": 1})
            self.assertEqual(report["submissions"][0]["classification"], "matched")

    def test_detail_identity_is_required_and_completion_code_is_unavailable_without_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            platform = PagedPlatform([{"results": [{"id": "S1", "participant_id": "P1"}], "next": None}])
            platform.details["S1"] = {"id": "S1", "study_id": "STUDY", "participant": "P1", "status": "AWAITING_REVIEW", "entered_code": "REAL"}
            report = reconcile_current_state(platform, Path(temporary), "STUDY")
            self.assertEqual(report["submissions"][0]["completion_code_class"], "unavailable")
            self.assertEqual(report["submissions"][0]["classification"], "awaiting_without_final_result")

    def test_corrupt_result_and_bad_schema_are_errors_not_absence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "submissions").mkdir(); (root / "submissions/S1.json").write_text("{broken", encoding="utf-8")
            self.write(root / "excluded_submissions/2026-09/S2.json", {"worker": {"study_id": "STUDY", "session_id": "S2", "prolific_pid": "P2"}, "tasks": [{"candidate_id": "C"}]})
            self.write(root / "excluded_submissions/2026-09/manifest.json", {"manifest": True})
            self.write(root / "assignments.json", {"S3": {"study_id": "STUDY", "session_id": "S3", "submitted": False}})
            platform = PagedPlatform([{"results": [{"id": "S1", "participant_id": "P1"}, {"id": "S2", "participant_id": "P2"}], "next": None}])
            rows = {r["session_id"]: r for r in reconcile_current_state(platform, root, "STUDY")["submissions"]}
            self.assertEqual(rows["S1"]["classification"], "local_read_error")
            self.assertIn("archived_result", rows["S2"]["evidence"])

    def test_returned_timed_out_results_and_cross_session_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for session in ("S1", "S2", "OTHER"):
                self.write(root / f"submissions/{session}.json", {"worker": {"study_id": "STUDY", "session_id": session, "prolific_pid": "P1"}, "tasks": [{"candidate_id": session}]})
            platform = PagedPlatform([{"results": [{"id": "S1", "participant_id": "P1", "status": "RETURNED"}, {"id": "S2", "participant_id": "P1", "status": "TIMED-OUT"}], "next": None}])
            rows = {r["session_id"]: r for r in reconcile_current_state(platform, root, "STUDY", {"REAL"})["submissions"]}
            self.assertEqual(rows["S1"]["classification"], "returned_with_local_result")
            self.assertEqual(rows["S2"]["classification"], "timed_out_with_local_result")
            self.assertIn("other_session_result", rows["S1"]["evidence"])

    def test_submitted_and_expired_claims_are_not_counted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root / "assignments.json", {"old": {"study_id": "STUDY", "session_id": "old", "submitted": False, "assigned_at": "2020-01-01T00:00:00Z"}, "done": {"study_id": "STUDY", "session_id": "done", "submitted": True}})
            platform = PagedPlatform([{"results": [], "next": None}])
            report = reconcile_current_state(platform, root, "STUDY", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            self.assertEqual(report["counts"]["temporary_claims"], 0)

    def test_missing_results_key_and_pagination_loop_are_failures(self):
        class Broken(PagedPlatform):
            def list_submissions(self, **kwargs): return {"data": []}
        with tempfile.TemporaryDirectory() as temporary:
            report = reconcile_current_state(Broken([]), Path(temporary), "STUDY")
            self.assertEqual(report["status"], "platform_query_failed")

    def test_api_client_uses_official_query_and_retries_without_redirects(self):
        class Headers:
            def get(self, key, default=None): return "0"
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"results": [], "next": null}'
        calls = []
        def open_url(request, timeout):
            calls.append((request.get_method(), request.full_url, request.get_header("Authorization")))
            if len(calls) == 1: raise HTTPError(request.full_url, 429, "rate limited", Headers(), None)
            return Response()
        opener = type("Opener", (), {"open": staticmethod(open_url)})()
        with patch("prolific.ctc_verification_app.reconciliation.build_opener", return_value=opener):
            with patch.dict("os.environ", {}, clear=True):
                client = ProlificSubmissionClient("synthetic", "https://api.test/v1", retries=1)
                result = client.list_submissions(study="STUDY", page=3, page_size=7)
        self.assertEqual(result["results"], [])
        self.assertIn("study=STUDY", calls[0][1]); self.assertIn("page=3", calls[0][1]); self.assertNotIn("cursor", calls[0][1])
        self.assertTrue(all(call[0] == "GET" and call[2] == "Token synthetic" for call in calls))


if __name__ == "__main__": unittest.main()
