import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prolific.ctc_verification_app.app import VerificationStore


class CtcVerificationAssignmentTest(unittest.TestCase):
    def candidate(self, index: int) -> dict:
        start = 10.0 + index
        end = 20.0 + index
        task_id = f"seamless_ctc_V00_S0001_I{index:08d}_{int(start * 100):06d}_{int(end * 100):06d}"
        return {
            "candidate_key": f"V00_S0001_I{index:08d}|P1|P2|{start:.3f}|{end:.3f}|target",
            "pred_is_ctc": True,
            "audio_verify": {"verify_is_ctc": True},
            "tos_audio": {"outer_url": f"https://example.test/{task_id}.wav"},
        }

    def write_candidates(self, root: Path, count: int) -> Path:
        path = root / "candidates.jsonl"
        path.write_text(
            "\n".join(json.dumps(self.candidate(index)) for index in range(1, count + 1))
            + "\n",
            encoding="utf-8",
        )
        return path

    def store(
        self,
        root: Path,
        count: int,
        *,
        redundancy: int,
        timeout_minutes: int = 240,
    ) -> VerificationStore:
        candidates_path = self.write_candidates(root, count)
        return VerificationStore(
            source_task_paths=[],
            auto_label_patterns=[str(candidates_path)],
            data_dir=root / "data",
            bundle_size=1,
            redundancy=redundancy,
            completion_url="https://example.test/complete",
            include_audio_unverified=False,
            assignment_timeout_minutes=timeout_minutes,
        )

    def worker(self, prolific_pid: str, session_id: str) -> dict[str, str]:
        return {
            "prolific_pid": prolific_pid,
            "study_id": "S1",
            "session_id": session_id,
        }

    def payload(self, worker: dict[str, str], assignment: dict) -> dict:
        return {
            "schema_version": "ctc-verification-v1",
            "worker": worker,
            "assignment": assignment["assignment"],
            "tasks": [
                {
                    "candidate_id": task["candidate_id"],
                    "task_id": task["task_id"],
                    "relevant_interruption": False,
                }
                for task in assignment["tasks"]
            ],
        }

    def test_participant_loading_errors_are_visible_in_the_real_app(self) -> None:
        static_dir = Path(__file__).resolve().parents[1] / 'prolific' / 'ctc_verification_app' / 'static'
        html = (static_dir / 'verify.html').read_text(encoding='utf-8')
        javascript = (static_dir / 'app.js').read_text(encoding='utf-8')
        stylesheet = (static_dir / 'style.css').read_text(encoding='utf-8')

        self.assertIn('id="loading-card"', html)
        self.assertIn('id="loading-message"', html)
        self.assertIn('try {', javascript)
        self.assertIn('Unable to load assignment:', javascript)
        self.assertIn('The server returned an invalid assignment response.', javascript)
        self.assertIn('.status.errors', stylesheet)
        self.assertIn('display: block;', stylesheet[stylesheet.index('.status.errors'):stylesheet.index('.status.errors') + 80])

    def test_same_participant_gets_different_candidate_across_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store = self.store(root, count=2, redundancy=3)

            first = store.assign(self.worker("P1", "SESSION1"))
            second = store.assign(self.worker("P1", "SESSION2"))

            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            self.assertNotEqual(
                first["tasks"][0]["candidate_id"],
                second["tasks"][0]["candidate_id"],
            )

    def test_submitted_candidate_is_not_reassigned_to_same_participant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store = self.store(root, count=2, redundancy=3)
            worker = self.worker("P1", "SESSION1")
            first = store.assign(worker)
            self.assertEqual(store.submit(self.payload(worker, first))["status"], "ok")

            second = store.assign(self.worker("P1", "SESSION2"))

            self.assertEqual(second["status"], "ok")
            self.assertNotEqual(
                first["tasks"][0]["candidate_id"],
                second["tasks"][0]["candidate_id"],
            )

    def test_candidate_is_not_assigned_after_three_unique_participants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store = self.store(root, count=1, redundancy=3)
            for index in range(1, 4):
                worker = self.worker(f"P{index}", f"SESSION{index}")
                assignment = store.assign(worker)
                self.assertEqual(assignment["status"], "ok")
                self.assertEqual(store.submit(self.payload(worker, assignment))["status"], "ok")

            response = store.assign(self.worker("P4", "SESSION4"))

            self.assertEqual(response["status"], "error")
            self.assertIn("No unassigned", response["errors"][0])

    def test_expired_pending_assignment_releases_claim_but_late_submit_cannot_overfill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store = self.store(root, count=1, redundancy=1, timeout_minutes=1)
            stale_worker = self.worker("P1", "SESSION1")
            stale_assignment = store.assign(stale_worker)
            assignments_path = root / "data" / "assignments.json"
            assignments = json.loads(assignments_path.read_text(encoding="utf-8"))
            assignments["SESSION1"]["assigned_at"] = (
                datetime.now(timezone.utc) - timedelta(minutes=5)
            ).isoformat().replace("+00:00", "Z")
            assignments_path.write_text(json.dumps(assignments), encoding="utf-8")

            current_worker = self.worker("P2", "SESSION2")
            current_assignment = store.assign(current_worker)
            self.assertEqual(current_assignment["status"], "ok")
            self.assertEqual(
                stale_assignment["tasks"][0]["candidate_id"],
                current_assignment["tasks"][0]["candidate_id"],
            )
            self.assertEqual(store.submit(self.payload(current_worker, current_assignment))["status"], "ok")

            late_response = store.submit(self.payload(stale_worker, stale_assignment))

            self.assertEqual(late_response["status"], "error")
            self.assertIn("required number", late_response["errors"][0])


    def test_returned_result_is_archived_once_and_old_session_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir); store = self.store(root, count=1, redundancy=2)
            worker = self.worker("P1", "SESSION1"); assignment = store.assign(worker)
            self.assertEqual(store.submit(self.payload(worker, assignment))["status"], "ok")
            observed = {"id": "SESSION1", "study_id": "S1", "participant": {"id": "P1"}, "status": "RETURNED"}
            self.assertEqual(store.reconcile_returned(observed)["action"], "archived_result")
            self.assertEqual(store.reconcile_returned(observed)["status"], "already_processed")
            self.assertFalse((root / "data" / "submissions" / "SESSION1.json").exists())
            self.assertTrue((next((root / "data" / "excluded_submissions").glob("*/prolific_returned/SESSION1.json"))).exists())
            self.assertEqual(store.assign(worker)["status"], "error")

    def test_returned_without_result_releases_claim(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir); store = self.store(root, count=1, redundancy=1)
            worker = self.worker("P1", "SESSION1"); store.assign(worker)
            observed = {"id": "SESSION1", "study_id": "S1", "participant": {"id": "P1"}, "status": "RETURNED"}
            self.assertEqual(store.reconcile_returned(observed)["action"], "released_claim")
            self.assertEqual(store.assign(self.worker("P2", "SESSION2"))["status"], "ok")

if __name__ == "__main__":
    unittest.main()
