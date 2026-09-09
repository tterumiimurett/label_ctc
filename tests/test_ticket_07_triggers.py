import base64
import hashlib
import hmac
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import Mock

from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger, make_webhook_server, run_periodic


class TriggerTest(unittest.TestCase):
    def signed(self, payload, event_id="E1", timestamp="100"):
        body = json.dumps(payload, separators=(",", ":")).encode()
        signature = base64.b64encode(hmac.new(b"secret", timestamp.encode() + body, hashlib.sha256).digest()).decode()
        return body, {"X-Prolific-Request-Signature": signature, "X-Prolific-Request-Timestamp": timestamp, "X-Event-ID": event_id}

    def trigger(self, directory, reader):
        data = Path(directory) / "data"; data.mkdir(exist_ok=True)
        return ReconciliationTrigger(reader, data, "STUDY", JsonTriggerStore(Path(directory) / "events.json"))

    def test_restart_after_api_failure_retries_pending_event(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock(); reader.get_submission.side_effect = [ConnectionError("offline"), {"id": "S1", "study_id": "STUDY"}]
            reader.list_submissions.return_value = {"results": [], "next": None}
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1", "status": "RETURNED"})
            first = self.trigger(directory, reader).handle(body, headers, "secret")
            second = self.trigger(directory, reader).handle(body, headers, "secret")
            self.assertEqual(first.status, "pending_retry"); self.assertEqual(second.status, "reconciled")
            saved = json.loads((Path(directory) / "events.json").read_text())
            self.assertEqual(saved["events"]["E1"]["stage"], "completed")

    def test_wrong_study_isolation_is_terminal_and_does_not_reconcile(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock(); reader.get_submission.return_value = {"id": "S1", "study_id": "OTHER"}
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1"})
            result = self.trigger(directory, reader).handle(body, headers, "secret")
            self.assertEqual(result.status, "ignored_wrong_study"); reader.list_submissions.assert_not_called()

    def test_http_contract_verifies_headers_and_returns_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock(); reader.get_submission.return_value = {"id": "S1", "study_id": "STUDY"}; reader.list_submissions.return_value = {"results": [], "next": None}
            server = make_webhook_server(self.trigger(directory, reader), "secret")
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1"})
                connection = HTTPConnection(*server.server_address); connection.request("POST", "/prolific/webhook", body, headers); response = connection.getresponse()
                self.assertEqual(response.status, 202); self.assertEqual(json.loads(response.read())["status"], "reconciled")
                connection.request("POST", "/prolific/webhook", body, {**headers, "X-Prolific-Request-Signature": "bad"}); self.assertEqual(connection.getresponse().status, 401)
            finally:
                server.shutdown(); thread.join(); server.server_close()

    def test_concurrent_duplicate_requests_reconcile_once(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock(); reader.get_submission.return_value = {"id": "S1", "study_id": "STUDY"}; reader.list_submissions.return_value = {"results": [], "next": None}
            trigger = self.trigger(directory, reader); body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1"})
            results = []; threads = [threading.Thread(target=lambda: results.append(trigger.handle(body, headers, "secret"))) for _ in range(6)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(sum(result.status == "reconciled" for result in results), 1)

    def test_out_of_order_event_is_recorded_but_not_processed(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock(); reader.get_submission.return_value = {"id": "S1", "study_id": "STUDY"}; reader.list_submissions.return_value = {"results": [], "next": None}
            trigger = self.trigger(directory, reader)
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1"}, "new", "200"); self.assertEqual(trigger.handle(body, headers, "secret").status, "reconciled")
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1"}, "old", "100"); self.assertEqual(trigger.handle(body, headers, "secret").status, "stale")
            self.assertEqual(reader.list_submissions.call_count, 1)

    def test_processing_lease_recovers_crashed_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Mock(); reader.get_submission.return_value = {"id": "S1", "study_id": "STUDY"}; reader.list_submissions.return_value = {"results": [], "next": None}
            path = Path(directory) / "events.json"; store = JsonTriggerStore(path, processing_lease_seconds=0)
            body, headers = self.signed({"event_type": "submission.status.change", "resource_id": "S1"})
            self.assertEqual(store.begin("E1", 100, json.loads(body)), "new")
            trigger = ReconciliationTrigger(reader, Path(directory) / "data", "STUDY", store)
            self.assertEqual(trigger.handle(body, headers, "secret").status, "reconciled")

    def test_periodic_entrypoint_uses_configured_interval_and_stop(self):
        calls = []
        class Fake:
            def periodic(self):
                calls.append(True); stop.set()
        stop = threading.Event()
        run_periodic(Fake(), 0.01, stop)
        self.assertEqual(calls, [True])


if __name__ == "__main__": unittest.main()
