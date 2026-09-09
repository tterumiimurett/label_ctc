import base64
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger


class TriggerTest(unittest.TestCase):
    def signed(self, payload, event_id="E1", timestamp="100"):
        body = json.dumps(payload, separators=(",", ":")).encode()
        signature = base64.b64encode(hmac.new(b"secret", timestamp.encode() + body, hashlib.sha256).digest()).decode()
        return body, {"X-Prolific-Request-Signature": signature, "X-Prolific-Request-Timestamp": timestamp, "X-Event-ID": event_id}

    def test_signed_event_is_deduplicated_and_current_state_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock()
            reader.list_submissions.return_value = {"results": [], "next": None}
            reader.get_submission.side_effect = AssertionError("no detail for empty synthetic study")
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            trigger = ReconciliationTrigger(reader, data_dir, "STUDY", JsonTriggerStore(Path(directory) / "events.json"))
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1", "status": "RETURNED"})
            first = trigger.handle(body, headers, "secret")
            second = trigger.handle(body, headers, "secret")
            self.assertEqual(first.status, "reconciled")
            self.assertEqual(second.status, "duplicate")
            self.assertEqual(reader.list_submissions.call_count, 1)

    def test_bad_signature_and_non_submission_are_not_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            trigger = ReconciliationTrigger(Mock(), Path(directory), "STUDY", JsonTriggerStore(path))
            body, headers = self.signed({"event_type": "study.status.change", "resource_id": "STUDY"})
            self.assertEqual(trigger.handle(body, {**headers, "X-Prolific-Request-Signature": "bad"}, "secret").status, "rejected_signature")
            self.assertEqual(trigger.handle(body, headers, "secret").status, "ignored_event")
            self.assertFalse(path.exists())

    def test_out_of_order_events_are_recorded_without_replaying_old_state(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock(); reader.list_submissions.return_value = {"results": [], "next": None}
            store = JsonTriggerStore(Path(directory) / "events.json")
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            trigger = ReconciliationTrigger(reader, data_dir, "STUDY", store)
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1", "status": "RETURNED"}, "new", "200")
            self.assertEqual(trigger.handle(body, headers, "secret").status, "reconciled")
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1", "status": "RETURNED"}, "old", "100")
            self.assertEqual(trigger.handle(body, headers, "secret").status, "duplicate")
            saved = json.loads((Path(directory) / "events.json").read_text())
            self.assertEqual(saved["latest_by_resource"]["S1"]["event_id"], "new")


if __name__ == "__main__": unittest.main()
