"""The TC lab app keeps annotator results separate and retains QC decisions."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from lab_ctc_agreement_app.app import Store


class LabCtcStoreTest(unittest.TestCase):
    def test_independent_labels_and_qc_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset"
            dataset.mkdir()
            key = "a" * 16
            (dataset / "tasks.json").write_text(json.dumps({"cases": [{"key": key}]}))
            annotators = root / "annotators.json"
            annotators.write_text(json.dumps({"annotators": [
                {"token": "A" * 24, "display_name": "A"},
                {"token": "B" * 24, "display_name": "B"},
            ]}))
            store = Store(dataset, root / "results", annotators)
            label = {
                "key": key, "turn_completion": "yes", "natural_completion": "no",
                "asr_quality": "material", "candidate_boundary": "incorrect",
                "user_transcript": "unfinished", "model_transcript": "first reply", "note": "wrong ASR",
            }
            store.save("A" * 24, key, label)
            self.assertEqual(store.progress("A" * 24)["saved_count"], 1)
            self.assertEqual(store.progress("B" * 24)["saved_count"], 0)
            self.assertEqual(json.loads(store.label_path("A" * 24, key).read_text())["asr_quality"], "material")
            with self.assertRaisesRegex(ValueError, "invalid_candidate_boundary"):
                store.save("B" * 24, key, {**label, "candidate_boundary": None})
            with self.assertRaisesRegex(ValueError, "natural_completion_required_for_tc"):
                store.save("B" * 24, key, {**label, "natural_completion": None})


if __name__ == "__main__":
    unittest.main()
