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
        unique_count = len({item.get("id") for page in pages for item in page.get("results", []) if isinstance(item, dict)})
        for page in pages:
            if isinstance(page, dict):
                page.setdefault("meta", {"count": unique_count})
        for page in pages:
            for item in page.get("results", []):
                self.details[item["id"]] = {"id": item["id"], "study_id": item.get("study_id", "STUDY"),
                                            "participant": item.get("participant_id", item.get("participant")),
                                            "status": item.get("status", "AWAITING_REVIEW"),
                                            "entered_code": item.get("entered_code")}

    def list_submissions(self, *, study, page=1, page_size=100, ordering="started_at"):
        self.calls.append((study, page, page_size, ordering))
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
            self.assertEqual(platform.calls, [("STUDY", 1, 100, "started_at"), ("STUDY", 2, 100, "started_at")])
            self.assertEqual(report["counts"], {"platform_submissions": 2, "local_final_results": 1, "temporary_claims": 1})
            self.assertEqual(report["submissions"][0]["classification"], "matched")

    def test_real_http_adapter_follows_nested_links_and_deduplicates_submission_ids(self):
        class Response:
            def __init__(self, payload): self.payload = json.dumps(payload).encode()
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return self.payload

        calls = []
        def open_url(request, timeout):
            calls.append(request.full_url)
            if "/submissions/?" in request.full_url:
                page = "2" if "page=2" in request.full_url else "1"
                if page == "1":
                    payload = {"results": [{"id": "S1"}], "meta": {"count": 2}, "_links": {"next": {"href": "https://api.test/v1/submissions/?study=STUDY&page=2&page_size=100"}}}
                else:
                    payload = {"results": [{"id": "S1"}, {"id": "S2"}], "meta": {"count": 2}, "_links": {"next": {"href": None}}}
            else:
                session = request.full_url.rstrip("/").rsplit("/", 1)[-1]
                payload = {"id": session, "study_id": "STUDY", "participant": f"P{session[-1]}", "status": "AWAITING REVIEW"}
            return Response(payload)

        opener = type("Opener", (), {"open": staticmethod(open_url)})()
        with tempfile.TemporaryDirectory() as temporary:
            with patch("prolific.ctc_verification_app.reconciliation.build_opener", return_value=opener):
                client = ProlificSubmissionClient("synthetic", "https://api.test/v1")
                report = reconcile_current_state(client, Path(temporary), "STUDY")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["counts"]["platform_submissions"], 2)
        self.assertEqual([row["session_id"] for row in report["submissions"]], ["S1", "S2"])
        list_calls = [url for url in calls if "/submissions/?" in url]
        detail_calls = [url for url in calls if "/submissions/" in url and "?" not in url]
        self.assertEqual(len(list_calls), 2)
        self.assertIn("page=2", list_calls[1])
        self.assertIn("ordering=started_at", list_calls[0])
        self.assertIn("ordering=started_at", list_calls[1])
        self.assertEqual(len(detail_calls), 2)

    def test_duplicate_pages_that_do_not_satisfy_meta_count_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            platform = PagedPlatform([
                {"results": [{"id": "S1", "participant_id": "P1"}], "meta": {"count": 3},
                 "_links": {"next": {"href": "https://api.test/api/v1/submissions/?study=STUDY&page=2&page_size=100"}}},
                {"results": [{"id": "S1", "participant_id": "P1"}, {"id": "S2", "participant_id": "P2"}],
                 "meta": {"count": 3}, "_links": {"next": {"href": None}}},
            ])

            report = reconcile_current_state(platform, Path(temporary), "STUDY")

        self.assertEqual(report["status"], "platform_query_failed")

    def test_missing_submission_count_metadata_fails_closed(self):
        class NoMeta(PagedPlatform):
            def list_submissions(self, **kwargs):
                return {"results": [], "_links": {"next": {"href": None}}}

        with tempfile.TemporaryDirectory() as temporary:
            report = reconcile_current_state(NoMeta([]), Path(temporary), "STUDY")

        self.assertEqual(report["status"], "platform_query_failed")
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
        self.assertIn("study=STUDY", calls[0][1]); self.assertIn("page=3", calls[0][1]); self.assertIn("ordering=started_at", calls[0][1]); self.assertNotIn("cursor", calls[0][1])
        self.assertTrue(all(call[0] == "GET" and call[2] == "Token synthetic" for call in calls))

    def test_missing_or_non_directory_data_root_is_storage_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            platform = PagedPlatform([{"results": [], "next": None}])
            missing = reconcile_current_state(platform, root / "missing", "STUDY")
            self.assertEqual(missing["status"], "local_storage_failed")
            file_path = root / "data.json"
            file_path.write_text("{}", encoding="utf-8")
            not_directory = reconcile_current_state(platform, file_path, "STUDY")
            self.assertEqual(not_directory["status"], "local_storage_failed")

    def test_malformed_list_entry_and_detail_are_platform_failures(self):
        class MalformedList(PagedPlatform):
            def list_submissions(self, **kwargs): return {"results": ["not-an-object"], "next": None}
        class MalformedDetail(PagedPlatform):
            def get_submission(self, submission_id): return ["not-an-object"]
        with tempfile.TemporaryDirectory() as temporary:
            malformed_list = reconcile_current_state(MalformedList([]), Path(temporary), "STUDY")
            self.assertEqual(malformed_list["status"], "platform_query_failed")
            malformed_detail = reconcile_current_state(MalformedDetail([{"results": [{"id": "S1"}], "next": None}]), Path(temporary), "STUDY")
            self.assertEqual(malformed_detail["status"], "platform_query_failed")


if __name__ == "__main__": unittest.main()
