import json
import tempfile
import unittest
from pathlib import Path

from tests.ctc_subclass_preview_app import (
    SubclassPreviewStore,
    load_source_task_index,
    match_source_task,
    normalize_category,
)


class CtcSubclassPreviewAppTest(unittest.TestCase):
    def test_normalize_category_preserves_subclass_meaning(self) -> None:
        self.assertEqual(normalize_category({"subclass": "stuck word"}), "stuck_word")
        self.assertEqual(normalize_category({"subclass": "stuck guide"}), "stuck_guide")
        self.assertEqual(normalize_category({"subclass": "unstuck"}), "not_stuck")
        self.assertEqual(normalize_category({"pred_is_ctc": False}), "not_ctc")

    def test_source_audio_match_allows_half_centisecond_rounding_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            source_path = Path(temporary_dir) / "tasks.json"
            source_path.write_text(
                json.dumps(
                    [
                        {
                            "data": {
                                "audio": (
                                    "https://example.test/"
                                    "seamless_ctc_V03_S1431_I00000375_045568_049186.wav"
                                ),
                                "path_seg": "/audio/example.wav",
                                "user": "main",
                                "assistant": "interrupter",
                            }
                        }
                    ]
                ),
                encoding="utf-8",
            )
            index = load_source_task_index(source_path)
            matched = match_source_task(
                {
                    "interaction_id": "V03_S1431_I00000375",
                    "candidate_key": (
                        "V03_S1431_I00000375|interrupter|main|"
                        "455.685|491.857|chakra"
                    ),
                },
                index,
            )

        self.assertIsNotNone(matched)
        self.assertEqual(matched["left_speaker"], "main")
        self.assertEqual(matched["match_start_delta_centiseconds"], 0.5)
        self.assertEqual(matched["match_end_delta_centiseconds"], 0.3)

    def test_store_builds_clip_relative_timestamps_and_summary(self) -> None:
        candidate = {
            "interaction_id": "V00_S0001_I00000001",
            "candidate_key": "V00_S0001_I00000001|right|left|10.000|20.000|word",
            "victim_id": "left",
            "interrupter_id": "right",
            "pred_is_ctc": True,
            "subclass": "stuck word",
            "subclass_status": "classified",
            "subclass_is_stuck": True,
            "subclass_gap_seconds": 0.75,
            "main_speaker_last_word_end_time": 14.25,
            "main_speaker_last_word_before_interruption": {
                "word": "the",
                "start": 14.0,
                "end": 14.25,
            },
            "interrupter_first_word_start_time": 15.0,
            "interrupter_first_word": {
                "word": "answer",
                "start": 15.0,
                "end": 15.4,
            },
            "interrupter_start_time": 15.0,
        }
        source_task = {
            "data": {
                "audio": (
                    "https://example.test/"
                    "seamless_ctc_V00_S0001_I00000001_001000_002000.wav"
                ),
                "path_seg": "/audio/example.wav",
                "user": "left",
                "assistant": "right",
            }
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            jsonl_path = root / "candidates.jsonl"
            source_path = root / "tasks.json"
            jsonl_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            source_path.write_text(json.dumps([source_task]), encoding="utf-8")
            data = SubclassPreviewStore(jsonl_path, source_path).preview_data()

        self.assertEqual(data["summary"]["rows"], 1)
        self.assertEqual(data["summary"]["category_counts"]["stuck_word"], 1)
        self.assertEqual(data["summary"]["audio_matched"], 1)
        item = data["items"][0]
        self.assertEqual(item["timeline"]["main_last_word_end_relative"], 4.25)
        self.assertEqual(
            item["timeline"]["interrupter_first_word_start_relative"],
            5.0,
        )
        self.assertEqual(item["timeline"]["main_last_word"]["relative_start"], 4.0)

    def test_store_can_preview_jsonl_without_source_audio_tasks(self) -> None:
        candidate = {
            "interaction_id": "V00_S0001_I00000001",
            "candidate_key": "V00_S0001_I00000001|right|left|10.000|20.000|word",
            "pred_is_ctc": True,
            "subclass": "unstuck",
            "subclass_is_stuck": False,
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            jsonl_path = Path(temporary_dir) / "train.jsonl"
            jsonl_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            data = SubclassPreviewStore(jsonl_path, None).preview_data()

        self.assertEqual(data["summary"]["rows"], 1)
        self.assertEqual(data["summary"]["audio_matched"], 0)
        self.assertIsNone(data["summary"]["source_tasks_path"])
        self.assertEqual(data["items"][0]["category"], "not_stuck")
        self.assertEqual(data["items"][0]["audio_url"], "")

    def test_static_page_exposes_filters_and_raw_json(self) -> None:
        static_dir = Path(__file__).with_name("ctc_subclass_preview_static")
        html = (static_dir / "preview.html").read_text(encoding="utf-8")
        javascript = (static_dir / "preview.js").read_text(encoding="utf-8")

        self.assertIn('<option value="stuck_word">Stuck word</option>', html)
        self.assertIn('<option value="stuck_guide">Stuck guide</option>', html)
        self.assertIn('<option value="not_stuck">Not stuck</option>', html)
        self.assertIn('id="raw-json"', html)
        self.assertIn("main_last_word_end_relative", javascript)
        self.assertIn("interrupter_first_word_start_relative", javascript)
        self.assertIn("value === null || value === undefined", javascript)
        self.assertIn("WaveSurfer.Regions", javascript)


if __name__ == "__main__":
    unittest.main()
