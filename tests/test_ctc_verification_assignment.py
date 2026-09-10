import json
import hashlib
import multiprocessing
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prolific.ctc_verification_app.app import VerificationStore


def _race_return(root_text):
    root=Path(root_text)
    store=VerificationStore([], [str(root/"candidates.jsonl")], root/"data", 1, 1, "https://example.test/complete", False)
    worker={"prolific_pid":"P1","study_id":"S1","session_id":"S1"}
    assignment=store.assign(worker)
    if assignment.get("status") != "ok": return assignment["status"]
    payload={"schema_version":"ctc-verification-v1","worker":worker,"assignment":assignment["assignment"],"tasks":[{"candidate_id":assignment["tasks"][0]["candidate_id"],"task_id":assignment["tasks"][0]["task_id"],"relevant_interruption":False}]}
    return store.submit(payload)["status"]


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

    def test_return_identity_mismatch_does_not_leave_intent_or_release_claim(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1); worker=self.worker("P1","S1"); store.assign(worker)
            bad={"id":"S1","study_id":"S1","participant":{"id":"P2"},"status":"RETURNED"}
            self.assertEqual(store.reconcile_returned(bad)["status"],"manual_review")
            self.assertEqual(store.assign(self.worker("P2","S2"))["status"],"error")
            self.assertIn("S1", json.loads((root/"data"/"assignments.json").read_text()))

    def test_consent_withdrawal_is_not_return_archival(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1)
            result=store.reconcile_returned({"id":"S1","study_id":"S1","participant":{"id":"P1"},"status":"RETURNED"}, consent_withdrawn=True)
            self.assertEqual(result["status"],"manual_review"); self.assertFalse((root/"data"/"returned-lifecycle.json").exists())

    def test_restart_recovers_each_persisted_transaction_boundary(self):
        for stage in ("intent", "archive_written", "source_removed", "assignment_removed", "complete"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as d:
                root=Path(d); store=self.store(root, count=1, redundancy=1); worker=self.worker("P1","S1"); assignment=store.assign(worker)
                payload=self.payload(worker, assignment); store.submit(payload)
                source=root/"data"/"submissions"/"S1.json"; raw=source.read_bytes(); archive=root/"data"/"excluded_submissions"/"2026-09-09"/"prolific_returned"/"S1.json"
                if stage in ("archive_written","source_removed","assignment_removed","complete"): archive.parent.mkdir(parents=True); archive.write_bytes(raw)
                if stage in ("source_removed","assignment_removed","complete"): source.unlink()
                assignments=json.loads((root/"data"/"assignments.json").read_text())
                if stage in ("assignment_removed","complete"): assignments.pop("S1",None); (root/"data"/"assignments.json").write_text(json.dumps(assignments))
                lifecycle={"S1":{"status":"RETURNED" if stage=="complete" else "PENDING","stage":stage,"session_id":"S1","study_id":"S1","participant_id":"P1","assignment":None if stage in ("assignment_removed","complete") else assignments.get("S1"),"source":str(source),"destination":str(archive),"sha256":hashlib.sha256(raw).hexdigest(),"action":"archived_result","processed_at":"2026-09-09T00:00:00Z"}}
                (root/"data"/"returned-lifecycle.json").write_text(json.dumps(lifecycle))
                recovered=self.store(root, count=1, redundancy=1)
                self.assertEqual(recovered.assign(self.worker("P1","S1"))["status"],"error")
                self.assertEqual(archive.read_bytes(), raw); self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), lifecycle["S1"]["sha256"])
                self.assertEqual(recovered.submit(self.payload(worker, assignment))["status"],"error")
                self.assertEqual(recovered.save_draft({"worker":worker,"taskState":[]})["status"],"error")

    def test_real_process_store_lock_race_does_not_resurrect_returned_session(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1); worker=self.worker("P1","S1"); assignment=store.assign(worker)
            returned={"id":"S1","study_id":"S1","participant":{"id":"P1"},"status":"RETURNED"}
            process=multiprocessing.Process(target=_race_return,args=(str(root),)); process.start(); store.reconcile_returned(returned); process.join(10)
            self.assertFalse(process.is_alive()); self.assertEqual(process.exitcode, 0)
            self.assertEqual(json.loads((root/"data"/"returned-lifecycle.json").read_text())["S1"]["status"],"RETURNED")
            self.assertFalse((root/"data"/"assignments.json").exists() and "S1" in json.loads((root/"data"/"assignments.json").read_text()))

    def test_assign_rejects_session_when_recovery_identity_is_uncertain(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1); worker=self.worker("P1","S1"); assignment=store.assign(worker)
            lifecycle={"S1":{"status":"PENDING","stage":"intent","session_id":"S1","study_id":"S1","participant_id":"P1","assignment":assignment["assignment"],"source":str(root/"data"/"submissions"/"S1.json"),"destination":str(root/"data"/"excluded_submissions/2026-09-09/prolific_returned/S1.json"),"sha256":"wrong","action":"archived_result"}}
            (root/"data"/"returned-lifecycle.json").write_text(json.dumps(lifecycle))
            self.assertEqual(store.assign(worker)["status"], "error")
            self.assertEqual(store.submit(self.payload(worker, assignment))["status"], "error")

    def test_timeout_consent_withdrawal_is_manual_without_any_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1)
            worker=self.worker('P1','S1'); assignment=store.assign(worker)
            lifecycle=root/'data'/'returned-lifecycle.json'; assignments=root/'data'/'assignments.json'
            before_lifecycle=lifecycle.read_bytes() if lifecycle.exists() else None
            before_assignments=assignments.read_bytes()
            observed={'id':'S1','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            result=store.reconcile_timed_out(observed, consent_withdrawn=True)
            self.assertEqual(result['status'], 'manual_review')
            self.assertEqual(assignments.read_bytes(), before_assignments)
            self.assertEqual(lifecycle.exists(), before_lifecycle is not None)
            self.assertFalse((root/'data'/'excluded_submissions').exists())
            recovered=store.reconcile_timed_out(observed, consent_withdrawn=True)
            self.assertEqual(recovered['status'], 'manual_review')
            self.assertEqual(assignments.read_bytes(), before_assignments)

    def test_timed_out_without_result_releases_and_blocks_late_submit(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir); store = self.store(root, count=1, redundancy=1)
            worker = self.worker("P1", "SESSION1"); assignment = store.assign(worker)
            observed = {"id": "SESSION1", "study_id": "S1", "participant": {"id": "P1"}, "status": "TIMED-OUT"}
            self.assertEqual(store.reconcile_timed_out(observed)["action"], "released_claim")
            self.assertEqual(store.reconcile_timed_out(observed)["status"], "already_processed")
            self.assertEqual(store.assign(self.worker("P2", "SESSION2"))["status"], "ok")
            late = store.submit(self.payload(worker, assignment))
            self.assertEqual(late["status"], "error")
            self.assertIn("cannot be used again", late["errors"][0])

    def test_timed_out_with_final_result_archives_exact_bytes_and_releases(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir); store = self.store(root, count=1, redundancy=1)
            worker = self.worker("P1", "SESSION1"); assignment = store.assign(worker)
            self.assertEqual(store.submit(self.payload(worker, assignment))["status"], "ok")
            source = root / "data" / "submissions" / "SESSION1.json"
            original = source.read_bytes()
            result = store.reconcile_timed_out({"id": "SESSION1", "study_id": "S1", "participant": {"id": "P1"}, "status": "TIMED_OUT"})
            self.assertEqual(result["status"], "processed")
            archive = next((root / "data" / "excluded_submissions").glob("*/prolific_timed_out/SESSION1.json"))
            self.assertEqual(archive.read_bytes(), original)
            self.assertFalse(source.exists())
            self.assertEqual(store.assign(self.worker("P2", "SESSION2"))["status"], "ok")

    def test_timed_out_final_archive_fault_recovers_before_new_assignment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1)
            worker=self.worker('P1','S1'); assignment=store.assign(worker); payload=self.payload(worker, assignment)
            self.assertEqual(store.submit(payload)['status'], 'ok')
            original=(root/'data'/'submissions'/'S1.json').read_bytes()
            observed={'id':'S1','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            app=__import__('prolific.ctc_verification_app.app', fromlist=['atomic_write_bytes','atomic_write_json'])
            real_bytes=app.atomic_write_bytes
            def fail_after_archive(path, data):
                real_bytes(path, data)
                raise OSError('crash after timeout archive')
            with patch('prolific.ctc_verification_app.app.atomic_write_bytes', side_effect=fail_after_archive):
                with self.assertRaises(OSError): store.reconcile_timed_out(observed)
            recovered=self.store(root, count=1, redundancy=1)
            self.assertEqual(recovered.assign(self.worker('P2','S2'))['status'], 'ok')
            self.assertEqual(recovered.assign(worker)['status'], 'error')
            archive=next((root/'data'/'excluded_submissions').glob('*/prolific_timed_out/S1.json'))
            self.assertEqual(archive.read_bytes(), original)

    def test_repeated_timeout_identity_mismatch_is_manual_and_byte_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1)
            worker=self.worker('P1','S1'); store.assign(worker)
            good={'id':'S1','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            self.assertEqual(store.reconcile_timed_out(good)['status'], 'processed')
            lifecycle=root/'data'/'returned-lifecycle.json'; assignments=root/'data'/'assignments.json'
            before_lifecycle=lifecycle.read_bytes(); before_assignments=assignments.read_bytes()
            bad={'id':'S1','study_id':'OTHER','participant':{'id':'P2'},'status':'TIMED-OUT'}
            self.assertEqual(store.reconcile_timed_out(bad)['status'], 'manual_review')
            self.assertEqual(store.reconcile_timed_out(bad)['status'], 'manual_review')
            self.assertEqual(lifecycle.read_bytes(), before_lifecycle)
            self.assertEqual(assignments.read_bytes(), before_assignments)

    def test_timeout_manual_then_returned_stays_manual(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1)
            worker=self.worker('P1','S1'); store.assign(worker)
            timeout={'id':'S1','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            self.assertEqual(store.reconcile_timed_out(timeout)['status'], 'processed')
            lifecycle=root/'data'/'returned-lifecycle.json'; state=json.loads(lifecycle.read_text())
            state['S1']['status']='TIMED_OUT_MANUAL'; state['S1']['stage']='final_result_conflict'; lifecycle.write_text(json.dumps(state))
            result=store.reconcile_returned({**timeout,'status':'RETURNED'})
            self.assertEqual(result['status'], 'manual_review')
            self.assertEqual(json.loads(lifecycle.read_text())['S1']['status'], 'TIMED_OUT_MANUAL')

    def test_mixed_timeout_recovery_reloads_assignments_between_intents(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=2, redundancy=1)
            worker_a=self.worker('P1','A'); worker_b=self.worker('P2','B')
            assignment_a=store.assign(worker_a); assignment_b=store.assign(worker_b)
            self.assertEqual(store.submit(self.payload(worker_a, assignment_a))['status'], 'ok')
            observed_a={'id':'A','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            app=__import__('prolific.ctc_verification_app.app', fromlist=['atomic_write_json'])
            real_write=app.atomic_write_json
            def crash_after_a_intent(path, payload):
                real_write(path, payload)
                if path.name == 'returned-lifecycle.json' and payload.get('A',{}).get('stage') == 'intent':
                    raise OSError('crash after archive intent')
            with patch('prolific.ctc_verification_app.app.atomic_write_json', side_effect=crash_after_a_intent):
                with self.assertRaises(OSError): store.reconcile_timed_out(observed_a)
            lifecycle=root/'data'/'returned-lifecycle.json'; state=json.loads(lifecycle.read_text())
            state['B']={'kind':'timeout','status':'TIMED_OUT','stage':'claim_release','session_id':'B','study_id':'S1','participant_id':'P2','assignment':json.loads((root/'data'/'assignments.json').read_text())['B'],'action':'released_claim'}
            lifecycle.write_text(json.dumps(state))
            recovered=self.store(root, count=2, redundancy=1)
            self.assertEqual(recovered.assign(self.worker('P3','C'))['status'], 'ok')
            assignments=json.loads((root/'data'/'assignments.json').read_text())
            self.assertEqual(set(assignments), {'C'})
            self.assertFalse((root/'data'/'submissions'/'A.json').exists())
            self.assertTrue(list((root/'data'/'excluded_submissions').glob('*/prolific_timed_out/A.json')))
            self.assertEqual(json.loads(lifecycle.read_text())['B']['status'], 'TIMED_OUT')
            self.assertEqual(recovered.assign(worker_a)['status'], 'error')

    def test_public_timeout_reconcile_drains_pending_archive_before_claim_release(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=2, redundancy=1)
            worker_a=self.worker('P1','A'); worker_b=self.worker('P2','B')
            assignment_a=store.assign(worker_a); assignment_b=store.assign(worker_b)
            self.assertEqual(store.submit(self.payload(worker_a, assignment_a))['status'], 'ok')
            original=(root/'data'/'submissions'/'A.json').read_bytes()
            observed_a={'id':'A','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            app=__import__('prolific.ctc_verification_app.app', fromlist=['atomic_write_bytes'])
            real_bytes=app.atomic_write_bytes
            def crash_after_archive(path, data):
                real_bytes(path, data)
                raise OSError('crash after archive')
            with patch('prolific.ctc_verification_app.app.atomic_write_bytes', side_effect=crash_after_archive):
                with self.assertRaises(OSError): store.reconcile_timed_out(observed_a)
            observed_b={'id':'B','study_id':'S1','participant':{'id':'P2'},'status':'TIMED-OUT'}
            self.assertEqual(store.reconcile_timed_out(observed_b)['status'], 'processed')
            assignments=json.loads((root/'data'/'assignments.json').read_text())
            self.assertEqual(assignments, {})
            archive=next((root/'data'/'excluded_submissions').glob('*/prolific_timed_out/A.json'))
            self.assertEqual(archive.read_bytes(), original)
            self.assertFalse((root/'data'/'submissions'/'A.json').exists())
            self.assertEqual(store.assign(worker_a)['status'], 'error')
            self.assertEqual(store.assign(worker_b)['status'], 'error')

    def test_timeout_fault_after_intent_is_recovered_by_new_assignment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1)
            worker=self.worker('P1','S1'); store.assign(worker)
            observed={'id':'S1','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            app=__import__('prolific.ctc_verification_app.app', fromlist=['atomic_write_json'])
            real_write=app.atomic_write_json
            def fail_after_intent(path, payload):
                real_write(path, payload)
                if path.name == 'returned-lifecycle.json' and payload.get('S1',{}).get('stage') == 'claim_release':
                    raise OSError('crash after intent')
            with patch('prolific.ctc_verification_app.app.atomic_write_json', side_effect=fail_after_intent):
                with self.assertRaises(OSError): store.reconcile_timed_out(observed)
            recovered=self.store(root, count=1, redundancy=1)
            self.assertEqual(recovered.assign(self.worker('P2','S2'))['status'], 'ok')
            self.assertNotIn('S1', json.loads((root/'data'/'assignments.json').read_text()))

    def test_timeout_fault_after_claim_delete_is_recovered_exactly_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); store=self.store(root, count=1, redundancy=1)
            worker=self.worker('P1','S1'); store.assign(worker)
            observed={'id':'S1','study_id':'S1','participant':{'id':'P1'},'status':'TIMED-OUT'}
            app=__import__('prolific.ctc_verification_app.app', fromlist=['atomic_write_json'])
            real_write=app.atomic_write_json
            def fail_after_delete(path, payload):
                real_write(path, payload)
                if path.name == 'assignments.json' and 'S1' not in payload:
                    raise OSError('crash after claim delete')
            with patch('prolific.ctc_verification_app.app.atomic_write_json', side_effect=fail_after_delete):
                with self.assertRaises(OSError): store.reconcile_timed_out(observed)
            recovered=self.store(root, count=1, redundancy=1)
            self.assertEqual(recovered.assign(self.worker('P2','S2'))['status'], 'ok')
            self.assertEqual(recovered.reconcile_timed_out(observed)['status'], 'already_processed')
            self.assertNotIn('S1', json.loads((root/'data'/'assignments.json').read_text()))

if __name__ == "__main__":
    unittest.main()
