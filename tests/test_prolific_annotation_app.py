import json
import tempfile
import unittest
from pathlib import Path

from prolific.conversation_annotation_app.app import (
    AnnotationStore,
    load_tasks,
    parse_args,
    validate_submission,
)


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
        stylesheet = (static_dir / "style.css").read_text(encoding="utf-8")

        self.assertIn('id="phenomenon-list"', html)
        self.assertIn('id="add-phenomenon"', html)
        self.assertIn('id="delete-phenomenon"', html)
        self.assertIn('<details class="card foldable intro-card" id="instruction" open>', html)
        self.assertIn('<details class="card foldable instructions" id="examples" open>', html)
        self.assertIn("Selected segment annotation <span class=\"muted\">(scrollable)</span>", html)
        self.assertIn("please read the Instruction and go through the Examples", html)
        self.assertNotIn('id="task-audio"', html)
        self.assertIn("`Audio ${index + 1} of ${state.tasks.length}`", javascript)
        self.assertIn("byId('task-nav').hidden = state.tasks.length === 1", javascript)
        self.assertNotIn('id="phenomenon-note"', html)
        self.assertNotIn('id="ctc-guess-accuracy"', html)
        self.assertNotIn('id="ctc-guidance-followup"', html)
        self.assertNotIn('id="pp-question-speaker"', html)
        self.assertNotIn('id="pp-response-speaker"', html)
        self.assertNotIn('id="pp-question-start"', html)
        self.assertNotIn('id="pp-response-start"', html)
        self.assertIn("pragmaticPairMetadataFromSegmentMap", javascript)
        self.assertIn('id="ctc-word-phrase-fit"', html)
        self.assertIn('<option value="not_applicable">Not applicable</option>', html)
        self.assertIn("word_phrase_confident", javascript)
        self.assertIn("word_phrase_unsure", javascript)
        self.assertIn("guiding_question", javascript)
        self.assertNotIn("['unspecified', 'Unspecified']", javascript)
        self.assertIn("notApplicable.disabled = enabled", javascript)
        self.assertIn("the interrupter and interrupted speaker must be different people", javascript)
        self.assertIn("the interrupter cannot start before the interrupted speaker", javascript)
        self.assertIn("cannot be combined with other annotations", javascript)
        self.assertIn("this segment pair has already been annotated", javascript)
        self.assertIn("the prompt and response must come from different people", javascript)
        self.assertIn("the response cannot start before the prompt or question", javascript)
        self.assertIn("Buzz-in segments do not overlap", javascript)
        self.assertIn('id="warnings"', html)
        self.assertIn("#playback-playhead", stylesheet)
        self.assertIn("playhead.id = 'playback-playhead'", javascript)
        self.assertIn("media: byId('fallback-audio')", javascript)
        self.assertIn("wave.on('timeupdate'", javascript)
        self.assertIn("wave.on('scroll'", javascript)
        self.assertIn("wave.on('redrawcomplete'", javascript)
        self.assertIn("phenomena: current.phenomena.map", javascript)
        self.assertIn("conversation-annotation-v3", javascript)
        for filename in (
            "ctc_stuck_confident.wav",
            "ctc_stuck_unsure.wav",
            "ctc_guiding_question.wav",
            "ctc_buzz_in.wav",
            "pragmatic_pair.wav",
        ):
            self.assertIn(f'/static/examples/audio/{filename}', html)
            self.assertTrue((static_dir / "examples" / "audio" / filename).is_file())

    def test_v3_submission_rejects_invalid_phenomenon_relationships(self) -> None:
        payload = {
            "schema_version": "conversation-annotation-v3",
            "worker": self.worker,
            "tasks": [
                {
                    "task_id": "stereo",
                    "segments": [
                        {
                            "segment_id": "speaker",
                            "channel": 0,
                            "start": 1.0,
                            "end": 3.0,
                            "transcript": "speaker",
                        },
                        {
                            "segment_id": "interrupter",
                            "channel": 0,
                            "start": 0.5,
                            "end": 2.0,
                            "transcript": "interrupter",
                        },
                        {
                            "segment_id": "prompt",
                            "channel": 1,
                            "start": 4.0,
                            "end": 5.0,
                            "transcript": "prompt",
                        },
                        {
                            "segment_id": "response",
                            "channel": 1,
                            "start": 3.5,
                            "end": 4.5,
                            "transcript": "response",
                        },
                    ],
                    "phenomena": [
                        {"phenomenon_type": "not_target"},
                        {
                            "phenomenon_type": "ctc",
                            "ctc": {
                                "interrupted_segment_id": "speaker",
                                "interrupting_segment_id": "interrupter",
                            },
                        },
                        {
                            "phenomenon_type": "ctc",
                            "ctc": {
                                "interrupted_segment_id": "speaker",
                                "interrupting_segment_id": "interrupter",
                            },
                        },
                        {
                            "phenomenon_type": "pragmatic_pair",
                            "pragmatic_pair": {
                                "question_segment_id": "prompt",
                                "response_segment_id": "response",
                            },
                        },
                    ],
                }
            ],
        }

        errors = "\n".join(validate_submission(payload))

        self.assertIn("cannot be combined with other annotations", errors)
        self.assertIn("this segment pair is duplicated", errors)
        self.assertIn("interrupter and interrupted speaker must differ", errors)
        self.assertIn("interrupter cannot start before", errors)
        self.assertIn("prompt and response speakers must differ", errors)
        self.assertIn("response cannot start before the prompt", errors)

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
