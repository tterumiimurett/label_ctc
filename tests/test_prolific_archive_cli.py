import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prolific.ctc_verification_app.app import VerificationStore
from prolific.ctc_verification_app.archive_cli import poll_archives


class Reader:
    def __init__(self, statuses):
        self.statuses = statuses
        self.calls = []

    def get_submission(self, sid):
        self.calls.append(sid)
        value = self.statuses[sid]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, dict):
            return value
        return {"id": sid, "study_id": "study", "participant": "person", "status": value}


class ArchivePollTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        labels = self.root / "labels.jsonl"
        labels.write_text(json.dumps({"candidate_key": "V_S_I|P1|P2|1.000|2.000|target", "pred_is_ctc": True, "audio_verify": {"verify_is_ctc": True}, "tos_audio": {"outer_url": "https://example.test/audio.wav"}}) + "\n", encoding="utf-8")
        self.store = VerificationStore([], [str(labels)], self.root / "data", 1, 3, "", False)
        self.store.submissions_dir.mkdir(parents=True)
        self.raw = {}

    def result(self, sid):
        raw = json.dumps({"worker": {"session_id": sid, "study_id": "study", "prolific_pid": "person"}, "tasks": [{"answer": True}]}, indent=3).encode()
        (self.store.submissions_dir / f"{sid}.json").write_bytes(raw)
        self.raw[sid] = raw

    def test_only_archive_statuses_and_preserve_bytes(self):
        for sid in ("returned", "timeout", "aw"):
            self.result(sid)
        reader = Reader({"returned": "RETURNED", "timeout": "TIMED-OUT", "aw": "AWAITING REVIEW"})
        preview = poll_archives(self.store, reader, "study")
        self.assertEqual(preview["counts"], {"unchanged": 1, "would_archive": 2})
        self.assertEqual(len(list(self.store.submissions_dir.glob("*.json"))), 3)
        report = poll_archives(self.store, reader, "study", execute=True)
        self.assertEqual(report["counts"], {"unchanged": 1, "processed": 2})
        for sid, category in (("returned", "prolific_returned"), ("timeout", "prolific_timed_out")):
            archive = list(self.store.data_dir.glob(f"excluded_submissions/*/{category}/{sid}.json"))
            self.assertEqual(len(archive), 1)
            self.assertEqual(archive[0].read_bytes(), self.raw[sid])
        self.assertEqual(poll_archives(self.store, reader, "study", execute=True)["counts"], {"unchanged": 1})

    def test_failures_are_isolated_and_identity_is_checked(self):
        for sid in ("bad", "failure", "good"):
            self.result(sid)
        reader = Reader({"bad": {"id": "bad", "study_id": "other", "participant": "person", "status": "RETURNED"}, "failure": RuntimeError("secret"), "good": "RETURNED"})
        report = poll_archives(self.store, reader, "study", execute=True)
        self.assertEqual(report["counts"], {"manual_review": 2, "processed": 1})
        self.assertNotIn("secret", json.dumps(report))
        self.assertTrue((self.store.submissions_dir / "bad.json").exists())

    def test_missing_directory_fails_before_api(self):
        self.store.submissions_dir.rmdir()
        reader = Reader({})
        with self.assertRaises(ValueError):
            poll_archives(self.store, reader, "study", execute=True)
        self.assertEqual(reader.calls, [])

    def test_recover_after_source_removed_and_require_fresh_status(self):
        self.result("returned")
        with patch.object(self.store, "_resume_exclusion_lifecycle", side_effect=OSError("interruption")):
            self.assertEqual(poll_archives(self.store, Reader({"returned": "RETURNED"}), "study", execute=True)["counts"], {"manual_review": 1})
        lifecycle = json.loads(self.store.lifecycle_path.read_text())
        record = lifecycle["returned"]
        destination = Path(record["destination"])
        destination.parent.mkdir(parents=True)
        destination.write_bytes(self.raw["returned"])
        Path(record["source"]).unlink()
        report = poll_archives(self.store, Reader({"returned": "AWAITING REVIEW"}), "study", execute=True)
        self.assertEqual(report["counts"], {"manual_review": 1})
        report = poll_archives(self.store, Reader({"returned": "RETURNED"}), "study", execute=True)
        self.assertEqual(report["counts"], {"processed": 1})
        self.assertEqual(destination.read_bytes(), self.raw["returned"])
        self.assertEqual(poll_archives(self.store, Reader({}), "study", execute=True)["counts"], {})

    def test_timeout_does_not_drain_other_unverified_intents(self):
        self.result("pending")
        with patch.object(self.store, "_resume_exclusion_lifecycle", side_effect=OSError):
            poll_archives(self.store, Reader({"pending": "TIMED-OUT"}), "study", execute=True)
        self.result("new")
        report = poll_archives(self.store, Reader({"pending": "AWAITING REVIEW", "new": "TIMED-OUT"}), "study", execute=True)
        self.assertEqual(report["counts"], {"processed": 1, "manual_review": 1})
        self.assertTrue((self.store.submissions_dir / "pending.json").exists())

    def test_consent_file_missing_or_withdrawn_blocks(self):
        self.result("returned")
        evidence = self.root / "consent.json"
        with self.assertRaises(OSError):
            poll_archives(self.store, Reader({}), "study", execute=True, consent_path=evidence)
        evidence.write_text(json.dumps({"records": [{"record_id": "r", "session_id": "returned", "study_id": "study", "participant_id": "person", "consent_withdrawn": True}]}))
        report = poll_archives(self.store, Reader({"returned": "RETURNED"}), "study", execute=True, consent_path=evidence)
        self.assertEqual(report["counts"], {"manual_review": 1})
        self.assertTrue((self.store.submissions_dir / "returned.json").exists())


if __name__ == "__main__":
    unittest.main()
