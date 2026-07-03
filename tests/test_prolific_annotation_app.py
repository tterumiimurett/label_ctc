import json
import tempfile
import unittest
from pathlib import Path

from prolific.conversation_annotation_app.app import AnnotationStore, load_tasks, parse_args


class ConversationAnnotationAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.task = {
            "data": {"audio": "https://example.test/stereo.wav", "path_seg": "/tmp/stereo.wav"},
            "predictions": [
                {
                    "result": [
                        {
                            "id": "seg-1",
                            "from_name": "channel",
                            "value": {
                                "start": 0.1,
                                "end": 1.2,
                                "channel": 0,
                                "labels": ["Left"],
                            },
                        },
                        {
                            "id": "seg-1",
                            "from_name": "transcript",
                            "value": {"text": ["hello"]},
                        },
                    ]
                }
            ],
        }
        self.worker = {
            "prolific_pid": "P1",
            "study_id": "S1",
            "session_id": "SESSION1",
        }

    def test_frontend_supports_multiple_phenomena_without_removed_ctc_fields(self) -> None:
        static_dir = (
            Path(__file__).resolve().parents[1]
            / "prolific"
            / "conversation_annotation_app"
            / "static"
        )
        html = (static_dir / "annotate.html").read_text(encoding="utf-8")
        javascript = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="phenomenon-list"', html)
        self.assertIn('id="add-phenomenon"', html)
        self.assertIn('id="delete-phenomenon"', html)
        self.assertNotIn('id="ctc-guess-accuracy"', html)
        self.assertNotIn('id="ctc-guidance-followup"', html)
        self.assertIn("phenomena: current.phenomena.map", javascript)
        self.assertIn("conversation-annotation-v3", javascript)

    def test_assign_is_stable_for_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            tasks_path = root / "label_studio_tasks_test_predictions.json"
            tasks_path.write_text(json.dumps([self.task]), encoding="utf-8")
            store = AnnotationStore(
                tasks_path=tasks_path,
                data_dir=root / "data",
                bundle_size=1,
                redundancy=3,
                completion_url="https://example.test/complete",
            )

            first = store.assign(self.worker)
            second = store.assign(self.worker)

            self.assertEqual(first["status"], "ok")
            self.assertEqual(first["assignment"]["bundle_id"], second["assignment"]["bundle_id"])
            self.assertEqual(first["tasks"][0]["schema_version"], "conversation-annotation-v2")
            self.assertEqual(first["tasks"][0]["task"]["task_id"], "stereo")

    def test_loaded_task_schema_has_file_level_and_segment_choices_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            tasks_path = root / "label_studio_tasks_test_predictions.json"
            tasks_path.write_text(json.dumps([self.task]), encoding="utf-8")

            task = load_tasks(tasks_path)[0]

            self.assertIn("ctc_status", task["choices"])
            self.assertIn("segment_flags", task["choices"])
            self.assertNotIn("event_type", task["choices"])

    def test_assignment_counts_pending_sessions_before_reusing_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            tasks_path = root / "label_studio_tasks_test_predictions.json"
            task_two = json.loads(json.dumps(self.task))
            task_two["data"]["audio"] = "https://example.test/second.wav"
            tasks_path.write_text(json.dumps([self.task, task_two]), encoding="utf-8")
            store = AnnotationStore(
                tasks_path=tasks_path,
                data_dir=root / "data",
                bundle_size=1,
                redundancy=1,
                completion_url="https://example.test/complete",
            )

            first = store.assign(self.worker)
            second = store.assign(
                {"prolific_pid": "P2", "study_id": "S1", "session_id": "SESSION2"}
            )

            self.assertEqual(first["tasks"][0]["task"]["task_id"], "stereo")
            self.assertEqual(second["tasks"][0]["task"]["task_id"], "second")

    def test_submit_writes_submission_and_marks_assignment_submitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            tasks_path = root / "label_studio_tasks_test_predictions.json"
            tasks_path.write_text(json.dumps([self.task]), encoding="utf-8")
            data_dir = root / "data"
            store = AnnotationStore(
                tasks_path=tasks_path,
                data_dir=data_dir,
                bundle_size=1,
                redundancy=3,
                completion_url="https://example.test/complete",
            )
            assignment = store.assign(self.worker)
            assigned_task = assignment["tasks"][0]

            response = store.submit(
                {
                    "schema_version": "conversation-annotation-v3",
                    "worker": self.worker,
                    "assignment": assignment["assignment"],
                    "tasks": [
                        {
                            "task_id": assigned_task["task"]["task_id"],
                            "audio_url": assigned_task["task"]["audio_url"],
                            "dataset": assigned_task["task"]["dataset"],
                            "bundle_id": assignment["assignment"]["bundle_id"],
                            "phenomena": [{"phenomenon_id": 1, "phenomenon_type": "not_target"}],
                            "segments": [
                                {
                                    "segment_id": "seg-1",
                                    "channel": 0,
                                    "speaker": "Left",
                                    "start": 0.1,
                                    "end": 1.2,
                                    "transcript": "hello",
                                    "flags": [],
                                    "note": "",
                                }
                            ],
                        }
                    ],
                }
            )

            self.assertEqual(response["status"], "ok")
            saved = json.loads((data_dir / "submissions" / "SESSION1.json").read_text())
            assignments = json.loads((data_dir / "assignments.json").read_text())
            self.assertEqual(saved["worker"]["session_id"], "SESSION1")
            self.assertTrue(assignments["SESSION1"]["submitted"])

    def test_submit_rejects_unassigned_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            tasks_path = root / "label_studio_tasks_test_predictions.json"
            tasks_path.write_text(json.dumps([self.task]), encoding="utf-8")
            store = AnnotationStore(
                tasks_path=tasks_path,
                data_dir=root / "data",
                bundle_size=1,
                redundancy=3,
                completion_url="https://example.test/complete",
            )

            response = store.submit(
                {
                    "worker": self.worker,
                    "tasks": [
                        {
                            "task_id": "stereo",
                            "file_level": {
                                "target_status": ["is_CTC"],
                                "audio_quality": "usable",
                                "transcript_quality": "good",
                            },
                            "segments": [
                                {
                                    "start": 0.1,
                                    "end": 1.2,
                                    "transcript": "hello",
                                }
                            ],
                        }
                    ],
                }
            )

            self.assertEqual(response["status"], "error")
            self.assertIn("No assignment exists", response["errors"][0])

    def test_parse_args_default_bundle_size_is_one(self) -> None:
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ["app.py"]
            self.assertEqual(parse_args().bundle_size, 1)
        finally:
            sys.argv = original_argv


if __name__ == "__main__":
    unittest.main()
